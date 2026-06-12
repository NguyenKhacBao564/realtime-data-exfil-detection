# Kế hoạch Bảng (TABLE_PLAN.md)

Tối thiểu 12 bảng.

| STT | Mã bảng | Tiêu đề | Cột | Vị trí chèn | Trạng thái giá trị |
|-----|---------|---------|-----|-------------|-------------------|
| 1 | Bảng 1.1 | So sánh nghiên cứu liên quan | Tác giả/Năm, Phương pháp, Dataset, Kết quả, Ghi chú | Chương 2.13 | 5–10 dòng — [CẦN BỔ SUNG] |
| 2 | Bảng 2.1 | Danh sách đặc trưng runtime 17 features | Tên feature, Kiểu, Ý nghĩa, Trọng số online | Chương 3.3 | **Có sẵn** từ runtime_features.py + online_anomaly_monitor.py |
| 3 | Bảng 2.2 | Tham số mô hình offline-trained | Mô hình, Loại, Tham số chính, File model | Chương 3.4.2 | **Có sẵn** từ train_anomaly.py, train_dl.py |
| 4 | Bảng 2.3 | Tham số Online Anomaly Monitor | Tham số, Giá trị mặc định, Ý nghĩa, CLI flag | Chương 3.4.3 | **Có sẵn** từ config.py, online_anomaly_monitor.py |
| 5 | Bảng 2.4 | Tham số hệ thống pipeline | window_size, min_packets, queue_size, HTTP_PORTS, burst_threshold | Chương 3.7 | **Có sẵn** từ config.py |
| 6 | Bảng 2.5 | Các thành phần Docker Lab | Service, Image/Build, Port, Volume, Command | Chương 3.2.6 | **Có sẵn** từ docker-compose.yml |
| 7 | Bảng 2.6 | Chế độ traffic generator | Mode, Payload size, Interval, Mục đích | Chương 3.2.7 | **Có sẵn** từ generate_http_traffic.py |
| 8 | Bảng 2.7 | Điều kiện kích hoạt cảnh báo | Trigger, Điều kiện, Mô tả | Chương 3.4 | **Có sẵn** từ model_inference.py |
| 9 | Bảng 2.8 | Kịch bản thực nghiệm | Scenario, Mode, Duration, Expected alert | Chương 4.2 | **Có sẵn** từ DEMO_SCRIPT.md |
| 10 | Bảng 3.1 | Kết quả đánh giá mô hình offline | Model, AUC, F1, Precision, Recall, FPR, Threshold | Chương 4.4 | **Có placeholder** từ CLAUDE.md (0.9971, 0.9966, etc.) |
| 11 | Bảng 3.2 | Kết quả online anomaly monitor | Scenario, burst_score, online_score, prediction, Alert? | Chương 4.5 | Placeholder — [CẦN CHẠY THỰC NGHIỆM] |
| 12 | Bảng 3.3 | Hiệu năng pipeline | Metric, Giá trị, Target, Pass/Fail | Chương 4.5 | Placeholder — [CẦN CHẠY THỰC NGHIỆM] |
| 13 | Bảng 3.4 | Thời gian phát hiện | Traffic type, Window size, Detection time, Target | Chương 4.5 | Placeholder — [CẦN CHẠY THỰC NGHIỆM] |
| 14 | Bảng 3.5 | Hạn chế và giải pháp | Hạn chế, Mức độ, Giải pháp đề xuất | Kết luận | [CẦN VIẾT] |
| 15 | Bảng 3.6 | Dataset CICIDS2017 dùng trong đồ án | File, Size, Attack types, Exfil proxy | Chương 1.3 / 4.1 | **Có sẵn** từ CLAUDE.md |

Lưu ý:
- Bảng 1: Cần tìm 5–10 bài báo khoa học liên quan (Google Scholar).
- Bảng 10: Giá trị từ CLAUDE.md là sau threshold tuning (CNN1D 0.9971, BiLSTM 0.9966).
- Bảng 11–13: Cần chạy demo thực tế trên VM Ubuntu để thu thập.
- Các bảng "Có sẵn" copy trực tiếp từ code/config.