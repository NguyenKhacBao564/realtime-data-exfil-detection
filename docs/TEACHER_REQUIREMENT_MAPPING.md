# docs/TEACHER_REQUIREMENT_MAPPING.md

# Teacher Requirement Mapping

> **Purpose:** Maps each teacher requirement directly to the implementation files and commands.
> This is the primary reference for verifying completeness.

---

## Requirement A: Reproducible VM/Docker Lab Workflow

> *"Demo should not only be local loopback. Add a reproducible VM/Docker lab workflow for: real-time/live capture, offline PCAP replay, multi-threaded processing."*

### A1 — VM Setup Guide

| Teacher Requirement | Implementation | File |
|---|---|---|
| VM setup instructions | UTM + Ubuntu ARM64 setup | `docs/VM_DOCKER_LAB_GUIDE.md` |
| Docker install | Docker Engine + Compose install | `docs/VM_DOCKER_LAB_GUIDE.md` §3 |
| Network config | Bridge/NAT interface guide | `docs/VM_DOCKER_LAB_GUIDE.md` §6 |
| MacBook M limitation note | Promiscuous mode not supported on macOS | `docs/VM_DOCKER_LAB_GUIDE.md` §1 |

### A2 — Docker Compose Lab

| Teacher Requirement | Implementation | File |
|---|---|---|
| Isolated lab environment | 3-service Docker Compose lab | `lab/docker-compose.yml` |
| HTTP server (logs metadata only) | Python HTTPServer, discards payloads | `lab/server/receiver.py` |
| Synthetic traffic generator | 3-mode generator (normal/exfil/slow-drip) | `lab/victim/generate_http_traffic.py` |
| Containerised detection pipeline | Monitor Dockerfile with runtime deps | `lab/monitor/Dockerfile` |
| PCAP capture support | Volume mount `lab/captures/` | `lab/docker-compose.yml` |
| Safety: no real data exfil | Dummy payloads only, SHA256 logged | `lab/server/receiver.py` §2 |

### A3 — Live Capture

| Teacher Requirement | Implementation | File |
|---|---|---|
| Real-time packet capture | `scapy sniff` on live interface | `src/capture/packet_capture.py` |
| Live detection command | `sudo python src/pipeline.py --live --iface eth0` | `src/pipeline.py` CLI |
| Helper script | Interface auto-detection + sudo check | `scripts/run_live_lab.sh` |
| `eth0` inside Docker container | Container eth0 on bridge network | `lab/docker-compose.yml` |

### A4 — Offline PCAP Replay

| Teacher Requirement | Implementation | File |
|---|---|---|
| PCAP capture | tcpdump with timed capture | `scripts/capture_lab_pcap.sh` |
| PCAP replay | scapy offline mode via pipeline | `src/capture/packet_capture.py` |
| Replay command | `python src/pipeline.py --offline --pcap <file>` | `src/pipeline.py` CLI |
| Helper script | PCAP selection + offline run | `scripts/run_offline_replay.sh` |

### A5 — Multi-threaded Processing

| Teacher Requirement | Implementation | File |
|---|---|---|
| Thread 1: Packet Capture | `PacketCaptureThread` | `src/capture/packet_capture.py` |
| Thread 2: Feature Aggregation | `FeatureAggregatorThread` | `src/features/feature_aggregator.py` |
| Thread 3: Inference | `InferenceThread` | `src/inference/model_inference.py` |
| Queue-based IPC | `queue.Queue` between threads | `src/pipeline.py` |
| Graceful shutdown | `stop_event`, `join(timeout=10)` | `src/pipeline.py` |

### A6 — Full Demo Script

| Teacher Requirement | Implementation | File |
|---|---|---|
| Step-by-step demo walkthrough | 6-phase demo covering all scenarios | `docs/DEMO_SCRIPT.md` |
| Expected results table | burst_score / model / online scores | `docs/DEMO_SCRIPT.md` |
| Troubleshooting guide | Common issues and fixes | `docs/DEMO_SCRIPT.md` §Troubleshooting |

