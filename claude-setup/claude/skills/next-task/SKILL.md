---
name: next-task
description: Lấy và thực hiện việc tiếp theo trong docs/ROADMAP.md của dự án AI Property Intelligence. Dùng khi người dùng nói "làm bước tiếp theo", "tiếp tục", "next", hoặc hỏi nên làm gì tiếp.
---

# Thực hiện việc tiếp theo trong ROADMAP

1. Gọi `mcp__aipi__roadmap_next` với n=3. Nếu MCP chưa chạy, đọc `docs/ROADMAP.md` và tìm dòng `- [ ]` đầu tiên.
2. Chọn việc chưa xong **đầu tiên** (thứ tự là ưu tiên). Chỉ chọn việc khác nếu người dùng chỉ định, hoặc việc đầu tiên bị chặn bởi thứ người dùng phải làm, ví dụ việc mở X.*.
3. Nói ngắn gọn cho người dùng (tiếng Việt): việc gì, DoD là gì, sẽ sửa những file nào.
4. Đọc code liên quan và `CLAUDE.md` (nguyên tắc bất biến). Nếu việc có skill riêng thì làm theo skill đó:
   - thêm nguồn → `add-source`
   - viết connector → `build-connector`
   - đổi schema → `db-migration`
   - mô hình → `model-experiment`
5. Viết code và test. Chạy trong `backend/`:
   - `pytest -q`
   - `ruff check .` và `ruff format --check .`
   - test DB nếu có `TEST_DATABASE_URL`
6. Nếu việc chạm vào crawler, schema hoặc dữ liệu: giao subagent `compliance-reviewer` rà diff và sửa mọi vấn đề nó báo.
7. Khi DoD đạt:
   - đổi `- [ ]` thành `- [x]` trong ROADMAP
   - thêm một mục vào `docs/RESEARCH_LOG.md` (ngày, việc, kết quả, số liệu)
8. Tóm tắt cho người dùng: đã làm gì, cách kiểm tra, việc tiếp theo là gì.

Không đánh dấu xong khi test đỏ hoặc DoD chưa đạt. Nếu DoD không khả thi, đề xuất sửa DoD và hỏi người dùng.
