"""
src/utils/constants.py — Constants for exfiltration detection.
"""

# =============================================================================
# EXFILTRATION SCORING THRESHOLDS
# Based on EDA analysis of Bot vs Normal traffic patterns
# =============================================================================

# burst_exfil_score thresholds
BURST_THRESHOLD       = 0.1   # seconds — inter-arrival < this = burst
BURST_COUNT_THRESHOLD = 10    # min burst packets to flag

# Upload ratio thresholds
UPLOAD_RATIO_HIGH     = 2.0   # fwd/bwd > 2.0 → suspicious
UPLOAD_RATIO_VERY_HIGH = 5.0  # fwd/bwd > 5.0 → strongly suspicious

# Unusual port threshold
UNUSUAL_PORT_RATIO_THRESHOLD = 0.5  # > 50% unusual ports → suspicious

# Inter-request time std threshold (automated = low std)
INTER_REQ_TIME_STD_THRESHOLD = 0.05  # seconds

# Session duration
LONG_SESSION_THRESHOLD = 300  # seconds

# Packet size thresholds for burst detection
MIN_PAYLOAD_FOR_BURST = 10  # bytes — ignore tiny ACK packets

# =============================================================================
# MODEL HYPERPARAMETERS
# =============================================================================

# Isolation Forest (anomaly detection — train on NORMAL only)
IFOREST_CONFIG = {
    "contamination": 0.05,     # 5% expected outliers
    "n_estimators": 200,
    "max_samples": 256,
    "random_state": 42,
    "n_jobs": -1,
}

# One-Class SVM (baseline anomaly — slow, for comparison)
OCSVM_CONFIG = {
    "kernel": "rbf",
    "gamma": "scale",
    "nu": 0.05,              # ~5% expected outliers
}

# BiLSTM (supervised — train on labeled data)
BILSTM_CONFIG = {
    "lstm_units_1": 64,
    "lstm_units_2": 32,
    "dense_units": 64,
    "dropout_rate": 0.3,
    "learning_rate": 0.001,
    "batch_size": 256,
    "epochs": 50,
    "patience": 5,           # early stopping patience
}

# CNN 1D (supervised — train on labeled data)
CNN1D_CONFIG = {
    "conv_filters_1": 64,
    "conv_filters_2": 32,
    "kernel_size": 1,
    "dense_units": 64,
    "dropout_rate": 0.3,
    "learning_rate": 0.001,
    "batch_size": 256,
    "epochs": 50,
    "patience": 5,
}

# =============================================================================
# FEATURE COLUMNS (after preprocessing)
# =============================================================================

# Numeric features used for training/inference
FEATURE_COLS = [
    # Flow statistics
    "Flow Duration",
    "Total Fwd Packets",
    "Total Backward Packets",
    "Total Length of Fwd Packets",
    "Total Length of Bwd Packets",

    # Packet length statistics
    "Fwd Packet Length Max",
    "Fwd Packet Length Min",
    "Fwd Packet Length Mean",
    "Fwd Packet Length Std",
    "Bwd Packet Length Max",
    "Bwd Packet Length Min",
    "Bwd Packet Length Mean",
    "Bwd Packet Length Std",
    "Min Packet Length",
    "Max Packet Length",
    "Packet Length Mean",
    "Packet Length Std",

    # Throughput
    "Flow Bytes/s",
    "Flow Packets/s",
    "Fwd Packets/s",
    "Bwd Packets/s",

    # Inter-arrival time
    "Flow IAT Mean",
    "Flow IAT Std",
    "Flow IAT Max",
    "Flow IAT Min",
    "Fwd IAT Mean",
    "Fwd IAT Std",
    "Fwd IAT Max",
    "Fwd IAT Min",
    "Bwd IAT Mean",
    "Bwd IAT Std",
    "Bwd IAT Max",
    "Bwd IAT Min",

    # TCP flags
    "FIN Flag Count",
    "SYN Flag Count",
    "RST Flag Count",
    "PSH Flag Count",
    "ACK Flag Count",
    "URG Flag Count",

    # Window & segment
    "Avg Fwd Segment Size",
    "Avg Bwd Segment Size",
    "Init_Win_bytes_forward",
    "Init_Win_bytes_backward",

    # Activity timing
    "Active Mean",
    "Active Std",
    "Active Max",
    "Active Min",
    "Idle Mean",
    "Idle Std",
    "Idle Max",
    "Idle Min",

    # Subflow
    "Subflow Fwd Packets",
    "Subflow Fwd Bytes",
    "Subflow Bwd Packets",
    "Subflow Bwd Bytes",

    # Counts
    "act_data_pkt_fwd",
    "Down/Up Ratio",
    "Average Packet Size",
]

# Custom features (computed at inference time, not in CSV)
CUSTOM_FEATURE_COLS = [
    "upload_download_ratio",
    "burst_count",
    "burst_ratio",
    "unusual_port_ratio",
    "inter_request_time_std",
    "requests_per_second",
    "is_long_session",
]

# All features (CSV + custom)
ALL_FEATURE_COLS = FEATURE_COLS + CUSTOM_FEATURE_COLS

# =============================================================================
# ALERT SEVERITY
# =============================================================================
ALERT_SEVERITY = {
    "CRITICAL": 0.85,   # score >= 0.85
    "HIGH":     0.70,   # score >= 0.70
    "MEDIUM":   0.50,   # score >= 0.50
    "LOW":      0.30,   # score >= 0.30
}
