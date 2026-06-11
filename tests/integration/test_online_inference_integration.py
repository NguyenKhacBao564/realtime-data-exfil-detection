"""
tests/integration/test_online_inference_integration.py — Integration tests
for OnlineAnomalyMonitor within the InferenceThread.

Tests the wiring between online_monitor.evaluate() and alert_logger.log_alert()
to ensure alert triggers, reason codes, and scores are all propagated correctly.
"""

import pytest
import sys
import threading
import time
import queue
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.inference.online_anomaly_monitor import OnlineAnomalyMonitor
from src.inference.alert_logger import AlertLogger, format_alert


def make_features(src_ip="10.0.0.1", **overrides):
    """Minimal valid feature dict for runtime."""
    defaults = {
        "request_count": 20,
        "total_fwd_bytes": 5000,
        "total_bwd_bytes": 10000,
        "total_bytes": 15000,
        "upload_download_ratio": 0.5,
        "burst_count": 2,
        "burst_ratio": 0.1,
        "unusual_port_ratio": 0.0,
        "request_rate": 0.5,
        "inter_request_time_mean": 1.5,
        "inter_request_time_std": 0.5,
        "mean_payload_size": 250.0,
        "std_payload_size": 50.0,
        "psh_flag_count": 10,
        "ack_flag_count": 20,
        "syn_flag_count": 2,
        "window_duration": 40.0,
        "unique_destinations": 1,
        "src_ip": src_ip,
        "window_start": time.time() - 60,
    }
    defaults.update(overrides)
    return defaults


class TestOnlineMonitorAlertIntegration:
    """Test that online monitor results are correctly passed to alert_logger."""

    def test_format_alert_with_online_fields(self):
        """format_alert should render online fields when provided."""
        alert_str = format_alert(
            features=make_features(),
            burst_score=0.3,
            model_score=0.4,
            prediction=0,
            severity="HIGH",
            online_score=0.8,
            online_prediction=1,
            online_reason_codes=["HIGH_Z: upload_download_ratio=4.7σ", "warmup done"],
            baseline_count=15,
            alert_triggers=["BURST_RULE", "ONLINE_UNKNOWN_ANOMALY"],
            color=False,
        )
        assert "Online score:" in alert_str
        assert "BURST_RULE" in alert_str
        assert "ONLINE_UNKNOWN_ANOMALY" in alert_str
        assert "ANOMALY" in alert_str
        assert "Baseline n:" in alert_str

    def test_format_alert_without_online_fields(self):
        """format_alert should still work without online fields (backward compat)."""
        alert_str = format_alert(
            features=make_features(),
            burst_score=0.8,
            severity="HIGH",
            color=False,
        )
        assert "BURST_RULE" not in alert_str
        assert "Online score:" not in alert_str
        assert "Burst score:   0.800" in alert_str

    def test_full_alert_chain_with_all_triggers(self):
        """Simulate a full alert chain: online anomaly triggers."""
        features = make_features(
            upload_download_ratio=300.0,
            burst_count=200,
            total_bytes=500000,
            request_count=500,
        )

        # Online monitor warmup + evaluation (use variable upload_ratio=2.0 weight)
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=10, online_threshold=0.5)
        for i in range(10):
            monitor.evaluate(make_features(
                src_ip="10.0.0.1",
                request_count=10 + (i % 3),
                upload_download_ratio=0.5 + (i % 3) * 0.1,  # variable, weight=2.0
            ))
        online_result = monitor.evaluate(make_features(
            src_ip="10.0.0.1",
            request_count=20,
            upload_download_ratio=500.0,  # extreme deviation, weight=2.0
        ))
        online_triggered = online_result["online_prediction"] == 1
        assert online_triggered, f"online_score={online_result['online_score']} should trigger"

        # Format alert with online anomaly trigger
        alert_str = format_alert(
            features=features,
            burst_score=0.6,  # not triggering in this feature set
            severity="HIGH",
            online_score=online_result["online_score"],
            online_prediction=online_result["online_prediction"],
            online_reason_codes=online_result["reason_codes"],
            baseline_count=online_result["baseline_count"],
            alert_triggers=["ONLINE_UNKNOWN_ANOMALY"],
            color=False,
        )

        assert "ONLINE_UNKNOWN_ANOMALY" in alert_str
        assert "Online score:" in alert_str


class TestOnlineMonitorInFeatureQueue:
    """Simulate the InferenceThread processing windows from a queue."""

    def test_processes_multiple_windows(self):
        """Simulate a queue of windows being processed by the monitor."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=3, online_threshold=0.5)

        # Queue of normal windows
        q = queue.Queue()
        for i in range(5):
            q.put(make_features(src_ip="10.0.0.1", request_count=10 + i))
        for i in range(5):
            q.put(make_features(src_ip="10.0.0.2", request_count=50 + i))

        results = []
        while not q.empty():
            feats = q.get_nowait()
            result = monitor.evaluate(feats)
            results.append(result)

        assert len(results) == 10
        # All IPs should have their baselines
        assert monitor.baseline_count() == 2

    def test_anomaly_isolated_to_ip(self):
        """An anomalous window from one IP should not affect another IP's baseline."""
        monitor = OnlineAnomalyMonitor(
            enabled=True,
            warmup_min_windows=10,
            online_threshold=0.5,
        )

        # Build normal baselines for both IPs with variable upload_download_ratio (weight=2.0)
        for i in range(10):
            monitor.evaluate(make_features(
                src_ip="10.0.0.1",
                request_count=10 + i,
                upload_download_ratio=0.5 + (i % 3) * 0.1,
            ))
            monitor.evaluate(make_features(
                src_ip="10.0.0.2",
                request_count=50 + i,
                upload_download_ratio=0.5 + (i % 3) * 0.1,
            ))

        # Inject anomaly only for IP A using upload_download_ratio deviation
        anomaly_result = monitor.evaluate(make_features(
            src_ip="10.0.0.1",
            request_count=20,
            upload_download_ratio=500.0,  # extreme deviation, weight=2.0
        ))

        # IP A should be flagged
        assert anomaly_result["online_prediction"] == 1

        # IP B's baseline should be unchanged
        baseline_b = monitor._baselines["10.0.0.2"]
        assert abs(baseline_b.features["request_count"].mean - 54.5) < 1.0

        # IP A's baseline should still have only the warmup windows (anomalous excluded)
        baseline_a = monitor._baselines["10.0.0.1"]
        assert baseline_a.features["upload_download_ratio"].count == 10


class TestAlertLoggerOnlineFields:
    """Test AlertLogger.log_alert with online fields."""

    def test_log_alert_accepts_all_fields(self, tmp_path, monkeypatch):
        """log_alert should accept and render online fields without error."""
        # Patch file handler to use temp dir (avoid writing to repo)
        log_file = tmp_path / "test.log"
        import logging
        handler = logging.FileHandler(str(log_file))
        handler.setLevel(logging.DEBUG)

        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)

        logger = AlertLogger(console_color=False)
        logger.log_alert(
            features=make_features(),
            burst_score=0.8,
            severity="HIGH",
            online_score=0.75,
            online_prediction=1,
            online_reason_codes=["HIGH_Z: upload_download_ratio=5.2σ"],
            baseline_count=15,
            alert_triggers=["BURST_RULE", "ONLINE_UNKNOWN_ANOMALY"],
        )

        # Check log file contains online fields
        log_content = log_file.read_text()
        assert "Online score:" in log_content
        assert "ONLINE_UNKNOWN_ANOMALY" in log_content

        root.removeHandler(handler)
