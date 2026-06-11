# docs/IMPLEMENTATION_SUMMARY.md

# Implementation Summary — Teacher's Additional Requirements

> **Date:** 2026-06-01
> **Project:** HTTP Data Exfiltration Detection with AI + Multi-threading
> **Course:** Đồ án môn học — GVMH: Thầy Đàm Minh Linh

---

## 1. Teacher's Additional Requirements

The teacher requested two major additions to the existing project:

### Requirement A — Reproducible VM/Docker Lab Workflow

> *"Demo should not only be local loopback. Add a reproducible VM/Docker lab workflow for: real-time/live capture, offline PCAP replay, multi-threaded processing."*

**Delivered in:**
- `lab/docker-compose.yml` — defines all lab services
- `lab/server/receiver.py` — HTTP server with metadata-only logging
- `lab/victim/generate_http_traffic.py` — synthetic traffic generator
- `lab/monitor/Dockerfile` — containerised detection pipeline
- `scripts/capture_lab_pcap.sh` — live PCAP capture script
- `scripts/run_live_lab.sh` — live detection runner
- `scripts/run_offline_replay.sh` — offline PCAP replay runner
- `docs/VM_DOCKER_LAB_GUIDE.md` — setup guide

### Requirement B — Online Anomaly Detection for Unknown/New Patterns

> *"Add a mechanism for detecting unknown/new attack patterns that were not present in the offline-trained models. This should be an online/adaptive anomaly monitor based on runtime traffic statistics, not a heavy new deep learning model."*

**Delivered in:**
- `src/inference/online_anomaly_monitor.py` — Welford-based adaptive baseline monitor
- Modified `src/inference/model_inference.py` — wired into InferenceThread
- Modified `src/inference/alert_logger.py` — new alert fields
- Modified `src/utils/config.py` — new config constants
- Modified `src/pipeline.py` — new CLI flags
- `tests/unit/test_online_anomaly_monitor.py` — 30 unit tests
- `tests/integration/test_online_inference_integration.py` — 7 integration tests
- `docs/ONLINE_ANOMALY_DESIGN.md` — design rationale

---

## 2. What Changed — File-by-File

### 2.1 New Files Added

| File | Lines | Purpose |
|---|---|---|
| `src/inference/online_anomaly_monitor.py` | ~410 | WelfordStats, IPBaseline, OnlineAnomalyMonitor |
| `lab/docker-compose.yml` | ~80 | Docker Compose lab definition |
| `lab/server/receiver.py` | ~120 | HTTP server, metadata-only logging |
| `lab/victim/generate_http_traffic.py` | ~200 | Traffic generator with 3 modes |
| `lab/monitor/Dockerfile` | ~20 | Monitor container image |
| `lab/README.md` | ~150 | Lab usage guide |
| `scripts/capture_lab_pcap.sh` | ~80 | Live PCAP capture with auto iface detection |
| `scripts/run_live_lab.sh` | ~60 | Live detection runner |
| `scripts/run_offline_replay.sh` | ~60 | PCAP replay runner |
| `docs/VM_DOCKER_LAB_GUIDE.md` | ~200 | VM setup + Docker networking guide |
| `docs/ONLINE_ANOMALY_DESIGN.md` | ~250 | Online monitor design document |
| `docs/DEMO_SCRIPT.md` | ~250 | Full demo walkthrough |
| `docs/EVALUATION_PLAN.md` | ~250 | Metrics + evaluation plan |
| `tests/unit/test_online_anomaly_monitor.py` | ~320 | 30 unit tests |
| `tests/integration/test_online_inference_integration.py` | ~180 | 7 integration tests |

**Total new lines:** ~2,500+

### 2.2 Modified Files

| File | Change |
|---|---|
| `src/utils/config.py` | Added `ENABLE_ONLINE_MONITOR=False`, `ONLINE_THRESHOLD=0.5`, `ONLINE_WARMUP_WINDOWS=10` |
| `src/inference/alert_logger.py` | Added `online_score`, `online_prediction`, `online_reason_codes`, `baseline_count`, `alert_triggers` to `format_alert()`, `log_alert()`, `format_telegram_alert()` |
| `src/inference/model_inference.py` | Added `OnlineAnomalyMonitor` instantiation, `_process_window()` now calls `online_monitor.evaluate()`, tracks `online_anomalies` in stats |
| `src/pipeline.py` | Added `--enable-online-monitor`, `--online-threshold`, `--online-warmup-windows` CLI flags; passes to InferenceThread |
| `README.md` | Added Docker lab section, helper scripts section, online monitor section |
| `CLAUDE.md` | Updated status and file tracking |
| `src/train/extract_pcap_features.py` | Fixed pre-existing duplicate `all_lens` syntax error |

