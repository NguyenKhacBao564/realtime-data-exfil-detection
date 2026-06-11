# docs/ONLINE_ANOMALY_DESIGN.md

# Online Anomaly Monitor — Design Document

## 1. Overview

The **Online Anomaly Monitor** (`src/inference/online_anomaly_monitor.py`) is an adaptive, runtime anomaly detector that identifies unknown or new attack patterns not covered by the offline-trained models.

Unlike the offline models (Isolation Forest, One-Class SVM, BiLSTM, CNN1D) which are trained on historical data and fixed at deploy time, the online monitor:

- **Learns at runtime** from the current traffic stream
- **Adapts per source IP** — each IP gets its own statistical baseline
- **Detects unknown anomalies** — zero-day patterns, novel exfiltration techniques
- **Requires no retraining** — purely statistical, no ML model needed

## 2. What Data the Online Model Learns

**Only metadata/statistical traffic features — NOT payload content:**

```
learned_data = {
    # Per-feature statistics:
    "upload_download_ratio": {"μ", "σ²", "n"},
    "burst_count":            {"μ", "σ²", "n"},
    "burst_ratio":           {"μ", "σ²", "n"},
    "unusual_port_ratio":     {"μ", "σ²", "n"},
    "request_rate":           {"μ", "σ²", "n"},
    "inter_request_time_std": {"μ", "σ²", "n"},
    "total_fwd_bytes":       {"μ", "σ²", "n"},
    "total_bytes":           {"μ", "σ²", "n"},
    "mean_payload_size":     {"μ", "σ²", "n"},
    "std_payload_size":      {"μ", "σ²", "n"},
    "psh_flag_count":        {"μ", "σ²", "n"},
    "request_count":         {"μ", "σ²", "n"},
    "total_bwd_bytes":       {"μ", "σ²", "n"},
    "inter_request_time_mean": {"μ", "σ²", "n"},
}
```

**No packet payloads, HTTP bodies, URLs, cookies, or user data are processed.**

## 3. Feature List (17 runtime features)

| Feature | Type | Weight | Rationale |
|---|---|---|---|
| `upload_download_ratio` | float | **2.0** | Primary exfil signal — attackers upload more |
| `burst_count` | int | **1.5** | Automated tools send many rapid packets |
| `burst_ratio` | float | **1.5** | Ratio of burst packets vs total |
| `unusual_port_ratio` | float | **1.5** | Non-standard ports = suspicious |
| `request_rate` | float | 1.0 | Unusual request frequency |
| `inter_request_time_std` | float | 1.0 | Machine vs human — low std = suspicious |
| `total_fwd_bytes` | int | 1.0 | Volume anomaly |
| `total_bytes` | int | 1.0 | Total traffic volume |
| `mean_payload_size` | float | 0.5 | Payload size anomaly |
| `std_payload_size` | float | 0.5 | Payload variance anomaly |
| `psh_flag_count` | int | 0.5 | TCP push = data carrying |
| `ack_flag_count` | int | 0.0 | Ignored — ACK only = not interesting |
| `syn_flag_count` | int | 0.0 | Ignored — SYN only = connection setup |
| `request_count` | int | 0.5 | Request count anomaly |
| `total_bwd_bytes` | int | 0.5 | Response size anomaly |
| `inter_request_time_mean` | float | 0.5 | Timing anomaly |
| `window_duration` | float | 0.0 | Ignored — already normalised by window |

## 4. How Unknown Attack Detection Works

### 4.1 Welford's Online Algorithm

The monitor uses **Welford's numerically stable online algorithm** for computing mean and variance with O(1) memory:

```python
# For each new value x in a sequence:
count += 1
delta = x - mean
mean += delta / count
m2 += delta * (x - mean)    # sum of squared deviations

# Variance = m2 / count
# Std      = sqrt(variance)
```

**Why Welford over naive mean/variance?**
- Naive: requires storing all values to compute variance
- Welford: single-pass, O(1) memory, numerically stable for large datasets
- Thread-safe: each IP has its own WelfordStats instance

### 4.2 Per-IP Baseline

Each source IP accumulates its own baseline:

```
For each window from src_ip:
    if baseline[src_ip] is cold:
        accumulate window into baseline (no scoring yet)
    else:
        compute z-scores for each feature
        compute weighted anomaly score
        if score >= threshold:
            → ANOMALY (do NOT update baseline)
        else:
            → NORMAL (update baseline with this window)
```

