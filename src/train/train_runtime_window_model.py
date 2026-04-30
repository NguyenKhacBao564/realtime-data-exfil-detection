#!/usr/bin/env python3
"""
Train a lightweight runtime model for live packet-window features.

This model is separate from the CICFlowMeter CNN1D/BiLSTM models. It is used
only in the live demo pipeline, where features are computed directly from
captured packets.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.capture.packet_parser import parse_packet
from src.features.runtime_features import (
    RUNTIME_FEATURE_KEYS,
    build_runtime_feature_matrix,
)
from src.features.window_features import extract_window_features
from src.utils.config import HTTP_PORTS, MODEL_DIR


def extract_features_from_pcap(pcap_path: Path, window_size: float) -> List[Dict]:
    """Extract runtime window features from a PCAP file."""
    if not pcap_path.exists():
        return []

    try:
        from scapy.all import sniff
    except ImportError as exc:
        raise RuntimeError("Scapy is required to extract features from PCAP files") from exc

    buffers = defaultdict(list)

    def callback(pkt):
        parsed = parse_packet(pkt)
        if parsed is None:
            return
        if parsed.get("src_port") not in HTTP_PORTS and parsed.get("dst_port") not in HTTP_PORTS:
            return
        bucket = int(parsed["timestamp"] // window_size) * window_size
        buffers[(parsed.get("src_ip", "unknown"), bucket)].append(parsed)

    sniff(offline=str(pcap_path), prn=callback, store=False, verbose=0)

    rows = []
    for (src_ip, window_start), packets in buffers.items():
        features = extract_window_features(packets, src_ip, window_start)
        if features:
            rows.append(features)
    return rows


def synthetic_normal_rows(n_rows: int, rng: np.random.Generator) -> List[Dict]:
    """Create benign-looking windows for demo model bootstrapping."""
    rows = []
    for _ in range(n_rows):
        req = int(rng.integers(8, 80))
        fwd = int(rng.integers(500, 25_000))
        bwd = int(rng.integers(10_000, 250_000))
        total = fwd + bwd
        duration = float(rng.uniform(8, 60))
        rows.append({
            "request_count": req,
            "total_fwd_bytes": fwd,
            "total_bwd_bytes": bwd,
            "total_bytes": total,
            "upload_download_ratio": fwd / max(bwd, 1),
            "burst_count": int(rng.integers(0, 25)),
            "burst_ratio": float(rng.uniform(0.0, 0.35)),
            "unusual_port_ratio": float(rng.uniform(0.0, 0.2)),
            "request_rate": req / duration,
            "inter_request_time_mean": duration / max(req, 1),
            "inter_request_time_std": float(rng.uniform(0.08, 1.5)),
            "mean_payload_size": total / max(req, 1),
            "std_payload_size": float(rng.uniform(30, 800)),
            "psh_flag_count": int(rng.integers(0, req)),
            "ack_flag_count": req,
            "syn_flag_count": int(rng.integers(1, 8)),
            "window_duration": duration,
        })
    return rows


def synthetic_attack_rows(n_rows: int, rng: np.random.Generator) -> List[Dict]:
    """Create exfil-like burst upload windows for demo model bootstrapping."""
    rows = []
    for _ in range(n_rows):
        req = int(rng.integers(150, 3_000))
        fwd = int(rng.integers(500_000, 8_000_000))
        bwd = int(rng.integers(1_000, 30_000))
        total = fwd + bwd
        duration = float(rng.uniform(5, 15))
        rows.append({
            "request_count": req,
            "total_fwd_bytes": fwd,
            "total_bwd_bytes": bwd,
            "total_bytes": total,
            "upload_download_ratio": fwd / max(bwd, 1),
            "burst_count": int(rng.integers(80, req)),
            "burst_ratio": float(rng.uniform(0.75, 1.0)),
            "unusual_port_ratio": float(rng.uniform(0.0, 0.6)),
            "request_rate": req / duration,
            "inter_request_time_mean": duration / max(req, 1),
            "inter_request_time_std": float(rng.uniform(0.0, 0.04)),
            "mean_payload_size": total / max(req, 1),
            "std_payload_size": float(rng.uniform(500, 5_000)),
            "psh_flag_count": int(rng.integers(req // 3, req)),
            "ack_flag_count": req,
            "syn_flag_count": int(rng.integers(10, 200)),
            "window_duration": duration,
        })
    return rows


def augment_rows(rows: List[Dict], target_rows: int, rng: np.random.Generator) -> List[Dict]:
    """Add small numeric jitter so a tiny PCAP can still train a stable model."""
    if not rows:
        return []
    augmented = list(rows)
    while len(augmented) < target_rows:
        base = dict(rows[int(rng.integers(0, len(rows)))])
        for key in RUNTIME_FEATURE_KEYS:
            value = float(base.get(key, 0.0))
            scale = max(abs(value) * 0.08, 1.0)
            jittered = max(0.0, value + float(rng.normal(0, scale)))
            base[key] = jittered
        augmented.append(base)
    return augmented


def main():
    parser = argparse.ArgumentParser(description="Train runtime RF model for live demo windows.")
    parser.add_argument("--normal-pcap", type=Path, default=None)
    parser.add_argument("--attack-pcap", type=Path, default=PROJECT_ROOT / "data/raw/demo_exfil_local.pcap")
    parser.add_argument("--output", type=Path, default=MODEL_DIR / "runtime_window_rf.pkl")
    parser.add_argument("--window-size", type=float, default=10.0)
    parser.add_argument("--synthetic-rows", type=int, default=200)
    parser.add_argument("--threshold", type=float, default=0.8)
    args = parser.parse_args()

    rng = np.random.default_rng(42)

    normal_rows = []
    attack_rows = []
    if args.normal_pcap:
        normal_rows = extract_features_from_pcap(args.normal_pcap, args.window_size)
    if args.attack_pcap:
        attack_rows = extract_features_from_pcap(args.attack_pcap, args.window_size)

    normal_rows = augment_rows(normal_rows, min(50, args.synthetic_rows), rng)
    attack_rows = augment_rows(attack_rows, min(50, args.synthetic_rows), rng)

    normal_rows.extend(synthetic_normal_rows(args.synthetic_rows, rng))
    attack_rows.extend(synthetic_attack_rows(args.synthetic_rows, rng))

    X = build_runtime_feature_matrix(normal_rows + attack_rows)
    y = np.array([0] * len(normal_rows) + [1] * len(attack_rows), dtype=np.int32)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=120,
        max_depth=8,
        min_samples_leaf=2,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    matrix = confusion_matrix(y_test, y_pred).tolist()

    artifact = {
        "model_type": "runtime_window_rf",
        "model": model,
        "feature_names": RUNTIME_FEATURE_KEYS,
        "threshold": args.threshold,
        "window_size": args.window_size,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "training_rows": {
            "normal": len(normal_rows),
            "attack": len(attack_rows),
        },
        "metrics": {
            "classification_report": report,
            "confusion_matrix": matrix,
        },
        "notes": (
            "Runtime demo model trained on live packet-window features. "
            "It is separate from CICFlowMeter CNN1D/BiLSTM models."
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, args.output)

    summary_path = args.output.with_suffix(".json")
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({
            "output": str(args.output),
            "feature_names": RUNTIME_FEATURE_KEYS,
            "threshold": args.threshold,
            "training_rows": artifact["training_rows"],
            "metrics": artifact["metrics"],
        }, f, indent=2)

    print(f"Saved runtime model: {args.output}")
    print(f"Saved summary: {summary_path}")
    print(f"Rows: normal={len(normal_rows)} attack={len(attack_rows)}")
    print(f"Confusion matrix: {matrix}")


if __name__ == "__main__":
    main()
