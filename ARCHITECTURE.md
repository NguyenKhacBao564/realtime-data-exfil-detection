# ARCHITECTURE.md — Multi-Threaded Pipeline Design

> Thiết kế chi tiết pipeline đa luồng phát hiện Data Exfiltration.

---

## 1. High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      MAIN PROCESS                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ stop_event = threading.Event()  (graceful shutdown)        │   │
│  │ packet_queue  = Queue(maxsize=10000)                       │   │
│  │ feature_queue = Queue(maxsize=1000)                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌────────────┐  raw packets  ┌────────────┐  features  ┌──────┴──┐  │
│  │ THREAD 1   │ ─────────────→ │ THREAD 2   │ ──────────→ │ THREAD 3 │  │
│  │ Capture    │               │ Feature    │            │Inference │  │
│  │            │               │ Aggregation│            │+ Logging │  │
│  │ Scapy sniff│               │ 60s window │            │          │  │
│  └────────────┘               └────────────┘            └─────────┘  │
│        │                            │                           │      │
│        ↓                            ↓                           ↓      │
│  packet_queue               feature_queue                  exfil_     │
│  (→10000)                   (→1000)                      detection.log │
│                                                                 console │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Thread Specifications

### 2.1 Thread 1 — Packet Capture (`src/capture/`)

**File:** `src/capture/packet_capture.py`

**Responsibility:** Sniff packets từ network interface hoặc PCAP file, extract relevant fields, đẩy vào `packet_queue`.

**Packet dict schema:**
```python
{
    'timestamp': float,          # Unix timestamp
    'src_ip': str,                # e.g. '192.168.1.100'
    'dst_ip': str,
    'src_port': int,
    'dst_port': int,             # Filter: 80, 443, 8080, 8443
    'payload_len': int,          # TCP payload bytes
    'flags': str,                # TCP flags string
    'pkt_len': int,              # Total packet size
    'protocol': str,             # 'TCP', 'UDP', etc.
}
```

**Filter logic:**
```
TCP ports ∈ {80, 443, 8080, 8443}
OR any port if HTTP payload inspection is enabled
```

**Queue overflow:** Log warning (`logging.warning`) → skip packet (do NOT block pipeline).

**Modes:**
| Mode | Config |
|---|---|
| Offline PCAP | `PCAP_FILE='data/raw/Friday-WorkingHours.pcap'`, `OFFLINE=True` |
| Live interface | `CAPTURE_IFACE='eth0'`, `OFFLINE=False` |

**Stop condition:** `stop_event.is_set()` OR EOF on PCAP.

---

### 2.2 Thread 2 — Feature Aggregation (`src/features/`)

**File:** `src/features/feature_aggregator.py`

**Responsibility:** Buffer raw packets per source IP into 60-second windows. Flush window → extract feature vector → push to `feature_queue`.

**Window buffer structure:**
```python
window_buffer: Dict[str, List[PacketDict]]
# key = src_ip, value = list of packets in current window
```

**Flush logic:**
- Every `WINDOW_SIZE` seconds (wall-clock)
- OR when `stop_event` is set (flush remaining)

**Skip rule:** If `len(flows) < 3` for an IP → skip (too few packets = noise).

**Feature vector schema:**
```python
{
    # Packet-level
    'mean_payload_size': float,
    'max_payload_size': float,
    'std_payload_size': float,
    'total_bytes': int,
    'request_count': int,

    # Window-level
    'request_rate': float,           # requests / second
    'inter_req_mean': float,
    'inter_req_std': float,
    'inter_req_min': float,
    'inter_req_max': float,

    # Upload/download
    'upload_ratio': float,            # fwd_bytes / total_bytes
    'total_fwd_bytes': int,
    'total_bwd_bytes': int,

    # Burst detection
    'burst_count': int,               # inter_arrival < 0.1s
    'burst_ratio': float,             # burst_count / len(inter_times)

    # Destination diversity
    'unique_destinations': int,
    'unusual_port_ratio': float,      # ports not in common_ports

    # Temporal
    'window_duration': float,         # seconds

    # Meta
    'src_ip': str,
    'window_start': float,
}
```

**Custom features (burst_exfil.py):**
```python
burst_exfil_score = 0.0
if upload_download_ratio > 2.0:       score += 0.30
if burst_count > 10:                   score += 0.25
if unusual_port_ratio > 0.5:          score += 0.20
if inter_request_time_std < 0.05:      score += 0.25
return min(score, 1.0)
```

---

### 2.3 Thread 3 — Inference + Logging (`src/inference/`)

**File:** `src/inference/model_inference.py`

**Responsibility:** Load trained model at startup, predict per window, compute `burst_exfil_score`, log results.

**Startup sequence:**
1. `joblib.load('models/isolation_forest.pkl')` OR `keras.models.load_model('models/bilstm_model.h5')`
2. `joblib.load('models/scaler.pkl')` — standardize features
3. Warm up: run 1 dummy prediction to verify model works

