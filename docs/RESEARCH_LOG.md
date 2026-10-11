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
