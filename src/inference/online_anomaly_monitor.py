"""
src/inference/online_anomaly_monitor.py — Online adaptive anomaly detection.

Maintains a per-source-IP statistical baseline using Welford's online algorithm.
Detects unknown/new attack patterns not covered by offline-trained models by
comparing each incoming window feature vector against the learned baseline.

Key design decisions:
- Welford's algorithm: numerically stable incremental mean/variance with O(1) memory.
- Per-IP baselines: each source IP accumulates its own statistics independently.
- Warm-up period: first N normal-looking windows build the baseline — no
  anomaly decisions are made until warmup_min_windows windows are observed.
- Selective update: only windows classified as NORMAL update the baseline.
  Anomalous windows are excluded to prevent poisoning the baseline.
- Weighted scoring: each feature contributes a z-score deviation; the final
  score is the weighted mean of per-feature z-scores.
- Feature selection: uses the 17 runtime features from runtime_features.py.
"""

import threading
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from src.features.runtime_features import RUNTIME_FEATURE_KEYS
from src.utils.helpers import get_logger

logger = get_logger("online_monitor")


# ---------------------------------------------------------------------------
# Welford's online algorithm (single-pass, numerically stable)
# ---------------------------------------------------------------------------

class WelfordStats:
    """
    Numerically stable incremental mean and variance (online algorithm).

    Maintains count, mean, and M2 (sum of squared deviations).
    Supports both update and merge (for combining two independent estimators).

    Reference: Welford, B.P. (1962). "Note on a method for calculating corrected
    sums of squares and products". Technometrics. 4(3):419-420.
    """

    __slots__ = ("count", "mean", "m2")

    def __init__(self, count: int = 0, mean: float = 0.0, m2: float = 0.0):
        self.count: int = count
        self.mean: float = mean
        self.m2: float = m2

    def update(self, value: float) -> "WelfordStats":
        """Incorporate a new value into the running statistics."""
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2
        return self

    def merge(self, other: "WelfordStats") -> "WelfordStats":
        """Combine two independent WelfordStats into one (parallel computation)."""
        if other.count == 0:
            return self
        if self.count == 0:
            self.count = other.count
            self.mean = other.mean
            self.m2 = other.m2
            return self
        count = self.count + other.count
        delta = other.mean - self.mean
        mean = (self.count * self.mean + other.count * other.mean) / count
        m2 = self.m2 + other.m2 + delta ** 2 * self.count * other.count / count
        self.count = count
        self.mean = mean
        self.m2 = m2
        return self

    @property
    def variance(self) -> float:
        """Sample variance (biased estimator, count >= 2)."""
        if self.count < 2:
            return 0.0
        return self.m2 / self.count

    @property
    def std(self) -> float:
        """Sample standard deviation (biased estimator, count >= 2)."""
        return self.variance ** 0.5


# ---------------------------------------------------------------------------
# Per-feature weights (tuneable — sum not required to be 1)
# ---------------------------------------------------------------------------

# Higher weight = more influence on the final score.
# Features that are most discriminative for unknown exfil get higher weights.
FEATURE_WEIGHTS: Dict[str, float] = {
    "upload_download_ratio":    2.0,   # primary exfil signal
    "burst_count":              1.5,   # automation / scripted tools
    "burst_ratio":              1.5,   # ratio of burst packets
    "unusual_port_ratio":       1.5,   # non-standard port usage
    "request_rate":             1.0,   # unusual request frequency
    "inter_request_time_std":   1.0,   # machine vs human (low std = suspicious)
    "total_fwd_bytes":          1.0,   # large uploads
    "total_bytes":              1.0,   # total volume anomaly
    "mean_payload_size":        0.5,   # payload size anomaly
    "std_payload_size":        0.5,   # payload size variance anomaly
    "psh_flag_count":           0.5,   # TCP push — payload carrying
    "ack_flag_count":           0.0,   # ACK only = not interesting
    "syn_flag_count":           0.0,   # SYN only = connection setup
    "request_count":            0.5,   # number of requests anomaly
    "total_bwd_bytes":          0.5,   # response size anomaly
    "inter_request_time_mean":  0.5,   # timing anomaly
    "window_duration":          0.0,   # window duration is already normalised
}

_EPSILON = 1e-8  # guard against division by zero in z-score computation


# ---------------------------------------------------------------------------
# Per-IP baseline tracker
# ---------------------------------------------------------------------------

