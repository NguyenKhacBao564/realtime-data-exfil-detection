#!/usr/bin/env python3
"""
src/self_capture/capture_and_generate.py — Self-capture dataset using Scapy on macOS.

This script solves the Docker network capture problem by running Scapy directly
on macOS to capture localhost traffic, while generating traffic via curl from a
generator container on the Docker bridge.

Flow:
  1. Start HTTP servers (baseline:8000, burst:8080)
  2. Start Scapy capture on lo0 (background thread)
  3. Generate baseline traffic (normal) → capture to baseline.pcap
  4. Generate burst attack traffic → capture to burst.pcap
  5. Extract flow features → CSV
"""

import sys
import time
import threading
import subprocess
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Check if scapy is available
try:
    from scapy.all import sniff, IP, TCP, Raw, wrpcap
    import numpy as np
    HAS_SCAPY = True
except ImportError:
    HAS_SCAPY = False
    print("WARNING: Scapy not available. Using tcpdump fallback.")

SCENARIOS_DIR = PROJECT_ROOT / "data" / "self_captured" / "scenarios"
BASELINE_PCAP = SCENARIOS_DIR / "baseline" / "baseline.pcap"
BURST_PCAP    = SCENARIOS_DIR / "burst_exfil" / "burst_exfil.pcap"


def start_docker_generator(port: int, n_requests: int, delay: float, label: str):
    """Start a Docker container to generate HTTP traffic."""
    print(f"  [{label}] Generating {n_requests} requests to localhost:{port}...")

    script = f"""
import urllib.request
for i in range({n_requests}):
    try:
        urllib.request.urlopen('http://localhost:{port}/', timeout=2)
    except:
        pass
    time.sleep({delay})
print('{label}: done')
"""
    encoded = __import__('base64').b64encode(script.encode()).decode()

    container_name = f"gen_{label}"
    result = subprocess.run([
        'docker', 'run', '--rm',
        '--name', container_name,
        '--network=bridge',
        '-d',
        'python:3.11-slim',
        'python3', '-c',
        f"import urllib.request,time; exec(__import__('base64').b64decode('{encoded}').decode())"
    ], capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  WARNING: Generator failed: {result.stderr.strip()}")
    return container_name


def capture_with_scapy(output_pcap: Path, duration_s: int, filter_str: str = "tcp"):
    """Capture traffic using Scapy on macOS."""
    if not HAS_SCAPY:
        return capture_with_tcpdump(output_pcap, duration_s, filter_str)

    print(f"  [Scapy] Capturing to {output_pcap.name} for {duration_s}s...")
    packets = []

    def _sniff():
        nonlocal packets
        try:
            # Capture on all interfaces (Scapy will get lo0 on macOS)
            captured = sniff(
                filter=filter_str,
                timeout=duration_s,
                store=True,
            )
            packets.extend(captured)
        except Exception as e:
            print(f"  [Scapy] Capture error: {e}")

    thread = threading.Thread(target=_sniff, daemon=True)
    thread.start()

    # Wait for duration
    thread.join(timeout=duration_s + 5)

    if packets:
        print(f"  [Scapy] Captured {len(packets)} packets")
        wrpcap(str(output_pcap), packets)
        print(f"  [Scapy] Saved to {output_pcap}")
    else:
        print(f"  [Scapy] WARNING: No packets captured!")

    return len(packets)


def capture_with_tcpdump(output_pcap: Path, duration_s: int, filter_str: str = "tcp"):
    """Fallback: use tcpdump on macOS."""
    print(f"  [tcpdump] Capturing to {output_pcap.name} for {duration_s}s...")

    # Try to use tcpdump with sudo for lo0
    cmd = ['/usr/sbin/tcpdump', '-i', 'lo0', '-s', '96', '-w', str(output_pcap),
           f'duration <= {duration_s} and (tcp port 8000 or tcp port 8080)']

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_s + 30)
    if result.returncode != 0:
        print(f"  [tcpdump] Failed: {result.stderr.strip()[:100]}")
    else:
        size = output_pcap.stat().st_size if output_pcap.exists() else 0
        print(f"  [tcpdump] Captured {size} bytes")

    return output_pcap.exists() and output_pcap.stat().st_size > 0


