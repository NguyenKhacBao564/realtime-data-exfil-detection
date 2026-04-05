# PROGRESS.md — Project Tracking

> Last updated: 2026-04-04
> Project: HTTP Data Exfiltration Detection with AI + Multi-threading
> Supervisor: Thầy Đàm Minh Linh, MSc — linhdm@ptit.edu.vn

---

## Overall Progress

```
Phase 1  ████████████████████████ 100%   Setup + EDA ✅
Phase 2  ████████████████████████ 100%   Feature Engineering ✅
Phase 3  ████████████████████████ 100%   Multi-thread Pipeline ✅ (tested on PCAP ✅)
Phase 4  ████████████████████████ 100%   Model Training ✅ (incl. FPR fix ✅)
Phase 5  ████████████████████████ 100%   Evaluation ✅ (ROC, CM, threshold tuning ✅)
Phase 6  ████████████████░░░░░  70%   Report ✅ (bao_cao.docx) + Slides pending
────────────────────────────────────────────────────────────────────────
TOTAL     ███████████████░░░░░░  92%   ~6/14 weeks complete
```

---

## Phase 1 — Setup + Dataset Exploration

**Timeline:** Tuần 1-2
**Target:** Hiểu dataset, cài environment, notebook EDA hoàn chỉnh

### Tasks

- [ ] **1.1** Tạo virtual environment và cài đặt dependencies
  - `python -m venv venv && source venv/bin/activate`
  - `pip install -r requirements.txt`
  - Verify: `python -c "import scapy, pandas, sklearn, tensorflow; print('OK')"`

- [ ] **1.2** Setup Jupyter kernel cho notebooks
  - `pip install ipykernel && python -m ipykernel install --user --name=exfil-env`

- [ ] **1.3** Khám phá dataset — `notebooks/01_EDA.ipynb`
  - Load `CICIDS2017_ML-CVE/*.csv` — mỗi file
  - Shape, dtypes, memory usage
  - Label distribution (value_counts)
  - Phân tích: attack types nào có thể là proxy cho exfiltration?
  - **Decision:** Chọn file nào dùng làm normal, file nào dùng làm attack

- [ ] **1.4** Phân tích features trong CICFlowMeter CSV
  - List all columns
  - Identify HTTP-related columns (port, payload size, etc.)
  - Null values, infinities
  - Statistical summary

- [ ] **1.5** Explore Friday-WorkingHours.pcap (raw PCAP)
  - `tshark` hoặc `scapy` để xem cấu trúc
  - Số lượng packets, flows
  - Protocols seen

- [ ] **1.6** Thiết lập Git repository
  - `git init`
  - `.gitignore` (ignore `.pcap`, `*.h5`, `*.pkl`, `venv/`, `__pycache__/`, `data/processed/`)
  - Initial commit

### Deliverables
- [x] ✅ Project directory structure created
- [x] ✅ `notebooks/01_EDA.ipynb` — notebook đầy đủ với markdown + plots
- [x] ✅ `requirements.txt` — tested in new environment
- [x] ✅ Git repo initialized with `.gitignore`
- [x] ✅ All source code written (Phase 2 & 3 modules)

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Phase 2 — Feature Engineering & Preprocessing

**Timeline:** Tuần 3
**Target:** Gán nhãn exfiltration, tính custom features, tạo train/test split

### Tasks

- [ ] **2.1** Filter và merge dataset
  - Filter HTTP traffic: ports 80, 443, 8080, 8443 (hoặc dùng all flows)
  - Merge tất cả CSV files vào 1 DataFrame
  - Handle duplicate column names (có space prefix: `' Label'`, `' Flow Duration'`)

- [ ] **2.2** Gán nhãn exfiltration
  - Label 0 = Normal (Benign traffic)
  - Label 1 = Exfiltration
  - **Method:** Dùng Infilteration (Thursday-Afternoon) + custom heuristics:
    - High upload ratio (fwd_bytes >> bwd_bytes)
    - Long duration sessions
    - Burst pattern detection
    - Unusual destination ports
  - Document rationale trong notebook + báo cáo

- [ ] **2.3** Tính custom features (`src/features/window_features.py`)
  - `upload_download_ratio`
  - `burst_count`, `burst_ratio`
  - `unusual_port_ratio`
  - `inter_request_time_std`
  - `is_long_session`
  - `payload_entropy` (nếu có plaintext payload)

