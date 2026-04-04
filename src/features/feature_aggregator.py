"""
src/features/feature_aggregator.py — Thread 2: Feature Aggregation.
Buffers packets per source IP, flushes every WINDOW_SIZE seconds.
"""

import threading
import time
import logging
from typing import Dict, List
from collections import defaultdict
from src.utils.config import WINDOW_SIZE, MIN_PACKETS_PER_WINDOW
from src.utils.helpers import get_logger

logger = get_logger("aggregator")


class FeatureAggregatorThread(threading.Thread):
    """
    Thread 2: Aggregates raw packets into windowed feature vectors.

    Algorithm:
      - Buffer packets per src_ip
      - Every WINDOW_SIZE seconds, flush all buffers → extract features → push to feature_queue
      - Skip IPs with fewer than MIN_PACKETS_PER_WINDOW packets
    """

    def __init__(
        self,
        packet_queue,
        feature_queue,
        stop_event: threading.Event,
        window_size: float = WINDOW_SIZE,
        min_packets: int = MIN_PACKETS_PER_WINDOW,
    ):
        super().__init__(name="FeatureAggregator", daemon=True)
        self.packet_queue = packet_queue
        self.feature_queue = feature_queue
        self.stop_event = stop_event
        self.window_size = window_size
        self.min_packets = min_packets

        # Per-IP packet buffers
        # Structure: {src_ip: {"packets": [...], "window_start": timestamp}}
        self._buffers: Dict[str, dict] = defaultdict(lambda: {"packets": [], "window_start": None})
        self._lock = threading.Lock()

        # Statistics
        self.stats = {
            "windows_created": 0,
            "windows_skipped": 0,
            "total_packets_processed": 0,
            "start_time": None,
        }

    def run(self):
        """Main loop — reads from packet_queue, buffers, flushes."""
        logger.info(f"[AGGREGATOR] Thread starting — window_size={self.window_size}s, min_packets={self.min_packets}")
        self.stats["start_time"] = time.time()

        last_flush = time.time()

        while not self.stop_event.is_set():
            try:
                # Try to get a packet (with timeout)
                try:
                    pkt = self.packet_queue.get(timeout=0.5)
                except Exception:
                    # No packet available — check if we should flush
                    now = time.time()
                    if now - last_flush >= self.window_size:
                        self._flush_all(now)
                        last_flush = now
                    continue

                # Process packet
                self._add_packet(pkt)

                # Check if we should flush
                now = time.time()
                if now - last_flush >= self.window_size:
                    self._flush_all(now)
                    last_flush = now

            except Exception as e:
                logger.error(f"[AGGREGATOR] Error: {e}")
                time.sleep(1)

        # Flush remaining on shutdown
        logger.info("[AGGREGATOR] Shutdown — flushing remaining buffers...")
        self._flush_all(time.time())

        elapsed = time.time() - (self.stats["start_time"] or time.time())
        logger.info(f"[AGGREGATOR] Thread stopped. "
                    f"windows={self.stats['windows_created']} "
                    f"skipped={self.stats['windows_skipped']} "
                    f"packets={self.stats['total_packets_processed']}")

    def _add_packet(self, pkt: dict):
        """Add a packet to the appropriate IP buffer."""
        src_ip = pkt.get("src_ip", "unknown")

        with self._lock:
            buf = self._buffers[src_ip]

            # Initialize window start on first packet
            if buf["window_start"] is None:
                buf["window_start"] = pkt.get("timestamp", time.time())

            buf["packets"].append(pkt)
            self.stats["total_packets_processed"] += 1

    def _flush_all(self, flush_time: float):
        """Flush all IP buffers, extract features, push to feature_queue."""
        with self._lock:
            buffers_snapshot = dict(self._buffers)
            self._buffers.clear()

        for src_ip, buf in buffers_snapshot.items():
            packets = buf["packets"]
            window_start = buf["window_start"]

            if len(packets) < self.min_packets:
                self.stats["windows_skipped"] += 1
                continue

            # Import here to avoid circular import
            from src.features.window_features import extract_window_features

            features = extract_window_features(packets, src_ip, window_start)
            if features is None:
                self.stats["windows_skipped"] += 1
                continue

            features["window_end"] = flush_time

            # Push to feature queue (non-blocking)
            try:
                self.feature_queue.put_nowait(features)
                self.stats["windows_created"] += 1
            except Exception:
                logger.warning(f"[AGGREGATOR] Feature queue full — dropped window for {src_ip}")

    def get_stats(self) -> dict:
        """Get aggregator statistics."""
        with self._lock:
            n_buffers = len(self._buffers)
        stats = self.stats.copy()
        stats["active_buffers"] = n_buffers
        return stats
