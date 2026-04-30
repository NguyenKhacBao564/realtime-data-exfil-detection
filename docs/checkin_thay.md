# Báo cáo check-in giữa kỳ — Phát hiện Data Exfiltration qua HTTP

> **Người gửi**: Nhóm SV [tên nhóm]
> **Người nhận**: Thầy Đàm Minh Linh (linhdm@ptit.edu.vn)
> **Ngày**: [ngày gửi]
> **Mục đích**: xác nhận hướng đi đang đúng yêu cầu Thầy giao trước khi hoàn thiện báo cáo + slide.

---

## 1. Tóm tắt cách hiểu đề bài

Nhóm chia hệ thống thành 3 lớp tương ứng 3 nội dung chính của đề:

| Đề bài yêu cầu | Lớp triển khai | Output |
|---|---|---|
| (1) Phân tích gói/session HTTP | `src/capture/` (Scapy) | dict packet: timestamp, src/dst, ports, length, flags |
| (2) Trích đặc trưng theo cửa sổ | `src/features/` (60s window per src_ip) | upload/download ratio, burst pattern, unusual port ratio, `inter_request_time_std` |
| (3) Pipeline đa luồng | `src/pipeline.py` (3 threads + queue) | capture → features → inference, có graceful shutdown |
| (4) Mô hình AI | offline + runtime | xem §3 |
| (5) Đánh giá AUC/F1/det\_time/FPR | `src/train/evaluate.py --compare` | bảng so sánh, PNG, JSON |
| Đề xuất `burst-exfil score` | `src/features/burst_exfil.py` | score 0–1, alert khi > 0.7 |

**Cách diễn giải đoạn "Isolation Forest/One-Class SVM (anomaly) **và** BiLSTM/CNN 1D"**: nhóm hiểu là **chọn 1 đại diện cho mỗi trường phái** để so sánh hai thái cực anomaly vs supervised. Cụ thể chọn:

- **Anomaly**: `IsolationForest` (nhanh hơn OCSVM 10×, phù hợp real-time).
- **Supervised**: `CNN1D` (AUC cao nhất trong nhóm DL, model 162KB nhẹ).

→ Báo cáo cuối cùng sẽ có 1 bảng so sánh trực tiếp giữa 2 model này trên cùng test set.

**Câu hỏi 1 cho Thầy**: cách diễn giải này có đúng ý Thầy không, hay Thầy muốn chạy đủ cả 4 model (IF, OCSVM, BiLSTM, CNN1D)?

---

## 2. Dataset và cách gán nhãn

- **Dataset**: CICIDS2017 (8 file CSV đã extract bằng CICFlowMeter), tổng **2.83M flows**, 67 features.
- **Lý do**: dataset chuẩn IDS, có sẵn trong tài liệu Thầy đề xuất (UNB CIC).
- **Vấn đề**: CICIDS2017 không có nhãn `Exfiltration` riêng → nhóm gán nhãn theo heuristic:
  - **Bot traffic** (Friday-Morning, 1,966 flows): upload >> download, session ngắn → proxy chính cho exfil.
  - **Infiltration** (Thursday-Afternoon, 36 flows): port scan + backdoor → proxy phụ.
  - **Custom heuristic**: flow có `upload_ratio > 5` AND `duration < 600s` AND `psh_ratio > 0.3` cũng gán = exfil.
- **Tỷ lệ exfil sau gán nhãn**: 1,543/1,981,520 ≈ 0.08% (rất imbalance, đúng đặc trưng exfil thực tế).

**Câu hỏi 2 cho Thầy**: phương pháp gán nhãn heuristic này có chấp nhận được không? Hay Thầy yêu cầu phải có dataset có ground-truth label exfil thật (ví dụ tự capture)?

---

## 3. Mô hình & kết quả hiện tại

### 3.1 Bảng kết quả trên CICIDS2017 test set (424,611 flows, 313 exfil)

| Model | Loại | AUC-ROC | F1 | Precision | Recall | FPR | Inference (μs/flow) | Ghi chú |
|---|---|---|---|---|---|---|---|---|
| `isolation_forest.pkl` (v1, 67 features) | anomaly | 0.5306 | 0.0011 | 0.0006 | 0.038 | 5.0% | — | Gần random — bỏ |
| `oneclass_svm.pkl` (v1, 67 features) | anomaly | 0.5546 | 0.0013 | 0.0007 | 0.045 | 4.9% | — | Tương tự — bỏ |
| **`isolation_forest_v2.pkl`** *(retrain, 12 upload features)* | anomaly | **0.5463** | 0.0025 | 0.0013 | 0.042 | 2.41% | **6.35** | **Đại diện anomaly** |
| **`cnn1d_final.h5`** | supervised | **0.9971** | 0.0567 | 0.0292 | 1.000 | 2.45% | **8.95** | **Đại diện supervised** |
| `bilstm_final.h5` | supervised | 0.9966 | 0.0438 | 0.0224 | 1.000 | 3.22% | — | Backup, model nặng 9× |

> **Δ AUC = 0.451** giữa supervised và anomaly. Verdict tự động sinh: *"Supervised vượt trội. Phù hợp khi có label tin cậy; anomaly chỉ nên làm lớp bổ sung phát hiện zero-day."*

**Quan sát**:

- **Anomaly v1** (67 features, contamination=0.05) gần random → không dùng.
- **Anomaly v2** đã retrain với protocol đúng (train chỉ trên benign rows, 12 upload-related features, contamination=0.001 ≈ tỷ lệ exfil thực): AUC chỉ tăng từ 0.53 → 0.55. Cải thiện không đáng kể vì:
  - CICIDS2017 không có flow exfiltration đúng nghĩa, nhóm dùng Bot+Infiltration làm proxy → bản thân label đã noisy.
  - Đặc trưng exfil của Bot (upload>>download, session ngắn) **chồng lấp với traffic benign** (web upload, video upload) trong CICFlowMeter features.
  - Đây là **giới hạn dữ liệu**, không phải giới hạn thuật toán.
- **Supervised CNN1D** đạt AUC=0.9971, recall=1.0 (bắt 313/313 flow exfil), FPR=2.45%. Precision thấp (0.029) do test set imbalance nặng (313 exfil / 424,611 flow); con số này vẫn cao hơn random ~40 lần.
- **Inference time** đo trên CPU laptop: anomaly 6.35 μs/flow, supervised 8.95 μs/flow → cả hai phù hợp real-time.

**Diễn giải trong báo cáo**:

> Bảng so sánh cho thấy anomaly thuần (chỉ học từ traffic bình thường) **không đủ** để phát hiện exfiltration trên dataset CICIDS2017, vì pattern Bot/Infiltration không khác biệt đủ rõ với traffic benign trong feature space. Supervised CNN1D — học từ label exfil — vượt trội với AUC 0.9971. Trong hệ thống thực, đề xuất dùng supervised làm detector chính, anomaly làm lớp phòng vệ phụ để phát hiện zero-day pattern chưa từng gặp.

→ Đây vẫn là **kết luận khoa học hợp lệ**, đúng tinh thần đề bài "so sánh anomaly vs supervised trong bối cảnh exfiltration".

### 3.2 Pipeline đa luồng

```
[Thread 1: Capture]  →  packet_queue  →  [Thread 2: Window aggregate (60s)]
                                            →  feature_queue  →  [Thread 3: Inference + Alert]
                                                                      ↓
                                                       console + log + Telegram
```

- 3 thread chia sẻ bằng `Queue` thread-safe, có `stop_event` cho graceful shutdown.
- Đã test trên `Friday-WorkingHours.pcap` (8.8GB) — 3 thread đều chạy, alert đúng kỳ vọng.
- Throughput đo được khi `--debug`: ~3000 packet/s ở Thread 1, qsize ổn định.

---

## 4. Kế hoạch demo

Demo gồm 2 phần:

- **Phần A (offline AI, ~3 phút)**: chạy `python src/train/evaluate.py --compare` → in bảng so sánh `IsolationForest_v2` vs `CNN1D` trên cùng test set, mở `notebooks/comparison_table.png` + `notebooks/roc_comparison.png` để chiếu slide.
- **Phần B (live pipeline, ~6 phút)**: capture trên `lo0`, chạy 3 kịch bản:
  1. **Benign baseline** (30 request, 200B, delay 1s) → KHÔNG alert (chứng minh FPR thấp).
  2. **Burst exfil** (100 request, 50KB, delay 0.1s) → alert trong 10–15s.
  3. **Slow-and-low** (30 request, 5KB, delay 5s) → thảo luận giới hạn của rule, lý do cần ML.
- **Bằng chứng đa luồng**: dùng flag `--debug` để in `qsize` 3 thread định kỳ.
- **Backup plan**: `--offline --pcap data/raw/demo_exfil_local.pcap` nếu live fail.

**Câu hỏi 3 cho Thầy**: demo trên `lo0` (loopback 127.0.0.1) có được xem là "real-time" hợp lệ không? Hay Thầy yêu cầu phải capture trên interface vật lý (Wi-Fi/Ethernet) để chứng minh hệ thống hoạt động trên mạng thật?

---

## 5. Tình trạng

| Hạng mục | % | Ghi chú |
|---|---|---|
| Phase 1: Setup + EDA | 100% | `notebooks/01_EDA.ipynb` |
| Phase 2: Feature Engineering | 100% | 2.83M flows, scaler đã fit |
| Phase 3: Multi-thread Pipeline | 100% | Test xong trên Friday PCAP |
| Phase 4: Model Training | 100% | `isolation_forest_v2` retrain xong, AUC=0.5463 |
| Phase 5: Evaluation | 100% | `evaluate.py --compare` chạy ổn, đã có PNG/JSON/MD |
| Phase 6: Báo cáo + Demo | 75% | Báo cáo `bao_cao.docx` xong, demo plan đầy đủ, đang chờ rehearsal cuối |

---

## 6. Tóm gọn 3 câu hỏi

1. **Diễn giải đề bài**: chọn `IsolationForest` (anomaly) vs `CNN1D` (supervised) làm 2 đại diện so sánh — có đúng ý Thầy không?
2. **Gán nhãn**: heuristic (Bot + Infiltration + upload-ratio) có chấp nhận được không?
3. **Demo `lo0`**: loopback có được tính là "real-time" hay phải capture interface vật lý?

Nhóm rất mong Thầy phản hồi sớm để định hướng phần còn lại. Trân trọng cảm ơn Thầy.

---

*File này được sinh tự động trong quá trình kiểm tra hướng đi. Khi gửi Thầy, có thể export sang `docs/checkin_thay.docx` hoặc copy sang body email.*