- [ ] **2.4** Implement `burst_exfil_score()` (`src/features/burst_exfil.py`)
  - Code function theo spec trong ARCHITECTURE.md
  - Test với known normal vs exfil samples

- [ ] **2.5** Train / Test / Validation split
  - 70% train, 15% test, 15% validation
  - Stratified by label (preserve class distribution)
  - Save: `data/processed/train.csv`, `test.csv`, `val.csv`

- [ ] **2.6** Standardization
  - `StandardScaler` fit trên train only
  - Save scaler: `models/scaler.pkl`
  - Apply to test/val

- [ ] **2.7** Chạy `notebooks/02_Feature_Engineering.ipynb`
  - Distribution plots cho mỗi feature (normal vs exfil)
  - Correlation matrix
  - Feature importance (nếu dùng Random Forest)

### Deliverables
- [x] ✅ `src/features/burst_exfil.py` — implemented
- [x] ✅ `src/features/window_features.py` — implemented
- [x] ✅ `data/processed/train.csv`, `test.csv`, `val.csv` — labeled (2.83M flows)
- [x] ✅ `models/scaler.pkl` — fitted (StandardScaler)
- [x] ✅ `notebooks/02_Feature_Engineering.ipynb` — written

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Phase 3 — Multi-Threaded Pipeline

**Timeline:** Tuần 4
**Target:** Pipeline chạy được offline trên PCAP

### Tasks

- [ ] **3.1** Viết `src/utils/config.py`
  - All configuration constants
  - Support offline/live mode toggle

- [ ] **3.2** Viết `src/utils/constants.py`
  - `HTTP_PORTS`, `BURST_THRESHOLD`, etc.
  - `COMMON_PORTS` list

- [ ] **3.3** Viết `src/capture/packet_parser.py`
  - Parse Scapy packet → dict
  - Handle malformed packets gracefully

- [ ] **3.4** Viết `src/capture/packet_capture.py`
  - Thread 1 entry point
  - `sniff()` with offline + live mode
  - `stop_event` integration

- [ ] **3.5** Viết `src/features/feature_aggregator.py`
  - Thread 2 entry point
  - Window buffer per src_ip
  - Flush logic (60s + on shutdown)

- [ ] **3.6** Viết `src/inference/alert_logger.py`
  - Thread-safe logging
  - RED alert formatting
  - Log rotation

- [ ] **3.7** Viết `src/inference/model_loader.py`
  - Load sklearn `.pkl` (Isolation Forest)
  - Load Keras `.h5` (BiLSTM/CNN) — separate path

- [ ] **3.8** Viết `src/inference/model_inference.py`
  - Thread 3 entry point
  - Predict + compute score + log

- [ ] **3.9** Viết `src/pipeline.py` (orchestration)
  - Start all threads
  - Monitor queue sizes (print every 1s)
  - KeyboardInterrupt → graceful shutdown
  - `python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap`

- [ ] **3.10** Benchmark: single-thread vs multi-thread
  - Time to process full PCAP (single vs 3 threads)
  - Speedup ratio
  - Queue depth over time

### Deliverables
- [x] ✅ `src/pipeline.py` — written and tested on real PCAP ✅
- [x] ✅ `exfil_detection.log` — generated on Friday-WorkingHours.pcap run
- [x] ✅ Pipeline tested: 3 threads working, alerts firing correctly
- [ ] ⏳ Benchmark results (speedup chart)
- [ ] ⏳ Unit tests

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Phase 4 — Model Training

**Timeline:** Tuần 5
**Target:** 4 trained models trong `models/`

### Tasks

- [ ] **4.1** Viết `src/train/preprocess.py`
  - Load `data/processed/train.csv`, `test.csv`, `val.csv`
  - Handle inf/nan values
  - Feature selection (remove constant columns)
  - Reshape for DL: `(N, 1, n_features)`

- [ ] **4.2** Train Isolation Forest (`src/train/train_anomaly.py`)
  - Train on NORMAL data only (label=0)
  - `contamination=0.05`, `n_estimators=200`
  - Evaluate on test set
  - Save: `models/isolation_forest.pkl`

