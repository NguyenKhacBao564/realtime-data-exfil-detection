"""
Shared runtime window feature vector definition.

These features are computed from live packet windows, not CICFlowMeter rows.
The runtime demo model must use this exact order.
"""

from typing import Any, Dict, Iterable, List

import numpy as np


RUNTIME_FEATURE_KEYS: List[str] = [
    "request_count",
    "total_fwd_bytes",
    "total_bwd_bytes",
    "total_bytes",
    "upload_download_ratio",
    "burst_count",
    "burst_ratio",
    "unusual_port_ratio",
    "request_rate",
    "inter_request_time_mean",
    "inter_request_time_std",
    "mean_payload_size",
    "std_payload_size",
    "psh_flag_count",
    "ack_flag_count",
    "syn_flag_count",
    "window_duration",
]


def build_runtime_feature_vector(features: Dict[str, Any]) -> np.ndarray:
    """Build a numeric vector from one live window feature dict."""
    values = []
    for key in RUNTIME_FEATURE_KEYS:
        value = features.get(key, 0.0)
        if value is None:
            value = 0.0
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        if not np.isfinite(value):
            value = 0.0
        values.append(value)
    return np.array(values, dtype=np.float32)


def build_runtime_feature_matrix(rows: Iterable[Dict[str, Any]]) -> np.ndarray:
    """Build a 2D matrix from runtime window feature dicts."""
    return np.vstack([build_runtime_feature_vector(row) for row in rows])
