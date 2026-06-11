# docs/DEMO_SCRIPT.md

# Demonstration Script — Full Lab Walkthrough

> **Duration:** ~30-45 minutes
> **Audience:** Academic supervisors, classmates
> **Environment:** Ubuntu VM (ARM64) with Docker + Docker Compose

---

## Prerequisites Checklist

Before starting, verify:

```bash
# 1. Docker installed
docker --version          # should be 24.x+
docker-compose --version  # should be 2.x+

# 2. Clone the repo
git clone https://github.com/yourusername/realtime-data-exfil-detection.git
cd realtime-data-exfil-detection

# 3. Lab files present
ls lab/docker-compose.yml
ls lab/server/receiver.py
ls lab/victim/generate_http_traffic.py

# 4. Source code present
ls src/pipeline.py
ls src/inference/model_inference.py
ls src/inference/online_anomaly_monitor.py
```

---

## Demo Flow

### Phase 1: Normal Traffic Baseline (5 min)

**Goal:** Establish a normal baseline for the online monitor.

```bash
# Terminal 1: Start the lab
cd lab/
docker-compose up -d
docker-compose logs -f exfil-server

# Terminal 2: Generate normal traffic
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode normal \
    --server http://exfil-server:8000 \
    --duration 120

# Expected output: Regular HTTP requests, status 200
```

**Talk track:**
- "This simulates normal user browsing — irregular timing, small payloads"
- "Notice the `X-Mode: normal` header — all traffic is dummy bytes, no real data"
- "The server logs only metadata — timestamp, source IP, content length, session ID"

---

### Phase 2: Simulated Exfiltration (5 min)

**Goal:** Show detection of burst exfiltration pattern.

```bash
# Terminal 2 (while still in lab/):
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode exfil \
    --server http://exfil-server:8000 \
    --duration 30
```

**Talk track:**
- "Now we simulate a data exfiltration scenario — large burst uploads"
- "The traffic generator sends 50KB-500KB payloads in rapid succession"
- "This mimics an attacker uploading stolen data via HTTP POST"
- "Let's run the detector to see if it catches this."

---

### Phase 3: Live Detection (5 min)

**Goal:** Demonstrate the detection pipeline in live mode.

```bash
# Terminal 3: Run the detector (inside lab/):
docker-compose exec monitor-detector bash

# Inside the container:
python3 -u src/pipeline.py \
  --live \
  --iface eth0 \
  --enable-online-monitor \
  --online-warmup-windows 5 \
  --debug
```

**Or from the host (if tcpdump available):**
```bash
./scripts/run_live_lab.sh eth0 --online-monitor
```

**Talk track:**
- "The pipeline has 3 threads: packet capture → feature aggregation → inference"
- "Each thread processes a queue independently — true parallelism"
- "The detector now sees both normal and exfil traffic patterns"
- "The alert shows: burst_score, model_score, and online_score"
- "Notice the `[Triggers]` section — BURST_RULE, OFFLINE_MODEL, ONLINE_UNKNOWN_ANOMALY"

---

### Phase 4: Offline PCAP Replay (5 min)

**Goal:** Show offline detection on captured traffic.

```bash
# Capture traffic first:
sudo ./scripts/capture_lab_pcap.sh eth0 60 lab/captures/demo.pcap

# Then replay with the detector:
./scripts/run_offline_replay.sh lab/captures/demo.pcap --online-monitor
```

**Talk track:**
- "Offline mode is useful for forensic analysis"
- "Capture traffic with tcpdump, replay through the detector later"
- "The online monitor learns from the captured traffic even in offline mode"

---

### Phase 5: Slow-Drip Anomaly (5 min)

**Goal:** Show the online monitor detecting unknown patterns.

```bash
# Run slow-drip traffic (designed to evade threshold-based detection):
docker-compose run --rm victim-client \
  python3 /generate.py \
    --mode slow-drip \
    --server http://exfil-server:8000 \
    --duration 120

# Observe: burst_score may be LOW, but online_score should be HIGH
```

**Talk track:**
- "Slow-drip is designed to evade traditional threshold-based detection"
- "Small regular uploads (5-15KB every 2-4 seconds)"
- "burst_exfil_score may stay below 0.7 — too small to trigger burst rules"
- "BUT the online monitor detects this as a deviation from the learned baseline"
- "This is why the online monitor is critical — it catches unknown patterns"

---

### Phase 6: Compare Models (5 min)

**Goal:** Show that offline models and online monitor complement each other.

```bash
# Run with ALL detection layers:
python3 src/pipeline.py \
  --offline \
  --pcap lab/captures/demo.pcap \
  --enable-online-monitor \
  --online-warmup-windows 10 \
  --debug
```

**Talk track:**
- "Three layers of detection working together:"
- "1. BURST_RULE: Rule-based — fast, interpretable, catches known patterns"
- "2. OFFLINE_MODEL: ML-based — catches patterns similar to training data"
- "3. ONLINE_UNKNOWN_ANOMALY: Adaptive — catches novel deviations from baseline"
- "Together they provide defence-in-depth against exfiltration"

---

## Quick Reference Commands

```bash
# === Setup ===
cd lab/
docker-compose up -d

# === Traffic Generation ===
docker-compose run --rm victim-client python3 /generate.py --mode normal --duration 60
docker-compose run --rm victim-client python3 /generate.py --mode exfil --duration 30
docker-compose run --rm victim-client python3 /generate.py --mode slow-drip --duration 60

# === Detection ===
python3 src/pipeline.py --live --iface eth0 --enable-online-monitor --debug
python3 src/pipeline.py --offline --pcap <file.pcap> --enable-online-monitor

# === Scripts ===
./scripts/run_live_lab.sh eth0 --online-monitor
./scripts/run_offline_replay.sh lab/captures/demo.pcap --online-monitor
sudo ./scripts/capture_lab_pcap.sh eth0 60

# === Cleanup ===
docker-compose down
```

---

## Expected Results

| Traffic Mode | burst_score | offline_model | online_score | Alert? |
|---|---|---|---|---|
| Normal (warmup) | < 0.7 | 0 | N/A | No |
| Normal (steady) | < 0.7 | 0 | < 0.5 | No |
| exfil burst | **> 0.7** | 1 | varies | **Yes** |
| slow-drip | < 0.7 | 0 | **> 0.5** | **Yes** |
| New unknown | varies | varies | **> 0.5** | **Yes** |

---

## Troubleshooting During Demo

| Problem | Quick Fix |
|---|---|
| Server not ready | `docker-compose logs exfil-server` — wait for health check |
| No packets in detector | Check interface name: `ip -br addr` |
| Online monitor never fires | Increase warmup to 20 windows |
| Too many false positives | Increase `--online-threshold` to 0.7 |
| Docker network error | `docker-compose down && docker-compose up -d` |