- [ ] **4.3** Train One-Class SVM (`src/train/train_anomaly.py`)
  - `kernel='rbf'`, `gamma='scale'`, `nu=0.05`
  - Save: `models/oneclass_svm.pkl`
  - Note: OCSVM chậm — có thể dùng subsample

- [ ] **4.4** Train BiLSTM (`src/train/train_dl.py`)
  - Input shape: `(None, 1, n_features)`
  - Architecture: BiLSTM(64) → Dropout → BiLSTM(32) → Dense(64) → BN → Dense(1, sigmoid)
  - Optimizer: Adam, loss: binary_crossentropy
  - Callbacks: EarlyStopping(monitor='val_auc', patience=5), ModelCheckpoint
  - Save: `models/bilstm_model.h5`

- [ ] **4.5** Train CNN 1D (`src/train/train_dl.py`)
  - Input shape: `(None, 1, n_features)`
  - Architecture: Conv1D(64) → BN → Conv1D(32) → Flatten → Dense(64) → Dense(1, sigmoid)
  - Same optimizer/loss/callbacks
  - Save: `models/cnn1d_model.h5`

- [ ] **4.6** Model selection for pipeline
  - Chọn 1 model anomaly (recommend: Isolation Forest)
  - Chọn 1 model supervised (recommend: BiLSTM)
  - Update `src/utils/config.py` → `MODEL_PATH`

### Deliverables
- [x] ✅ `models/isolation_forest.pkl` — trained (AUC=0.5277 — poor, expected)
- [x] ✅ `models/oneclass_svm.pkl` — trained (AUC=0.5546 — poor, expected)
- [x] ✅ `models/bilstm_model.h5` — trained (AUC=0.9012 ✅ vượt target 0.90)
- [x] ✅ `models/cnn1d_model.h5` — trained (AUC=0.9423 ✅ vượt target 0.90, best model)
- [x] ✅ `models/cnn1d_final.h5` — retrained with FPR fix (AUC=0.9971, FPR=0.0245 ✅)
- [x] ✅ `models/bilstm_final.h5` — retrained with FPR fix (AUC=0.9966, FPR=0.0322 ✅)
- [x] ✅ Training logs / loss curves — saved in processed/

> **Key Result:** CNN1D Final đạt AUC=0.9971, FPR=0.0245 ✅ — mục tiêu FPR<5%, Recall≥85% đạt được! Chiến lược: Subsample 100K → SMOTE 10% → Focal α=0.50 → class_weight={0:1,1:5} → threshold tuning → optimal threshold=0.207

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Phase 5 — Evaluation & Comparison

**Timeline:** Tuần 6
**Target:** Bảng so sánh 4 models, ROC curves, kết luận

### Tasks

- [ ] **5.1** Viết `src/train/evaluate.py`
  - Compute: AUC-ROC, F1, Precision, Recall, FPR, Confusion Matrix
  - For all 4 models on test set
  - Save results to `data/processed/evaluation_results.json`

- [ ] **5.2** Vẽ ROC curves
  - 4 curves trên 1 plot
  - AUC labels
  - Save: `notebooks/roc_curves.png`

- [ ] **5.3** Vẽ confusion matrices
  - 2×2 grid cho mỗi model
  - Normalized + raw counts

- [ ] **5.4** So sánh anomaly vs supervised
  - Pros/cons table (theo spec topic.md §7.1)
  - Khi nào nên dùng cái nào?
  - burst_exfil_score: đóng góp bao nhiêu vào detection?

- [ ] **5.5** Performance analysis
  - Detection time distribution
  - Throughput (packets/sec)
  - Speedup multi-thread vs single-thread

- [ ] **5.6** Threshold sensitivity analysis
  - Vary burst_exfil_score threshold: 0.5, 0.6, 0.7, 0.8
  - Impact on F1 and FPR
  - Recommend optimal threshold

- [ ] **5.7** Chạy `notebooks/03_Model_Comparison.ipynb`
  - Tổng hợp tất cả plots và metrics
  - Markdown summary với kết luận

### Deliverables
- [x] ✅ `notebooks/02_Feature_Engineering.ipynb` — written
- [x] ✅ `notebooks/03_Model_Comparison.ipynb` — written with actual results
- [x] ✅ `notebooks/roc_curves.png` — generated
- [x] ✅ `notebooks/confusion_matrices.png` — generated
- [x] ✅ `data/processed/evaluation_results.json` — saved
- [x] ✅ `docs/metrics_report.md` — generated

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Phase 6 — Report + Bonus + Demo

