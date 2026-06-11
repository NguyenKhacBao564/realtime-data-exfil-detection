"""
src/utils/config.py — Central configuration for the exfiltration detection pipeline.
All constants are defined here. Import this in every module.
"""

import os
from pathlib import Path

# =============================================================================
# PROJECT PATHS
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = PROJECT_ROOT / "models"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
TESTS_DIR = PROJECT_ROOT / "tests"
DOCS_DIR = PROJECT_ROOT / "docs"

# Ensure directories exist
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# DATASET CONFIG
# =============================================================================
CICIDS_ML_CVE_DIR = RAW_DIR / "CICIDS2017_ML-CVE"
CICIDS_ORIGINAL_DIR = RAW_DIR / "CICIDS2017_TrafficLabelling_Original"
PCAP_FILE = RAW_DIR / "Friday-WorkingHours.pcap"

# CSV files for training (in order of preference for exfil proxy)
CSV_FILES = {
    "monday":    CICIDS_ML_CVE_DIR / "Monday-WorkingHours.pcap_ISCX.csv",
    "tuesday":   CICIDS_ML_CVE_DIR / "Tuesday-WorkingHours.pcap_ISCX.csv",
    "wednesday":  CICIDS_ML_CVE_DIR / "Wednesday-workingHours.pcap_ISCX.csv",
    "thu_am":    CICIDS_ML_CVE_DIR / "Thursday-WorkingHours-Morning-WebAttacks.pcap_ISCX.csv",
    "thu_pm":    CICIDS_ML_CVE_DIR / "Thursday-WorkingHours-Afternoon-Infilteration.pcap_ISCX.csv",
    "fri_am":    CICIDS_ML_CVE_DIR / "Friday-WorkingHours-Morning.pcap_ISCX.csv",
    "fri_pm_ps": CICIDS_ML_CVE_DIR / "Friday-WorkingHours-Afternoon-PortScan.pcap_ISCX.csv",
    "fri_pm_dd": CICIDS_ML_CVE_DIR / "Friday-WorkingHours-Afternoon-DDos.pcap_ISCX.csv",
}

# =============================================================================
# LABELING CONFIG — based on EDA findings
# =============================================================================
# Label 0 = Normal, Label 1 = Exfiltration
# PRIMARY EXFIL PROXY: Bot traffic (Friday-Morning) — high upload, short session
EXFIL_LABELS = {
    "Bot",           # 1,966 flows — BEST exfil proxy (upload 4.5x > download)
    "Infiltration",  # 36 flows — secondary (port scan + backdoor)
}
# Normal labels (Label 0)
NORMAL_LABELS = {"BENIGN"}

# =============================================================================
# PREPROCESSING CONFIG
# =============================================================================
TRAIN_RATIO = 0.70
TEST_RATIO  = 0.15
VAL_RATIO   = 0.15
RANDOM_STATE = 42

# Columns to drop (known bad / redundant / constant)
COLS_TO_DROP = [
    # CICFlowMeter artifact columns with negative values
    "Fwd Header Length",    # has negative values (bug)
    "Bwd Header Length",    # has negative values (bug)
    "Fwd Header Length.1",  # duplicate of Fwd Header Length
    "min_seg_size_forward", # has negative values (bug)
    # Bulk rate columns — mostly zero/NaN in CICIDS2017
    "Fwd Avg Bytes/Bulk",
    "Fwd Avg Packets/Bulk",
    "Fwd Avg Bulk Rate",
    "Bwd Avg Bytes/Bulk",
    "Bwd Avg Packets/Bulk",
    "Bwd Avg Bulk Rate",
]

# =============================================================================
# PIPELINE CONFIG
# =============================================================================
WINDOW_SIZE            = 60       # seconds — aggregation window
MIN_PACKETS_PER_WINDOW = 3      # skip IPs with fewer packets
PACKET_QUEUE_SIZE      = 50000   # max packets in queue
FEATURE_QUEUE_SIZE     = 10000   # max windows in queue

# =============================================================================
# CAPTURE CONFIG
# =============================================================================
CAPTURE_IFACE  = None          # None = offline mode (PCAP)
OFFLINE_MODE    = True          # True = read PCAP, False = live interface
HTTP_PORTS      = [80, 443, 8000, 8080, 8443]
COMMON_PORTS = [53, 80, 443, 22, 123, 137, 389, 88, 21, 465, 3268, 139, 445, 135, 8000, 8080, 8443]
# =============================================================================
# INFERENCE CONFIG
# =============================================================================
DEFAULT_MODEL   = "isolation_forest"  # switchable: isolation_forest, oneclass_svm, bilstm, cnn1d
BURST_EXFIL_THRESHOLD = 0.7  # alert if score > 0.7
SCALER_PATH = MODEL_DIR / "scaler.pkl"

# =============================================================================
# ONLINE ANOMALY MONITOR CONFIG
# =============================================================================
ENABLE_ONLINE_MONITOR    = False        # Disabled by default (opt-in via CLI)
ONLINE_THRESHOLD         = 0.5          # Alert fires when online_score >= threshold
ONLINE_WARMUP_WINDOWS    = 10           # Normal windows needed before scoring starts

# =============================================================================
# LOGGING CONFIG
# =============================================================================
LOG_FILE    = PROJECT_ROOT / "exfil_detection.log"
LOG_LEVEL   = "INFO"  # DEBUG for development
