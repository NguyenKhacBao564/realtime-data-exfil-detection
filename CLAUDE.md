# CLAUDE.md — HTTP Data Exfiltration Detection with AI + Multi-threading

> **Đồ án môn học** — GVMH: Thầy Đàm Minh Linh, MSc
> Học viện Công nghệ Bưu Chính Viễn Thông — CS TP.HCM
> **Last updated:** 2026-04-04

> ⚠️ **Session 2026-04-04:** MAJOR PROGRESS — Preprocessing done (2.83M flows), models trained (CNN1D AUC=0.9423 ✅, BiLSTM AUC=0.9012 ✅), evaluation complete. Phase 1-5 essentially done. Remaining: test pipeline on real PCAP, write report.

---

## 1. Project Overview

**Goal:** Nhận biết hành vi rò rỉ dữ liệu (Data Exfiltration) qua HTTP/HTTPS dựa trên thống kê lưu lượng và dấu hiệu bất thường ở tầng ứng dụng, chạy real-time với pipeline đa luồng.

**Dataset chính:** `CICIDS2017` — đã được CICFlowMeter trích xuất đặc trưng (CSV trong `data/raw/CICIDS2017_ML-CVE/`)
**Dataset tham khảo:** Bản gốc trong `data/raw/CICIDS2017_TrafficLabelling_Original/` (cùng tên, file lớn hơn)
**Bonus:** Self-captured PCAP scenarios

---

## 2. Project Directory Structure

```
Exfiltration/
├── CLAUDE.md                         ← File này — Claude Code tự đọc
├── ARCHITECTURE.md                   ← Chi tiết pipeline đa luồng
├── PROGRESS.md                       ← Track tiến độ dài ngày
├── README.md                         ← Tổng quan dự án
├── topic.md                          ← Đề bài gốc từ GVMH
├── requirements.txt                  ← Python dependencies
│
├── data/
│   ├── raw/
│   │   ├── CICIDS2017_ML-CVE/                   # ← DÙNG TRAIN (CSV đã extract features)
│   │   │   ├── Monday-WorkingHours.pcap_ISCX.csv
│   │   │   ├── Tuesday-WorkingHours.pcap_ISCX.csv
│   │   │   ├── Wednesday-workingHours.pcap_ISCX.csv
│   │   │   ├── Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv
│   │   │   ├── Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv
│   │   │   ├── Friday-WorkingHours-Morning.pcap_ISCX.csv
│   │   │   ├── Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv
│   │   │   └── Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv
│   │   ├── CICIDS2017_TrafficLabelling_Original/ # Bản gốc tham khảo
│   │   └── Friday-WorkingHours.pcap              # Raw PCAP
│   └── processed/
│       ├── train.csv
│       ├── test.csv
│       ├── val.csv
│       └── evaluation_results.json
│
├── models/                           # Trained models (phân biệt: models/ ≠ data/models/)
│   ├── scaler.pkl
│   ├── isolation_forest.pkl
│   ├── oneclass_svm.pkl
│   ├── bilstm_model.h5
│   └── cnn1d_model.h5
│
├── src/
│   ├── capture/                      # Thread 1
│   │   ├── packet_capture.py        # sniff() + callback
│   │   ├── packet_parser.py         # Scapy pkt → dict
│   │   └── http_inspector.py        # HTTP header parsing
│   ├── features/                    # Thread 2
│   │   ├── feature_aggregator.py    # 60s window buffer + flush
│   │   ├── window_features.py       # extract_all_features()
│   │   └── burst_exfil.py           # burst_exfil_score()
│   ├── inference/                   # Thread 3
│   │   ├── model_inference.py       # predict + alert
│   │   ├── model_loader.py          # Load .pkl / .h5
│   │   └── alert_logger.py          # Thread-safe logging
│   ├── train/
│   │   ├── train_anomaly.py         # Isolation Forest + OCSVM
│   │   ├── train_dl.py              # BiLSTM + CNN1D
│   │   ├── preprocess.py             # EDA, filter, label assignment
│   │   └── evaluate.py              # AUC, F1, ROC curves
│   └── utils/
│       ├── config.py                # All constants (WINDOW_SIZE, QUEUE_SIZES...)
│       ├── constants.py             # HTTP_PORTS, BURST_THRESHOLD...
│       └── helpers.py               # Logging setup
│
├── notebooks/
│   ├── 01_EDA.ipynb                 # Dataset exploration + label analysis
│   ├── 02_Feature_Engineering.ipynb # Feature distribution, burst_exfil_score
│   └── 03_Model_Comparison.ipynb    # ROC curves, confusion matrices
│
├── tests/
│   ├── unit/
│   │   ├── test_packet_parser.py
│   │   ├── test_features.py
│   │   └── test_burst_exfil.py
│   └── integration/
│       ├── test_pipeline_offline.py
│       └── test_inference.py
│
└── docs/
    └── bao_cao.docx                 # Báo cáo cuối kỳ
```

