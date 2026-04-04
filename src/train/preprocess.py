"""
src/train/preprocess.py — Dataset preprocessing and train/test/val split.

Based on EDA findings:
- PRIMARY EXFIL PROXY: Bot traffic (Friday-Morning) — upload 4.5x > download, short sessions
- SECONDARY: Infiltration (36 flows) — port scan + backdoor behavior
- Custom heuristics augment the exfil label

Labeling scheme:
  Label 0 = Normal (BENIGN traffic)
  Label 1 = Exfiltration (Bot + Infiltration + custom heuristic flows)
"""

import os
import sys
import json
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import joblib

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import (
    CSV_FILES, PROCESSED_DIR, MODEL_DIR,
    TRAIN_RATIO, TEST_RATIO, VAL_RATIO, RANDOM_STATE,
    COLS_TO_DROP, EXFIL_LABELS, NORMAL_LABELS,
)
from src.utils.helpers import normalize_columns, clip_inf, get_logger

warnings.filterwarnings("ignore")
logger = get_logger("preprocess")


def load_and_merge_csv() -> pd.DataFrame:
    """
    Load all CSV files, normalize columns, merge into single DataFrame.
    Returns: DataFrame with all flows
    """
    logger.info("Loading and merging all CSV files...")
    dfs = []
    for name, path in CSV_FILES.items():
        if not path.exists():
            logger.warning(f"  File not found: {path} — skipping")
            continue
        logger.info(f"  Loading {name}: {path.name}")
        df = pd.read_csv(path, low_memory=False)
        df = normalize_columns(df)
        df["_source_file"] = name
        dfs.append(df)
        logger.info(f"    Shape: {df.shape}, Labels: {df['Label'].unique().tolist()}")

    if not dfs:
        raise RuntimeError("No CSV files loaded!")

    df = pd.concat(dfs, ignore_index=True)
    logger.info(f"Merged DataFrame: {df.shape}")
    return df


def assign_exfil_label(df: pd.DataFrame) -> pd.DataFrame:
    """
    Assign exfiltration labels based on EDA findings.

    Label 0 = Normal traffic
    Label 1 = Exfiltration

    Exfil proxies:
    - Bot traffic (Friday-Morning): 1,966 flows
      → high upload ratio, short sessions, automated behavior
    - Infiltration (Thursday-Afternoon): 36 flows
      → port scan + backdoor
    """
    logger.info("Assigning exfiltration labels...")

    # Copy to avoid SettingWithCopyWarning
    df = df.copy()

    # 1. Direct label assignment from known attack types
    def _map_label(label):
        label = str(label).strip()
        if label in EXFIL_LABELS:
            return 1
        elif label in NORMAL_LABELS:
            return 0
        else:
            return 0  # Other attacks (DoS, DDoS, PortScan) → treat as "not exfil" for now

    df["exfil_label"] = df["Label"].apply(_map_label)

    # 2. Custom heuristic augmentation for exfil detection
    # Compute upload ratio
    fwd_bytes = clip_inf(df["Total Length of Fwd Packets"].copy(), 0)
    bwd_bytes = clip_inf(df["Total Length of Bwd Packets"].copy(), 0)
    upload_ratio = fwd_bytes / bwd_bytes.replace(0, 1)
    upload_ratio = upload_ratio.replace([np.inf, -np.inf], np.nan).clip(0, 100)

    # Session duration
    duration = clip_inf(df["Flow Duration"].copy(), 0)

    # PSH flag ratio
    psh_flags = clip_inf(df["PSH Flag Count"].copy(), 0)
    total_packets = clip_inf(df["Total Fwd Packets"].copy(), 0) + \
                    clip_inf(df["Total Backward Packets"].copy(), 0)
    psh_ratio = (psh_flags / total_packets.replace(0, 1)).clip(0, 1)

    # Custom heuristic: suspicious if ALL of these are true:
    # - upload_ratio > 5.0 (very high upload)
    # - duration < 600s (short session = automated)
    # - psh_ratio > 0.3 (some push flags = active transfer)
    heuristic_exfil = (
        (upload_ratio > 5.0) &
        (duration < 600_000_000) &  # microseconds
        (psh_ratio > 0.3)
    )

    # Count heuristic detections
    heuristic_count = heuristic_exfil.sum()
    logger.info(f"  Heuristic exfil flows (not already labeled): {heuristic_count}")

    # Only apply heuristic to flows not already labeled as exfil
    # (avoid double-counting Bot/Infiltration)
    already_exfil = df["exfil_label"] == 1
    df.loc[already_exfil, "exfil_label"] = 1
    df.loc[~already_exfil & heuristic_exfil, "exfil_label"] = 1

    # Summary
    total_exfil = df["exfil_label"].sum()
    total_normal = len(df) - total_exfil
    logger.info(f"  Label distribution:")
    logger.info(f"    Normal (0): {total_normal:,}")
    logger.info(f"    Exfiltration (1): {total_exfil:,}")
    logger.info(f"    Ratio: {total_exfil/len(df)*100:.2f}% exfil")

    return df


