"""
src/features/burst_exfil.py — Compute burst_exfil_score from window features.

Score ranges 0→1. Higher = more likely exfiltration.
Based on EDA analysis of Bot vs Normal traffic patterns.
"""

from typing import Dict, Any

# Thresholds from EDA analysis
UPLOAD_RATIO_THRESHOLD      = 2.0   # fwd/bwd > 2.0 → exfil signal
BURST_COUNT_THRESHOLD       = 10    # min burst packets
UNUSUAL_PORT_THRESHOLD      = 0.5   # >50% unusual ports
INTER_REQ_STD_THRESHOLD     = 0.05  # seconds — automated exfil = low std

# Score weights (must sum to 1.0)
WEIGHTS = {
    "upload_ratio":    0.30,
    "burst_count":     0.25,
    "unusual_port":    0.20,
    "inter_req_std":   0.25,
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
            - (other keys are ignored)

    Returns:
        Score from 0.0 (normal) to 1.0 (definite exfil).
        Alert threshold: score > 0.7

    Algorithm:
        - Upload ratio > 2.0 → +0.30 (strongest signal from EDA: Bot uploads 4.5x)
        - Burst count > 10 → +0.25 (automated behavior)
        - Unusual port ratio > 0.5 → +0.20 (exfil over non-standard port)
        - Inter-request std < 0.05s → +0.25 (machine-generated traffic)
    """
    score = 0.0

    # 1. Upload ratio — primary signal
    # EDA: Bot traffic has upload 4.57x higher than normal, bwd bytes ~0
    upload_ratio = window_features.get("upload_download_ratio", 0.0)
    if upload_ratio > UPLOAD_RATIO_THRESHOLD:
        score += WEIGHTS["upload_ratio"]

    # 2. Burst count — automated exfil
    # Many rapid packets = script/tool uploading data
    burst_count = window_features.get("burst_count", 0)
    if burst_count > BURST_COUNT_THRESHOLD:
        score += WEIGHTS["burst_count"]

    # 3. Unusual destination ports
    # Exfil often uses non-standard ports to avoid detection
    unusual_port_ratio = window_features.get("unusual_port_ratio", 0.0)
    if unusual_port_ratio > UNUSUAL_PORT_THRESHOLD:
        score += WEIGHTS["unusual_port"]

    # 4. Inter-request time std — automated pattern
    # Human browsing: high variance in inter-request times
    # Exfil tool: very regular, low variance
    inter_req_std = window_features.get("inter_request_time_std", 1.0)
    if inter_req_std < INTER_REQ_STD_THRESHOLD:
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
