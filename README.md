# HTTP Data Exfiltration Detection with AI + Multi-threading

**Đồ án môn học** — GVMH: Thầy Đàm Minh Linh, MSc
Học viện Công nghệ Bưu Chính Viễn Thông — CS TP.HCM

---

## Mục tiêu

Nhận biết hành vi rò rỉ dữ liệu (Data Exfiltration) qua HTTP/HTTPS dựa trên thống kê lưu lượng và dấu hiệu bất thường ở tầng ứng dụng, hoạt động real-time với pipeline đa luồng.

---

## Kiến trúc

```
Thread 1: Packet Capture ──→ Thread 2: Feature Aggregation ──→ Thread 3: Inference
   (Scapy sniff)                (60s window / IP)              (AI model + Alert)
```

**4 mô hình ML:**
- Anomaly-based: **Isolation Forest**, **One-Class SVM**
- Supervised: **BiLSTM**, **CNN 1D**

---

## Cài đặt

```bash
# Clone repo
git clone <repo-url>
cd Exfiltration

# Tạo virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Cài dependencies
pip install -r requirements.txt

# Setup Jupyter kernel
python -m ipykernel install --user --name=exfil-env
```

---

## Cấu trúc thư mục

```
Exfiltration/
├── CLAUDE.md              ← Claude Code reference
├── ARCHITECTURE.md        ← Pipeline design chi tiết
├── PROGRESS.md            ← Track tiến độ dự án
├── README.md
├── requirements.txt
│
├── data/
│   ├── raw/               ← CICIDS2017 CSV + PCAP files
│   │   ├── CICIDS2017_ML-CVE/         # Dùng huấn luyện
│   │   ├── CICIDS2017_TrafficLabelling_Original/  # Tham khảo
│   │   └── Friday-WorkingHours.pcap
│   └── processed/         ← Features đã xử lý, train/test split
│
├── models/                ← Trained models (.pkl, .h5)
│
├── src/
│   ├── capture/           ← Thread 1: packet capture
│   ├── features/          ← Thread 2: feature extraction
│   ├── inference/         ← Thread 3: model inference
│   ├── train/             ← Training scripts
│   └── utils/             ← Config, constants, helpers
│
├── notebooks/
│   ├── 01_EDA.ipynb              ← Dataset exploration
│   ├── 02_Feature_Engineering.ipynb  ← Feature analysis
│   └── 03_Model_Comparison.ipynb ← Results comparison
│
├── tests/
│   ├── unit/              ← Unit tests
│   └── integration/        ← Integration tests
│
└── docs/
    └── bao_cao.docx       ← Báo cáo cuối kỳ
```

---

## Chạy Pipeline

### Offline (trên PCAP file)

```bash
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap --model models/isolation_forest.pkl
```

### Live (trên network interface)

```bash
sudo python src/pipeline.py --live --iface eth0 --model models/isolation_forest.pkl
```

> ⚠️ Live capture cần chạy với `sudo` (root privileges) vì Scapy cần raw socket access.

---

## Huấn luyện Model

```bash
# Anomaly-based (Isolation Forest + OCSVM)
python src/train/train_anomaly.py

# Supervised (BiLSTM + CNN1D)
python src/train/train_dl.py
```

---

## Đánh giá

```bash
python src/train/evaluate.py --models models/isolation_forest.pkl models/cnn1d_model.h5
```

Metrics: AUC-ROC, F1-Score, FPR, Precision, Recall, Detection Time, Throughput.

---

## Dataset

| Source | Location | Mô tả |
|---|---|---|
| CICIDS2017 (ML-CVE) | `data/raw/CICIDS2017_ML-CVE/` | 8 CSV files, đã trích xuất features bằng CICFlowMeter. **Dùng để huấn luyện.** |
| CICIDS2017 (Original) | `data/raw/CICIDS2017_TrafficLabelling_Original/` | Bản gốc — tham khảo |
| Friday-WorkingHours.pcap | `data/raw/` | Raw packet capture |

**Source:** https://www.unb.ca/cic/datasets/index.html

---

## Key Files

| File | Mô tả |
|---|---|
| `src/features/burst_exfil.py` | `burst_exfil_score()` metric |
| `src/features/window_features.py` | Feature extraction per window |
| `src/pipeline.py` | Main orchestrator — 3 threads |
| `src/train/train_anomaly.py` | Isolation Forest + OCSVM |
| `src/train/train_dl.py` | BiLSTM + CNN1D |

---

## Contact

- **GVMH:** Thầy Đàm Minh Linh — linhdm@ptit.edu.vn
- **Supervisor:** CS TP.HCM, Học viện Công nghệ Bưu Chính Viễn Thông