class IPBaseline:
    """
    Maintains a per-IP Welford statistics baseline for each feature.

    The baseline starts empty (cold) and accumulates during the warm-up
    period. Once warm, it tracks running statistics that are updated only
    when the current window is classified as NORMAL.
    """

    __slots__ = ("features", "warmup_done", "_lock")

    def __init__(self):
        # Dict[feature_name, WelfordStats]
        self.features: Dict[str, WelfordStats] = {
            name: WelfordStats() for name in RUNTIME_FEATURE_KEYS
        }
        self.warmup_done: bool = False
        self._lock = threading.Lock()

    def is_warmed_up(self, min_windows: int) -> bool:
        """
        True once the baseline has enough normal samples.

        Uses the maximum sample count across all features (consistent with
        baseline_count()). This allows warmup to proceed as long as enough
        windows have been processed, even if not every feature has been observed
        in every window.
        """
        if self.warmup_done:
            return True
        warmed = self.baseline_count() >= min_windows
        if warmed:
            self.warmup_done = True
        return warmed

    def update(self, features: Dict[str, Any]):
        """Incorporate a normal-looking window into the baseline (thread-safe)."""
        with self._lock:
            for name in RUNTIME_FEATURE_KEYS:
                val = features.get(name, 0.0)
                if val is None:
                    val = 0.0
                self.features[name].update(float(val))

    def compute_z_scores(
        self, features: Dict[str, Any]
    ) -> Tuple[Dict[str, float], Dict[str, str]]:
        """
        Compute per-feature z-scores for the given window.

        Returns:
            z_scores: {feature_name: abs_z_score}
            reasons:  {feature_name: human-readable reason}
        """
        z_scores: Dict[str, float] = {}
        reasons: Dict[str, str] = {}

        for name in RUNTIME_FEATURE_KEYS:
            val = features.get(name, 0.0)
            if val is None:
                val = 0.0
            val = float(val)

            stat = self.features[name]
            if stat.count < 2:
                z_scores[name] = 0.0
                reasons[name] = f"{name}=N/A (baseline n={stat.count})"
                continue

            std = stat.std
            if std < _EPSILON:
                # Constant feature — no variation to measure deviation against
                z_scores[name] = 0.0
                reasons[name] = f"{name}=const (std≈0)"
                continue

            z = abs(val - stat.mean) / std
            z_scores[name] = z

            # Human-readable reason only for deviations beyond threshold
            if z > 2.0:
                direction = "↑" if val > stat.mean else "↓"
                reasons[name] = (
                    f"{name}{direction} {val:.2f} (baseline μ={stat.mean:.2f} σ={std:.2f}, z={z:.1f})"
                )
            else:
                reasons[name] = ""

        return z_scores, reasons

    def compute_anomaly_score(
        self, features: Dict[str, Any], z_thresholds: Optional[Dict[str, float]] = None
    ) -> Tuple[float, Dict[str, float], Dict[str, str]]:
        """
        Compute the weighted anomaly score for a window.

        Args:
            features: Window feature dict
            z_thresholds: Optional per-feature z-score thresholds for reason codes

        Returns:
            online_score: float (0 = normal, 1 = definite anomaly)
            z_scores: per-feature z-scores
            reasons: per-feature reason strings
        """
        if z_thresholds is None:
            z_thresholds = {}

        z_scores, reasons = self.compute_z_scores(features)

        total_weight = 0.0
        weighted_sum = 0.0

        for name, z in z_scores.items():
            weight = FEATURE_WEIGHTS.get(name, 0.5)
            # Use per-feature threshold if provided, else global 2.0
            threshold = z_thresholds.get(name, 2.0)
            # Cap z-score contribution per feature to avoid single extreme values dominating
            capped_z = min(z, 10.0)
            weighted_sum += weight * (capped_z / threshold)
            total_weight += weight

        if total_weight < _EPSILON:
            return 0.0, z_scores, reasons

        # Score is the normalised weighted mean of capped z-scores
        # Scale so that avg deviation at threshold → score ~0.5
        score = min(weighted_sum / total_weight, 1.0)
        return score, z_scores, reasons

    def baseline_count(self) -> int:
        """Return the number of samples in the most-sampled feature (warmup proxy)."""
        with self._lock:
            return max(s.count for s in self.features.values())


# ---------------------------------------------------------------------------
# OnlineAnomalyMonitor — top-level orchestrator
# ---------------------------------------------------------------------------

