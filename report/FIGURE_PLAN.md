# Kế hoạch Hình ảnh (FIGURE_PLAN.md)

Tối thiểu 25 hình ảnh để đạt 50+ trang sau khi chèn.

| STT | Mã hình | Tên file | Caption | Vị trí chèn | Cách tạo/chụp |
|-----|---------|----------|---------|-------------|---------------|
| 1 | Hình 1.1 | arch_overview.png | Sơ đồ kiến trúc tổng quan: Packet Capture → Feature Aggregation → Inference | Chương 3.1 | Vẽ draw.io/Mermaid từ pipeline.py |
| 2 | Hình 1.2 | docker_lab_arch.png | Kiến trúc Docker Lab: victim-client → exfil-server → monitor-detector | Chương 3.2.6 | Vẽ từ lab/docker-compose.yml |
| 3 | Hình 1.3 | pipeline_threads.png | Pipeline đa luồng 3 threads với queue | Chương 3.2 | Vẽ từ pipeline.py |
| 4 | Hình 1.4 | online_monitor_arch.png | Online Anomaly Monitor: Welford + per-IP baseline + z-score | Chương 3.4.3 | Vẽ từ online_anomaly_monitor.py |
| 5 | Hình 1.5 | detection_layers.png | 3 lớp phát hiện: BURST_RULE, OFFLINE_MODEL, ONLINE_UNKNOWN_ANOMALY | Chương 3.4 | Vẽ từ model_inference.py |
| 6 | Hình 2.1 | feature_vector.png | Vector đặc trưng runtime 17 features | Chương 3.3 | Bảng từ runtime_features.py |
| 7 | Hình 2.2 | feature_extraction_flow.png | Quy trình trích xuất: packet → window → feature vector | Chương 3.3 | Vẽ từ feature_aggregator.py |
| 8 | Hình 3.1 | lab_docker_ps.png | docker-compose ps — 3 services healthy | Chương 4.1 | `docker compose -f lab/docker-compose.yml ps` |
| 9 | Hình 3.2 | lab_normal_cmd.png | Lệnh make lab-normal DURATION=15 | Chương 4.2.1 | Chụp terminal |
| 10 | Hình 3.3 | lab_normal_logs.png | Log exfil-server khi chạy normal traffic | Chương 4.2.1 | `make lab-logs` |
| 11 | Hình 3.4 | lab_exfil_cmd.png | Lệnh make lab-exfil DURATION=15 | Chương 4.2.2 | Chụp terminal |
| 12 | Hình 3.5 | lab_exfil_logs.png | Log server + detector khi exfil | Chương 4.2.2 | Chụp log detector |
| 13 | Hình 3.6 | lab_slow_drip_cmd.png | Lệnh make lab-slow-drip DURATION=15 | Chương 4.2.3 | Chụp terminal |
| 14 | Hình 3.7 | lab_slow_drip_logs.png | Log server + detector khi slow-drip | Chương 4.2.3 | Chụp log detector |
| 15 | Hình 3.8 | live_detector_startup.png | Khởi động live detector --enable-online-monitor | Chương 4.2.4 | `make live-demo` |
| 16 | Hình 3.9 | bpf_filter_8000.png | BPF filter: tcp and (port 80 or 443 or 8000 or 8080 or 8443) | Chương 4.2.4 | Log pipeline startup |
| 17 | Hình 3.10 | online_anomaly_alert.png | Cảnh báo ONLINE_UNKNOWN_ANOMALY với HIGH_Z | Chương 4.3 | Log detector khi slow-drip |
| 18 | Hình 3.11 | combined_alert.png | Cảnh báo kết hợp 3 layers | Chương 4.3 | Log detector khi exfil |
| 19 | Hình 3.12 | tcpdump_capture.png | Chụp PCAP tcpdump từ lab | Chương 4.2.4 | `sudo ./scripts/capture_lab_pcap.sh eth0 60` |
| 20 | Hình 3.13 | offline_replay.png | Replay PCAP offline với online monitor | Chương 4.2.5 | `make offline-replay` |
| 21 | Hình 3.14 | final_stats.png | Thống kê cuối: processed, alerts, online_anomalies | Chương 4.3 | Output pipeline khi dừng |
| 22 | Hình 3.15 | pytest_passed.png | pytest 37 passed | Chương 4.3 | `make test` |
| 23 | Hình 3.16 | model_comparison_chart.png | So sánh AUC/F1/FPR các mô hình | Chương 4.4 | Vẽ từ evaluate.py / placeholder |
| 24 | Hình 3.17 | confusion_matrix.png | Ma trận nhầm lẫn | Chương 4.4 | Placeholder |
| 25 | Hình 3.18 | roc_curve.png | Đường cong ROC | Chương 4.4 | Placeholder |
| 26 | Hình 3.19 | detection_time_chart.png | Thời gian phát hiện theo cửa sổ | Chương 4.5 | Placeholder |
| 27 | Hình 3.20 | queue_throughput_chart.png | Queue size & throughput theo thời gian | Chương 4.5 | Placeholder |
| 28 | Hình 3.21 | vm_arch.png | MacBook M → Ubuntu VM → Docker Lab | Chương 4.1 | Vẽ từ VM_DOCKER_LAB_GUIDE.md |
| 29 | Hình 3.22 | alert_detail.png | Chi tiết cảnh báo: scores, triggers, reason codes | Chương 4.3 | Log alert đầy đủ |
| 30 | Hình 3.23 | burst_rule_formula.png | Công thức burst_exfil_score | Chương 3.4.1 | Vẽ từ burst_exfil.py |

Lưu ý: Hình 16–20, 23–27 là placeholder cần vẽ từ dữ liệu thực sau demo.