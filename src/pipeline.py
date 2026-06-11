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
    capture_host: str = None,
    model_path: str = None,
    scaler_path: str = None,
    window_size: float = WINDOW_SIZE,
    burst_threshold: float = None,
    enable_online_monitor: bool = False,
    online_threshold: float = 0.5,
    online_warmup_windows: int = 10,
):
    """
    Run the full detection pipeline.

    Args:
        offline_mode: Use PCAP file (True) or live interface (False)
        pcap_file: Path to PCAP file (for offline mode)
        capture_iface: Network interface name (for live mode)
        capture_host: Optional src/dst IP filter for focused demo capture
        model_path: Path to model file (.pkl or .h5)
        scaler_path: Path to scaler file (.pkl)
        window_size: Aggregation window size in seconds
        burst_threshold: Alert threshold for burst_exfil_score
    """
    import queue

    logger = get_logger("pipeline")
    logger.info("="*60)
    logger.info("EXFILTRATION DETECTION PIPELINE — STARTING")
    logger.info("="*60)
    logger.info(f"Mode: {'OFFLINE (PCAP)' if offline_mode else 'LIVE (interface)'}")
    logger.info(f"PCAP: {pcap_file}")
    logger.info(f"Interface: {capture_iface}")
    logger.info(f"Capture host: {capture_host}")
    logger.info(f"Model: {model_path}")
    logger.info(f"Window size: {window_size}s")
    logger.info(f"Burst threshold: {burst_threshold if burst_threshold is not None else 'default'}")
    logger.info(f"Online monitor: enabled={enable_online_monitor} threshold={online_threshold} warmup={online_warmup_windows}")

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
        capture_host=capture_host,
    )

    aggregator_thread = FeatureAggregatorThread(
        packet_queue=packet_queue,
        feature_queue=feature_queue,
        stop_event=stop_event,
        window_size=window_size,
    )

    inference_thread = InferenceThread(
        feature_queue=feature_queue,
        stop_event=stop_event,
        model_path=model_path,
        scaler_path=scaler_path,
        burst_threshold=burst_threshold,
        enable_online_monitor=enable_online_monitor,
        online_threshold=online_threshold,
        online_warmup_windows=online_warmup_windows,
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
            if not capture_thread.is_alive():
                if offline_mode:
                    logger.info("Capture thread finished — waiting for processing to complete...")
                    # Give aggregator time to flush remaining windows
                    time.sleep(window_size + 2)
                else:
                    logger.error("Live capture thread stopped unexpectedly — stopping pipeline")
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
          f"alerts={inf_stats['alerts_triggered']:,}  "
          f"online_anomalies={inf_stats.get('online_anomalies', 0):,}")
    if inf_stats.get("online_baselines_active"):
        print(f"[ONLINE]     baselines={inf_stats['online_baselines_active']:,}  "
              f"windows_processed={inf_stats.get('online_monitor_stats', {}).get('windows_processed', 0):,}")
    print(inf_stats.get("alert_summary", ""))

    logger.info("Pipeline stopped gracefully.")


def main():
    parser = argparse.ArgumentParser(
        description="HTTP Exfiltration Detection Pipeline "
                     "(offline-trained models + burst rules + online adaptive monitor)",
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
    parser.add_argument("--capture-host", type=str, default=None,
                      help="Only capture packets where src/dst IP matches this host")
    parser.add_argument("--model", type=str, default=None,
                      help="Path to model file (.pkl or .h5)")
    parser.add_argument("--scaler", type=str, default=None,
                      help="Path to scaler file (.pkl)")
    parser.add_argument("--window-size", type=float, default=WINDOW_SIZE,
                      help="Aggregation window size in seconds")
    parser.add_argument("--burst-threshold", type=float, default=None,
                      help="Alert threshold for burst_exfil_score")
    parser.add_argument("--enable-online-monitor", action="store_true",
                      help="Enable the online anomaly monitor (detects unknown/new patterns)")
    parser.add_argument("--online-threshold", type=float, default=0.5,
                      help="Alert threshold for online anomaly score (0-1) [default: 0.5]")
    parser.add_argument("--online-warmup-windows", type=int, default=10,
                      help="Normal windows needed before online scoring starts [default: 10]")
    parser.add_argument("--debug", action="store_true",
                      help="Enable DEBUG logging")

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    setup_logging(log_level)

    # Determine mode. Explicit CLI flags must override config defaults.
    if args.live:
        offline = False
    elif args.offline:
        offline = True
    else:
        offline = OFFLINE_MODE
    pcap = args.pcap or str(PCAP_FILE)
    iface = args.iface or CAPTURE_IFACE

    run_pipeline(
        offline_mode=offline,
        pcap_file=pcap,
        capture_iface=iface,
        capture_host=args.capture_host,
        model_path=args.model,
        scaler_path=args.scaler,
        window_size=args.window_size,
        burst_threshold=args.burst_threshold,
        enable_online_monitor=args.enable_online_monitor,
        online_threshold=args.online_threshold,
        online_warmup_windows=args.online_warmup_windows,
    )


if __name__ == "__main__":
    main()
