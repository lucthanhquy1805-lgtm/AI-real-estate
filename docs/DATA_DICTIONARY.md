# Từ điển dữ liệu

Mọi cột lưu dữ liệu nguồn phải có tên trong `packages/contracts/field_policy.yaml`.
Cột kỹ thuật (id, khóa ngoại, thời điểm hệ thống) không cần khai báo.

## 1. Đã có (migration 0001)

| Bảng | Mục đích |
|---|---|
| data_sources | Bản sao trong DB của sources.yaml (seed) |
| admin_units | 5 phường mới, slug `hcm.<ten>` |
| admin_unit_mapping | phường cũ → phường mới (full/partial) |
| ward_boundaries | ranh giới phường (MULTIPOLYGON 4326), chưa có dữ liệu |

## 2. Đã có (migration 0002, T0.4)

Quy ước: thời điểm là `timestamptz`; enum chuỗi có CHECK `ck_<bảng>_<cột>`; CHECK coi NULL là đạt.
"Dãy dạng SĐT" = `(+84|0)` + 9 chữ số, không dính chữ số hai bên (giá tiền dài không bị khớp nhầm). SĐT có khoảng trắng không bị CHECK bắt; tầng code phải chặn.
Cột "Lớp" ghi lớp trong `field_policy.yaml`; "—" là cột kỹ thuật (không cần khai báo).

### ingestion_jobs — một lần chạy thu thập
| Cột | Kiểu | Ràng buộc |
|---|---|---|
| job_id | uuid PK | `gen_random_uuid()` |
| source_id | varchar(64) | FK data_sources, NOT NULL |
| kind | varchar(16) | discover / fetch / full |
| status | varchar(20) | queued (mặc định) / running / succeeded / failed / aborted_blocked |
| started_at, finished_at | timestamptz | finished_at >= started_at |
| fetched_count, parsed_count, error_count, blocked_count | int | NOT NULL, mặc định 0, >= 0 |
| parser_version | varchar(32) | NOT NULL |
| checkpoint | jsonb | chỉ con trỏ (cursor sitemap, offset, hash); CHECK object ≤ 2 KB, không chứa dãy dạng SĐT |
| error_summary | text | chỉ lỗi kỹ thuật, không chép nội dung trang; CHECK ≤ 1000 ký tự, không chứa dãy dạng SĐT |
| created_at | timestamptz | NOT NULL, now() |

### fetch_log — mỗi request một dòng
| Cột | Lớp | Ràng buộc |
|---|---|---|
| id | — | bigint identity PK |
| job_id | — | FK ingestion_jobs ON DELETE CASCADE, NOT NULL |
| source_id | — | FK data_sources, NOT NULL |
| url_hash | FINGERPRINT | sha256 hex 64 ký tự, NOT NULL |
| request_url | FACT | chỉ URL trang tin / sitemap. **CHECK chặn URL ảnh/video** (`.jpg .png .webp .gif .avif .bmp .svg .mp4 .webm`) |
| http_status | — | smallint, null khi bỏ qua / lỗi mạng |
| latency_ms | — | >= 0 |
| fetched_at | — | NOT NULL, now() |
| outcome | — | ok / blocked / error / skipped_robots / skipped_policy |

### listings — một dòng cho mỗi (nguồn, mã tin)
| Cột | Lớp | Ràng buộc |
|---|---|---|
| listing_id | — | uuid PK |
| source_id | — | FK, **NOT NULL** (provenance) |
| source_listing_id | FACT | varchar(128), NOT NULL; UNIQUE (source_id, source_listing_id) |
| source_url | FACT | NOT NULL; CHECK chặn URL ảnh/video |
| transaction_type | FACT | sale / rent |
| property_type | FACT | townhouse / apartment / land / villa / shophouse / other |
| asking_price_vnd | FACT | bigint > 0; null nếu "thỏa thuận". Là **giá rao**, không phải giá giao dịch |
| price_raw | FACT | varchar(64), vd "5,2 tỷ"; CHECK không có dãy ≥ 9 chữ số, "lh", "zalo", "liên hệ", "@" |
| land_area_sqm, floor_area_sqm | FACT | numeric(10,2) > 0 |
| floors, bedrooms, bathrooms | FACT | smallint >= 0 |
| direction | FACT | n / ne / e / se / s / sw / w / nw |
| ward_name_old, district_alias | FACT | |
| ward_slug_new | DERIVED | FK admin_units.slug, nullable |
| ward_method | DERIVED | text / geo |
| ward_confidence | DERIVED | real, 0–1 |
| ward_flags | DERIVED | text[], NOT NULL, mặc định `{}` |
| geo_point | DERIVED | POINT 4326, index GiST; làm tròn ~50–100 m ở tầng code |
| price_per_sqm_vnd | DERIVED | bigint > 0 |
| poster_pseudonym | PSEUDONYM | HMAC-SHA256 hex 64 ký tự |
| posted_at | FACT | |
| first_seen_at, last_seen_at | — | NOT NULL; last >= first |
| listing_status | — | active (mặc định) / not_seen / removed |
| out_of_scope | — | bool, mặc định false |
| parser_version | — | **NOT NULL** (provenance) |
| collected_at | — | **NOT NULL** (provenance) |

Index: ward_slug_new, last_seen_at, poster_pseudonym, GiST geo_point.
Không có cột `allow_training`: khi dựng tập huấn luyện, join `data_sources` và loại nguồn `allow_training = false`.

### listing_features — đặc điểm trích từ tin
PK (listing_id, feature_name); listing_id FK listings ON DELETE CASCADE.
feature_name varchar(64); value jsonb NOT NULL (CHECK: chỉ số, bool hoặc chuỗi ≤ 64 ký tự); provenance SOURCE_REPORTED / INFERRED; confidence real 0–1;
extractor_version NOT NULL; extracted_at NOT NULL.
**`feature_name` phải là trường đã khai báo và có `store: true` trong `field_policy.yaml`** (vd frontage_type, alley_width_m, legal_status).
DB không kiểm tra được điều này; tầng persist (T0.6) kiểm tra bằng `FieldPolicy.can_store`.

### listing_observations — lịch sử quan sát
PK (listing_id, observed_at); listing_id FK listings ON DELETE CASCADE.
asking_price_vnd (FACT, > 0); listing_status (cùng enum với listings); changed_fields (DERIVED, text[]);
content_checksum (FINGERPRINT, sha256 hex của các trường FACT đã chuẩn hóa, không phải của mô tả); parser_version NOT NULL.

### data_quality_issues
id bigint identity PK; entity_type listing / source / job / fetch; entity_id varchar(64); issue_code; severity info / warning / error;
details jsonb (chỉ tên trường và giá trị FACT, **không chép nội dung trang**; CHECK object ≤ 2 KB, không chứa dãy dạng SĐT); detected_at now(); resolution_status open (mặc định) / resolved / ignored.
Index: (entity_type, entity_id), (resolution_status, severity).

## 3. Dự kiến sau (W9–W15)

image_fingerprints, text_fingerprints, embeddings (pgvector), clusters, cluster_members, aux_poi, aux_roads, aux_land_price, labels, review_tasks, predictions, model_registry (hoặc MLflow), trust_alerts, audit_log.
Chi tiết: SRS v1.4 mục 13.

## 4. Không bao giờ có cột

title, description, image_url, image_bytes, video_url, poster_name, poster_phone, poster_email, poster_avatar_url, house_number.
`tests/test_compliance_schema.py` thực thi điều này.