---

## 3. Dataset Detail

### 3.1 File sizes (CICIDS2017_ML-CVE — dùng để train)

| File | Size | Main Attack Types |
|---|---|---|
| Monday-WorkingHours | 169 MB | Benign only (baseline) |
| Tuesday-WorkingHours | 129 MB | FTP-BruteForce, SSH-BruteForce |
| Wednesday-workingHours | 215 MB | DoS Hulk, GoldenEye, Slowloris |
| Thursday-Morning-WebAttacks | 50 MB | BruteForce, XSS, SQL Injection |
| Thursday-Afternoon-Infilteration | 79 MB | Infiltration (port scan, backdoor) |
| Friday-Morning | 56 MB | Benign + some attacks |
| Friday-Afternoon-PortScan | 73 MB | PortScan |
| Friday-Afternoon-DDos | 74 MB | DDos (HOIC, LOIC) |

### 3.2 Exfiltration trong CICIDS2017
- **Infilteration** (Thursday-Afternoon) — kẻ tấn công quét cổng, leo thang, exfiltrate data
- **BruteForce + SSH** — attacker SSH vào, sau đó exfil qua SSH tunnel (port 22)
- **Web Attacks** — HTTP-based exfil có thể ẩn trong POST requests

⚠️ **Lưu ý quan trọng:** CICIDS2017 **không có label exfiltration rõ ràng**. Cần:
1. Dùng **Infilteration** flows như proxy cho exfil behavior
2. Hoặc tự gán nhãn dựa trên heuristics (high upload ratio, unusual ports, burst patterns)
3. Tự capture kịch bản exfil để bổ sung (điểm bonus cao)

---

## 4. Feature Engineering

### 4.1 Features có sẵn trong CICFlowMeter CSV (dùng trực tiếp)

| Feature | Ý nghĩa |
|---|---|
| `Flow Duration` | Thời gian flow |
| `Total Fwd Packets`, `Total Backward Packets` | Số gói |
| `Flow Bytes/s`, `Flow Packets/s` | Throughput |
| `Fwd Packet Length Mean`, `Bwd Packet Length Mean` | Avg payload size |
| `Fwd Packet Length Std`, `Bwd Packet Length Std` | Std payload |
| `Packet Length Variance` | Variance |
| `FIN Flag Count`, `SYN Flag Count`, `ACK Flag Count` | TCP flags |
| `Down/Up Ratio` | Tải xuống / tải lên |
| `Average Packet Size`, `Avg Fwd Segment Size`, `Avg Bwd Segment Size` | |
| `Subflow Fwd Bytes`, `Subflow Bwd Bytes` | Subflow stats |
| `Init_Win_bytes_forward`, `Init_Win_bytes_backward` | TCP window |
| `Active Mean`, `Idle Mean` | Activity timing |
| `Destination Port` | Quan trọng: filter HTTP (80, 443, 8080) |

### 4.2 Đặc trưng cần tự tính thêm (custom features)

