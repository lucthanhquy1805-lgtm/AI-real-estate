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

## 2. Dự kiến cho migration 0002 (T0.4)

### ingestion_jobs
job_id (uuid PK), source_id (FK), kind (discover/fetch/full), status (queued/running/succeeded/failed/aborted_blocked), started_at, finished_at, fetched_count, parsed_count, error_count, blocked_count, parser_version, checkpoint (jsonb), error_summary (text).

### fetch_log
id, job_id (FK), source_id, url_hash (sha256 của URL, **không lưu URL ảnh**), url (chỉ cho URL trang tin/sitemap), http_status, latency_ms, fetched_at, outcome (ok/blocked/error/skipped_robots/skipped_policy).

### listings — một dòng cho mỗi (nguồn, mã tin)
| Cột | Lớp | Ghi chú |
|---|---|---|
| listing_id | — | uuid PK |
| source_id | — | FK, NOT NULL |
| source_listing_id | FACT | NOT NULL; unique cùng source_id |
| source_url | FACT | NOT NULL |
| transaction_type | FACT | sale/rent |
| property_type | FACT | townhouse/... |
| asking_price_vnd | FACT | bigint, null nếu "thỏa thuận" |
| price_raw | FACT | chuỗi ngắn, vd "5,2 tỷ" |
| land_area_sqm, floor_area_sqm | FACT | numeric |
| floors, bedrooms, bathrooms | FACT | int |
| direction | FACT | |
| ward_name_old, district_alias | FACT | |
| ward_slug_new | DERIVED | FK admin_units, nullable |
| ward_method, ward_confidence, ward_flags | DERIVED | từ resolve_ward |
| geo_point | DERIVED | POINT 4326, làm tròn ~50–100 m |
| price_per_sqm_vnd | DERIVED | |
| poster_pseudonym | PSEUDONYM | HMAC |
| posted_at | FACT | |
| first_seen_at, last_seen_at | — | NOT NULL |
| listing_status | — | active/not_seen/removed |
| out_of_scope | — | bool |
| parser_version | — | NOT NULL |
| collected_at | — | NOT NULL |

### listing_features
listing_id, feature_name (frontage_type, alley_width_m, legal_status, ...), value (jsonb), provenance (SOURCE_REPORTED/INFERRED), confidence, extractor_version.

### listing_observations
listing_id, observed_at, asking_price_vnd, listing_status, changed_fields (text[]), content_checksum.

### data_quality_issues
id, entity_type, entity_id, issue_code, severity, details (jsonb), detected_at, resolution_status.

## 3. Dự kiến sau (W9–W15)

image_fingerprints, text_fingerprints, embeddings (pgvector), clusters, cluster_members, aux_poi, aux_roads, aux_land_price, labels, review_tasks, predictions, model_registry (hoặc MLflow), trust_alerts, audit_log.
Chi tiết: SRS v1.4 mục 13.

## 4. Không bao giờ có cột

title, description, image_url, image_bytes, video_url, poster_name, poster_phone, poster_email, poster_avatar_url, house_number.
`tests/test_compliance_schema.py` thực thi điều này.