---

## Requirement B: Online Anomaly Detection for Unknown/New Patterns

> *"Add a mechanism for detecting unknown/new attack patterns that were not present in the offline-trained models. This should be an online/adaptive anomaly monitor based on runtime traffic statistics, not a heavy new deep learning model."*

### B1 — Core Online Anomaly Monitor

| Teacher Requirement | Implementation | File |
|---|---|---|
| Welford-based adaptive baseline | `WelfordStats` class (O(1) memory, numerically stable) | `src/inference/online_anomaly_monitor.py` |
| Per-IP baseline tracking | `IPBaseline` class, independent per source IP | `src/inference/online_anomaly_monitor.py` |
| Online/adaptive (not DL) | Statistical z-score computation, no model file | `src/inference/online_anomaly_monitor.py` |
| Runtime traffic statistics | Uses 17 runtime window features | `src/features/runtime_features.py` |
| Detects unknown patterns | Z-score deviation from per-IP baseline | `src/inference/online_anomaly_monitor.py` |
| Anti-poisoning design | Anomalous windows do NOT update baseline | `src/inference/online_anomaly_monitor.py` |

### B2 — Feature Extraction

| Feature | Weight | Rationale | File |
|---|---|---|---|
| `upload_download_ratio` | 2.0 | Primary exfil signal — attackers upload more | `online_anomaly_monitor.py` |
| `burst_count` | 1.5 | Automation / scripted tools | `online_anomaly_monitor.py` |
| `burst_ratio` | 1.5 | Ratio of burst packets | `online_anomaly_monitor.py` |
| `unusual_port_ratio` | 1.5 | Non-standard port usage | `online_anomaly_monitor.py` |
| `request_rate` | 1.0 | Unusual request frequency | `online_anomaly_monitor.py` |
| `inter_request_time_std` | 1.0 | Machine vs human (low std = suspicious) | `online_anomaly_monitor.py` |
| `total_fwd_bytes` | 1.0 | Large uploads | `online_anomaly_monitor.py` |
| `total_bytes` | 1.0 | Total volume anomaly | `online_anomaly_monitor.py` |
| `mean_payload_size` | 0.5 | Payload size anomaly | `online_anomaly_monitor.py` |
| `std_payload_size` | 0.5 | Payload variance anomaly | `online_anomaly_monitor.py` |
| `psh_flag_count` | 0.5 | TCP push — payload carrying | `online_anomaly_monitor.py` |
| `request_count` | 0.5 | Number of requests anomaly | `online_anomaly_monitor.py` |
| `total_bwd_bytes` | 0.5 | Response size anomaly | `online_anomaly_monitor.py` |
| `inter_request_time_mean` | 0.5 | Timing anomaly | `online_anomaly_monitor.py` |
| `ack_flag_count` | 0.0 | Not discriminative | `online_anomaly_monitor.py` |
| `syn_flag_count` | 0.0 | Connection setup only | `online_anomaly_monitor.py` |
| `window_duration` | 0.0 | Already normalised | `online_anomaly_monitor.py` |

### B3 — Inference Integration

| Teacher Requirement | Implementation | File |
|---|---|---|
| Online score in alert output | `online_score`, `online_prediction` fields | `src/inference/alert_logger.py` |
| Reason codes | `HIGH_Z: feature=valueσ` per feature | `src/inference/online_anomaly_monitor.py` |
| Baseline count | `baseline_count` in alert output | `src/inference/alert_logger.py` |
| Alert trigger labeling | `[ONLINE_UNKNOWN_ANOMALY]` in triggers | `src/inference/model_inference.py` |
| Online monitor stats in final output | `online_anomalies`, `online_baselines_active` | `src/pipeline.py` |

### B4 — Configuration

