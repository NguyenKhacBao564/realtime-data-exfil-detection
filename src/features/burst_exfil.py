"""
src/features/burst_exfil.py — Compute burst_exfil_score from window features.

Score ranges 0→1. Higher = more likely exfiltration.
Based on EDA analysis of Bot vs Normal traffic patterns.
"""

from typing import Dict, Any

# Thresholds from EDA analysis
# MUST have BOTH high upload ratio AND many burst packets to fire
UPLOAD_RATIO_THRESHOLD      = 100.0  # fwd/bwd > 100.0 → strong exfil signal
BURST_COUNT_THRESHOLD       = 50     # min burst packets (forward direction)
TOTAL_BYTES_THRESHOLD       = 50_000 # min total bytes (50KB) to be suspicious
UNUSUAL_PORT_THRESHOLD      = 0.8   # >80% unusual ports
INTER_REQ_STD_THRESHOLD     = 0.05  # seconds — automated exfil = low std

# Score weights (must sum to 1.0)
WEIGHTS = {
    "upload_ratio":    0.40,
    "burst_count":     0.20,
    "unusual_port":    0.20,
    "inter_req_std":   0.20,
}


def burst_exfil_score(window_features: Dict[str, Any]) -> float:
    """
    Compute exfiltration score from aggregated window features.

    Args:
        window_features: dict with keys like:
            - upload_download_ratio: float
            - burst_count: int
            - unusual_port_ratio: float (0-1)
            - inter_request_time_std: float (seconds)
            - total_bytes: int
            - (other keys are ignored)

    Returns:
        Score from 0.0 (normal) to 1.0 (definite exfil).
        Alert threshold: score > 0.7

    Algorithm (conservative — minimize false positives):
        - Upload ratio > 100.0 AND total_bytes > 50KB → +0.40
          (Bot traffic: upload 4.57x, massive bytes = true exfil)
        - Burst count > 50 (automated, many rapid packets) → +0.20
        - Unusual port ratio > 0.8 → +0.20 (non-HTTP ports)
        - Inter-request std < 0.05s → +0.20 (machine-generated, regular)
    """
    score = 0.0

    total_bytes = window_features.get("total_bytes", 0)

    # 1. Upload ratio — PRIMARY signal (weight 40%)
    # Require BOTH high ratio AND substantial byte count to avoid flagging
    # small bursts with misleading ratios
    upload_ratio = window_features.get("upload_download_ratio", 0.0)
    if upload_ratio > UPLOAD_RATIO_THRESHOLD and total_bytes > TOTAL_BYTES_THRESHOLD:
        score += WEIGHTS["upload_ratio"]

    # 2. Burst count — automated exfil (weight 20%)
    # Threshold 50: ignores normal browsing bursts, flags genuine automation
    burst_count = window_features.get("burst_count", 0)
    if burst_count > BURST_COUNT_THRESHOLD:
        score += WEIGHTS["burst_count"]

    # 3. Unusual destination ports (weight 20%)
    # Exfil often uses non-standard ports to avoid detection
    unusual_port_ratio = window_features.get("unusual_port_ratio", 0.0)
    if unusual_port_ratio > UNUSUAL_PORT_THRESHOLD:
        score += WEIGHTS["unusual_port"]

    # 4. Inter-request time std — automated pattern (weight 20%)
    # Human browsing: high variance in inter-request times
    # Exfil tool: very regular, low variance
    # Guard: only check if window has enough packets for meaningful std
    inter_req_std = window_features.get("inter_request_time_std", 1.0)
    request_count = window_features.get("request_count", 0)
    if inter_req_std < INTER_REQ_STD_THRESHOLD and request_count >= 5:
        score += WEIGHTS["inter_req_std"]

    return min(score, 1.0)


def get_severity(score: float) -> str:
    """Get severity label from score."""
    if score >= 0.85:
        return "CRITICAL"
    elif score >= 0.70:
        return "HIGH"
    elif score >= 0.50:
        return "MEDIUM"
    elif score >= 0.30:
        return "LOW"
    else:
        return "INFO"