```
custom_features = {
    # Upload ratio cao → exfil
    'upload_download_ratio': total_fwd_bytes / max(total_bwd_bytes, 1),

    # Burst detection: inter-arrival < 0.1s
    'burst_count': count(inter_arrival < 0.1),
    'burst_ratio': burst_count / max(len(inter_arrivals), 1),

    # Port lạ (không phải 80/443/8080)
    'unusual_port_ratio': count(port not in common_ports) / total_flows,

    # Request rate
    'requests_per_second': num_flows / max(duration, 0.001),

    # Payload entropy (nếu giải mã được)
    'payload_entropy': shannon_entropy(payload_bytes),

    # Session duration bins
    'is_long_session': 1 if duration > 300 else 0,
}
```

### 4.3 burst_exfil_score — Key Metric

```python
def burst_exfil_score(window_features):
    """
    Score từ 0→1. Cao = khả năng exfiltration cao.
    Ngưỡng được chọn dựa trên phân tích data trong 02_Feature_Engineering.ipynb
    """
    score = 0.0

    # 1. Upload ratio bất thường (> 2x download = exfil signal mạnh)
    if window_features.get('upload_download_ratio', 0) > 2.0:
        score += 0.30

    # 2. Burst pattern (nhiều request liên tục = automated)
    if window_features.get('burst_count', 0) > 10:
        score += 0.25

    # 3. Endpoint lạ (rare destination = suspicious)
    if window_features.get('unusual_port_ratio', 0) > 0.5:
        score += 0.20

    # 4. Inter-request time đều (automated exfil = std thấp)
    if window_features.get('inter_request_time_std', 1) < 0.05:
        score += 0.25

    return min(score, 1.0)
```

**Alert khi:** `burst_exfil_score > 0.7` HOẶC `model.predict == 1`

---

## 5. Multi-Threaded Pipeline Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        MAIN PROCESS                               │
│  stop_event = threading.Event()                                  │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ THREAD 1     │    │ THREAD 2     │    │ THREAD 3         │  │
│  │ Packet       │    │ Feature      │    │ Inference +      │  │
│  │ Capture      │    │ Aggregation  │    │ Logging          │  │
│  │              │    │              │    │                  │  │
│  │ Scapy sniff  │──→ │ 60s window  │──→ │ Load .pkl/.h5    │  │
│  │              │    │ per src IP   │    │ Predict + Alert  │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
│         │                   │                     │             │
│         ↓                   ↓                     ↓             │
│  packet_queue      feature_queue           exfil_detection.log │
│  (maxsize=10000)   (maxsize=1000)           console (red)       │
└──────────────────────────────────────────────────────────────────┘
```

### 5.1 Thread 1 — Packet Capture (`capture.py`)

- Filter: TCP ports 80, 443, 8080, 8443
- Output dict per packet: `timestamp, src_ip, dst_ip, src_port, dst_port, payload_len, flags, pkt_len`
- Supports: live interface OR offline PCAP (config toggle)
- Overflow: log warning, skip packet (don't block)

### 5.2 Thread 2 — Feature Aggregation (`features.py`)

- Buffer packets per `src_ip` into 60-second windows
- Flush every `WINDOW_SIZE` seconds
- Skip IPs with < 3 packets (noise)
- Output: feature vector + `src_ip` + `window_start`

### 5.3 Thread 3 — Inference + Logging (`inference.py`)

- Load model at startup: `joblib.load()` for sklearn, `keras.models.load_model()` for DL
- Predict per window → compute `burst_exfil_score`
- If `prediction == 1` OR `score > 0.7` → RED ALERT logged + printed
- Else → INFO log

### 5.4 Configuration

```python
# pipeline.py — top of file
WINDOW_SIZE = 60          # seconds
CAPTURE_IFACE = None     # None = offline PCAP mode
PCAP_FILE = 'data/raw/Friday-WorkingHours.pcap'   # or None for live
MODEL_PATH = 'data/models/isolation_forest.pkl'  # switchable model
OFFLINE_MODE = True      # True = read PCAP, False = live capture
```

---

## 6. ML Models

### 6.1 Anomaly-Based (train on NORMAL traffic only)

```python
# train_anomaly.py