| Teacher Requirement | Implementation | File |
|---|---|---|
| Default disabled (opt-in) | `ENABLE_ONLINE_MONITOR = False` | `src/utils/config.py` |
| Threshold configurable | `--online-threshold` CLI arg | `src/pipeline.py` |
| Warmup windows configurable | `--online-warmup-windows` CLI arg | `src/pipeline.py` |
| CLI flag name | `--enable-online-monitor` | `src/pipeline.py` |

### B5 — Testing

| Teacher Requirement | Implementation | File |
|---|---|---|
| Unit tests (30 tests) | Welford, IPBaseline, OnlineAnomalyMonitor | `tests/unit/test_online_anomaly_monitor.py` |
| Integration tests (7 tests) | Alert chain, multi-window, multi-IP | `tests/integration/test_online_inference_integration.py` |
| Warmup behavior tests | Baseline grows during warmup | `test_online_anomaly_monitor.py` |
| Anomaly doesn't update baseline | Anti-poisoning test | `test_online_anomaly_monitor.py` |
| Multi-IP isolation | Independent baselines per IP | `test_online_anomaly_monitor.py` |

---

## Requirement C: Evaluation

> *"Metrics: AUC-ROC, F1-Score, FPR, Precision, Recall, Detection Time, Throughput."*

| Metric | Target | Implementation | File |
|---|---|---|---|
| AUC-ROC | > 0.90 (supervised) | `sklearn.metrics.roc_auc_score` | `src/train/evaluate.py` |
| F1-Score | Maximize | `sklearn.metrics.f1_score` | `src/train/evaluate.py` |
| FPR | < 5% | `FP / (FP + TN)` | `src/train/evaluate.py` |
| Precision | > 0.80 | `sklearn.metrics.precision_score` | `src/train/evaluate.py` |
| Recall | > 0.85 | `sklearn.metrics.recall_score` | `src/train/evaluate.py` |
| Detection Time | < 5s | Window timestamp vs alert timestamp | `src/train/evaluate.py` |
| Throughput | packets/sec pipeline | Benchmark in evaluate.py | `src/train/evaluate.py` |
| Queue sizes | Monitored | `monitor_queues()` every 5s | `src/pipeline.py` |

Full evaluation plan: `docs/EVALUATION_PLAN.md`

---

## Implementation Checklist

| Requirement | Status | Files |
|---|---|---|
| A1 — VM setup guide | ✅ | `docs/VM_DOCKER_LAB_GUIDE.md` |
| A2 — Docker lab | ✅ | `lab/docker-compose.yml`, `lab/server/receiver.py`, `lab/victim/generate_http_traffic.py`, `lab/monitor/Dockerfile` |
| A3 — Live capture | ✅ | `src/capture/packet_capture.py`, `scripts/run_live_lab.sh` |
| A4 — PCAP replay | ✅ | `scripts/capture_lab_pcap.sh`, `scripts/run_offline_replay.sh` |
| A5 — Multi-threaded pipeline | ✅ | `src/pipeline.py`, 3 thread classes |
| A6 — Demo script | ✅ | `docs/DEMO_SCRIPT.md` |
| B1 — Online anomaly monitor | ✅ | `src/inference/online_anomaly_monitor.py` |
| B2 — Feature extraction | ✅ | `src/features/runtime_features.py`, `online_anomaly_monitor.py` |
| B3 — Inference integration | ✅ | `src/inference/model_inference.py`, `src/inference/alert_logger.py` |
| B4 — Configuration | ✅ | `src/utils/config.py`, `src/pipeline.py` CLI args |
| B5 — Tests | ✅ | `tests/unit/`, `tests/integration/` |
| C — Evaluation | ✅ | `src/train/evaluate.py`, `docs/EVALUATION_PLAN.md` |
| Documentation | ✅ | `docs/IMPLEMENTATION_SUMMARY.md`, `docs/ONLINE_ANOMALY_DESIGN.md` |
| Makefile | ✅ | `Makefile` |
| Evidence collection | ✅ | `scripts/collect_demo_evidence.sh` |
