# docs/EVALUATION_PLAN.md

# Evaluation Plan — Exfiltration Detection Pipeline

## 1. Metrics Overview

| Category | Metric | Target | How to Measure |
|---|---|---|---|
| **Detection** | AUC-ROC | > 0.90 (supervised) | `src/train/evaluate.py` |
| **Detection** | F1-Score | Maximize | `sklearn.metrics.f1_score` |
| **Detection** | False Positive Rate | < 5% | `FP / (FP + TN)` |
| **Detection** | Precision | > 0.80 | `TP / (TP + FP)` |
| **Detection** | Recall | > 0.85 | `TP / (TP + FN)` |
| **Timing** | Detection Time | < 5s from exfil start | Window timestamps |
| **Throughput** | Packets/sec processed | Maximize | Benchmark |
| **Pipeline** | Queue sizes | < 80% capacity | `pipeline.py --debug` |
| **Pipeline** | Windows processed/sec | > 10 wps | `inference.get_stats()` |
| **Online** | Baseline convergence | Warmup < 10 windows | `online_monitor.get_stats()` |
| **Online** | Unknown pattern recall | Depends on traffic | Lab demo |

---

## 2. Offline Model Evaluation (CICIDS2017)

### 2.1 Setup

```bash
cd src/train/
python evaluate.py --model cnn1d --output results/
python evaluate.py --model bilstm --output results/
python evaluate.py --model isolation_forest --output results/
```

### 2.2 Expected Results (from CLAUDE.md)

| Model | AUC-ROC | F1 | Precision | Recall | FPR |
|---|---|---|---|---|---|
| CNN1D (tuned) | **0.9971** | 0.0567 | 0.0292 | 1.0000 | **0.0245** |
| BiLSTM (tuned) | **0.9966** | 0.0438 | 0.0224 | 1.0000 | **0.0322** |
| One-Class SVM | 0.5546 | 0.0013 | 0.0007 | 0.0447 | 0.0493 |
| Isolation Forest | 0.5277 | 0.0006 | 0.0003 | 0.0383 | 0.1010 |

### 2.3 Why F1 is Low Despite High AUC

The CICIDS2017 dataset has **extreme class imbalance** (~0.07% exfil flows). AUC measures ranking quality (discrimination power), which is excellent. F1 measures per-class accuracy, which is limited by the threshold. Threshold tuning (from 0.5 → optimal threshold) improved FPR from 0.45 → 0.025, demonstrating the importance of threshold tuning for deployment.

---

## 3. Online Anomaly Monitor Evaluation

### 3.1 Baseline Warmup Test

```python
# In tests/unit/test_online_anomaly_monitor.py:
def test_warmup_does_not_score():
    monitor = OnlineAnomalyMonitor(
        enabled=True,
        warmup_min_windows=10,
    )
    for i in range(9):
        result = monitor.evaluate({"src_ip": "10.0.0.1", **normal_features})
        assert result["online_prediction"] == 0  # No scoring during warmup

    # After warmup, scoring begins
    result = monitor.evaluate({"src_ip": "10.0.0.1", **normal_features})
    assert "warmup" not in result["reason_codes"][0]  # warmup complete
```

### 3.2 Normal Window Updates Baseline

```python
def test_normal_updates_baseline():
    monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=3)

    # Feed 3 normal windows
    for _ in range(3):
        monitor.evaluate({"src_ip": "10.0.0.1", **normal_features})

    # Baseline should now have n=3
    assert monitor.baseline_count() == 1
    baseline = monitor._baselines["10.0.0.1"]
    assert baseline.features["request_count"].count == 3
```

### 3.3 Anomalous Window Does Not Update Baseline

```python
def test_anomaly_does_not_update():
    monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=3, online_threshold=0.3)

    # Feed 3 normal windows
    for _ in range(3):
        monitor.evaluate({"src_ip": "10.0.0.1", **normal_features})

    # Feed anomalous window (large upload)
    anomalous = {**normal_features, "upload_download_ratio": 500.0}
    result = monitor.evaluate({"src_ip": "10.0.0.1", **anomalous})

    assert result["online_prediction"] == 1
    # Baseline should NOT have been updated with the anomalous window
    assert baseline.features["upload_download_ratio"].count == 3
```

### 3.4 Lab Demo Evaluation

| Scenario | Expected burst_score | Expected online_score | Alert? |
|---|---|---|---|
| Normal (first 10 windows) | < 0.7 | N/A (warmup) | No |
| Normal (after warmup) | < 0.7 | < 0.5 | No |
| exfil burst (500KB) | > 0.7 | varies | Yes |
| slow-drip (5KB/3s) | < 0.7 | > 0.5 | Yes |
| slow-drip after baseline | < 0.7 | > 0.5 | Yes |

