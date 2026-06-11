"""
tests/unit/test_online_anomaly_monitor.py — Unit tests for OnlineAnomalyMonitor.

Covers:
  - WelfordStats correctness
  - IPBaseline warmup behaviour
  - Normal window updates baseline
  - Anomalous window does NOT update baseline
  - High deviation triggers online_prediction = 1
  - reason_codes are produced
  - Multi-IP isolation
  - Disabled mode returns safe defaults
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.inference.online_anomaly_monitor import (
    WelfordStats,
    IPBaseline,
    OnlineAnomalyMonitor,
    RUNTIME_FEATURE_KEYS,
)


# ---------------------------------------------------------------------------
# Helper: minimal normal feature dict (all required keys present)
# ---------------------------------------------------------------------------

def make_normal_features(src_ip="10.0.0.1", **overrides):
    """Create a valid feature dict with defaults."""
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
        "src_ip": src_ip,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Tests: WelfordStats
# ---------------------------------------------------------------------------

class TestWelfordStats:
    def test_empty_stats(self):
        s = WelfordStats()
        assert s.count == 0
        assert s.mean == 0.0
        assert s.variance == 0.0
        assert s.std == 0.0

    def test_single_update(self):
        s = WelfordStats()
        s.update(10.0)
        assert s.count == 1
        assert s.mean == 10.0
        assert s.variance == 0.0  # variance undefined with n=1

    def test_two_updates(self):
        s = WelfordStats()
        s.update(0.0)
        s.update(10.0)
        assert s.count == 2
        assert s.mean == 5.0
        # Biased variance = sum((x-mean)^2) / n = (25 + 25) / 2 = 25.0
        assert abs(s.variance - 25.0) < 1e-10

    def test_five_updates(self):
        s = WelfordStats()
        values = [2.0, 4.0, 4.0, 4.0, 5.0]
        for v in values:
            s.update(v)
        assert s.count == 5
        assert abs(s.mean - 3.8) < 1e-9
        # Biased variance = sum((x-mean)^2) / n = 4.8 / 5 = 0.96
        assert abs(s.variance - 0.96) < 1e-9
        assert abs(s.std - (0.96 ** 0.5)) < 1e-6

    def test_merge(self):
        s1 = WelfordStats()
        for v in [1.0, 2.0, 3.0]:
            s1.update(v)
        s2 = WelfordStats()
        for v in [7.0, 8.0, 9.0]:
            s2.update(v)
        s1.merge(s2)
        assert s1.count == 6
        assert abs(s1.mean - 5.0) < 1e-9
        assert s1.variance >= 0  # positive variance


# ---------------------------------------------------------------------------
# Tests: IPBaseline
# ---------------------------------------------------------------------------

class TestIPBaseline:
    def test_cold_baseline(self):
        baseline = IPBaseline()
        assert baseline.is_warmed_up(min_windows=10) is False

    def test_warmup_completes(self):
        """After 10 updates, warmup completes (baseline_count >= 10)."""
        baseline = IPBaseline()
        for i in range(10):
            baseline.update(make_normal_features(request_count=10 + i))
        assert baseline.is_warmed_up(min_windows=10) is True

    def test_baseline_updates_stats(self):
        """Normal windows update the baseline statistics."""
        baseline = IPBaseline()
        for i in range(10):
            baseline.update(make_normal_features(request_count=15 + i))
        assert baseline.features["request_count"].count == 10
        assert abs(baseline.features["request_count"].mean - 19.5) < 1.0  # mean of 15..24

    def test_z_score_normal(self):
        """Within-baseline traffic produces low z-scores."""
        baseline = IPBaseline()
        # Use variable values so std > 0
        for i in range(20):
            baseline.update(make_normal_features(request_count=10 + (i % 5)))
        feats = make_normal_features(request_count=12)  # within normal range
        z_scores, reasons = baseline.compute_z_scores(feats)
        assert z_scores["request_count"] < 2.0

    def test_z_score_deviation(self):
        """Outside-baseline traffic produces high z-scores."""
        baseline = IPBaseline()
        # Use variable values so std > 0
        for i in range(20):
            baseline.update(make_normal_features(request_count=10 + (i % 5)))
        # request_count=100 is far outside normal range
        feats = make_normal_features(request_count=100)
        z_scores, reasons = baseline.compute_z_scores(feats)
        assert z_scores["request_count"] > 10.0

    def test_anomaly_score_normal(self):
        """Normal traffic produces a low anomaly score."""
        baseline = IPBaseline()
        # Use variable values so std > 0
        for i in range(10):
            baseline.update(make_normal_features(
                request_count=10 + (i % 5),
                upload_download_ratio=0.5 + (i % 3) * 0.1,
            ))
        feats = make_normal_features(request_count=12, upload_download_ratio=0.6)
        score, z_scores, reasons = baseline.compute_anomaly_score(feats)
        assert 0.0 <= score <= 1.0
        assert score < 0.5  # normal traffic should score low

    def test_anomaly_score_high(self):
        """Anomalous traffic produces a measurable anomaly score."""
        baseline = IPBaseline()
        # Build baseline with variable values (upload_download_ratio is high-weight=2.0)
        for i in range(10):
            baseline.update(make_normal_features(
                request_count=10 + (i % 5),
                upload_download_ratio=0.5 + (i % 3) * 0.1,
            ))
        # Anomalous: extreme upload_download_ratio deviation (weight=2.0)
        feats = make_normal_features(request_count=20, upload_download_ratio=500.0)
        score, z_scores, reasons = baseline.compute_anomaly_score(feats)
        # Score is driven by upload_download_ratio (weight 2.0) — should be measurable
        assert score > 0.2

    def test_reason_codes_produced(self):
        """High-deviation windows produce non-empty reason codes."""
        baseline = IPBaseline()
        for _ in range(10):
            baseline.update(make_normal_features(request_count=10))
        feats = make_normal_features(request_count=1000)
        z_scores, reasons = baseline.compute_z_scores(feats)
        non_empty = [r for r in reasons.values() if r]
        assert len(non_empty) > 0

    def test_baseline_count(self):
        """baseline_count() returns the maximum sample count across features."""
        baseline = IPBaseline()
        assert baseline.baseline_count() == 0
        for _ in range(5):
            baseline.update(make_normal_features())
        assert baseline.baseline_count() == 5


# ---------------------------------------------------------------------------
# Tests: OnlineAnomalyMonitor (public API)
# ---------------------------------------------------------------------------

class TestOnlineAnomalyMonitor:
    def test_disabled_monitor_returns_defaults(self):
        """Disabled monitor returns safe defaults without processing."""
        monitor = OnlineAnomalyMonitor(enabled=False)
        result = monitor.evaluate(make_normal_features())
        assert result["online_score"] == 0.0
        assert result["online_prediction"] == 0
        assert result["reason_codes"] == ["online_monitor_disabled"]
        assert result["baseline_count"] == 0

    def test_warmup_no_scoring(self):
        """During warmup, online_prediction is always 0."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=10)
        for i in range(9):
            result = monitor.evaluate(make_normal_features(src_ip="10.0.0.1"))
            assert result["online_prediction"] == 0
            assert f"warmup" in result["reason_codes"][0]

    def test_warmup_complete_after_n_windows(self):
        """After warmup_min_windows normal windows, scoring begins."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=10)
        for i in range(10):
            monitor.evaluate(make_normal_features(src_ip="10.0.0.1", request_count=10 + i))
        result = monitor.evaluate(make_normal_features(src_ip="10.0.0.1", request_count=15))
        # No longer in warmup
        warmup_codes = [c for c in result["reason_codes"] if "warmup" in c]
        assert len(warmup_codes) == 0

    def test_normal_updates_baseline(self):
        """Normal windows after warmup update the baseline."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=3)
        for i in range(3):
            monitor.evaluate(make_normal_features(src_ip="10.0.0.1", request_count=10 + i))
        # After warmup, normal window should update baseline
        monitor.evaluate(make_normal_features(src_ip="10.0.0.1", request_count=15))
        baseline = monitor._baselines["10.0.0.1"]
        assert baseline.features["request_count"].count == 4  # 3 warmup + 1 normal

    def test_anomalous_does_not_update_baseline(self):
        """Anomalous windows are NOT used to update the baseline."""
        monitor = OnlineAnomalyMonitor(
            enabled=True,
            warmup_min_windows=3,
            online_threshold=0.3,
        )
        for i in range(3):
            monitor.evaluate(make_normal_features(
                src_ip="10.0.0.1",
                request_count=10 + i,
                upload_download_ratio=0.5 + (i % 3) * 0.1,  # variable
            ))
        # Anomalous window: extreme upload_download_ratio deviation (weight=2.0)
        anomalous = make_normal_features(
            src_ip="10.0.0.1",
            upload_download_ratio=500.0,  # massive deviation
            request_count=20,
        )
        result = monitor.evaluate(anomalous)
        assert result["online_prediction"] == 1
        # Baseline should NOT have been updated with the anomalous window
        baseline = monitor._baselines["10.0.0.1"]
        assert baseline.features["upload_download_ratio"].count == 3  # still at warmup count

    def test_high_deviation_triggers_prediction(self):
        """Extreme deviation from baseline triggers anomaly prediction."""
        monitor = OnlineAnomalyMonitor(
            enabled=True,
            warmup_min_windows=5,
            online_threshold=0.5,
        )
        for i in range(5):
            monitor.evaluate(make_normal_features(
                src_ip="10.0.0.1",
                request_count=10 + (i % 3),
                upload_download_ratio=0.5 + (i % 3) * 0.1,  # variable with weight=2.0
            ))
        # Anomalous: extreme upload_download_ratio deviation
        anomalous = make_normal_features(
            src_ip="10.0.0.1",
            upload_download_ratio=500.0,  # extreme deviation
            request_count=20,
        )
        result = monitor.evaluate(anomalous)
        assert result["online_prediction"] == 1
        assert result["online_score"] > 0.5

    def test_reason_codes_in_result(self):
        """Anomalous windows include structured reason codes in the result."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=5, online_threshold=0.5)
        for i in range(5):
            monitor.evaluate(make_normal_features(
                src_ip="10.0.0.1",
                request_count=10 + (i % 3),
                upload_download_ratio=0.5 + (i % 3) * 0.1,
            ))
        anomalous = make_normal_features(
            src_ip="10.0.0.1",
            upload_download_ratio=500.0,
            request_count=20,
        )
        result = monitor.evaluate(anomalous)
        assert len(result["reason_codes"]) > 0
        assert result["online_prediction"] == 1

    def test_multi_ip_isolation(self):
        """Each IP gets an independent baseline."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=3)
        # Feed IP A with variable request_count values
        for i in range(3):
            monitor.evaluate(make_normal_features(src_ip="10.0.0.1", request_count=10 + i))
        # Feed IP B with different variable values
        for i in range(3):
            monitor.evaluate(make_normal_features(src_ip="10.0.0.2", request_count=50 + i))
        baseline_a = monitor._baselines["10.0.0.1"]
        baseline_b = monitor._baselines["10.0.0.2"]
        assert baseline_a.features["request_count"].count == 3
        assert baseline_b.features["request_count"].count == 3
        assert abs(baseline_a.features["request_count"].mean - 11.0) < 1.0  # mean of 10,11,12
        assert abs(baseline_b.features["request_count"].mean - 51.0) < 1.0  # mean of 50,51,52

    def test_get_stats(self):
        """get_stats() returns accurate counters."""
        monitor = OnlineAnomalyMonitor(enabled=True)
        monitor.evaluate(make_normal_features(src_ip="10.0.0.1"))
        stats = monitor.get_stats()
        assert stats["windows_processed"] == 1

    def test_reset(self):
        """reset() clears all baselines."""
        monitor = OnlineAnomalyMonitor(enabled=True)
        monitor.evaluate(make_normal_features(src_ip="10.0.0.1"))
        assert monitor.baseline_count() == 1
        monitor.reset()
        assert monitor.baseline_count() == 0
        stats = monitor.get_stats()
        assert stats["baselines_created"] == 0

    def test_reset_ip(self):
        """reset_ip() clears baseline for a specific IP."""
        monitor = OnlineAnomalyMonitor(enabled=True)
        monitor.evaluate(make_normal_features(src_ip="10.0.0.1"))
        monitor.evaluate(make_normal_features(src_ip="10.0.0.2"))
        assert monitor.baseline_count() == 2
        monitor.reset_ip("10.0.0.1")
        assert monitor.baseline_count() == 1

    def test_all_runtime_features_accepted(self):
        """All 17 runtime features are accepted without errors."""
        monitor = OnlineAnomalyMonitor(enabled=True, warmup_min_windows=2)
        feats = {k: 1.0 for k in RUNTIME_FEATURE_KEYS}
        feats["src_ip"] = "10.0.0.1"
        for _ in range(2):
            result = monitor.evaluate(feats)
        # Consistent features should produce a consistent (non-error) result
        assert "online_prediction" in result


