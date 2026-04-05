#!/usr/bin/env python3
"""
src/self_capture/capture_and_generate_sudo.py — Self-capture dataset using sudo tcpdump.

macOS requires sudo for packet capture. This script:
  1. Checks if sudo tcpdump is available (calls out to bash for privilege)
  2. Starts HTTP servers (baseline + burst) in Docker
  3. Generates traffic from macOS via curl
  4. Captures using sudo tcpdump on lo0
  5. Extracts features using extract_pcap_features.py
"""

import subprocess
import time
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCENARIOS_DIR = PROJECT_ROOT / "data" / "self_captured" / "scenarios"
BASELINE_PCAP = SCENARIOS_DIR / "baseline" / "baseline.pcap"
BURST_PCAP    = SCENARIOS_DIR / "burst_exfil" / "burst_exfil.pcap"
SUDO_AVAILABLE = False

def check_sudo_tcpdump():
    """Test if sudo tcpdump works."""
    print("Checking sudo tcpdump availability...")
    result = subprocess.run(
        ['sudo', '-n', '/usr/sbin/tcpdump', '-i', 'lo0', '-c', '1', '-w', '/tmp/test.pcap'],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        print("  ✅ sudo tcpdump available (no password required)")
        return True
    else:
        print(f"  ⚠️  sudo tcpdump not available (needs password)")
        print(f"  Error: {result.stderr.strip()[:100]}")
        return False

def run_sudo_tcpdump(output_pcap: Path, duration_s: int, filter_str: str):
    """Run sudo tcpdump for capture."""
    print(f"  [sudo tcpdump] Starting capture: {output_pcap.name} ({duration_s}s) filter='{filter_str}'")

    cmd = [
        'sudo', '/usr/sbin/tcpdump',
        '-i', 'lo0',
        '-s', '96',
        '-w', str(output_pcap),
        '-G', str(duration_s),   # rotate every duration_s
        '-W', '1',                # only 1 file
        '-z', 'true',             # no post-rotate command
        filter_str
    ]

    print(f"  Running: sudo tcpdump -i lo0 -s 96 -w {output_pcap} -G {duration_s} {filter_str}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_s + 30)

    if result.returncode != 0 and 'signal' not in result.stderr.lower():
        print(f"  WARNING: {result.stderr.strip()[:200]}")

    size = output_pcap.stat().st_size if output_pcap.exists() else 0
    print(f"  Captured: {size:,} bytes")
    return size > 0


def generate_curl(port: int, method: str, path: str, data: str, label: str):
    """Generate single HTTP request via curl."""
    cmd = ['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', '-m', '5']
    if method == 'POST':
        cmd += ['-X', 'POST']
        cmd += ['-d', data]
    cmd.append(f'http://localhost:{port}{path}')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() == '200'
    except:
        return False


def generate_normal_requests(port: int, n: int, delay: float, label: str):
    """Generate normal GET requests."""
    print(f"  [{label}] Generating {n} GET requests to localhost:{port}...")
    ok = 0
    for i in range(n):
        if generate_curl(port, 'GET', '/', '', label):
            ok += 1
        time.sleep(delay)
    print(f"  [{label}] Done: {ok}/{n} successful")


def generate_burst_requests(port: int, n_per_round: int, n_rounds: int,
                            delay: float, label: str):
    """Generate burst POST requests (simulate exfil)."""
    print(f"  [{label}] Generating burst POST requests to localhost:{port}...")
    ok = 0
    for r in range(n_rounds):
        for i in range(n_per_round):
            # Random data simulating exfil
            data = f'exfil_chunk_{r}_{i}_ts{time.time_ns()}_payloadDATA'
            if generate_curl(port, 'POST', '/upload', data, label):
                ok += 1
            time.sleep(delay)
        print(f"  [{label}] Round {r+1}/{n_rounds} done ({ok} requests). Resting 3s...")
        time.sleep(3)

    # Slow exfil: 1 request/second
    print(f"  [{label}] Slow exfil: 30 requests at 1 req/s...")
    for i in range(30):
        data = f'slow_exfil_{i}_payload{i*100}'
        generate_curl(port, 'POST', '/upload', data, label)
        time.sleep(1)
    print(f"  [{label}] Burst complete: {ok} fast + 30 slow requests")


def run_self_capture():
    global SUDO_AVAILABLE

    print(f"\n{'='*70}")
    print("SELF-CAPTURE — Sudo tcpdump + Docker servers + macOS curl")
    print(f"{'='*70}")

    # Check sudo
    SUDO_AVAILABLE = check_sudo_tcpdump()

    # Ensure directories
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    (SCENARIOS_DIR / "baseline").mkdir(exist_ok=True)
    (SCENARIOS_DIR / "burst_exfil").mkdir(exist_ok=True)

    # ── Ensure servers are running ─────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("ENSURING HTTP SERVERS ARE RUNNING")
    print(f"{'─'*70}")

    result = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                             'http://localhost:8000/'], capture_output=True, text=True)
    baseline_ok = result.stdout.strip() == '200'
    print(f"  Baseline (8000): {'✅ running' if baseline_ok else '❌ not responding'}")

    result = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                             'http://localhost:8080/'], capture_output=True, text=True)
    burst_ok = result.stdout.strip() == '200'
    print(f"  Burst (8080):    {'✅ running' if burst_ok else '❌ not responding'}")

    if not baseline_ok or not burst_ok:
        print("\n  Starting servers via Docker...")
        # Kill existing
        subprocess.run(['docker', 'kill', 's_baseline', 's_burst'],
                        capture_output=True)
        subprocess.run(['docker', 'rm',   's_baseline', 's_burst'],
                        capture_output=True)
        # Start fresh
        subprocess.Popen(['docker', 'run', '-d', '--name', 's_baseline',
                          '-p', '8000:8000', 'python:3.11-slim',
                          'python3', '-m', 'http.server', '8000'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(['docker', 'run', '-d', '--name', 's_burst',
                          '-p', '8080:8000', 'python:3.11-slim',
                          'python3', '-m', 'http.server', '8000'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        print("  Servers started")

    # ── SCENARIO 1: Baseline ──────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("SCENARIO 1: Baseline Traffic (localhost:8000)")
    print(f"{'─'*70}")

    # Remove old capture
    if BASELINE_PCAP.exists():
        os.remove(BASELINE_PCAP)

    if SUDO_AVAILABLE:
        import threading

        # Start capture in background thread
        capture_thread = threading.Thread(
            target=run_sudo_tcpdump,
            args=(BASELINE_PCAP, 30, 'tcp port 8000'),
            daemon=True
        )
        capture_thread.start()
        time.sleep(1)  # Let tcpdump start

        # Generate traffic
        generate_normal_requests(8000, n=25, delay=0.8, label="baseline")

        capture_thread.join(timeout=35)
    else:
        print("  ⚠️  Skipping capture (no sudo)")
        # Just generate traffic without capture
        generate_normal_requests(8000, n=25, delay=0.8, label="baseline")

    # ── SCENARIO 2: Burst Exfil ───────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("SCENARIO 2: Burst Exfiltration (localhost:8080)")
    print(f"{'─'*70}")

    if BURST_PCAP.exists():
        os.remove(BURST_PCAP)

    if SUDO_AVAILABLE:
        import threading

        capture_thread = threading.Thread(
            target=run_sudo_tcpdump,
            args=(BURST_PCAP, 90, 'tcp port 8080'),
            daemon=True
        )
        capture_thread.start()
        time.sleep(1)

        # Fast burst
        generate_burst_requests(8080, n_per_round=50, n_rounds=3,
                                 delay=0.1, label="burst")

        capture_thread.join(timeout=95)
    else:
        print("  ⚠️  Skipping capture (no sudo)")
        generate_burst_requests(8080, n_per_round=50, n_rounds=3,
                                 delay=0.1, label="burst")

    # ── EXTRACT FEATURES ──────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("EXTRACTING FEATURES")
    print(f"{'─'*70}")

    for pcap in [BASELINE_PCAP, BURST_PCAP]:
        size = pcap.stat().st_size if pcap.exists() else 0
        print(f"  {pcap.name}: {size:,} bytes {'✅' if size > 0 else '❌ empty'}")

    if not SUDO_AVAILABLE:
        print("\n⚠️  No capture data. Run with sudo next time:")
        print("   sudo /opt/miniconda3/envs/exfil/bin/python src/self_capture/capture_and_generate_sudo.py")
        return

    extract_py = PROJECT_ROOT / "src" / "train" / "extract_pcap_features.py"
    if extract_py.exists() and (BASELINE_PCAP.exists() or BURST_PCAP.exists()):
        print(f"\nRunning feature extraction...")
        result = subprocess.run(
            ['/opt/miniconda3/envs/exfil/bin/python', str(extract_py)],
            capture_output=True, text=True, timeout=300
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr[:500])

    # ── SUMMARY ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("SELF-CAPTURE COMPLETE")
    print(f"{'='*70}")

    for pcap in [BASELINE_PCAP, BURST_PCAP]:
        size = pcap.stat().st_size if pcap.exists() else 0
        print(f"  {pcap.name}: {size:,} bytes")

    csv_path = PROJECT_ROOT / "data" / "self_captured" / "self_captured_features.csv"
    if csv_path.exists():
        import pandas as pd
        df = pd.read_csv(csv_path)
        print(f"\n  Feature CSV: {len(df)} flows")
        print(f"  Label dist: {df['Label'].value_counts().to_dict()}")
        print(f"  Scenario dist:\n{df['Scenario'].value_counts().to_string()}")


if __name__ == '__main__':
    run_self_capture()