def clean_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean dataset: remove bad columns, handle inf/nan, select features.
    """
    logger.info("Cleaning features...")

    # Drop known bad columns
    original_cols = len(df.columns)
    for col in COLS_TO_DROP:
        if col in df.columns:
            df = df.drop(columns=[col])

    dropped = original_cols - len(df.columns)
    logger.info(f"  Dropped {dropped} bad columns")

    # Get feature columns (exclude metadata and label columns)
    exclude_cols = {
        "Label", "exfil_label", "_source_file",
        "Source IP", "Destination IP", "Source Port", "Destination Port",
        "Protocol", "Timestamp",
    }
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    # Only keep numeric columns
    numeric_cols = df[feature_cols].select_dtypes(include=[np.number]).columns.tolist()
    df = df[numeric_cols + ["exfil_label"]]

    logger.info(f"  Numeric features: {len(numeric_cols)}")

    # Replace inf with nan
    for col in numeric_cols:
        df[col] = clip_inf(df[col], 0)

    # Fill remaining nan with 0
    df[numeric_cols] = df[numeric_cols].fillna(0)

    # Remove rows where ALL features are 0 (corrupted flows)
    feature_sum = df[numeric_cols].abs().sum(axis=1)
    df = df[feature_sum > 0]
    logger.info(f"  After removing zero-sum rows: {len(df):,} rows")

    return df, numeric_cols


def split_data(df: pd.DataFrame, numeric_cols: list) -> dict:
    """
    Split into train/test/val with stratification.
    Train set: only NORMAL traffic (for anomaly models)
    Full labeled set: for supervised models
    """
    logger.info("Splitting data (stratified)...")

    # Stratified split: 70 train, 15 test, 15 val
    X = df[numeric_cols].values
    y = df["exfil_label"].values

    # First split: 70% train, 30% temp
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y, test_size=(TEST_RATIO + VAL_RATIO),
        stratify=y, random_state=RANDOM_STATE,
    )

    # Second split: 15% test, 15% val
    val_ratio = VAL_RATIO / (TEST_RATIO + VAL_RATIO)
    n_temp = len(X_temp)
    n_val = int(n_temp * val_ratio)

    X_test = X_temp[:n_val]
    y_test = y_temp[:n_val]
    X_val  = X_temp[n_val:]
    y_val  = y_temp[n_val:]

    logger.info(f"  Train: {len(X_train):,} ({y_train.mean()*100:.2f}% exfil)")
    logger.info(f"  Test:  {len(X_test):,} ({y_test.mean()*100:.2f}% exfil)")
    logger.info(f"  Val:   {len(X_val):,} ({y_val.mean()*100:.2f}% exfil)")

    # For ANOMALY models — only normal traffic in training
    normal_mask_train = y_train == 0
    X_train_normal = X_train[normal_mask_train]
    logger.info(f"  Anomaly train (normal only): {len(X_train_normal):,}")

    # Create DataFrames with column names for saving
    df_train = pd.DataFrame(X_train, columns=numeric_cols)
    df_train["exfil_label"] = y_train

    df_test = pd.DataFrame(X_test, columns=numeric_cols)
    df_test["exfil_label"] = y_test

    df_val = pd.DataFrame(X_val, columns=numeric_cols)
    df_val["exfil_label"] = y_val

    return {
        "train": (df_train, X_train, y_train),
        "test":  (df_test,  X_test,  y_test),
        "val":   (df_val,   X_val,   y_val),
        "anomaly_train": (X_train_normal, y_train[normal_mask_train]),
        "feature_cols": numeric_cols,
    }


def fit_scaler(X_train, save_path: Path) -> StandardScaler:
    """Fit StandardScaler on training data and save."""
    logger.info("Fitting StandardScaler...")
    scaler = StandardScaler()
    scaler.fit(X_train)
    joblib.dump(scaler, save_path)
    logger.info(f"  Scaler saved: {save_path}")
    return scaler


def save_splits(splits: dict, out_dir: Path):
    """Save train/test/val CSVs."""
    for name in ["train", "test", "val"]:
        df, *_ = splits[name]
        path = out_dir / f"{name}.csv"
        df.to_csv(path, index=False)
        logger.info(f"  Saved {name}: {path} ({len(df):,} rows)")
    logger.info("All splits saved.")


def run_preprocessing():
    """Main preprocessing pipeline."""
    print("\n" + "="*70)
    print("PREPROCESSING PIPELINE — CICIDS2017 Exfiltration Detection")
    print("="*70 + "\n")

    # 1. Load & merge
    df = load_and_merge_csv()
    print()

    # 2. Assign labels
    df = assign_exfil_label(df)
    print()

    # 3. Clean features
    df, feature_cols = clean_features(df)
    print()

    # 4. Split
    splits = split_data(df, feature_cols)
    print()

    # 5. Fit scaler (on full train set, not just normal)
    scaler = fit_scaler(splits["train"][1], MODEL_DIR / "scaler.pkl")

    # Apply scaling
    X_train, y_train = splits["train"][1], splits["train"][2]
    X_test,  y_test  = splits["test"][1],  splits["test"][2]
    X_val,   y_val   = splits["val"][1],   splits["val"][2]

    X_train_scaled = scaler.transform(X_train)
    X_test_scaled  = scaler.transform(X_test)
    X_val_scaled   = scaler.transform(X_val)

    # Save scaled data
    np.save(PROCESSED_DIR / "X_train_scaled.npy", X_train_scaled)
    np.save(PROCESSED_DIR / "X_test_scaled.npy",  X_test_scaled)
    np.save(PROCESSED_DIR / "X_val_scaled.npy",   X_val_scaled)
    np.save(PROCESSED_DIR / "y_train.npy",        y_train)
    np.save(PROCESSED_DIR / "y_test.npy",         y_test)
    np.save(PROCESSED_DIR / "y_val.npy",          y_val)

    # Save feature column names
    with open(PROCESSED_DIR / "feature_cols.json", "w") as f:
        json.dump(feature_cols, f, indent=2)

    # 6. Save CSVs
    save_splits(splits, PROCESSED_DIR)
    print()

    # 7. Summary
    summary = {
        "total_rows": int(len(df)),
        "train_rows": int(len(X_train)),
        "test_rows":  int(len(X_test)),
        "val_rows":   int(len(X_val)),
        "n_features": len(feature_cols),
        "exfil_count_train": int(y_train.sum()),
        "exfil_count_test":  int(y_test.sum()),
        "exfil_count_val":   int(y_val.sum()),
        "feature_cols": feature_cols,
        "label_distribution": {
            "normal": int((y_train == 0).sum()),
            "exfil":  int((y_train == 1).sum()),
        },
    }
    summary_path = PROCESSED_DIR / "preprocessing_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    logger.info(f"Preprocessing summary: {summary_path}")

    print("\n" + "="*70)
    print("PREPROCESSING COMPLETE")
    print("="*70)
    print(f"  Features: {len(feature_cols)}")
    print(f"  Train: {len(X_train):,} | Test: {len(X_test):,} | Val: {len(X_val):,}")
    print(f"  Exfil rate (train): {y_train.mean()*100:.3f}%")
    print(f"  Outputs: {PROCESSED_DIR}/")

    return splits, scaler, feature_cols


if __name__ == "__main__":
    from src.utils.helpers import setup_logging
    setup_logging("INFO")
    run_preprocessing()
