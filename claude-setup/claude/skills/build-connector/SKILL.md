---
name: build-connector
description: Quy trình viết hoặc sửa connector thu thập cho một nguồn đã được duyệt (tầng 1 viết tay, tầng 2 extractor LLM) — discovery, fetch, parse, normalize, persist, fixture tests. Dùng khi làm T1.1, T1.6, T2.1, T2.2 hoặc khi parser của một nguồn bị hỏng.
---

# Viết connector cho một nguồn

## Điều kiện trước

- Nguồn đã có trong `sources.yaml`, với `permission_level` là `approved_facts_only` hoặc `approved_licensed` (skill `add-source`).
- Crawler core đã có (T0.5): HttpClient, RateLimiter, RobotsChecker, BlockDetector, TransientStore. **Không tự gọi httpx trực tiếp trong connector**; luôn đi qua HttpClient của core.

## Cấu trúc

```
backend/ingestion/connectors/<source_id>/
  __init__.py
  discover.py     # sitemap → URL trang tin chi tiết; lọc theo khu vực (Quận 9 / TP Thủ Đức / 5 phường mới)
  parse.py        # HTML → dict thô (chỉ trích; không gọi mạng)
  adapter.py      # class <Source>Adapter(BaseAdapter): nối discover → fetch → parse → normalize
backend/tests/connectors/test_<source_id>_parse.py
data/fixtures/<source_id>/<listing_id>.html   # đã ẩn danh
```

## Các bước

1. **Lấy fixture**
   - Lấy 10–20 trang tin mẫu bằng HttpClient, có rate limit.
   - **Ẩn danh trước khi lưu:**
     - thay tên, SĐT, email người đăng bằng `NGUOI_DANG`, `0900000000`;
     - xóa thẻ `<img>` và URL ảnh;
     - bỏ số nhà.
   - Kiểm tra lại bằng grep: không còn số điện thoại thật (regex `0\d{9}` và `\+84`).
2. **Parser**
   - Trích các trường FACT: `source_listing_id`, `source_url`, `asking_price_vnd` / `price_raw`, diện tích đất và sàn, số tầng, phòng, hướng, chuỗi địa chỉ, breadcrumb khu vực, `posted_at`.
   - Mô tả và ảnh chỉ được trả về trong một đối tượng `TransientContent`. Đối tượng này phải được giải phóng sau bước extract.
   - Gọi `mcp__aipi__check_fields` với danh sách khóa parser trả về. Không có `unknown`; không có trường forbidden ngoài TransientContent.
3. **Normalize**
   - giá: "5,2 tỷ", "5 tỷ 200 triệu", "thỏa thuận" → null kèm cờ
   - diện tích
   - địa chỉ: `resolve_ward(address, context_text=breadcrumb)`
4. **Persist**
   - `FieldPolicy.filter_for_storage(record)` → upsert theo `(source_id, source_listing_id)`
   - tạo `listing_observations`
   - provenance đầy đủ: `parser_version`, `collected_at`
5. **Test**
   - parser từ fixture: mỗi fixture có expected dict
   - normalize: bảng giá trị
   - adapter dùng HttpClient giả: tôn trọng policy gate; robots chặn → skip; 403 liên tiếp → dừng
   - không gọi mạng thật
6. **Chạy thử**
   - `--dry-run --limit 20`, rồi `--limit 100` cho 1 phường
   - kiểm tra bằng `mcp__aipi__data_summary` và `db_query`
7. Giao subagent `compliance-reviewer` rà diff.
8. Chuyển `status: active` trong `sources.yaml`, ghi RESEARCH_LOG (số tin, tỷ lệ parse lỗi, tỷ lệ resolve phường).

## Khi parser hỏng (HTML đổi)

- Không sửa vội bằng cách nới lỏng validation.
- Lấy fixture mới, cập nhật parser, tăng `PARSER_VERSION`, và giữ fixture cũ nếu trang cũ vẫn còn.