---

## 4. Pipeline Throughput Benchmark

### 4.1 Measure Queue Sizes and Processing Rate

```bash
python src/pipeline.py \
  --offline \
  --pcap data/raw/Friday-WorkingHours.pcap \
  --debug 2>&1 | grep "packet_queue\|feature_queue\|windows_processed"
```

**Target:**
- `packet_queue` stays < 80% of `PACKET_QUEUE_SIZE` (50,000)
- `feature_queue` stays < 80% of `FEATURE_QUEUE_SIZE` (10,000)
- Throughput > 10,000 packets/sec on modern hardware

### 4.2 Single-Thread vs Multi-Thread Speedup

```bash
# Measure with 3 threads (default):
time python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap

# Expected: Complete processing of ~300K packets in < 60s
```

---

## 5. Detection Time Evaluation

### 5.1 Methodology

```
T_detect = T_alert - T_exfil_start

Where:
  T_exfil_start = first packet timestamp in exfil burst
  T_alert = timestamp when alert fires in pipeline log
```

### 5.2 Target

- **T_detect < 5 seconds** for burst exfil (> 100KB upload in < 1 second)
- **T_detect < 60 seconds** for slow-drip (depends on window size)

### 5.3 Measurement

```bash
# Run lab traffic:
docker-compose run --rm victim-client \
  python3 /generate.py --mode exfil --duration 30 &

# Run detector with timestamps:
python src/pipeline.py --live --iface eth0 --enable-online-monitor --debug

# Compare alert timestamps in log with traffic start time
```

---

## 6. Queue Size Monitoring

During pipeline execution, the monitor thread prints queue sizes every 5 seconds:

```
[  5.2s] packet_queue=847/50000  feature_queue=12/10000
[ 10.4s] packet_queue=923/50000  feature_queue=15/10000
[ 15.1s] packet_queue=1247/50000  feature_queue=23/10000
```

**Interpret:**
- `packet_queue` growing fast → capture faster than aggregation → increase queue size or parallelise aggregation
- `feature_queue` growing → inference too slow → check if model prediction is the bottleneck
- Both stable → healthy pipeline

---

## 7. Integration Test Checklist

```bash
# 1. Pipeline imports work
python -c "from src.pipeline import run_pipeline; print('OK')"

# 2. Online monitor standalone
python -c "from src.inference.online_anomaly_monitor import OnlineAnomalyMonitor; m = OnlineAnomalyMonitor(enabled=True); print(m.evaluate({'src_ip': '127.0.0.1', 'request_count': 10, 'total_fwd_bytes': 1000, 'total_bwd_bytes': 500, 'total_bytes': 1500, 'upload_download_ratio': 2.0, 'burst_count': 5, 'burst_ratio': 0.5, 'unusual_port_ratio': 0.1, 'request_rate': 1.0, 'inter_request_time_mean': 1.0, 'inter_request_time_std': 0.5, 'mean_payload_size': 100.0, 'std_payload_size': 50.0, 'psh_flag_count': 5, 'ack_flag_count': 10, 'syn_flag_count': 1, 'window_duration': 10.0})); print('OK')"

# 3. Pipeline with online monitor
python src/pipeline.py --help | grep online

# 4. Unit tests
pytest tests/unit/test_online_anomaly_monitor.py -v

# 5. Integration test
pytest tests/integration/test_online_inference_integration.py -v

# 6. Compile all
python -m compileall src lab scripts tests
```

---

## 8. Reporting Template

```
## Evaluation Results — [Date]

### Offline Models
| Model | AUC-ROC | F1 | FPR | Threshold |
|---|---|---|---|---|
| CNN1D | X.XXXX | X.XXXX | X.XXXX | X.XXX |

### Online Monitor
| Scenario | burst_score | online_score | online_prediction | Alert? |
|---|---|---|---|---|
| Normal | X.XXX | X.XXX | 0 | No |
| Exfil burst | X.XXX | X.XXX | 1 | Yes |
| Slow-drip | X.XXX | X.XXX | 1 | Yes |

### Pipeline Performance
| Metric | Value | Target | Status |
|---|---|---|---|
| Packets/sec | X | > 10000 | PASS/FAIL |
| Windows/sec | X | > 10 | PASS/FAIL |
| Max queue size | X% | < 80% | PASS/FAIL |
| Detection time | Xs | < 5s | PASS/FAIL |

### Notes
- [Any unexpected results or observations]
```
