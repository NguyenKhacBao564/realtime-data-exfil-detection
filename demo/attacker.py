#!/usr/bin/env python3
"""Controlled HTTP POST burst generator for the local exfiltration demo."""

import argparse
import os
import time
from urllib.request import Request, urlopen


def post_payload(url: str, payload: bytes) -> int:
    request = Request(url, data=payload, method="POST")
    with urlopen(request, timeout=5) as response:
        response.read()
        return response.status


def main():
    parser = argparse.ArgumentParser(description="Generate demo HTTP exfiltration traffic.")
    parser.add_argument("--url", default="http://127.0.0.1:8080/upload")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--bytes", type=int, default=50_000)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()

    print(
        f"Sending {args.requests} POST requests to {args.url} "
        f"({args.bytes} bytes/request, {args.delay}s delay)"
    )

    ok = 0
    for i in range(args.requests):
        payload = os.urandom(args.bytes)
        status = post_payload(args.url, payload)
        ok += int(status == 200)
        print(f"{i + 1:03d}/{args.requests} status={status} bytes={len(payload)}")
        time.sleep(args.delay)

    print(f"Done: {ok}/{args.requests} successful requests")


if __name__ == "__main__":
    main()