**Prediction flow:**
```python
feature_vec = extract_feature_vector(features)   # order columns
X = scaler.transform([feature_vec])             # standardize
pred = model.predict(X)[0]                       # 0=normal, 1=anomaly

# burst_exfil_score is computed from raw features
score = burst_exfil_score(features)

# Alert condition
if pred == 1 or score > 0.7:
    log_ALERT(features, pred, score)
else:
    log_INFO(features, score)
```

**Alert format (logged + printed in red):**
```
2026-04-03 12:00:00 WARNING - ALERT: Potential exfiltration from 192.168.1.100
  | Score: 0.75 | Requests: 45 | Burst ratio: 0.82 | Upload ratio: 3.2
  | Destinations: 3 | Window: 170×10^9 → 170×10^9
```

**Graceful shutdown:** Drain `feature_queue` before exiting.

---

## 3. Queue Design

| Queue | Type | Max Size | Overflow Strategy | Consumer |
|---|---|---|---|---|
| `packet_queue` | `queue.Queue` | 10000 | Log warning, skip packet | Thread 2 |
| `feature_queue` | `queue.Queue` | 1000 | Log warning, skip window | Thread 3 |

**Rationale:**
- `packet_queue` large because packets arrive faster than features can be extracted
- `feature_queue` smaller because features are computed less frequently (per window)
- Overflow = warning + drop (never block producer) to maintain real-time throughput

---

## 4. Stop & Shutdown Protocol

```
1. User presses Ctrl+C → KeyboardInterrupt in main()
2. main() sets stop_event.set()
3. All threads receive stop_event via stop_filter (Thread 1) or check in loop (Thread 2, 3)
4. Thread 1: stops sniff() via stop_filter
5. Thread 2: flushes remaining window_buffer → feature_queue, then exits
6. Thread 3: drains feature_queue → processes remaining, then exits
7. All threads join(timeout=5) in main()
8. Log: "Pipeline stopped gracefully."
```

---

## 5. Module Structure

```
src/
├── __init__.py
├── capture/
│   ├── __init__.py
│   ├── packet_capture.py      # Thread 1: sniff() + callback
│   ├── packet_parser.py       # Parse Scapy packet → dict
│   └── http_inspector.py      # HTTP header parsing (if plaintext)
│
├── features/
│   ├── __init__.py
│   ├── feature_aggregator.py  # Thread 2: window buffer + flush
│   ├── window_features.py    # extract_all_features()
│   └── burst_exfil.py         # burst_exfil_score()
│
├── inference/
│   ├── __init__.py
│   ├── model_inference.py     # Thread 3: predict + alert
│   ├── model_loader.py        # Load .pkl / .h5
│   └── alert_logger.py        # Formatting + file/console logging
│
├── train/
│   ├── __init__.py
│   ├── train_anomaly.py       # Isolation Forest + OCSVM
│   ├── train_dl.py            # BiLSTM + CNN1D
│   └── preprocess.py          # EDA, filter, label assignment
│
└── utils/
    ├── __init__.py
    ├── config.py              # WINDOW_SIZE, QUEUE_SIZES, etc.
    ├── constants.py           # HTTP_PORTS, BURST_THRESHOLD, etc.
    └── helpers.py             # Logging setup, etc.
```

---

## 6. Configuration (`src/utils/config.py`)

```python
# ===== CAPTURE =====
CAPTURE_IFACE = None        # None = offline, 'eth0' = live
PCAP_FILE = 'data/raw/Friday-WorkingHours.pcap'
OFFLINE_MODE = True
HTTP_PORTS = [80, 443, 8080, 8443]

# ===== PIPELINE =====
WINDOW_SIZE = 60             # seconds
MIN_PACKETS_PER_WINDOW = 3  # skip IPs with fewer
PACKET_QUEUE_SIZE = 10000
FEATURE_QUEUE_SIZE = 1000

# ===== INFERENCE =====
MODEL_PATH = 'models/isolation_forest.pkl'   # swappable
SCALER_PATH = 'models/scaler.pkl'
BURST_EXFIL_THRESHOLD = 0.7

# ===== LOGGING =====
LOG_FILE = 'exfil_detection.log'
LOG_LEVEL = 'INFO'           # DEBUG for development
```

---

## 7. Performance Considerations

1. **Scapy `store=False`**: Never store packets in memory — process and discard immediately.
2. **Queue bypass**: If `packet_queue` is full, log and skip (don't block capture).
3. **Feature extraction batching**: Thread 2 processes all IPs in one flush cycle to amortize overhead.
4. **Model inference caching**: Load model once at startup, not per prediction.
5. **NumPy vectorized**: All feature computations use NumPy — no Python loops over packet lists.
6. **Thread-safe logging**: Use Python's `logging` module (already thread-safe) — not print().

---

## 8. Testing Strategy

| Test | File | What |
|---|---|---|
| Unit: packet parser | `tests/unit/test_packet_parser.py` | Scapy pkt → dict |
| Unit: feature extraction | `tests/unit/test_features.py` | Feature vector correctness |
| Unit: burst_exfil_score | `tests/unit/test_burst_exfil.py` | Score thresholds |
| Integration: offline pipeline | `tests/integration/test_pipeline_offline.py` | End-to-end on PCAP |
| Integration: model inference | `tests/integration/test_inference.py` | Model loading + predict |