---

## 3. How Requirement B Is Satisfied

### 3.1 The Problem

The offline-trained models (CNN1D, BiLSTM, Isolation Forest, One-Class SVM) are trained on **historical data** (CICIDS2017). They can only detect patterns **similar to what they saw during training**. Any new attack technique not present in the training data will slip through.

### 3.2 The Solution: Online Anomaly Monitor

The online monitor is a **lightweight statistical detector** (no DL, no retraining) that:

1. **Builds a per-IP baseline** at runtime using Welford's numerically stable online algorithm
2. **Scores each window** against the learned baseline using z-score deviation
3. **Adapts continuously** — each normal window improves the baseline
4. **Does NOT update with anomalous windows** — prevents attacker from "training" the detector

```
Window → burst_exfil_score (rule-based, known patterns)
      → offline_model.predict() (ML, trained patterns)
      → online_monitor.evaluate() (adaptive, UNKNOWN patterns)

Alert fires if ANY is true:
  burst_score > 0.7  → BURST_RULE
  model.predict == 1 → OFFLINE_MODEL
  online_pred == 1   → ONLINE_UNKNOWN_ANOMALY
```

### 3.3 Why It's Not a "Heavy New Deep Learning Model"

| Approach | Memory | Compute | Retraining | Detects |
|---|---|---|---|---|
| CNN1D / BiLSTM | ~50MB+ | Per-window inference | Offline only | Known patterns in training data |
| **Online Anomaly Monitor** | ~2KB per IP | O(1) per window | Online (implicit) | **Any deviation from learned baseline** |

The online monitor uses only:
- **WelfordStats**: 3 floats per feature (`count`, `mean`, `m2`)
- **17 features** × 3 floats × 4 bytes = ~204 bytes per feature
- **17 features** per IP baseline = ~3.5KB per IP
- 1000 IPs = ~3.5MB total

**No GPU, no training loop, no gradient descent, no large model file.**

### 3.4 Alert Output Shows All Three Layers

```
━━━ EXFILTRATION ALERT ━━━
[CRITICAL]  2026-06-01 12:34:56
  Source IP:     172.28.0.2
  ── Triggers ──
  [BURST_RULE] Burst exfil score
  [ONLINE_UNKNOWN_ANOMALY] Online anomaly (unknown pattern)
  ── Scores ──
  Burst score:   0.800
  Online score:  0.723  (ANOMALY)
  Baseline n:   15
    HIGH_Z: upload_download_ratio=4.7σ
    HIGH_Z: burst_count=3.2σ
━━━━━━━━━━━━━━━━━━━━━━━━
```

The `[Triggers]` section explicitly shows which detection layer fired. `HIGH_Z` lines explain **why** the online monitor flagged the traffic.

---

## 4. Step-by-Step Demo Instructions

### 4.1 Setup (One-Time)

**On MacBook M:** Create Ubuntu ARM64 VM with UTM (see `docs/VM_DOCKER_LAB_GUIDE.md`).

Inside the VM:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo apt install docker-compose

# Clone the project
git clone https://github.com/yourusername/realtime-data-exfil-detection.git
cd realtime-data-exfil-detection

# Verify the code
python -m compileall src lab scripts tests
pytest tests/unit/test_online_anomaly_monitor.py tests/integration/test_online_inference_integration.py -v
# Expected: 37 passed
```

### 4.2 Start the Lab

```bash
cd lab/
docker-compose build
docker-compose up -d

# Verify all services are running
docker-compose ps
# Should show: exfil-server, victim-client, monitor-detector
```

### 4.3 Demo Phase 1: Normal Traffic (5 min)

**Purpose:** Establish a baseline for the online monitor to learn from.

```bash
# In a new terminal:
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode normal \
    --server http://exfil-server:8000 \
    --duration 120
```

**Expected:** Regular HTTP requests, small payloads, irregular timing. No alerts should fire.

**Talk track:**
- "Normal browsing has irregular timing (0.5-5 seconds between requests)"
- "Small payloads (100B–2KB)"
- "Server logs only metadata — timestamp, source IP, content length"
- "The online monitor is building a baseline for source IP 172.28.0.2"

### 4.4 Demo Phase 2: Simulated Exfiltration (5 min)

**Purpose:** Demonstrate that burst exfiltration is detected by burst rules.

```bash
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode exfil \
    --server http://exfil-server:8000 \
    --duration 30
