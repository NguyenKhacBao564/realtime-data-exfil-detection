#!/usr/bin/env python3
"""
lab/victim/generate_http_traffic.py — Synthetic HTTP traffic generator for lab demo.

Generates dummy traffic only. No real user data, secrets, or credentials are used.

Modes:
  normal   — Irregular low/medium rate, small payloads. Mimics human browsing.
  exfil    — Burst of large synthetic uploads. Mimics data exfiltration.
  slow-drip — Small repeated uploads with regular timing. Mimics unknown/covert channel.

Usage:
  python generate_http_traffic.py --mode normal --server http://exfil-server:8000
  python generate_http_traffic.py --mode exfil  --server http://exfil-server:8000
  python generate_http_traffic.py --mode slow-drip --server http://exfil-server:8000
"""

import argparse
import random
import sys
import time
import hashlib

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed. Run: pip install requests")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Payload generators — synthetic only, no real data
# ---------------------------------------------------------------------------

DUMMY_WORDS = [
    "lorem", "ipsum", "dolor", "sit", "amet", "consectetur",
    "adipiscing", "elit", "sed", "do", "eiusmod", "tempor",
    "incididunt", "ut", "labore", "et", "dolore", "magna", "aliqua",
]

DUMMY_HEX = "0123456789ABCDEF"


def make_dummy_payload(size_bytes: int) -> bytes:
    """Generate a deterministic but meaningless payload of exact size."""
    # Use repeatable pattern — no real content
    return (DUMMY_HEX * ((size_bytes // 16) + 1))[:size_bytes].encode()


def make_text_payload(size_bytes: int) -> str:
    """Generate dummy text payload of approximate size."""
    words = []
    current = 0
    while current < size_bytes:
        word = random.choice(DUMMY_WORDS)
        words.append(word)
        current += len(word) + 1
    return " ".join(words)[:size_bytes]


# ---------------------------------------------------------------------------
# Traffic modes
# ---------------------------------------------------------------------------

def send_normal_traffic(server_url: str, duration: int, session_id: str):
    """
    Normal browsing: irregular timing, small payloads, mixed GET/POST.
    """
    print(f"[NORMAL] Starting normal traffic to {server_url} for {duration}s")
    print(f"[NORMAL] Session: {session_id}")

    end_time = time.time() + duration
    request_count = 0

    while time.time() < end_time:
        method = random.choices(["GET", "POST"], weights=[0.7, 0.3])[0]

        if method == "GET":
            payload = None
            url = f"{server_url}/browse?" + f"page={random.randint(1,100)}&t={time.time()}"
        else:
            # Small payload — normal upload
            size = random.randint(100, 2000)
            payload = make_text_payload(size)
            url = f"{server_url}/upload"

        try:
            resp = requests.post(
                url,
                data=payload,
                headers={
                    "X-Session-ID": session_id,
                    "X-Mode": "normal",
                    "Content-Type": "text/plain",
                },
                timeout=5,
            )
            request_count += 1
            if request_count % 20 == 0:
                print(f"[NORMAL] req={request_count} status={resp.status_code}")
        except Exception as e:
            print(f"[NORMAL] Request failed: {e}")

        # Irregular sleep — human-like
        time.sleep(random.uniform(0.5, 5.0))

    print(f"[NORMAL] Finished. Total requests: {request_count}")


def send_exfil_traffic(server_url: str, duration: int, session_id: str):
    """
    Simulated exfiltration: burst of large synthetic uploads.
    This mimics an attacker uploading stolen data via HTTP POST.
    """
    print(f"[EXFIL]  Starting EXFILTRATION simulation to {server_url} for {duration}s")
    print(f"[EXFIL]  Session: {session_id}")
    print("[EXFIL]  WARNING: This is synthetic academic demo traffic only!")

    end_time = time.time() + duration
    request_count = 0
    total_bytes = 0

    while time.time() < end_time:
        # Large payload — typical exfil pattern
        size = random.randint(50_000, 500_000)  # 50KB–500KB per request
        payload = make_dummy_payload(size)

        try:
            resp = requests.post(
                f"{server_url}/upload",
                data=payload,
                headers={
                    "X-Session-ID": session_id,
                    "X-Mode": "exfil",
                    "X-Chunk-ID": str(request_count),
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(size),
                },
                timeout=10,
            )
            request_count += 1
            total_bytes += size

            if request_count % 5 == 0:
                elapsed = time.time() - (end_time - duration)
                rate = total_bytes / max(elapsed, 1) / 1024
                print(
                    f"[EXFIL]  req={request_count} bytes={total_bytes:,} "
                    f"rate={rate:.1f}KB/s status={resp.status_code}"
                )
        except Exception as e:
            print(f"[EXFIL]  Request failed: {e}")

        # Short sleep between bursts — automated tool pattern
        time.sleep(random.uniform(0.05, 0.3))

    print(f"[EXFIL]  Finished. Total requests: {request_count}, bytes: {total_bytes:,}")


def send_slow_drip(server_url: str, duration: int, session_id: str):
    """
    Slow drip exfiltration: small regular uploads mimicking a covert channel.
    This is designed to be hard to detect by traditional threshold-based systems.
    """
    print(f"[DRIP]   Starting SLOW DRIP simulation to {server_url} for {duration}s")
    print(f"[DRIP]   Session: {session_id}")
    print("[DRIP]   WARNING: This is synthetic academic demo traffic only!")

    end_time = time.time() + duration
    request_count = 0
    total_bytes = 0

    while time.time() < end_time:
        # Small but consistent payload — typical slow exfil
        size = random.randint(5000, 15000)  # 5–15KB per request
        payload = make_dummy_payload(size)

        try:
            resp = requests.post(
                f"{server_url}/upload",
                data=payload,
                headers={
                    "X-Session-ID": session_id,
                    "X-Mode": "slow-drip",
                    "X-Seq": str(request_count),
                    "Content-Type": "application/octet-stream",
                },
                timeout=5,
            )
            request_count += 1
            total_bytes += size

            if request_count % 20 == 0:
                elapsed = time.time() - (end_time - duration)
                rate = total_bytes / max(elapsed, 1) / 1024
                print(
                    f"[DRIP]   req={request_count} bytes={total_bytes:,} "
                    f"rate={rate:.1f}KB/s status={resp.status_code}"
                )
        except Exception as e:
            print(f"[DRIP]   Request failed: {e}")

        # Very regular interval — 2–4 seconds, simulating a scheduled task
        time.sleep(random.uniform(2.0, 4.0))

    print(f"[DRIP]   Finished. Total requests: {request_count}, bytes: {total_bytes:,}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Synthetic HTTP traffic generator for lab demo. "
                    "ALL payloads are dummy bytes — no real data.",
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "exfil", "slow-drip"],
        default="normal",
        help="Traffic mode (normal=human-like, exfil=burst upload, slow-drip=regular small uploads)",
    )
    parser.add_argument(
        "--server",
        default="http://exfil-server:8000",
        help="Base URL of the exfil server [default: http://exfil-server:8000]",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds [default: 60]",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session ID (auto-generated if not provided)",
    )

    args = parser.parse_args()

    # Generate a repeatable but meaningless session ID
    if args.session_id is None:
        args.session_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:16]

    if args.mode == "normal":
        send_normal_traffic(args.server, args.duration, args.session_id)
    elif args.mode == "exfil":
        send_exfil_traffic(args.server, args.duration, args.session_id)
    elif args.mode == "slow-drip":
        send_slow_drip(args.server, args.duration, args.session_id)


if __name__ == "__main__":
    main()
