"""
src/pipeline.py — Main pipeline orchestration.
Starts 3 threads, monitors queues, handles graceful shutdown.

Usage:
    python src/pipeline.py --offline --pcap data/raw/Friday-WorkingHours.pcap
    python src/pipeline.py --live --iface eth0
"""

import argparse
import queue
import signal
import sys
import threading
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import (
    PACKET_QUEUE_SIZE, FEATURE_QUEUE_SIZE,
    OFFLINE_MODE, PCAP_FILE, CAPTURE_IFACE,
    WINDOW_SIZE,
)
from src.utils.helpers import setup_logging, get_logger


def monitor_queues(
    packet_queue: queue.Queue,
    feature_queue: queue.Queue,
    stop_event: threading.Event,
    interval: float = 5.0,
):
    """Print queue sizes every interval seconds."""
    logger = get_logger("monitor")
    start = time.time()
    while not stop_event.is_set():
        time.sleep(interval)
        elapsed = time.time() - start
        pq_size = packet_queue.qsize()
        fq_size = feature_queue.qsize()
        print(
            f"[{elapsed:6.1f}s] "
            f"packet_queue={pq_size}/{PACKET_QUEUE_SIZE}  "
            f"feature_queue={fq_size}/{FEATURE_QUEUE_SIZE}",
            flush=True,
        )


def run_pipeline(
    offline_mode: bool = True,
    pcap_file: str = None,
    capture_iface: str = None,
    model_path: str = None,
    scaler_path: str = None,
):
    """
    Run the full detection pipeline.

    Args:
        offline_mode: Use PCAP file (True) or live interface (False)
        pcap_file: Path to PCAP file (for offline mode)
        capture_iface: Network interface name (for live mode)
        model_path: Path to model file (.pkl or .h5)
        scaler_path: Path to scaler file (.pkl)
    """
    import queue

    logger = get_logger("pipeline")
    logger.info("="*60)
    logger.info("EXFILTRATION DETECTION PIPELINE — STARTING")
    logger.info("="*60)
    logger.info(f"Mode: {'OFFLINE (PCAP)' if offline_mode else 'LIVE (interface)'}")
    logger.info(f"PCAP: {pcap_file}")
    logger.info(f"Interface: {capture_iface}")
    logger.info(f"Model: {model_path}")
    logger.info(f"Window size: {WINDOW_SIZE}s")

    # Shared state
    packet_queue = queue.Queue(maxsize=PACKET_QUEUE_SIZE)
    feature_queue = queue.Queue(maxsize=FEATURE_QUEUE_SIZE)
    stop_event = threading.Event()

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.warning("Shutdown signal received — stopping pipeline...")
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Import thread classes
    from src.capture.packet_capture import PacketCaptureThread
    from src.features.feature_aggregator import FeatureAggregatorThread
    from src.inference.model_inference import InferenceThread

    # Create threads
    capture_thread = PacketCaptureThread(
        packet_queue=packet_queue,
        stop_event=stop_event,
        offline_mode=offline_mode,
        pcap_file=pcap_file,
        capture_iface=capture_iface,
    )

    aggregator_thread = FeatureAggregatorThread(
        packet_queue=packet_queue,
        feature_queue=feature_queue,
        stop_event=stop_event,
    )

    inference_thread = InferenceThread(
        feature_queue=feature_queue,
        stop_event=stop_event,
        model_path=model_path,
        scaler_path=scaler_path,
    )

    # Start all threads
    logger.info("Starting threads...")
    capture_thread.start()
    aggregator_thread.start()
    inference_thread.start()

    # Start queue monitor in main thread
    monitor_thread = threading.Thread(
        target=monitor_queues,
        args=(packet_queue, feature_queue, stop_event),
        daemon=True,
    )
    monitor_thread.start()

    # Wait for threads to finish
    logger.info("Pipeline running — press Ctrl+C to stop")
    try:
        while not stop_event.is_set():
            # Check if capture thread has finished (for offline mode)
            if offline_mode and not capture_thread.is_alive():
                logger.info("Capture thread finished — waiting for processing to complete...")
                # Give aggregator time to flush remaining windows
                time.sleep(WINDOW_SIZE + 2)
                stop_event.set()
                break
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()

    # Wait for threads to finish
    logger.info("Waiting for threads to finish...")
    for t in [capture_thread, aggregator_thread, inference_thread]:
        t.join(timeout=10)
        if t.is_alive():
            logger.warning(f"  {t.name} did not finish in time")

    # Print final stats
    print("\n" + "="*60)
    print("FINAL STATISTICS")
    print("="*60)

    cap_stats = capture_thread.get_stats()
    print(f"[CAPTURE]     seen={cap_stats['packets_seen']:,}  "
          f"queued={cap_stats['packets_queued']:,}  "
          f"skipped={cap_stats['packets_skipped']:,}")

    agg_stats = aggregator_thread.get_stats()
    print(f"[AGGREGATOR] windows={agg_stats['windows_created']:,}  "
          f"skipped={agg_stats['windows_skipped']:,}")

    inf_stats = inference_thread.get_stats()
    print(f"[INFERENCE]  processed={inf_stats['windows_processed']:,}  "
          f"alerts={inf_stats['alerts_triggered']:,}")
    print(inf_stats.get("alert_summary", ""))

    logger.info("Pipeline stopped gracefully.")


def main():
    parser = argparse.ArgumentParser(
        description="HTTP Exfiltration Detection Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true",
                      help="Run in offline mode (read PCAP file)")
    mode.add_argument("--live", action="store_true",
                      help="Run in live mode (sniff network interface)")
    parser.add_argument("--pcap", type=str, default=None,
                      help="Path to PCAP file (offline mode)")
    parser.add_argument("--iface", type=str, default=None,
                      help="Network interface name (live mode)")
    parser.add_argument("--model", type=str, default=None,
                      help="Path to model file (.pkl or .h5)")
    parser.add_argument("--scaler", type=str, default=None,
                      help="Path to scaler file (.pkl)")
    parser.add_argument("--debug", action="store_true",
                      help="Enable DEBUG logging")

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(log_level)

    # Determine mode
    offline = args.offline or OFFLINE_MODE
    pcap = args.pcap or str(PCAP_FILE)
    iface = args.iface or CAPTURE_IFACE

    run_pipeline(
        offline_mode=offline,
        pcap_file=pcap,
        capture_iface=iface,
        model_path=args.model,
        scaler_path=args.scaler,
    )


if __name__ == "__main__":
    main()