**Timeline:** Tuần 7-8
**Target:** Báo cáo hoàn chỉnh, demo live, slide

### Tasks

- [ ] **6.1** Viết báo cáo `docs/bao_cao.docx`
  - Theo cấu trúc đề bài yêu cầu
  - Bao gồm: tổng quan, dataset, phương pháp, kết quả, kết luận
  - Bảng so sánh anomaly vs supervised
  - burst_exfil_score metric — justify thresholds

- [ ] **6.2** Bonus: Self-captured exfiltration scenario
  - Normal browsing 30 phút → capture background
  - Simulate exfil: upload file 50MB burst qua HTTP POST
  - Capture bằng tcpdump → `tcpdump -i en0 -w bonus_capture.pcap 'port 80'`
  - Extract features → test với trained models
  - Compare vs CICIDS2017 results
  - **Đây là cách ghi điểm cao nhất**

- [ ] **6.3** Chuẩn bị demo live
  - Chạy `python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap`
  - Highlight alerts trong console
  - Show log file

- [ ] **6.4** Chuẩn bị slide (~15-20 slides)
  - Cover: problem, dataset, features, pipeline, models, results, demo
  - Include screenshots của EDA plots, ROC curves

- [ ] **6.5** Backup lên GitHub
  - Tạo private repo
  - Push tất cả code + docs
  - Không push: `.pcap`, `.h5`, `.pkl`, `venv/`, `data/processed/`

### Deliverables
- [x] ✅ `docs/bao_cao.docx` — hoàn chỉnh (44KB, 8 sections, 7 tables)
- [ ] ⏳ `docs/bonus_capture/` — self-captured scenario (NOT STARTED)
- [ ] ⏳ Slide presentation (NOT STARTED)
- [ ] ⏳ GitHub repo (NOT STARTED)

### Notes / Blockers
> (Ghi lại issues, decisions, questions cho GVMH)

---

## Checkpoint History

| Date | Phase | Status | Notes |
|---|---|---|---|
| 2026-04-03 | Setup | ✅ | Project structure created, CLAUDE.md, ARCHITECTURE.md, PROGRESS.md written |
| 2026-04-04 | Code | ✅ | All source code written (Phase 1-3): capture, features, inference, pipeline modules |
| 2026-04-04 | Preprocessing | ✅ | 2.83M flows loaded, 67 features, 2,204 exfil (0.08%), scaler saved |
| 2026-04-04 | Anomaly Training | ✅ | IsolationForest (AUC=0.53), OCSVM (AUC=0.55) — poor, expected |
| 2026-04-04 | DL Training | ✅ | CNN1D AUC=0.9423 ✅, BiLSTM AUC=0.9012 ✅ |
| 2026-04-04 | Evaluation | ✅ | ROC curves, confusion matrices, metrics report done |
| 2026-04-04 | Blocking | ✅ | Pipeline tested on Friday-WorkingHours.pcap — 3 threads working, burst_exfil_score alerts firing correctly. Direction detection fixed, queue sizes increased to 50K/10K. |
| 2026-04-04 | Session | ✅ | Context loaded, checkpoint updated, next steps identified |
| 2026-04-05 | Training Fix | ✅ | train_final.py done: CNN1D AUC=0.9971/FPR=0.0245 ✅, BiLSTM AUC=0.9966/FPR=0.0322 ✅. evaluate.py updated to auto-use tuned thresholds. FPR target < 5% achieved! |
| | | | |

---

## Questions for GVMH

> Ghi câu hỏi ở đây để hỏi Thầy trong giờ học hoặc qua email (linhdm@ptit.edu.vn)

1. **Labeling:** CICIDS2017 không có label exfiltration rõ ràng. Phương pháp gán nhãn dùng Infilteration + heuristics có được chấp nhận không? Có nên tự gán label bằng cách nào khác không?
2. **HTTP traffic:** Có nên filter chỉ traffic port 80/443 không? Hay dùng tất cả flows?
3. **Deadline:** Thời hạn nộp báo cáo là khi nào?
4. **(Thêm câu hỏi của bạn ở đây)**

