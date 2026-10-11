# ROADMAP — kế hoạch thực thi chi tiết

Nguồn gốc: SRS v1.4 (`docs/SRS_v1.4.docx`), mục 17. File này là **danh sách việc đang dùng hằng ngày**.
Claude Code và MCP tool `roadmap_next` đọc file này, nên giữ đúng định dạng:

- Mỗi việc là một dòng `- [ ] Tx.y — tiêu đề`, đánh dấu `- [x]` khi xong.
- Dưới mỗi việc là các dòng `  - DoD:` (tiêu chí hoàn thành) và `  - Files:` (nơi sửa).
- Chỉ đánh dấu xong khi DoD đạt **và** `pytest` + `ruff` xanh.
- Ghi kết quả quan trọng vào `docs/RESEARCH_LOG.md`.

Giả định: 1 người, 20–30 giờ/tuần. Thứ tự là thứ tự ưu tiên; đừng nhảy giai đoạn khi DoD giai đoạn trước chưa đạt.

---

## Giai đoạn 0 — Nền móng (W1–W2) · Sprint 0

- [x] T0.1 — Bảng ánh xạ 13 phường cũ → 5 phường mới + bộ chuẩn hóa địa chỉ
  - DoD: test 3 kiểu địa chỉ, tên trùng tỉnh khác, Long Thạnh Mỹ → AMBIGUOUS_WARD
  - Files: data/reference/hcm_q9_ward_mapping.csv, backend/ingestion/normalize/admin_units.py
