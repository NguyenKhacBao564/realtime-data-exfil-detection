"""
src/capture/packet_capture.py — Thread 1: Packet Capture.
Sniffs packets from network interface or PCAP file and pushes to packet_queue.
"""

import threading
import time
import logging
from typing import Optional

from scapy.all import sniff

from src.capture.packet_parser import parse_packet, is_http_port
from src.utils.config import (
    CAPTURE_IFACE, OFFLINE_MODE, PCAP_FILE, HTTP_PORTS, PACKET_QUEUE_SIZE
)
from src.utils.helpers import get_logger

logger = get_logger("capture")


def stop_filter(pkt):
    """Filter used by scapy sniff() to check stop_event."""
    # The actual stop check happens in the callback
    return False  # Never stop sniff() itself — we handle stop via stop_event in callback


def packet_callback(pkt_dict: Optional[dict], packet_queue, stop_event: threading.Event, capture_stats: dict):
    """
    Callback for each sniffed packet.
    Parses packet → pushes to queue.

    Args:
        pkt_dict: Scapy packet (set dynamically via closure)
        packet_queue: queue.Queue to push packets to
        stop_event: threading.Event to check for shutdown
        capture_stats: dict to track statistics (shared across threads)
    """
    # This function signature is just for reference — actual callback is a closure
    pass


class PacketCaptureThread(threading.Thread):
    """
    Thread 1: Captures packets and pushes to packet_queue.

    Modes:
      - Offline: reads from PCAP file (default)
      - Live: sniffs from network interface
    """

    def __init__(
        self,
        packet_queue,
        stop_event: threading.Event,
        capture_iface: Optional[str] = None,
        offline_mode: bool = True,
        pcap_file: Optional[str] = None,
        http_only: bool = True,
    ):
        super().__init__(name="PacketCapture", daemon=True)
        self.packet_queue = packet_queue
        self.stop_event = stop_event
        self.capture_iface = capture_iface or CAPTURE_IFACE
        self.offline_mode = offline_mode
        self.pcap_file = str(pcap_file or PCAP_FILE)
        self.http_only = http_only

        # Statistics
        self.stats = {
            "packets_seen": 0,
            "packets_queued": 0,
            "packets_skipped": 0,
            "parse_errors": 0,
            "start_time": None,
            "end_time": None,
        }

        self._lock = threading.Lock()

    def run(self):
        """Main loop — starts packet capture."""
        logger.info(f"[CAPTURE] Thread starting — mode={'offline' if self.offline_mode else 'live'}")
        if self.offline_mode:
            logger.info(f"[CAPTURE] PCAP file: {self.pcap_file}")
        else:
            logger.info(f"[CAPTURE] Interface: {self.capture_iface}")

        self.stats["start_time"] = time.time()

        try:
            if self.offline_mode:
                self._run_offline()
            else:
                self._run_live()
        except Exception as e:
            logger.error(f"[CAPTURE] Error: {e}")

        self.stats["end_time"] = time.time()
        logger.info(f"[CAPTURE] Thread stopped. "
                    f"seen={self.stats['packets_seen']} "
                    f"queued={self.stats['packets_queued']} "
                    f"skipped={self.stats['packets_skipped']}")

    def _run_offline(self):
        """Read packets from PCAP file."""
        import os
        if not os.path.exists(self.pcap_file):
            logger.error(f"[CAPTURE] PCAP file not found: {self.pcap_file}")
            return

        # Build BPF filter for HTTP ports
        port_filter = " or ".join(f"port {p}" for p in HTTP_PORTS)
        bpf_filter = f"tcp ({port_filter})"

        logger.info(f"[CAPTURE] BPF filter: {bpf_filter}")

        def _callback(pkt):
            """Process each packet from PCAP."""
            if self.stop_event.is_set():
                return

            self.stats["packets_seen"] += 1

            # Parse packet
            pkt_dict = parse_packet(pkt)
            if pkt_dict is None:
                self.stats["parse_errors"] += 1
                return

            # Optional HTTP port filter
            if self.http_only:
                if pkt_dict["dst_port"] not in HTTP_PORTS and pkt_dict["src_port"] not in HTTP_PORTS:
                    self.stats["packets_skipped"] += 1
                    return

            # Push to queue (non-blocking)
            try:
                self.packet_queue.put_nowait(pkt_dict)
                self.stats["packets_queued"] += 1
            except Exception:
                # Queue full — skip packet
                self.stats["packets_skipped"] += 1
                if self.stats["packets_skipped"] % 1000 == 0:
                    logger.warning(f"[CAPTURE] Queue full — skipped {self.stats['packets_skipped']} packets")

        sniff(
            offline=self.pcap_file,
            prn=_callback,
            store=False,
            verbose=0,
        )

    def _run_live(self):
        """Sniff from live network interface."""
        port_filter = " or ".join(f"port {p}" for p in HTTP_PORTS)
        bpf_filter = f"tcp ({port_filter})"

        def _callback(pkt):
            if self.stop_event.is_set():
                return

            self.stats["packets_seen"] += 1

            pkt_dict = parse_packet(pkt)
            if pkt_dict is None:
                self.stats["parse_errors"] += 1
                return

            try:
                self.packet_queue.put_nowait(pkt_dict)
                self.stats["packets_queued"] += 1
            except Exception:
                self.stats["packets_skipped"] += 1
                if self.stats["packets_skipped"] % 1000 == 0:
                    logger.warning(f"[CAPTURE] Queue full — skipped {self.stats['packets_skipped']} packets")

        sniff(
            iface=self.capture_iface,
            prn=_callback,
            filter=bpf_filter,
            store=False,
            verbose=0,
            stop_filter=lambda _: self.stop_event.is_set(),
        )

    def get_stats(self) -> dict:
        """Get capture statistics."""
        with self._lock:
            stats = self.stats.copy()
        elapsed = (stats["end_time"] or time.time()) - (stats["start_time"] or time.time())
        stats["elapsed_seconds"] = elapsed
        if elapsed > 0:
            stats["packets_per_second"] = stats["packets_seen"] / elapsed
        return stats
