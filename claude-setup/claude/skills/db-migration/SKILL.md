---
name: db-migration
description: Quy trình thêm hoặc sửa bảng/cột PostgreSQL bằng Alembic cho dự án, kèm kiểm tra field policy và compliance test. Dùng mỗi khi thay đổi backend/app/db/models.py hoặc schema DB.
---

# Thay đổi schema DB

1. **Kiểm tra field policy trước.** Liệt kê mọi cột dữ liệu nguồn mới, rồi gọi `mcp__aipi__check_fields`.
   - `unknown` → thêm vào `packages/contracts/field_policy.yaml` với đúng lớp (FACT, DERIVED, FINGERPRINT, EMBEDDING, PSEUDONYM). Nếu không chắc lớp nào, hỏi người dùng.
   - `forbidden` → **không được tạo cột**. Xem lại thiết kế: có thể chỉ cần hash, embedding hoặc trường đã trích.
2. Cập nhật `backend/app/db/models.py`, và `docs/DATA_DICTIONARY.md` nếu là bảng mới.
3. Tạo migration: `alembic revision -m "<mo_ta>"`. Đặt tên file theo thứ tự `000N_<mo_ta>.py`, `revision = "000N"`.
   - Viết tay cả `upgrade` và `downgrade`; không dựa hoàn toàn vào autogenerate (PostGIS, pgvector hay bị sai).
   - Cột provenance (`source_id`, `parser_version`, `collected_at`) phải `NOT NULL`.
   - Thêm `CheckConstraint` cho các cột enum dạng chuỗi.
   - Index không gian: GiST; vector: thêm sau khi có dữ liệu (HNSW).
4. Kiểm tra:
   - `alembic upgrade head`, rồi `alembic downgrade -1`, rồi `alembic upgrade head` trên DB test
   - `pytest -q` (gồm `test_compliance_schema.py`) với `TEST_DATABASE_URL`
   - `mcp__aipi__db_schema` để xem lại kết quả
5. Giao subagent `compliance-reviewer` rà diff.
