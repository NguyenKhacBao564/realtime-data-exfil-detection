#!/usr/bin/env python3
"""
lab/server/receiver.py — Simple HTTP server that accepts POST requests.

This is a DEMO server for the exfiltration detection lab.
It logs REQUEST METADATA ONLY — no real content is stored.

Stored metadata per request:
  - timestamp
  - source IP (from connection)
  - content length
  - headers (X-Session-ID, X-Mode, etc.)
  - SHA256 of content (for size verification only — content discarded immediately)

No user files, secrets, credentials, or payload content are stored.

Usage:
  python receiver.py --port 8000
"""

import argparse
import hashlib
import logging
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from typing import Optional

# Configure logging (stream only — file handler added in main if writable)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("exfil-server")


class ExfilRequestHandler(BaseHTTPRequestHandler):
    """
    Handles HTTP POST /upload and GET /browse requests.

    Security properties:
    - Payload content is read and immediately discarded (not stored)
    - Only metadata is logged
    - Content-Length is enforced to prevent memory exhaustion
    - Requests are rate-limited by the OS/HTTP server
    """

    # Suppress default request logging to keep output clean
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        """Handle GET /browse — health check / normal browsing simulation."""
        if self.path.startswith("/browse"):
            logger.info(
                f"GET {self.path} from={self.client_address[0]}:{self.client_address[1]} "
                f"agent={self.headers.get('User-Agent', 'unknown')}"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>OK</h1></body></html>")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        """Handle POST /upload — log metadata, discard content."""
        timestamp = datetime.utcnow().isoformat()
        content_length = int(self.headers.get("Content-Length", 0))
        client_ip = self.client_address[0]
        client_port = self.client_address[1]

        # Reject unreasonably large uploads (memory safety)
        MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
        if content_length > MAX_CONTENT_LENGTH:
            logger.warning(
                f"POST /upload from={client_ip}:{client_port} "
                f"REJECTED content_length={content_length} (exceeds {MAX_CONTENT_LENGTH})"
            )
            self.send_response(413)
            self.end_headers()
            self.wfile.write(b"Payload too large")
            return

        # Read content safely
        content_bytes = b""
        try:
            if content_length > 0:
                content_bytes = self.rfile.read(content_length)
        except Exception as e:
            logger.error(f"POST /upload from={client_ip}:{client_port} read error: {e}")
            self.send_response(400)
            self.end_headers()
            return

        # Compute SHA256 of content (for logging only — no content stored)
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        # Extract relevant headers
        session_id = self.headers.get("X-Session-ID", "N/A")
        mode = self.headers.get("X-Mode", "N/A")
        chunk_id = self.headers.get("X-Chunk-ID", self.headers.get("X-Seq", "N/A"))

        # Log METADATA ONLY — no payload content
        logger.info(
            f"POST /upload from={client_ip}:{client_port} "
            f"size={content_length:,} bytes "
            f"session={session_id} "
            f"mode={mode} "
            f"chunk={chunk_id} "
            f"sha256={content_hash[:16]}..."
        )

        # Respond with minimal acknowledgment
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Received-Size", str(content_length))
        self.end_headers()
        response = f'{{"status":"ok","size":{content_length},"hash":"{content_hash[:16]}"}}'
        self.wfile.write(response.encode())

    def do_HEAD(self):
        """Handle HEAD /upload — quick connectivity check."""
        self.send_response(200)
        self.end_headers()


class SilentLoggingHTTPServer(HTTPServer):
    """Suppress default HTTP server logging."""

    def handle_error(self, request, client_address):
        # Log non-fatal errors but don't spam stderr
        logger.error(f"Handler error from {client_address}: {sys.exc_info()[1]}")


def main():
    parser = argparse.ArgumentParser(
        description="Simple HTTP server for exfiltration detection lab demo. "
                    "Logs METADATA ONLY — no content stored.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on [default: 8000]",
    )
    parser.add_argument(
        "--bind",
        default="0.0.0.0",
        help="Bind address [default: 0.0.0.0]",
    )
    parser.add_argument(
        "--max-upload",
        type=int,
        default=10 * 1024 * 1024,
        help="Max upload size in bytes [default: 10MB]",
    )

    args = parser.parse_args()

    ExfilRequestHandler.MAX_CONTENT_LENGTH = args.max_upload

    server_address = (args.bind, args.port)

    # Add file handler if /var/log is writable
    try:
        fh = logging.FileHandler("/var/log/exfil-server.log", mode="a")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
    except PermissionError:
        logger.warning("/var/log/exfil-server.log not writable — logging to stdout only")

    httpd = SilentLoggingHTTPServer(server_address, ExfilRequestHandler)

    logger.info(f"=" * 60)
    logger.info("EXFILTRATION DETECTION LAB — DEMO SERVER")
    logger.info("=" * 60)
    logger.info(f"Listening on {args.bind}:{args.port}")
    logger.info("POST /upload — accepts uploads, logs METADATA only")
    logger.info("GET  /browse  — health check / browsing simulation")
    logger.info("Ctrl+C to stop")
    logger.info("=" * 60)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