class OnlineAnomalyMonitor:
    """
    Adaptive online anomaly detector for unknown/new attack patterns.

    Each source IP gets its own baseline. For each incoming window:
      1. If baseline is cold (< warmup_min_windows), collect without scoring.
      2. Otherwise, compute z-score deviation from baseline.
      3. If online_score >= online_threshold → ANOMALY, do NOT update baseline.
      4. Else → NORMAL, update baseline with this window.

    This runs in the same thread as InferenceThread (no extra thread needed)
    because Welford updates are O(1) and lock contention is minimal.
    """

    def __init__(
        self,
        online_threshold: float = 0.5,
        warmup_min_windows: int = 10,
        enabled: bool = True,
    ):
        """
        Args:
            online_threshold: Alert fires when online_score >= threshold (0-1).
                             0.5 = moderate sensitivity, 0.7 = conservative.
            warmup_min_windows: Number of normal windows needed before scoring.
            enabled: If False, all methods return safe defaults (no-op).
        """
        self.online_threshold = online_threshold
        self.warmup_min_windows = warmup_min_windows
        self.enabled = enabled

        # Per-IP baselines: {src_ip: IPBaseline}
        self._baselines: Dict[str, IPBaseline] = {}
        self._lock = threading.Lock()

        # Stats (not critical path — updated every window)
        self._stats = {"windows_processed": 0, "anomalies_detected": 0, "baselines_created": 0}
        self._stats_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API — called by InferenceThread
    # ------------------------------------------------------------------

    def evaluate(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a single window and return the online anomaly result.

        Args:
            features: Window feature dict (must include 'src_ip').

        Returns:
            {
                "online_score": float,
                "online_prediction": 0 or 1,
                "reason_codes": list[str],
                "baseline_count": int,
            }
            If disabled, returns safe defaults.
        """
        if not self.enabled:
            return {
                "online_score": 0.0,
                "online_prediction": 0,
                "reason_codes": ["online_monitor_disabled"],
                "baseline_count": 0,
            }

        src_ip = features.get("src_ip", "unknown")

        with self._lock:
            if src_ip not in self._baselines:
                self._baselines[src_ip] = IPBaseline()
                self._stats["baselines_created"] += 1
                logger.debug(f"[ONLINE] New baseline created for {src_ip}")

            baseline = self._baselines[src_ip]

        # Increment stats
        with self._stats_lock:
            self._stats["windows_processed"] += 1

        # During warmup: accumulate baseline but don't score (no decisions yet)
        if not baseline.is_warmed_up(self.warmup_min_windows):
            baseline.update(features)
            return {
                "online_score": 0.0,
                "online_prediction": 0,
                "reason_codes": [f"warmup_{baseline.baseline_count()}/{self.warmup_min_windows}"],
                "baseline_count": baseline.baseline_count(),
            }

        # Compute anomaly score
        score, z_scores, reasons = baseline.compute_anomaly_score(features)
        prediction = 1 if score >= self.online_threshold else 0

        # Collect non-empty reason strings
        reason_codes: List[str] = [
            r for r in reasons.values() if r
        ]
        if prediction == 1:
            # Add top deviations as structured codes
            top = sorted(
                [(n, z) for n, z in z_scores.items() if z > 2.0],
                key=lambda x: x[1],
                reverse=True,
            )[:3]
            for name, z in top:
                reason_codes.append(f"HIGH_Z: {name}={z:.1f}σ")
        else:
            reason_codes.append("within_baseline")

        # Update stats
        if prediction == 1:
            with self._stats_lock:
                self._stats["anomalies_detected"] += 1
            logger.info(
                f"[ONLINE] ANOMALY detected for {src_ip}: "
                f"score={score:.3f} reasons={reason_codes[:3]}"
            )

        # IMPORTANT: Only update baseline with normal windows (prevent poisoning)
        if prediction == 0:
            baseline.update(features)

        return {
            "online_score": round(score, 4),
            "online_prediction": prediction,
            "reason_codes": reason_codes,
            "baseline_count": baseline.baseline_count(),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Return online monitor statistics."""
        with self._stats_lock:
            return self._stats.copy()

    def reset(self):
        """Clear all baselines (for testing or re-initialisation)."""
        with self._lock:
            self._baselines.clear()
        with self._stats_lock:
            self._stats = {"windows_processed": 0, "anomalies_detected": 0, "baselines_created": 0}
        logger.info("[ONLINE] All baselines reset.")

    def reset_ip(self, src_ip: str):
        """Clear baseline for a specific IP."""
        with self._lock:
            if src_ip in self._baselines:
                del self._baselines[src_ip]
                logger.info(f"[ONLINE] Baseline reset for {src_ip}")

    def baseline_count(self) -> int:
        """Number of IPs currently being tracked."""
        with self._lock:
            return len(self._baselines)
