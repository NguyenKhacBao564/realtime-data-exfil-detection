# Danh sách Giá trị Cần Điền Thủ Công (TODO_FILL_VALUES.md)

Tất cả placeholder `[CẦN ĐIỀN...]` trong báo cáo.

## Thông tin chung (Bìa báo cáo)
- [ ] **Tên môn học chính xác** (VD: "Môn học: Xử lý tín hiệu số" / "Môn học: An toàn thông tin mạng")
- [ ] **Họ tên thành viên 01** (Trưởng nhóm) + **MSSV**
- [ ] **Họ tên thành viên 02** + **MSSV**
- [ ] **Họ tên thành viên 03** + **MSSV**
- [ ] **Tháng/Năm nộp** (VD: "06/2026")

## Chương 1
- [ ] Câu mở đầu/Tóm tắt đề tài (1–2 đoạn)
- [ ] Danh sách 7–10 bài báo khoa học cho Chương 1 (Google Scholar: "HTTP data exfiltration detection", "network anomaly detection", "CICIDS2017 exfiltration")

## Chương 2
- [ ] **Bảng 1.1**: 5–10 bài báo liên quan — cần điền: Tác giả, Năm, Phương pháp, Dataset, Kết quả chính, Ghi chú
- [ ] Mô tả chi tiết lý thuyết cho từng mục 2.1–2.12 (dựa trên tài liệu tham khảo)
- [ ] Trích dẫn đúng chuẩn (IEEE/APA) cho tài liệu tham khảo

## Chương 3
- [ ] **Hình 1.1–1.5, 2.1–2.2, 3.23**: Vẽ sơ đồ (draw.io/Mermaid) và export PNG
- [ ] **Bảng 2.1–2.8**: Copy giá trị từ code — **đã có sẵn**, chỉ cần format
- [ ] Công thức toán học (LaTeX):
  - `upload_download_ratio = total_fwd_bytes / (total_bwd_bytes + ε)`
  - `request_rate = request_count / window_duration`
  - `z_i = |x_i - μ_i| / (σ_i + ε)`
  - `online_score = Σ(w_i * min(z_i, 10) / 2.0) / Σ(w_i)`
  - `burst_exfil_score` weights & thresholds
  - `alert = BURST_RULE ∨ OFFLINE_MODEL ∨ ONLINE_UNKNOWN_ANOMALY`
- [ ] Mô tả thuật toán Welford (có pseudocode)

## Chương 4
### 4.1 Môi trường
- [ ] **Interface name VM** (eth0 / ens33 / ens192) — dùng cho live capture
- [ ] Spec VM: CPU cores, RAM, Disk
- [ ] Spec MacBook host: Model, macOS version
- [ ] Docker version, Docker Compose version

### 4.2 Kịch bản — Chụp ảnh & Log
- [ ] **Hình 3.1–3.22**: Tất cả screenshot từ checklist thực nghiệm
- [ ] Log alert đầy đủ cho mỗi scenario (copy vào phụ lục hoặc mô tả)

### 4.3 Kết quả thực nghiệm
- [ ] **Bảng 3.2**: online anomaly monitor results — chạy thực tế trên VM:
  | Scenario | burst_score | online_score | online_prediction | Alert? |
  |---|---|---|---|---|
  | Normal (warmup) | [CẦN CHẠY] | N/A | 0 | No |
  | Normal (steady) | [CẦN CHẠY] | [CẦN CHẠY] | 0 | No |
  | Exfil burst | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | Yes |
  | Slow-drip | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | Yes |

### 4.4 Đánh giá mô hình offline
- [ ] **Bảng 3.1**: Metrics chính xác từ `python src/train/evaluate.py`:
  | Model | AUC | F1 | Precision | Recall | FPR | Threshold |
  |---|---|---|---|---|---|---|
  | CNN1D | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] |
  | BiLSTM | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] |
  | Isolation Forest | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | N/A |
  | One-Class SVM | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | [CẦN CHẠY] | N/A |
- [ ] **Train/Val/Test split** chính xác: 70/10/20 hay 80/20? (Check preprocess.py)
- [ ] **Hình 3.16–3.18**: Confusion matrix, ROC curve, F1 comparison — export từ evaluate.py

### 4.5 Đánh giá online
- [ ] **Bảng 3.3**: Pipeline performance
  | Metric | Value | Target | Pass/Fail |
  |---|---|---|---|
  | Packets/sec | [CẦN CHẠY] | > 10000 | [CẦN CHẠY] |
  | Windows/sec | [CẦN CHẠY] | > 10 | [CẦN CHẠY] |
  | Max queue % | [CẦN CHẠY] | < 80% | [CẦN CHẠY] |
  | Detection time (burst) | [CẦN CHẠY] | < 5s | [CẦN CHẠY] |
  | Detection time (slow-drip) | [CẦN CHẠY] | < 60s | [CẦN CHẠY] |
- [ ] **Bảng 3.4**: Detection time chi tiết
- [ ] **Hình 3.19–3.20**: Charts detection time, queue/throughput

### 4.6 Thảo luận
- [ ] Viết 5–6 đoạn thảo luận dựa trên kết quả thực

## Kết luận
- [ ] **Đoạn 1**: Kết quả đạt được (3–5 bullet points)
- [ ] **Đoạn 2**: Hạn chế (3–5 bullet points)
- [ ] **Đoạn 3**: Phát triển tương lai (3–5 bullet points)

## Tài liệu tham khảo
- [ ] **15–20 citations** đúng chuẩn IEEE
- [ ] Dataset: CICIDS2017, UNSW-NB15
- [ ] Tools: Scapy, Docker, tcpdump, scikit-learn, TensorFlow/Keras
- [ ] Papers: Đánh dấu `[CẦN KIỂM TRA LẠI THÔNG TIN TRÍCH DẪN]` cho citation chưa verify

## Khác
- [ ] Tạo thư mục `report/images/` và copy tất cả PNG vào đó
- [ ] Kiểm tra numbering hình/bảng liên tục (Hình 1.1, 1.2... Hình 3.1, 3.2...)
- [ ] Kiểm tra cross-reference trong text: "như Hình 3.5", "xem Bảng 2.1"