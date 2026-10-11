---
name: add-source
description: Quy trình rà soát và thêm một nguồn dữ liệu web mới (sàn BĐS, trang rao vặt, dữ liệu bổ trợ) vào sources.yaml. Dùng trước khi viết bất kỳ connector hoặc crawl bất kỳ domain mới nào.
---

# Thêm nguồn dữ liệu mới

Không có nguồn nào được crawl nếu chưa qua quy trình này.

## 1. Kiểm tra kỹ thuật

- Gọi `mcp__aipi__check_robots` với một URL trang tin chi tiết và URL sitemap của nguồn. Ghi lại:
  - `allowed`
  - `crawl_delay`
  - `sitemaps`
  - `content_signals`, đặc biệt `ai_train_disallowed`
- Xác định cách khám phá URL:
  - ưu tiên sitemap;
  - nếu không có thì danh mục trang chi tiết **mà robots cho phép**;
  - không dùng tham số tìm kiếm hoặc phân trang bị chặn.
- Kiểm tra trang có cần đăng nhập, hoặc có Cloudflare challenge hay CAPTCHA ngay từ đầu không. Nếu có → nguồn `blocked`, dừng tại đây.

## 2. Đọc điều khoản

- Dùng WebFetch đọc trang điều khoản / quy chế / chính sách của nguồn.
- Tìm các điều khoản về:
  - thu thập tự động, bot, crawl;
  - sao chép, tái xuất bản nội dung;
  - dùng cho AI/ML;
  - dùng nội bộ.
- Tóm tắt 3–5 dòng, có trích ngắn số điều khoản.

## 3. Quyết định

| Tình huống | permission_level | allow_training |
|---|---|---|
| Robots chặn trang tin, hoặc điều khoản cấm rõ ràng truy cập tự động, hoặc phải đăng nhập/vượt chặn | blocked | — |
| Robots cho phép; điều khoản chỉ cấm tái xuất bản/thương mại | approved_facts_only | true |
| Như trên nhưng có `ai-train=no` hoặc cấm dùng cho AI/ML | approved_facts_only | **false** |
| Có hợp đồng/giấy phép | approved_licensed | theo hợp đồng |
| Chưa rõ | pending | false |

Không tự quyết khi điều khoản mơ hồ: trình bày cho người dùng và hỏi.

## 4. Ghi lại

- Thêm mục vào `packages/contracts/sources.yaml`:
  - `id` (snake_case), `tier`, `base_url`, `sitemaps`
  - `min_delay_seconds` ≥ mặc định, và ≥ crawl_delay của robots
  - `reviewed_at` = hôm nay, `next_review_at` ≤ 1 tháng
  - `status: paused`
  - `notes` tóm tắt robots và điều khoản
- Thêm một dòng vào bảng "Nhật ký rà soát" trong `docs/DATA_SOURCE_POLICY.md`.
- Chạy `pytest -q tests/test_contracts.py`.
- Chỉ chuyển `status: active` sau khi connector và test đã xong (skill `build-connector`).
