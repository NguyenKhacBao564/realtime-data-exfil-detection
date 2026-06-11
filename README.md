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

**Online Anomaly Monitor:** Welford-based adaptive baseline per source IP — detects unknown/new attack patterns at runtime, complementing the offline-trained models.

**Lab Environment:** Docker Compose lab with synthetic HTTP traffic generator — normal browsing, burst exfil, slow-drip scenarios.

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

## Chạy Pipeline với Online Monitor

```bash
# Offline mode với online anomaly monitor:
python src/pipeline.py \
  --offline \
  --pcap data/raw/Friday-WorkingHours.pcap \
  --enable-online-monitor \
  --online-threshold 0.5 \
  --online-warmup-windows 10

# Live mode với online monitor:
sudo python src/pipeline.py \
  --live \
  --iface eth0 \
  --enable-online-monitor \
  --online-warmup-windows 5
```

> Online monitor mặc định **disabled**. Bật với `--enable-online-monitor` để phát hiện unknown/novel attack patterns.

## Chạy Pipeline (cơ bản)

### Offline (trên PCAP file)

```bash
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap --model models/isolation_forest.pkl
```

### Live (trên network interface)

```bash
sudo -E /opt/miniconda3/envs/exfil/bin/python src/pipeline.py \
  --live \
  --iface lo0 \
  --window-size 10 \
  --burst-threshold 0.7
```

> ⚠️ Live capture cần chạy với `sudo` (root privileges) vì Scapy cần raw socket access.

### Telegram alert (tùy chọn)

Tạo file `.env.local` từ `.env.example`, điền token/chat id thật, rồi chạy pipeline. File `.env.local` đã bị `.gitignore` chặn commit.

```bash
cp .env.example .env.local
chmod 600 .env.local
# sửa TELEGRAM_BOT_TOKEN và TELEGRAM_CHAT_ID trong .env.local
```

Pipeline tự load `.env.local`; khi dùng `sudo`, có thể thêm `-E` nếu bạn export biến môi trường thủ công.

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

## Tải Data & Models

> ⚠️ File data và trained models **quá lớn** cho GitHub (~900MB).
> Download từ **Google Drive**: `[Link Google Drive]`

Sau khi tải, giải nén vào thư mục gốc:

```
Exfiltration/
├── data/
│   ├── raw/CICIDS2017_ML-CVE/*.csv     ← 8 file CSV
│   └── processed/
│       ├── train.csv, test.csv, val.csv
│       ├── *.npy
│       └── evaluation_results.json
└── models/
    ├── scaler.pkl
    ├── isolation_forest.pkl
    ├── oneclass_svm.pkl
    ├── bilstm_model.h5
    └── cnn1d_model.h5
```

Hoặc tự download CICIDS2017 từ: https://www.unb.ca/cic/datasets/ids-2017.html

---

## Key Files

| File | Mô tả |
|---|---|
| `src/features/burst_exfil.py` | `burst_exfil_score()` metric |
| `src/features/window_features.py` | Feature extraction per window |
| `src/inference/online_anomaly_monitor.py` | **NEW** — Welford-based adaptive anomaly detector |
| `src/pipeline.py` | Main orchestrator — 3 threads |
| `src/train/train_anomaly.py` | Isolation Forest + OCSVM |
| `src/train/train_dl.py` | BiLSTM + CNN1D |

## Docker Lab (Xem chi tiết: `lab/README.md`)

Lab này tạo môi trường cô lập với Docker Compose cho demo:

```bash
cd lab/

# Khởi động lab:
docker-compose up -d

# Tạo traffic bình thường:
docker-compose run --rm victim-client \
  python3 /generate.py --mode normal --server http://exfil-server:8000 --duration 60

# Tạo traffic giả lập exfiltration:
docker-compose run --rm victim-client \
  python3 /generate.py --mode exfil --server http://exfil-server:8000 --duration 30

# Tạo slow-drip anomaly:
docker-compose run --rm victim-client \
  python3 /generate.py --mode slow-drip --server http://exfil-server:8000 --duration 60

# Chạy detector trong container:
docker-compose exec monitor-detector \
  python3 -u src/pipeline.py --live --iface eth0 --enable-online-monitor

# Dừng lab:
docker-compose down
```

**MacBook M users:** Chạy Ubuntu ARM64 VM với UTM/VMware Fusion. Xem `docs/VM_DOCKER_LAB_GUIDE.md` để biết chi tiết.

## Helper Scripts

```bash
# Live capture + detect (cần sudo):
sudo ./scripts/run_live_lab.sh eth0 --online-monitor

# Offline PCAP replay:
./scripts/run_offline_replay.sh lab/captures/demo.pcap --online-monitor

# Capture PCAP:
sudo ./scripts/capture_lab_pcap.sh eth0 60
```

## Documentation

| File | Mô tả |
|---|---|
| `docs/VM_DOCKER_LAB_GUIDE.md` | Hướng dẫn setup VM + Docker lab |
| `docs/ONLINE_ANOMALY_DESIGN.md` | Chi tiết thiết kế online anomaly monitor |
| `docs/DEMO_SCRIPT.md` | Script demo đầy đủ (~30-45 phút) |
| `docs/EVALUATION_PLAN.md` | Kế hoạch đánh giá + metrics |
| `docs/IMPLEMENTATION_SUMMARY.md` | Tổng hợp thay đổi + hướng dẫn demo |

---

## Contact

- **GVMH:** Thầy Đàm Minh Linh — linhdm@ptit.edu.vn
- **Supervisor:** CS TP.HCM, Học viện Công nghệ Bưu Chính Viễn Thông
