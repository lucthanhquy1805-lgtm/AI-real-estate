---
name: weekly-report
description: Tạo báo cáo tuần của dự án — tình trạng nguồn, dữ liệu mới, chất lượng, nhãn, mô hình, drift, việc ROADMAP. Dùng khi người dùng hỏi "báo cáo tuần", "tuần này thế nào", hoặc cuối mỗi tuần.
---

# Báo cáo tuần

Thu thập số liệu bằng MCP `aipi` (chỉ đọc). Nếu bảng chưa tồn tại thì ghi "chưa có".

1. **Nguồn:** `list_sources`, cộng `db_query` trên `ingestion_jobs` và `fetch_log` 7 ngày qua:
   - số job, số request
   - tỷ lệ lỗi
   - số lần bị chặn
   - nguồn đang paused, và lý do
2. **Dữ liệu:** `data_summary`, cộng `db_query`:
   - tin mới, tin cập nhật giá, tin không còn thấy (7 ngày)
   - số tin đang hoạt động theo phường
   - tỷ lệ chưa xác định phường (AMBIGUOUS_WARD, NO_WARD)
3. **Chất lượng:**
   - số issue trong `data_quality_issues` theo mã
   - tỷ lệ parse lỗi theo nguồn
4. **Nhãn và mô hình** (nếu có):
   - nhãn mới theo task
   - mô hình production hiện hành, metric holdout
   - lần huấn luyện tuần này: promote hay không, và vì sao
   - drift
5. **ROADMAP:** `roadmap_next`, gồm số việc xong / tổng và 3 việc tiếp theo.

Đầu ra:
- Thêm một mục `## Tuần <ngày đầu> – <ngày cuối>` vào `docs/RESEARCH_LOG.md` với các bảng ngắn.
- Tóm tắt 5–8 dòng cho người dùng (tiếng Việt). Nêu rõ điểm bất thường, ví dụ nguồn bị chặn hoặc tỷ lệ parse giảm, kèm đề xuất xử lý.