# ---------------------------------------------------------------------------
# Tests: burst_exfil_score still works (backward compatibility)
# ---------------------------------------------------------------------------

class TestBurstExfilStillWorks:
    def test_burst_exfil_normal(self):
        """Normal features produce a low burst score."""
        from src.features.burst_exfil import burst_exfil_score
        score = burst_exfil_score(make_normal_features())
        assert 0.0 <= score <= 1.0
        assert score < 0.5

    def test_burst_exfil_exfil(self):
        """Exfil features produce a high burst score."""
        from src.features.burst_exfil import burst_exfil_score
        score = burst_exfil_score(make_normal_features(
            upload_download_ratio=200.0,
            burst_count=100,
            total_bytes=200000,
        ))
        assert score > 0.5


# ---------------------------------------------------------------------------
# Tests: pipeline imports still work
# ---------------------------------------------------------------------------

class TestPipelineImports:
    def test_model_inference_imports(self):
        from src.inference.model_inference import InferenceThread
        assert InferenceThread is not None

    def test_online_monitor_imports(self):
        from src.inference.online_anomaly_monitor import OnlineAnomalyMonitor
        assert OnlineAnomalyMonitor is not None

    def test_pipeline_imports(self):
        from src.pipeline import run_pipeline
        assert run_pipeline is not None