```

**Expected:** Burst of large uploads (50KB–500KB), rapid requests (0.05–0.3s intervals). `BURST_RULE` should fire.

**Talk track:**
- "This simulates an attacker exfiltrating data via HTTP POST"
- "The traffic generator sends large payloads in rapid succession"
- "Notice the burst pattern — automated tool vs human browsing"
- "burst_exfil_score > 0.7 fires `BURST_RULE`"

### 4.5 Demo Phase 3: Live Detection with Online Monitor (5 min)

**Purpose:** Show the full pipeline running with online monitoring.

```bash
docker-compose exec monitor-detector bash

# Inside the container:
python3 -u src/pipeline.py \
  --live \
  --iface eth0 \
  --enable-online-monitor \
  --online-warmup-windows 5 \
  --debug
```

**Talk track:**
- "The pipeline has 3 threads running in parallel"
- "Thread 1 captures packets from eth0"
- "Thread 2 aggregates features per 60-second window"
- "Thread 3 runs burst rules, offline model, AND online monitor"
- "The online monitor has learned the normal baseline during Phase 1"

### 4.6 Demo Phase 4: Slow-Drip Anomaly (5 min)

**Purpose:** Show that the online monitor catches patterns that bypass burst rules.

```bash
# While the detector is still running:
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode slow-drip \
    --server http://exfil-server:8000 \
    --duration 120
```

**Expected:** Small regular uploads (5–15KB every 2–4 seconds). `burst_score` may stay < 0.7, but `ONLINE_UNKNOWN_ANOMALY` should fire.

**Talk track:**
- "Slow-drip is designed to evade threshold-based detection"
- "Small payloads (5-15KB) don't trigger the burst rule"
- "But the online monitor detects this as a deviation from the learned baseline"
- "The server sent regular requests every 2-4 seconds — that's not normal browsing"
- "This is why the online monitor is critical — it catches unknown patterns"

### 4.7 Demo Phase 5: Offline PCAP Replay (3 min)

```bash
# Capture traffic from any of the above phases:
sudo ./scripts/capture_lab_pcap.sh eth0 60 lab/captures/demo.pcap

# Replay with full detection:
./scripts/run_offline_replay.sh lab/captures/demo.pcap --online-monitor
```

### 4.8 Demo Phase 6: Compare All Detection Layers (5 min)

```bash
# Run with all three detection layers:
python3 src/pipeline.py \
  --offline \
  --pcap lab/captures/demo.pcap \
  --enable-online-monitor \
  --online-warmup-windows 10 \
  --debug
```

**Expected final output:**
```
━━━ EXFILTRATION ALERT ━━━
[CRITICAL] ...
  ── Triggers ──
  [BURST_RULE] Burst exfil score
  [ONLINE_UNKNOWN_ANOMALY] Online anomaly (unknown pattern)
  ── Scores ──
  Burst score:   0.800
  Online score:  0.723  (ANOMALY)
    HIGH_Z: upload_download_ratio=4.7σ
    HIGH_Z: burst_count=3.2σ
━━━━━━━━━━━━━━━━━━━━━━━━

FINAL STATISTICS
[INFERENCE]  processed=47  alerts=12  online_anomalies=5
[ONLINE]     baselines=3  windows_processed=47
```

---

## 5. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Docker Compose Lab (172.28.0.0/16)                 │
│                                                                      │
│  victim-client ──HTTP POST──→ exfil-server                           │
│       │                       (logs metadata only)                    │
│       │                                                                 │
│       └────── tcpdump ────────────→ monitor-detector                 │
│                                ┌────────────────────┐                 │
│                                │ Detection Pipeline  │                 │
│                                │                    │                 │
│                                │ Thread 1: Capture  │                 │
│                                │ Thread 2: Features │                 │
│                                │ Thread 3: Inference│                 │
│                                │  ├── burst_score  │ (rule-based)   │
│                                │  ├── model.predict │ (CNN1D/BiLSTM) │
│                                │  └── online_monitor│ (adaptive)      │
│                                └────────────────────┘                 │
└──────────────────────────────────────────────────────────────────────┘

Alert fires if ANY:
  burst_score > 0.7     → BURST_RULE
  model.predict == 1    → OFFLINE_MODEL
  online_pred == 1     → ONLINE_UNKNOWN_ANOMALY
```