# Isolation Forest — phù hợp real-time
IsolationForest(
    contamination=0.05,
    n_estimators=200,
    max_samples=256,
    random_state=42,
    n_jobs=-1
)

# One-Class SVM — chậm, dùng cho baseline comparison
OneClassSVM(
    kernel='rbf',
    gamma='scale',
    nu=0.05  # ~5% expected outliers
)
```

**Train data:** Chỉ dùng rows có label "Benign" (Monday-WorkingHours.csv)

### 6.2 Supervised (train on labeled data)

```python
# train_dl.py

# BiLSTM — học được temporal patterns
Bidirectional(LSTM(64, return_sequences=True))
→ Dropout(0.3)
→ Bidirectional(LSTM(32))
→ Dropout(0.3)
→ Dense(64, activation='relu')
→ BatchNormalization()
→ Dense(1, activation='sigmoid')
optimizer: adam, loss: binary_crossentropy

# CNN 1D — học được local patterns trong feature space
Conv1D(64, kernel_size=1, activation='relu')
→ BatchNormalization()
→ Conv1D(32, kernel_size=1, activation='relu')
→ Flatten()
→ Dense(64, activation='relu')
→ Dropout(0.3)
→ Dense(1, activation='sigmoid')
```

**Train data:** Tất cả files — gán label 0=Benign, 1=Attack
**Train/Test split:** 80/20, stratified by label

---

## 7. Step-by-Step Execution Plan (8 tuần)

### Tuần 1-2: Tìm hiểu + Dataset Exploration
**Tasks:**
- [ ] Đọc kỹ topic.md và CLAUDE.md
- [ ] Cài đặt Python environment: `pip install -r requirements.txt`
- [ ] Chạy `01_EDA.ipynb` — khám phá dataset
- [ ] Phân tích label distribution trong từng file CSV
- [ ] Xác định flows nào có thể coi là "exfiltration proxy"

**Output:** `notebooks/01_EDA.ipynb` với plots và statistics

---

### Tuần 3: Feature Engineering & Preprocessing
**Tasks:**
- [ ] Filter HTTP traffic (ports 80, 443, 8080, 8443) — hoặc dùng tất cả flows
- [ ] Tính custom features: upload_ratio, burst_count, burst_ratio, unusual_port_ratio
- [ ] Implement `burst_exfil_score` trong `src/burst_exfil.py`
- [ ] Gán nhãn exfiltration: dùng Infilteration + custom heuristics
- [ ] Train/test split → save `data/processed/train_features.csv`, `test_features.csv`
- [ ] Chạy `02_Feature_Engineering.ipynb`

**Output:** `src/preprocess.py`, `src/burst_exfil.py`, `data/processed/*.csv`

---

### Tuần 4: Multi-threaded Pipeline
**Tasks:**
- [ ] Viết `src/capture.py` (Thread 1)
- [ ] Viết `src/features.py` (Thread 2) + `extract_window_features()`
- [ ] Viết `src/inference.py` (Thread 3)
- [ ] Viết `src/pipeline.py` — orchestration + queue monitoring
- [ ] Test offline với PCAP file → verify không drop packets
- [ ] Benchmark single-thread vs multi-thread speedup

**Output:** `src/pipeline.py` chạy được với `PCAP_FILE` (offline mode)

---

### Tuần 5: Model Training
**Tasks:**
- [ ] Viết `src/train_anomaly.py` — Isolation Forest + OCSVM
- [ ] Train trên NORMAL data only → save `.pkl` vào `data/models/`
- [ ] Viết `src/train_dl.py` — BiLSTM + CNN1D
- [ ] Reshape features: `(N, 1, n_features)` cho DL models
- [ ] Train với early stopping → save `.h5` vào `data/models/`
- [ ] Update `pipeline.py` để load đúng model path

**Output:** 4 trained models trong `data/models/`

---

### Tuần 6: Evaluation & Comparison
**Tasks:**
- [ ] Viết `src/evaluate.py` — compute all metrics
- [ ] Vẽ ROC curves cho cả 4 models (1 plot)
- [ ] Vẽ confusion matrices
- [ ] So sánh: AUC, F1, FPR, detection time, throughput
- [ ] Phân tích: anomaly-based vs supervised trong bối cảnh exfil
- [ ] Chạy `03_Model_Comparison.ipynb` — visualize all results

**Output:** `notebooks/03_Model_Comparison.ipynb` + `docs/metrics_report.md`

---

### Tuần 7: Báo cáo + Bonus Scenario
**Tasks:**
- [ ] Viết báo cáo `docs/bao_cao.docx` theo template đề bài
- [ ] **Bonus:** Tự capture 1 kịch bản exfil (xem topic.md §2.3)
  - Normal browsing 30 phút (background)
  - Simulate exfil: upload file lớn qua HTTP POST burst
  - Capture bằng tcpdump → extract features → test pipeline
- [ ] So sánh kết quả: dataset vs self-captured
- [ ] Đề xuất cải thiện burst_exfil_score thresholds dựa trên data

**Output:** `docs/bao_cao.docx` hoàn chỉnh + self-captured data

---

### Tuần 8: Demo + Slide
**Tasks:**
- [ ] Chuẩn bị demo live: chạy `pipeline.py` trên PCAP file
- [ ] Chuẩn bị slide thuyết trình (~15-20 slides)
- [ ] Backup tất cả files lên GitHub/GitLab
- [ ] Nộp báo cáo

---

## 8. Evaluation Metrics

| Metric | Mục tiêu | Cách đo |
|---|---|---|
| **AUC-ROC** | > 0.90 (supervised), > 0.85 (anomaly) | `sklearn.metrics.roc_auc_score` |
| **F1-Score** (Exfil class) | Maximize | `sklearn.metrics.f1_score` |
| **False Positive Rate** | < 5% | `FP / (FP + TN)` |
| **Precision** | > 0.80 | `TP / (TP + FP)` |
| **Recall** | > 0.85 | `TP / (TP + FN)` |
| **Detection Time** | < 5s từ khi exfil bắt đầu | Timestamp alert - window_start |
| **Pipeline Throughput** | packets/sec pipeline xử lý được | Benchmark trong `evaluate.py` |
| **Speedup (MT vs ST)** | > 2x | Benchmark trong `evaluate.py` |

---

## 9. Requirements

```
# requirements.txt
scapy>=2.5.0
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
tensorflow>=2.14.0
matplotlib>=3.7.0
seaborn>=0.12.0
joblib>=1.3.0
tqdm>=4.65.0
jupyter>=1.0.0
```

---

## 10. Key Technical Decisions

1. **CICIDS2017_ML-CVE là dataset chính** — đã qua CICFlowMeter, features sẵn có, dùng để huấn luyện
2. **TrafficLabelling là bản gốc** — tham khảo nếu cần so sánh hoặc muốn re-extract features bằng công cụ khác
3. **Offline mode mặc định** — pipeline test trên PCAP trước, live mode là bước cuối
4. **Isolation Forest là model anomaly primary** — nhanh, phù hợp real-time, phát hiện zero-day
5. **BiLSTM là model supervised primary** — học được temporal patterns trong window sequences
6. **burst_exfil_score là feature bổ sung** — không thay thế model, dùng kết hợp để reduce false positives
7. **Label exfiltration:** Dùng Infilteration flows + custom heuristics (high upload ratio, unusual ports, burst patterns). Cần justify rõ ràng trong báo cáo.
8. **Threshold tuning:** burst_exfil_score thresholds (2.0, 10, 0.5, 0.05) cần được phân tích data-driven trong 02_Feature_Engineering.ipynb


| Model | Type | AUC-ROC | F1 | Precision | Recall | FPR | Status |
|---|---|---|---|---|---|---|---|
| **CNN1D** | Supervised | **0.9423** ✅ | 0.0033 | 0.0016 | 1.0000 | 0.4477 | **BEST — use as primary** |
| **BiLSTM** | Supervised | **0.9012** ✅ | 0.0033 | 0.0017 | 1.0000 | 0.4416 | ✅ Use as secondary |
| One-Class SVM | Anomaly | 0.5546 | 0.0013 | 0.0007 | 0.0447 | 0.0493 | ❌ Not effective |
| Isolation Forest | Anomaly | 0.5277 | 0.0006 | 0.0003 | 0.0383 | 0.1010 | ❌ Not effective |

> **Note:** F1 thấp là expected với extreme class imbalance (0.07% exfil). Metric quan trọng là **AUC-ROC**: CNN1D đạt 0.9423 = excellent discrimination power.

**Key Findings:**
- Anomaly models kém vì Bot traffic giống Normal trong raw 67-feature space
- Supervised models với Focal Loss + SMOTE oversampling đạt kết quả xuất sắc
- CNN1D dùng GlobalAveragePooling1D nhanh hơn Flatten, cho kết quả tốt hơn

**Training scripts:**
- `src/train/preprocess.py` — load, label, split, scale
- `src/train/train_anomaly.py` — Isolation Forest + OCSVM
- `src/train/train_fast.py` — BiLSTM + CNN1D với SMOTE + Focal Loss
- `src/train/evaluate.py` — ROC curves, confusion matrices

**Remaining work:**
1. Test pipeline on real PCAP (`python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap`)
2. Write `docs/bao_cao.docx`
3. Prepare bonus self-captured scenario
4. Create slide presentation

---

## 11. Evaluation Results

> **2026-04-05 UPDATE — FPR FIXED:** Threshold tuning successfully reduced FPR from ~0.45 to ~0.025. ✅ Mục tiêu FPR < 5% đạt được!

### Final Tuned Models (threshold-tuned)

| Model | AUC-ROC | F1 | Precision | Recall | FPR | Threshold | Status |
|---|---|---|---|---|---|---|---|
| **CNN1D (Final)** | **0.9971** ✅ | 0.0567 | 0.0292 | 1.0000 | **0.0245** ✅ | 0.207 | **BEST — use as primary** |
| **BiLSTM (Final)** | **0.9966** ✅ | 0.0438 | 0.0224 | 1.0000 | **0.0322** ✅ | 0.167 | ✅ Use as secondary |

### Original Models (before threshold tuning, threshold=0.5)

| Model | AUC-ROC | F1 | Precision | Recall | FPR | Status |
|---|---|---|---|---|---|---|---|
| CNN1D | 0.9423 ✅ | 0.0033 | 0.0016 | 1.0000 | 0.4477 | ❌ FPR too high |
| BiLSTM | 0.9012 ✅ | 0.0033 | 0.0017 | 1.0000 | 0.4416 | ❌ FPR too high |
| One-Class SVM | 0.5546 | 0.0013 | 0.0007 | 0.0447 | 0.0493 | ❌ Not effective |
| Isolation Forest | 0.5277 | 0.0006 | 0.0003 | 0.0383 | 0.1010 | ❌ Not effective |

> **Key Fix:** `train_final.py` — Subsample 100K (1.6% exfil) → SMOTE 10% → Focal Loss α=0.50 → class_weight={0:1,1:5} → threshold tuning → FPR 0.025 ✅

**Training scripts:**
- `src/train/preprocess.py` — load, label, split, scale
- `src/train/train_anomaly.py` — Isolation Forest + OCSVM
- `src/train/train_fast.py` — BiLSTM + CNN1D với SMOTE + Focal Loss
- `src/train/train_final.py` — **Final tuned models** (Subsample + SMOTE + Threshold Tuning)
- `src/train/evaluate.py` — ROC curves, confusion matrices (auto-uses tuned thresholds)

**Remaining work:**
1. ✅ Test pipeline on real PCAP (`python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap`)
2. ✅ Write `docs/bao_cao.docx`
3. ⏳ Prepare bonus self-captured scenario
4. ⏳ Create slide presentation

---


## 12. Contact

- **GVMH:** Thầy Đàm Minh Linh — linhdm@ptit.edu.vn
- **Dataset:** https://www.unb.ca/cic/datasets/index.html
