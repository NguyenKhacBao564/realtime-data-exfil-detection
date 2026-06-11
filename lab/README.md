# lab/README.md — Exfiltration Detection Lab

> **Academic demo only.** All traffic is synthetic. No real user data is used.

---

## Overview

This lab provides a reproducible, containerised environment for demonstrating:

1. **Normal traffic** — irregular HTTP browsing patterns
2. **Simulated exfiltration** — burst of large synthetic uploads
3. **Slow-drip anomaly** — small regular uploads mimicking a covert channel
4. **Live detection** — the detection pipeline with online adaptive monitoring
5. **Offline PCAP replay** — capture traffic with tcpdump, replay with scapy

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│              Docker Compose Network (172.28.0.0/16)      │
│                                                          │
│  victim-client ──HTTP──→ exfil-server                   │
│       │                      (logs metadata only)         │
│       │                                                 │
│       └──── tcpdump ──→ monitor-detector                 │
│                       (detection pipeline)               │
└──────────────────────────────────────────────────────────┘
```

---

## Prerequisites

### Linux VM (Recommended for Mac M-series)

> **MacBook M users:** Docker networking behaves differently on macOS.
> For best results, run this lab inside an Ubuntu ARM64 VM via UTM or VMware Fusion.

1. Install Docker Engine + Docker Compose:
   ```bash
   # Ubuntu 22.04 LTS
   curl -fsSL https://get.docker.com | sh
   sudo apt install docker-compose
   sudo usermod -aG docker $USER
   newgrp docker
   ```

2. Verify Docker:
   ```bash
   docker --version
   docker-compose --version
   ```

### macOS (Development Only)

Docker Desktop on macOS can run this lab, but packet capture (tcpdump from within containers) requires Linux. For full network capture demos, use the Linux VM.

---

## Quick Start

### 1. Start the lab

```bash
cd lab/
docker-compose build
docker-compose up -d
docker-compose logs -f exfil-server
```

### 2. Generate normal traffic (background)

```bash
# In a new terminal:
docker-compose run --rm victim-client \
  python3 /generate.py --mode normal --server http://exfil-server:8000 --duration 120
```

### 3. Generate simulated exfiltration

```bash
docker-compose run --rm victim-client \
  python3 /generate.py --mode exfil --server http://exfil-server:8000 --duration 60
```

### 4. Generate slow-drip anomaly

```bash
docker-compose run --rm victim-client \
  python3 /generate.py --mode slow-drip --server http://exfil-server:8000 --duration 120
```

### 5. Run the detection pipeline (live mode)

```bash
docker-compose run --rm monitor-detector \
  python3 -u src/pipeline.py \
    --live \
    --iface eth0 \
    --enable-online-monitor \
    --online-warmup-windows 5 \
    --debug
```

### 6. Run offline PCAP replay

```bash
# Capture traffic first:
docker-compose run --rm --privileged victim-client \
  tcpdump -i any -w /app/lab/captures/lab_traffic.pcap &
# ... run traffic modes ...
# Then replay:
docker-compose run --rm monitor-detector \
  python3 -u src/pipeline.py \
    --offline \
    --pcap /app/lab/captures/lab_traffic.pcap \
    --enable-online-monitor
```

---

## Traffic Modes Reference

| Mode | Payload Size | Rate | Pattern | Detection |
|------|-------------|------|---------|-----------|
| `normal` | 100B–2KB | Irregular (0.5–5s) | Human browsing | Quiet |
| `exfil` | 50KB–500KB | Fast burst (0.05–0.3s) | Automated upload | burst_score ↑ + model |
| `slow-drip` | 5KB–15KB | Regular (2–4s) | Scheduled task | online_monitor ↑ |

---

## Stopping the Lab

```bash
docker-compose down
# Or with volumes:
docker-compose down -v
```

---

## Network Interface Note

Inside Docker Compose, containers communicate over the `exfil-lab` bridge network. The monitor container can capture traffic by:

1. **Shared network** — monitor is on the same Docker network (current setup)
2. **Promiscuous mode** — requires `--privileged` and a physical interface (Linux VM only)
3. **PCAP replay** — capture with tcpdump, replay offline (recommended for macOS)

The `--iface eth0` inside the monitor container refers to the container's eth0 on the bridge network. For physical interface capture, use `--iface <physical_iface>` from the host or a privileged container.

---

## Alert Interpretation

When the pipeline fires an alert, the `[Triggers]` section shows which component detected it:

| Trigger | Meaning |
|---------|---------|
| `BURST_RULE` | burst_exfil_score exceeded threshold — known pattern |
| `OFFLINE_MODEL` | Trained ML model predicted exfiltration |
| `ONLINE_UNKNOWN_ANOMALY` | Online monitor detected deviation from learned baseline — **unknown/new pattern** |

The `online_score` and `reason_codes` fields in the alert show which features deviated most significantly from the per-IP baseline.
