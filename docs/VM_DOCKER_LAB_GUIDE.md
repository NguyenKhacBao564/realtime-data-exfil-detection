# docs/VM_DOCKER_LAB_GUIDE.md

# VM + Docker Lab Setup Guide

> **Why a VM?** MacBook M-series users cannot run Docker in full network-promiscuous mode.
> This guide explains the recommended architecture and setup.

---

## 1. Why Loopback Demo Is Only Development Validation

Running the pipeline on `lo0` (loopback interface) has limited value:

| Limitation | Impact |
|---|---|
| All traffic stays on `lo0` | No real network packets — scapy sees them differently |
| No cross-host communication | Can't test Docker network capture |
| No real TCP 3-way handshake | Burst patterns may not be realistic |
| No external server involved | Only useful for code debugging |

**Use loopback for:** unit tests, integration tests, pipeline code development.

**Use the VM lab for:** full demo with real HTTP traffic, network capture, multi-container interaction.

---

## 2. Recommended Final Demo Architecture

### MacBook M-Series Setup

```
┌─────────────────────────────────────────────────────────────┐
│  MacBook M (Host)                                           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Ubuntu 22.04 ARM64 VM (UTM or VMware Fusion)       │   │
│  │                                                     │   │
│  │  ┌──────────────────────────────────────────────┐  │   │
│  │  │  Docker Engine + Docker Compose              │  │   │
│  │  │                                              │  │   │
│  │  │  victim-client ──HTTP──→ exfil-server        │  │   │
│  │  │       │                       (logs metadata)│  │   │
│  │  │       └──── tcpdump ──→ monitor-detector     │  │   │
│  │  │                                       ↑       │  │   │
│  │  │                              detection pipeline│  │   │
│  │  └──────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Linux PC Setup (Native)

```
┌─────────────────────────────────────────────────────────────┐
│  Ubuntu 22.04 LTS (native or VM)                            │
│                                                             │
│  Docker Engine + Docker Compose                             │
│                                                             │
│  victim-client ──HTTP──→ exfil-server                       │
│       │                                                        │
│       └──── tcpdump ──→ monitor-detector (--live --iface eth0)│
└─────────────────────────────────────────────────────────────┘
```

---

## 3. VM Setup (UTM — Mac M-Series)

### Download Ubuntu ARM64

1. Download **Ubuntu 22.04 LTS ARM64** from https://ubuntu.com/download/server/arm
2. Or use the **Desktop** image: https://ubuntu.com/download/desktop

### Create VM with UTM

1. Open UTM → Click **+** (New)
2. Select **Virtualize** → **Linux**
3. Boot ISO: point to downloaded `.iso` file
4. Allocate: **4+ CPU cores**, **4+ GB RAM**, **30+ GB disk**
5. Network: **Bridged** (important for network capture)
6. Install Ubuntu normally

### Install Docker in VM

```bash
# Inside the Ubuntu VM:
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo apt install docker-compose
sudo usermod -aG docker $USER

# Log out and back in, then:
docker --version
docker-compose --version
```

### Clone the Project in VM

```bash
# In the VM terminal:
git clone https://github.com/yourusername/realtime-data-exfil-detection.git
cd realtime-data-exfil-detection
```

### Known Issues

| Issue | Solution |
|---|---|
| Docker build slow on ARM64 | Use `docker buildx` with `--platform linux/amd64` if cross-building |
| Network bridged mode not working | Try NAT mode + port forwarding instead |
| VM freezes during capture | Allocate more RAM, reduce capture duration |

---

## 4. Docker Lab Quick Reference

```bash
# Inside the VM:
cd realtime-data-exfil-detection/lab/

# Build and start:
docker-compose build
docker-compose up -d

# Check logs:
docker-compose logs -f exfil-server
docker-compose logs -f victim-client

# Run normal traffic:
docker-compose run --rm victim-client \
  python3 /generate.py --mode normal --duration 60

# Run simulated exfil:
docker-compose run --rm victim-client \
  python3 /generate.py --mode exfil --duration 30

# Run slow-drip:
docker-compose run --rm victim-client \
  python3 /generate.py --mode slow-drip --duration 60

# Run detector:
docker-compose exec monitor-detector \
  python3 -u src/pipeline.py \
    --live \
    --iface eth0 \
    --enable-online-monitor \
    --online-warmup-windows 5 \
    --debug

# Capture PCAP from victim:
docker-compose exec --privileged victim-client \
  tcpdump -i any -w /app/lab/captures/capture.pcap &

# Stop lab:
docker-compose down
```

---

## 5. PCAP Capture in Docker

### Option A: Capture from Host (Best for macOS)

```bash
# Run traffic first:
docker-compose up -d exfil-server victim-client

# In a separate terminal on the HOST (not inside Docker):
sudo tcpdump -i lo0 -w capture.pcap 'port 8000'
# or on Linux VM with physical iface:
sudo tcpdump -i eth0 -w capture.pcap 'port 8000'

# Then replay:
./scripts/run_offline_replay.sh capture.pcap --online-monitor
```

### Option B: Capture Inside Container (Linux VM Only)

```bash
# Requires --privileged for raw socket access:
docker-compose run --rm --privileged victim-client \
  tcpdump -i any -w /app/lab/captures/capture.pcap 'tcp port 8000' &

# Generate traffic, then stop capture with Ctrl+C
# Replay:
docker-compose run --rm monitor-detector \
  python3 -u src/pipeline.py --offline --pcap /app/lab/captures/capture.pcap
```

---

## 6. Interface Selection Guide

| Environment | Recommended Interface | Notes |
|---|---|---|
| macOS loopback | `lo0` | Dev only — limited value |
| Linux VM (NAT) | `eth0` or `ens*` | Try this first |
| Linux VM (Bridged) | `eth0` | Best for network demos |
| Physical Linux PC | `<physical_iface>` | Use `ip -br addr` to find |
| Docker Compose | Container internal eth0 | Lab network only |

```bash
# Find all interfaces:
ip -br addr show
# or
ifconfig -a | grep -E "^[a-z]"
```

---

## 7. Troubleshooting

| Problem | Solution |
|---|---|
| `tcpdump: no suitable device` | Use `--privileged` flag or run on host |
| Docker can't resolve `exfil-server` | Check `docker-compose ps`, ensure same network |
| `exfil-server:8000` connection refused | Server not ready — wait for health check |
| No packets captured in detector | Check interface name matches, try `any` |
| Pipeline hangs waiting for packets | Offline mode finished — press Ctrl+C |
