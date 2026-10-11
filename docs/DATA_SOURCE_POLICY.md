# Chính sách nguồn dữ liệu

Tóm tắt SRS v1.4, mục 6, 7 và 15. Nguồn sự thật nằm ở `packages/contracts/sources.yaml` và `field_policy.yaml`.

## Thêm một nguồn mới

1. Đọc robots.txt và trang điều khoản. Lưu bản chụp vào `docs/source_snapshots/<source_id>/<ngày>/`.
2. Thêm mục vào `sources.yaml`, bắt đầu với `permission_level: pending` và `status: paused`.
3. Quyết định:
   - robots chặn đường dẫn chi tiết tin, hoặc điều khoản cấm truy cập tự động → `blocked`
   - có tín hiệu `ai-train=no` hoặc điều khoản cấm dùng cho AI/ML → `allow_training: false`
   - còn lại → `approved_facts_only`
4. Điền `reviewed_at` và `next_review_at` (tối đa 1 tháng).
5. Viết connector kèm fixture test, rồi mới chuyển `status: active`.

## Khi bị chặn hoặc chủ nguồn yêu cầu dừng

- Crawler tự chuyển nguồn sang `paused` khi gặp 403/429 liên tiếp, trang challenge hoặc CAPTCHA.
- Không dùng proxy xoay vòng, trình duyệt giả lập để vượt chặn, hay dịch vụ giải CAPTCHA.
- Nếu chủ nguồn yêu cầu: đặt `blocked`, xóa dữ liệu của nguồn đó, ghi vào RESEARCH_LOG.

## Nhật ký rà soát

| Ngày | Nguồn | Kết quả |
|---|---|---|
| 2026-10-10 | batdongsan | robots: `User-agent: *` Allow /. Điều khoản: cho phép sao chép để dùng nội bộ, cấm khai thác thương mại nội dung → approved_facts_only, allow_training true |
| 2026-10-10 | nhatot | robots: ai-train=no; chặn page=/price=/sort=/q= → approved_facts_only, allow_training false, không lật trang tìm kiếm |
