# Checklist Thu Thập Bằng Chứng Thực Nghiệm (EXPERIMENT_CHECKLIST.md)

Dùng để theo dõi tiến độ thu thập ảnh/log/metric cho báo cáo.

## 1. Kiểm tra chất lượng code
- [ ] `make compile` — python3 -m compileall src lab scripts tests → OK
- [ ] `make test` — pytest 37 passed
- [ ] `python3 src/pipeline.py --help` — CLI hiển thị flags online monitor
- [ ] `python3 lab/victim/generate_http_traffic.py --help` — CLI traffic generator

## 2. Docker Lab
- [ ] `make lab-up` — docker-compose up -d → 3 services up
- [ ] `docker compose -f lab/docker-compose.yml ps` → exfil-server Healthy, victim-client Up, monitor-detector Up
- [ ] Chụp ảnh **Hình 3.1**: docker-compose ps

## 3. Traffic Generation & Logs
### 3.1 Normal Traffic (Baseline)
- [ ] `DURATION=120 make lab-normal` — chạy 120s để warmup online monitor
- [ ] Chụp **Hình 3.2**: lệnh make lab-normal
- [ ] Chụp **Hình 3.3**: log exfil-server (make lab-logs)
- [ ] Ghi nhận: số request, payload size, interval

### 3.2 Exfiltration Burst
- [ ] `DURATION=30 make lab-exfil`
- [ ] Chụp **Hình 3.4**: lệnh make lab-exfil
- [ ] Chụp **Hình 3.5**: log detector (burst_score > 0.7, BURST_RULE trigger)
- [ ] Ghi nhận: burst_score, model_score, online_score

### 3.3 Slow-Drip (Unknown Anomaly)
- [ ] `DURATION=120 make lab-slow-drip`
- [ ] Chụp **Hình 3.6**: lệnh make lab-slow-drip
- [ ] Chụp **Hình 3.7**: log detector (burst_score < 0.7, ONLINE_UNKNOWN_ANOMALY trigger)
- [ ] Ghi nhận: online_score, HIGH_Z reason codes

## 4. Live Capture
- [ ] `make live-demo INTERFACE=eth0` (trong VM Ubuntu)
- [ ] Chụp **Hình 3.8**: khởi động live detector
- [ ] Chụp **Hình 3.9**: BPF filter bao gồm port 8000
- [ ] Chụp **Hình 3.10/3.11**: cảnh báo real-time
- [ ] Ghi nhận: detection time, queue sizes

## 5. PCAP Capture & Offline Replay
- [ ] `sudo ./scripts/capture_lab_pcap.sh eth0 60 lab/captures/demo.pcap`
- [ ] Chụp **Hình 3.12**: tcpdump capture
- [ ] `make offline-replay PCAP=lab/captures/demo.pcap`
- [ ] Chụp **Hình 3.13**: offline replay với online monitor
- [ ] Kiểm tra: PCAP replay phát hiện giống live

## 6. Final Statistics & Evidence
- [ ] Dừng pipeline (Ctrl+C) → chụp **Hình 3.14**: final stats (processed, alerts, online_anomalies, baselines)
- [ ] Chụp **Hình 3.15**: pytest 37 passed
- [ ] Chụp **Hình 3.22**: chi tiết cảnh báo đầy đủ (scores, triggers, reason codes)

## 7. Model Evaluation (nếu có data)
- [ ] Chạy `python src/train/evaluate.py` cho CNN1D, BiLSTM
- [ ] Export confusion matrix, ROC curve
- [ ] Chụp **Hình 3.16, 3.17, 3.18**
- [ ] Điền **Bảng 3.1** metrics chính xác

## 8. VM Demo Checklist (Demo chính thức)
- [ ] MacBook M → UTM → Ubuntu 22.04 ARM64 VM
- [ ] VM: Docker + Docker Compose cài đặt
- [ ] VM: Bridge network mode
- [ ] VM: Clone repo, make compile, make test
- [ ] VM: make lab-up → 3 services healthy
- [ ] VM: Chạy tuần tự normal → exfil → slow-drip
- [ ] VM: Live detector trên eth0
- [ ] VM: PCAP capture → offline replay
- [ ] VM: Thu thập tất cả screenshot/log

## 9. Screenshots cần rename/copy vào report/images/
- [ ] arch_overview.png
- [ ] docker_lab_arch.png
- [ ] pipeline_threads.png
- [ ] online_monitor_arch.png
- [ ] detection_layers.png
- [ ] feature_vector.png
- [ ] feature_extraction_flow.png
- [ ] lab_docker_ps.png
- [ ] lab_normal_cmd.png
- [ ] lab_normal_logs.png
- [ ] lab_exfil_cmd.png
- [ ] lab_exfil_logs.png
- [ ] lab_slow_drip_cmd.png
- [ ] lab_slow_drip_logs.png
- [ ] live_detector_startup.png
- [ ] bpf_filter_8000.png
- [ ] online_anomaly_alert.png
- [ ] combined_alert.png
- [ ] tcpdump_capture.png
- [ ] offline_replay.png
- [ ] final_stats.png
- [ ] pytest_passed.png
- [ ] vm_arch.png
- [ ] alert_detail.png
- [ ] burst_rule_formula.png
- [ ] model_comparison_chart.png (placeholder)
- [ ] confusion_matrix.png (placeholder)
- [ ] roc_curve.png (placeholder)
- [ ] detection_time_chart.png (placeholder)
- [ ] queue_throughput_chart.png (placeholder)