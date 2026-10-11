---
name: model-experiment
description: Quy trình chạy một thí nghiệm mô hình (định giá hoặc độ uy tín) có thể tái lập — chuẩn bị dữ liệu đúng quyền, temporal/group split, so baseline, ghi MLflow, cổng thăng hạng. Dùng cho T3.3–T3.5, T4.1, T4.4.
---

# Thí nghiệm mô hình

## Dữ liệu

- Chỉ lấy tin từ nguồn có `allow_training = true` cho tập **train**. Nguồn `allow_training = false` chỉ được vào tập **đánh giá phụ** và phải báo cáo riêng.
- Nhãn định giá: giá rao tại lần quan sát cuối của **mỗi cụm tin**, mỗi cụm 1 mẫu. Không dùng tin chưa gom cụm.
- Loại tin `out_of_scope`, tin không có `ward_slug_new` (trừ khi thí nghiệm nói rõ), và giá null.
- Lưu snapshot dữ liệu (câu SQL, thời điểm, số dòng, hash) vào MLflow.

## Chia tập

- **Temporal holdout cố định:** 4 tuần gần nhất tại thời điểm tạo holdout. Lưu ngày cắt vào `ml/registry/holdout.yaml`, không đổi giữa các vòng.
- **Group split theo cluster_id** để không rò rỉ giữa các tin trùng.
- Đặc trưng lân cận (spatial lag, giá trung bình khu vực) chỉ tính từ dữ liệu **trước** ngày của mẫu.

## Đánh giá

- Định giá:
  - MAE, MedAE, MedAPE, coverage của khoảng q10–q90
  - theo phường, theo nhóm diện tích, theo hẻm/mặt tiền
- Độ uy tín:
  - precision@50, precision theo mức điểm, calibration (reliability)
  - trên tập review do người gán
- Luôn so với **baseline** (median giá/m² theo phường × nhóm diện tích × hẻm/mặt tiền) và với **mô hình production hiện hành**.
- Ablation khi thêm một nhóm tín hiệu: bỏ nhóm đó và đo lại.

## Thăng hạng

- Chỉ promote khi thắng production trên holdout cố định. Ví dụ: MedAPE giảm ≥ 0,5 điểm phần trăm và coverage không giảm quá 2 điểm.
- Ghi registry: data snapshot, code commit, tham số, metric, lý do.
- Không bao giờ dùng dự đoán của mô hình làm nhãn huấn luyện.

## Báo cáo

- Thêm mục vào `docs/RESEARCH_LOG.md`: giả thuyết, cấu hình, bảng metric so baseline và production, kết luận, việc tiếp theo.
- Cập nhật `docs/MODEL_CARD.md` nếu thay production.
- Ngôn ngữ đầu ra: "ước tính dựa trên giá rao"; "mức rủi ro" (không dùng "lừa đảo").
