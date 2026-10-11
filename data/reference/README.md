# Dữ liệu tham chiếu

## hcm_q9_ward_mapping.csv

Ánh xạ 13 phường cũ của Quận 9 (từ 2021 thuộc TP Thủ Đức) sang 5 phường mới của TP.HCM, hiệu lực từ 01/07/2025.

- Văn bản: Nghị quyết 1685/NQ-UBTVQH15 ngày 16/6/2025 của Ủy ban Thường vụ Quốc hội.
- Nguồn tổng hợp: Thư viện Pháp luật — "Danh sách 12 phường mới của TP Thủ Đức (cũ) sau sáp nhập ngày 01/7/2025" (đọc ngày 10/10/2026).
- TODO: đối chiếu lại với văn bản gốc và bổ sung mã đơn vị hành chính chính thức (cột `official_code` trong DB đang để trống).

Hai cột cần lưu ý:

- `mapping_type = partial`: phường cũ bị chia cho nhiều phường mới (chỉ có Long Thạnh Mỹ). Khi chỉ có tên mà không có toạ độ thì không đoán; hệ thống gắn cờ `AMBIGUOUS_WARD`.
- `new_ward_slug`: mã nội bộ ổn định, dùng làm khóa trong DB, ví dụ `hcm.long_binh`.

## Ranh giới phường (chưa có)

Sẽ thêm ở W1–W9 (GeoJSON ranh giới 5 phường mới, kèm nguồn và giấy phép) để xác định phường bằng point-in-polygon.