def generate_traffic_from_macOS(port: int, n_requests: int, delay: float, label: str):
    """Generate traffic from macOS using subprocess (not Docker)."""
    print(f"  [{label}] Generating {n_requests} requests via curl to localhost:{port}...")
    success = 0
    for i in range(n_requests):
        result = subprocess.run(
            ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', f'http://localhost:{port}/'],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip() == '200':
            success += 1
        time.sleep(delay)
    print(f"  [{label}] Done: {success}/{n_requests} successful")


def run_self_capture():
    """Main self-capture pipeline."""
    print(f"\n{'='*70}")
    print("SELF-CAPTURE DATASET — Scapy on macOS + Docker traffic generators")
    print(f"{'='*70}")
    print(f"Scapy available: {HAS_SCAPY}")
    print(f"Baseline PCAP:   {BASELINE_PCAP}")
    print(f"Burst PCAP:      {BURST_PCAP}")

    # Ensure directories exist
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    (SCENARIOS_DIR / "baseline").mkdir(exist_ok=True)
    (SCENARIOS_DIR / "burst_exfil").mkdir(exist_ok=True)

    # ── SCENARIO 1: Baseline (Normal Traffic) ─────────────────────────────────
    print(f"\n{'─'*70}")
    print("SCENARIO 1: Baseline — Normal traffic (localhost:8000)")
    print(f"{'─'*70}")

    # Start generator container (goes through Docker bridge, captured by Scapy on lo0)
    gen = start_docker_generator(8000, n_requests=30, delay=1.0, label="baseline")

    # Capture simultaneously with Scapy
    if HAS_SCAPY:
        from scapy.all import sniff, TCP
        packets = []
        stop_event = threading.Event()

        def _sniff():
            try:
                captured = sniff(
                    filter="tcp port 8000",
                    timeout=45,
                    store=True,
                )
                packets.extend(captured)
            except Exception as e:
                print(f"  Scapy error: {e}")

        sniff_thread = threading.Thread(target=_sniff, daemon=True)
        sniff_thread.start()

        # Generate traffic from macOS as backup
        generate_traffic_from_macOS(8000, n_requests=20, delay=1.0, label="baseline_mac")

        # Wait for generator
        time.sleep(35)
        sniff_thread.join(timeout=10)

        if packets:
            from scapy.all import wrpcap
            wrpcap(str(BASELINE_PCAP), packets)
            print(f"\n  ✅ Baseline capture: {len(packets)} packets → {BASELINE_PCAP}")
        else:
            print(f"\n  ⚠️ No packets captured")
    else:
        # Fallback: tcpdump from macOS
        capture_with_tcpdump(BASELINE_PCAP, duration_s=40,
                              filter_str="tcp port 8000")

    # ── SCENARIO 2: Burst Exfiltration ─────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("SCENARIO 2: Burst Exfiltration (localhost:8080)")
    print(f"{'─'*70}")

    # Generate burst attack from macOS
    print("  [burst] Generating attack traffic...")
    for round_num in range(3):
        print(f"  Round {round_num + 1}/3...")
        for i in range(30):
            # POST with random data (simulate exfil payload)
            result = subprocess.run([
                'curl', '-s', '-o', '/dev/null',
                '-X', 'POST',
                '-d', f'exfil_chunk_{round_num}_{i}_$(openssl rand -base64 500)',
                f'http://localhost:8080/upload'
            ], capture_output=True, text=True, timeout=5)
            time.sleep(0.1)

        time.sleep(3)

    # Also try GET requests (some will succeed, some 404)
    for i in range(20):
        subprocess.run(['curl', '-s', '-o', '/dev/null', f'http://localhost:8080/req{i}'],
                        capture_output=True, timeout=3)
        time.sleep(0.5)

    print("  [burst] Attack traffic generation complete")

    # ── SIMULTANEOUS CAPTURE ──────────────────────────────────────────────────
    # Capture both scenarios during generation
    if HAS_SCAPY:
        from scapy.all import sniff, TCP, wrpcap

        # Capture both ports for burst scenario
        all_packets = []
        stop_event = threading.Event()

        def _sniff_burst():
            try:
                captured = sniff(
                    filter="tcp port 8000 or tcp port 8080",
                    timeout=120,
                    store=True,
                )
                all_packets.extend(captured)
            except Exception as e:
                print(f"  Scapy error: {e}")

        thread = threading.Thread(target=_sniff_burst, daemon=True)
        thread.start()

        # Generate burst traffic
        for round_num in range(2):
            for i in range(50):
                data = f'burst_exfil_{round_num}_{i}_{i*100}_'
                subprocess.run([
                    'curl', '-s', '-o', '/dev/null',
                    '-X', 'POST',
                    '-d', data,
                    'http://localhost:8080/upload'
                ], capture_output=True, timeout=3)
                time.sleep(0.1)

            time.sleep(5)

        # Also generate slow exfil
        for i in range(30):
            subprocess.run([
                'curl', '-s', '-o', '/dev/null',
                '-X', 'POST',
                '-d', f'slow_exfil_{i}',
                'http://localhost:8080/upload'
            ], capture_output=True, timeout=3)
            time.sleep(1)

        thread.join(timeout=10)

        if all_packets:
            wrpcap(str(BURST_PCAP), all_packets)
            print(f"\n  ✅ Burst capture: {len(all_packets)} packets → {BURST_PCAP}")

    # ── EXTRACT FEATURES ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("EXTRACTING FEATURES FROM PCAP FILES")
    print(f"{'='*70}")

    # Run extract_pcap_features.py
    extract_py = PROJECT_ROOT / "src" / "train" / "extract_pcap_features.py"
    if extract_py.exists():
        print(f"\nRunning: {extract_py}")
        result = subprocess.run(
            ['/opt/miniconda3/envs/exfil/bin/python', str(extract_py)],
            capture_output=True, text=True, timeout=300
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr[:500])
    else:
        print(f"  extract_pcap_features.py not found at {extract_py}")

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SELF-CAPTURE COMPLETE")
    print(f"{'='*70}")

    for pcap in [BASELINE_PCAP, BURST_PCAP]:
        if pcap.exists():
            size = pcap.stat().st_size
            print(f"  {pcap.name}: {size:,} bytes")
        else:
            print(f"  {pcap.name}: NOT FOUND")

    csv_path = PROJECT_ROOT / "data" / "self_captured" / "self_captured_features.csv"
    if csv_path.exists():
        import pandas as pd
        df = pd.read_csv(csv_path)
        print(f"\n  Feature CSV: {len(df)} flows")
        print(f"  Label dist: {df['Label'].value_counts().to_dict()}")


if __name__ == '__main__':
    run_self_capture()