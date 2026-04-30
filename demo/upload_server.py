#!/usr/bin/env python3
"""Minimal local HTTP upload receiver for the exfiltration demo."""

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import time


UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class UploadHandler(BaseHTTPRequestHandler):
    discard_payload = False
    upload_dir = UPLOAD_DIR

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK\n")

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(content_length)

        if not self.discard_payload:
            output_path = self.upload_dir / f"upload_{time.time_ns()}.bin"
            output_path.write_bytes(payload)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"uploaded\n")

    def log_message(self, fmt, *args):
        print(f"[upload-server] {self.address_string()} - {fmt % args}")


def main():
    parser = argparse.ArgumentParser(description="Local HTTP upload receiver for demo traffic.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--discard-payload", action="store_true",
                        help="Read request bodies but do not save payload bytes to disk")
    parser.add_argument("--upload-dir", default=str(UPLOAD_DIR))
    args = parser.parse_args()

    UploadHandler.discard_payload = args.discard_payload
    UploadHandler.upload_dir = Path(args.upload_dir)
    UploadHandler.upload_dir.mkdir(parents=True, exist_ok=True)

    print(f"Upload server listening at http://{args.host}:{args.port}/upload")
    if args.discard_payload:
        print("Discarding uploaded payloads after reading request bodies")
    else:
        print(f"Saving uploaded payloads to {UploadHandler.upload_dir}")
    HTTPServer((args.host, args.port), UploadHandler).serve_forever()


if __name__ == "__main__":
    main()