- [x] T0.2 — Source registry + field policy + policy gate
  - DoD: sources.yaml hợp lệ; Nhà Tốt allow_training=false; test chặn CONTENT/MEDIA/PERSONAL
  - Files: packages/contracts/*.yaml, backend/app/contracts.py, backend/ingestion/core/policy.py
- [x] T0.3 — Khung repo: Docker Compose (PostGIS + pgvector), FastAPI, Alembic 0001, seed, CI
  - DoD: `docker compose up --build` → /health trả postgis, vector, pg_trgm
  - Files: docker-compose.yml, infra/docker/*, backend/alembic/*, backend/app/*
- [x] T0.3b — Tài liệu cho Claude Code: CLAUDE.md, ROADMAP, skills, subagents, MCP server
- [x] T0.4 — Migration 0002: bảng ingestion và tin đăng
  - DoD: các bảng theo docs/DATA_DICTIONARY.md mục 2; provenance NOT NULL; test_compliance_schema xanh; downgrade chạy được
  - Files: backend/app/db/models.py, backend/alembic/versions/0002_*.py, docs/DATA_DICTIONARY.md
- [ ] T0.5 — Crawler core: HttpClient, RateLimiter, RobotsChecker, BlockDetector, TransientStore
  - DoD: (a) không bao giờ gửi 2 request cùng domain cách nhau < min_delay; (b) URL robots chặn → không fetch và ghi fetch_log outcome=skipped_robots; (c) 3 lần 403/429 liên tiếp hoặc trang challenge/CAPTCHA → nguồn chuyển paused + log; (d) thư mục tạm trống sau job (kể cả khi lỗi); đủ unit test, không gọi mạng thật trong test
  - Files: backend/ingestion/core/{http.py,rate_limit.py,robots.py,block_detect.py,transient.py}
  - Từ rà soát T0.4: chỉ ghi `fetch_log.request_url` khi host thuộc `base_url` của nguồn (URL khác chỉ lưu `url_hash`); `error_summary` chỉ ghi `type(exc).__name__` + mã lỗi, ValidationError dùng `include_input=False`
- [ ] T0.6 — Adapter interface + job runner tối thiểu (chạy tay qua CLI, chưa cần queue)
  - DoD: `python -m ingestion.run --source batdongsan --limit 20 --dry-run`; mọi bước discover → fetch → parse → normalize → persist đi qua policy gate và FieldPolicy.filter_for_storage
  - Files: backend/ingestion/core/adapter.py, backend/ingestion/run.py
  - Từ rà soát T0.4: persist kiểm tra `feature_name` bằng `FieldPolicy.can_store` (fail closed); quyết định cách tách cột kỹ thuật khỏi `filter_for_storage` (lọc phần dữ liệu nguồn trước rồi mới gộp, hoặc thêm lớp TECHNICAL), không tắt kiểm tra; test `content_checksum` chỉ băm trường FACT; `details` của data_quality_issues tạo qua một helper duy nhất
- [ ] T0.7 — Pseudonym người đăng (HMAC-SHA256) + kiểm tra khóa
  - DoD: thiếu POSTER_HMAC_KEY thì job từ chối chạy; cùng SĐT + khóa → cùng pseudonym; chuẩn hóa SĐT (+84/0, khoảng trắng)
  - Files: backend/ingestion/extract/pseudonym.py

## Giai đoạn 1 — Thu thập tầng 1 (W3–W6) · Sprint 1

- [ ] T1.1 — Connector Batdongsan: discovery qua sitemap, lọc URL tin nhà phố bán tại Quận 9 cũ / TP Thủ Đức
  - DoD: skill `build-connector` được tuân thủ; 20 fixture HTML đã che thông tin cá nhân; parser trích đủ trường FACT; test parser từ fixture
  - Files: backend/ingestion/connectors/batdongsan/, data/fixtures/batdongsan/
- [ ] T1.2 — Normalize tin đăng: giá ("5,2 tỷ", "thỏa thuận"), diện tích, giá/m², loại tài sản, resolve_ward
  - DoD: test bảng ≥ 30 chuỗi giá/diện tích thực tế; giá "thỏa thuận" → null + cờ
  - Files: backend/ingestion/normalize/{price.py,area.py}
- [ ] T1.3 — Validation + quarantine
  - DoD: bản ghi lỗi vào data_quality_issues với error code; không mất âm thầm
- [ ] T1.4 — Chạy end-to-end 1 phường ở tốc độ thấp; bật `status: active` cho batdongsan
  - DoD: ≥ 100 tin thật trong DB; provenance 100%; compliance tests xanh; ghi RESEARCH_LOG
- [ ] T1.5 — Lập lịch hằng ngày bằng Procrastinate (Postgres queue) + checkpoint + observation/change tracking
  - DoD: tin thấy lại tạo listing_observations; đổi giá được ghi changed_fields; last_seen_at cập nhật
- [ ] T1.6 — Connector Nhà Tốt (allow_training=false), không dùng tham số tìm kiếm bị robots chặn
  - DoD: 2 nguồn chạy độc lập; một nguồn lỗi không ảnh hưởng nguồn kia
- [ ] T1.7 — Dashboard nguồn tối giản (API `/admin/sources/health`)
  - DoD: theo nguồn: số tin, tỷ lệ parse lỗi, độ mới, trạng thái chặn

## Giai đoạn 2 — Đa nguồn và làm giàu (W7–W10) · Sprint 2

- [ ] T2.1 — Extractor LLM tổng quát cho tầng 2 (Ollama, model mở 7–8B, JSON schema)
  - DoD: thêm nguồn bằng cấu hình; tự tắt nguồn khi tỷ lệ validation lỗi > 20%; đo trên 50 tin gán nhãn
- [ ] T2.2 — Khảo sát và bật 3–5 nguồn tầng 2 có tin Quận 9 (skill `add-source` cho từng nguồn)
- [ ] T2.3 — Trích đặc điểm từ mô tả: mặt tiền/hẻm, độ rộng hẻm, số tầng, loại sổ, hướng (rule trước, LLM sau)
  - DoD: F1 ≥ 0,85 cho hẻm/mặt tiền, tầng, loại sổ trên 200 tin gán nhãn; mô tả bị xóa sau job
- [ ] T2.4 — Fingerprint và embedding lúc crawl: pHash/dHash ảnh, SimHash mô tả, embedding văn bản/ảnh
  - DoD: chỉ lưu vector/hash + tên/phiên bản model; test thư mục tạm trống
- [ ] T2.5 — Dữ liệu tầng 3: ranh giới phường (point-in-polygon), OSM POI/đường, bảng giá đất TP.HCM
  - DoD: ≥ 90% tin có ward_slug_new; đặc trưng khoảng cách tới tiện ích; Long Thạnh Mỹ được tách bằng toạ độ
  - Từ rà soát T0.4: làm tròn `geo_point` (~3 chữ số thập phân) + cân nhắc CHECK làm tròn và bbox Q9 cũ
- [ ] T2.6 — Dedup và gom cụm xuyên nguồn
  - DoD: precision ≥ 0,9 trên 300 cặp gán nhãn; recall được báo cáo
- [ ] T2.7 — Mốc quyết định W8: nếu < 600 tin nhà phố đang hoạt động → mở rộng sang phường lân cận

## Giai đoạn 3 — Gán nhãn, định giá, độ uy tín (W11–W14) · Sprint 3

- [ ] T3.1 — EDA thị trường Quận 9 (SRS mục 2.2) → docs/reports/eda_q9.md
- [ ] T3.2 — Công cụ review/gán nhãn (Next.js tối giản, phím tắt) + bảng labels, review_tasks
- [ ] T3.3 — Định giá bước 1–3: baseline median → LightGBM cấu trúc → + không gian (skill `model-experiment`)
  - DoD: temporal + group split; MedAPE, coverage; SHAP; model card v0
  - Từ rà soát T0.4: một điểm dựng tập huấn luyện duy nhất (view `training_listings` hoặc hàm) loại nguồn `allow_training = false`, kèm test
- [ ] T3.4 — Định giá bước 4–5: + embedding mô tả, + embedding ảnh; khoảng giá (quantile/conformal); ablation
- [ ] T3.5 — Mô hình độ uy tín: labeling functions → label model → GBM → calibration
  - DoD: Precision@50 ≥ 0,7 trên tập review; output điểm + 3 lý do; không dùng từ "lừa đảo"

## Giai đoạn 4 — Tự cải thiện, giao diện, báo cáo (W15–W18) · Sprint 4

- [ ] T4.1 — Active learning queue + huấn luyện lại hằng tuần + promotion gate + rollback (MLflow registry)
- [ ] T4.2 — Drift monitoring + báo cáo tuần (skill `weekly-report`)
- [ ] T4.3 — Giao diện tra cứu, bản đồ, định giá có SHAP và comparables
- [ ] T4.4 — Định giá bước 6: mạng neural đa phương thức so với GBM bước 5
- [ ] T4.5 — Báo cáo nghiên cứu RQ1–RQ4, backup/restore, backlog giai đoạn 2

---

## Việc mở (không theo tuần)

- [ ] X.1 — Điền email liên hệ thật vào User-Agent trong sources.yaml
- [ ] X.2 — Mã đơn vị hành chính chính thức cho 5 phường (admin_units.official_code)
- [ ] X.3 — Đối chiếu bảng ánh xạ với văn bản gốc NQ 1685/NQ-UBTVQH15
- [ ] X.4 — Rà soát lại robots/điều khoản mỗi tháng (next_review_at trong sources.yaml)
- [ ] X.5 — Nộp hồ sơ khai thác dữ liệu theo NĐ 357/2025 (tùy chọn)
