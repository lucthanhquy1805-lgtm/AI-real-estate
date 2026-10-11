# Nhật ký nghiên cứu

Ghi sau mỗi mốc: dữ liệu mới, quyết định, kết quả huấn luyện, sự cố nguồn.

## 2026-10-10 — Sprint 0, ngày 1–3

- Chốt phạm vi: nhà phố, giao dịch bán, Quận 9 cũ (5 phường mới theo NQ 1685/NQ-UBTVQH15).
- Đã có: bảng ánh xạ 13 → 5 phường; bộ chuẩn hóa địa chỉ 3 cách gọi (Quận 9 / TP Thủ Đức / phường mới); Long Thạnh Mỹ bị chia đôi nên gắn cờ `AMBIGUOUS_WARD` khi không có toạ độ.
- Source registry: 2 nguồn tầng 1 (đều đang paused), dữ liệu bổ trợ OSM, bảng giá đất, NĐ 357 (pending), nhập tay.
- Field policy và test tuân thủ schema đã chạy.
- Việc còn mở:
  - mã đơn vị hành chính chính thức của 5 phường
  - ranh giới phường (GeoJSON)
  - email liên hệ trong User-Agent (`sources.yaml`)

## 2026-10-10 — Bộ công cụ Claude Code

- Thêm `CLAUDE.md`, `docs/ROADMAP.md` (giai đoạn 0–4, mỗi việc có DoD và Files) và `docs/DATA_DICTIONARY.md` (schema dự kiến cho migration 0002).
- MCP server `aipi` (MCP Python SDK 2.x, stdio, chỉ đọc), 8 tool. SQL chạy trong transaction READ ONLY, timeout 10 giây.
- 6 skills và 4 subagents trong `.claude/`.
- Test: 48 passed (gồm test MCP và test DB).
- Việc tiếp theo: T0.4 — migration 0002 (bảng ingestion và tin đăng).

## 2026-10-11 — Môi trường Windows sẵn sàng

- Máy chính: `C:\AI\AI-bat-dong-san` (Windows, Docker Desktop, Python 3.12).
- DB Docker chạy ở cổng **55432**, vì 5432/5433 đã bị dự án khác chiếm. Image DB: `pgvector/pgvector:0.8.1-pg16-bookworm` + PostGIS (bản bullseye đã hết hỗ trợ).
- Sửa lỗi Windows: `alembic.ini` chỉ dùng ASCII (cp1252); config luôn đọc `.env` ở gốc repo.
- Đã chạy: `alembic upgrade head`, seed → `{'sources': 7, 'wards': 5, 'mappings': 14}`; `pytest` → **48 passed**.
- Việc tiếp theo: T0.4 — migration 0002 (bảng ingestion và tin đăng), làm qua Claude Code.

## 2026-10-11 — T0.4: migration 0002 (ingestion và tin đăng)

- Thêm 6 bảng: `ingestion_jobs`, `fetch_log`, `listings`, `listing_features`, `listing_observations`, `data_quality_issues`.
  Migration viết tay, có downgrade; `alembic check` xác nhận ORM khớp migration.
- field_policy: đổi `ward_code_new` → `ward_slug_new` (khớp code); thêm `ward_method`, `ward_confidence`, `ward_flags`,
  `changed_fields` (DERIVED), `content_checksum`, `url_hash` (FINGERPRINT), `request_url` (FACT, chỉ trong fetch_log).
- Chọn tên `request_url` thay vì `url` để không mở đường cho một cột `url` chung chung ở bảng khác.
- Ràng buộc chống rò dữ liệu ở tầng DB (sau rà soát compliance, 0 BLOCKER, 7 WARN):
  - URL ảnh/video bị CHECK chặn ở `fetch_log.request_url` và `listings.source_url`.
  - `price_raw` không được chứa dãy ≥ 9 chữ số, "lh", "zalo", "liên hệ", "@".
  - `listing_features.value` chỉ là số, bool hoặc chuỗi ≤ 64 ký tự.
  - `error_summary` ≤ 1000 ký tự; `checkpoint` và `details` là object ≤ 2 KB; cả ba không được chứa dãy dạng SĐT.
    Mẫu SĐT đòi không dính chữ số hai bên, nên giá 11 chữ số (vd 10000000000) không bị chặn nhầm (có test).
  - Giới hạn: SĐT viết có khoảng trắng ("090 123 4567") không bị CHECK bắt; tầng code (T0.5, T0.6) phải chặn.
- Test compliance: miễn trừ cột kỹ thuật theo cặp (bảng, cột) và rà đủ 6 bảng mới.
- Việc dời sang T0.5, T0.6, T2.5, T3.3 đã ghi trong ROADMAP.
- Test: 77 passed với DB (47 passed + 30 skipped khi không có DB); ruff sạch.
- Việc tiếp theo: T0.5 — crawler core.