**Why not update baseline with anomalous windows?**
- Anomalous windows represent attack traffic
- Including them in the baseline would poison the normal profile
- This prevents the attacker from "training" the detector to accept their traffic

### 4.3 Z-Score Computation

```python
z_i = |x_i - μ_i| / (σ_i + ε)
```

Where:
- `x_i` = current window's value for feature `i`
- `μ_i` = running mean for feature `i`
- `σ_i` = running std for feature `i`
- `ε` = 1e-8 (guard against division by zero)

A z-score of 2.0 means the current value is **2 standard deviations** from the learned mean.

### 4.4 Weighted Anomaly Score

```python
score = Σ(weight_i * capped_z_i / threshold_i) / Σ(weight_i)

where:
    capped_z_i = min(z_i, 10.0)   # prevent single extreme values dominating
    threshold_i = 2.0 (global default)
```

The score is normalised to [0, 1]:
- **0.0** = identical to baseline
- **0.5** = average deviation equals threshold
- **1.0** = maximum deviation (cap reached)

### 4.5 Warm-up Behaviour

```
warmup_min_windows = 10 (configurable)

During warmup:
    → Accumulate windows into baseline
    → No scoring, return online_prediction=0
    → reason_codes = ["warmup_3/10", ...]

After warmup:
    → Full scoring active
    → Online anomalies can fire
```

This prevents false positives during the initial observation period when the baseline is being established.

## 5. Integration with Offline Models

The online monitor runs **in parallel** with the offline models:

```
Window features → burst_exfil_score
               → offline_model.predict()   (Isolation Forest / CNN1D / etc.)
               → online_monitor.evaluate() (unknown pattern detection)

Alert fires if ANY of:
  - burst_score > 0.7  → BURST_RULE
  - model.predict == 1 → OFFLINE_MODEL
  - online_pred == 1   → ONLINE_UNKNOWN_ANOMALY
```

## 6. Offline Models vs Online Monitor

| Aspect | Offline Models | Online Monitor |
|---|---|---|
| Training | Fixed at deploy time | Adapts at runtime |
| Data needed | Historical labeled dataset | Live traffic stream |
| Pattern types | Known patterns in training data | Any deviation from normal |
| Memory | O(models) | O(IPs × features) |
| Computation | Per-window ML inference | O(1) per window |
| False positives | Depends on training data quality | Reduces as baseline converges |
| Zero-day detection | Limited | Full |
| Thread-safe | Yes | Yes |

## 7. Configuration

| Parameter | CLI Flag | Default | Meaning |
|---|---|---|---|
| `enable_online_monitor` | `--enable-online-monitor` | `False` | Opt-in only |
| `online_threshold` | `--online-threshold` | `0.5` | Alert threshold (0-1) |
| `warmup_min_windows` | `--online-warmup-windows` | `10` | Windows before scoring |

### Tuning Recommendations

| Scenario | Threshold | Warmup | Rationale |
|---|---|---|---|
| High-security | 0.3 | 20 | Sensitive, slower to stabilise |
| Balanced | 0.5 | 10 | Default — good for demos |
| Low-noise | 0.7 | 15 | Fewer false positives |

## 8. Alert Output Example

```
━━━ EXFILTRATION ALERT ━━━
[CRITICAL]  2026-06-01 12:34:56
  Source IP:     172.28.0.2
  Window start:  1717200000  (12:00:00  UTC)
  Requests:      412
  Total bytes:   2,847,293  (↑2,730,000 / ↓117,293)
  Upload ratio:  23.27x
  Burst count:   412  (ratio: 0.49)
  ── Triggers ──
  [BURST_RULE] Burst exfil score
  [ONLINE_UNKNOWN_ANOMALY] Online anomaly (unknown pattern)
  ── Scores ──
  Burst score:   0.800
  Online score:  0.723  (ANOMALY)
  Baseline n:     15
    HIGH_Z: upload_download_ratio=4.7σ
    HIGH_Z: burst_count=3.2σ
    HIGH_Z: inter_request_time_std=2.1σ
━━━━━━━━━━━━━━━━━━━━━━━━
```

The `HIGH_Z` lines show which features deviated most from the learned baseline, helping analysts understand **why** the online monitor flagged the traffic.