---

## 6. Safety Boundaries

All lab components are designed for **academic simulation only**:

| What IS generated | What is NOT generated |
|---|---|
| Random hex bytes as payloads | Real user files |
| Lorem ipsum text as payloads | Credentials or secrets |
| Synthetic session IDs | SSH keys or tokens |
| Metadata logging (timestamps, sizes) | Payload content storage |

The `receiver.py` server **discards all payload content immediately** after reading. Only metadata is logged.

---

## 7. Key Design Decisions Explained

### 7.1 Why Welford's Algorithm?

Naive mean/variance requires storing all values. Welford updates in O(1) with O(1) memory:

```python
# Welford update (numerically stable):
count += 1
delta = x - mean
mean += delta / count
m2 += delta * (x - mean)    # sum of squared deviations
variance = m2 / count
```

This is thread-safe per IP and works in streaming settings.

### 7.2 Why Per-IP Baselines?

Different hosts have different normal traffic profiles:
- A backup server may legitimately send large uploads
- A developer workstation may have different request rates
- A database server may have different patterns than a browser

Per-IP baselines prevent "normal for server A" from triggering for server B.

### 7.3 Why Not Update Baseline with Anomalous Windows?

If an attacker learns that their traffic is being scored, they could send a mix of normal and attack traffic, gradually "normalising" the baseline. By excluding anomalous windows from the baseline, the monitor remains robust against this attack.

### 7.4 Why Weighted Features?

Not all features are equally discriminative for exfiltration:

| Feature | Weight | Rationale |
|---|---|---|
| `upload_download_ratio` | **2.0** | Primary exfil signal — attackers upload more |
| `burst_count`, `burst_ratio`, `unusual_port_ratio` | **1.5** | Automation + stealth signals |
| `request_rate`, `inter_request_time_std` | 1.0 | Machine vs human |
| `total_fwd_bytes`, `total_bytes` | 1.0 | Volume anomaly |
| `ack_flag_count`, `syn_flag_count`, `window_duration` | 0.0 | Not discriminative for exfil |

### 7.5 Why Opt-In (Not On by Default)?

The online monitor requires **normal traffic** during the warmup period. In a pure attack dataset (no normal traffic), the monitor would flag every window as anomalous. Users should enable `--enable-online-monitor` only when they can provide initial normal traffic.

---

## 8. Backward Compatibility

All existing commands continue to work exactly as before:

```bash
# Old command — still works:
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap

# Old command — still works:
sudo python src/pipeline.py --live --iface lo0

# New command — adds online monitor:
python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap \
  --enable-online-monitor --online-threshold 0.5 --online-warmup-windows 10
```

If `--enable-online-monitor` is not specified, the behavior is **identical to before** — the online monitor returns safe defaults and the pipeline uses only burst rules + offline model.

---

## 9. Verification Commands

```bash
# 1. Syntax check all files
python -m compileall src lab scripts tests

# 2. Run unit + integration tests
pytest tests/unit/test_online_anomaly_monitor.py \
       tests/integration/test_online_inference_integration.py -v
# Expected: 37 passed

# 3. Verify CLI shows new flags
python src/pipeline.py --help | grep online
# Expected: --enable-online-monitor, --online-threshold, --online-warmup-windows

# 4. Verify online monitor standalone
python -c "from src.inference.online_anomaly_monitor import OnlineAnomalyMonitor; m = OnlineAnomalyMonitor(enabled=True); print(m.evaluate({'src_ip': '127.0.0.1', 'request_count': 10, 'total_fwd_bytes': 1000, 'total_bwd_bytes': 500, 'total_bytes': 1500, 'upload_download_ratio': 2.0, 'burst_count': 5, 'burst_ratio': 0.5, 'unusual_port_ratio': 0.1, 'request_rate': 1.0, 'inter_request_time_mean': 1.0, 'inter_request_time_std': 0.5, 'mean_payload_size': 100.0, 'std_payload_size': 50.0, 'psh_flag_count': 5, 'ack_flag_count': 10, 'syn_flag_count': 1, 'window_duration': 10.0})); print('OK')"
# Expected: {'online_score': 0.0, 'online_prediction': 0, 'reason_codes': [...], 'baseline_count': 0}

# 5. Docker lab health check
docker-compose -f lab/docker-compose.yml config
# Expected: Valid YAML with 3 services
```
