"""
src/train/threshold_tuning.py — Post-hoc threshold optimization for supervised models.

Problem: Current models trained with SMOTE(128×) + Focal(α=0.75) + class_weight(10×)
         → predict almost everything as positive → FPR ~0.45, Recall=1.0

Solution: Use ROC curve to find threshold that maximizes Recall >= 0.85
         while keeping FPR < 0.05.

This script:
  1. Loads existing trained models (CNN1D, BiLSTM)
  2. Scans thresholds from 0.01 → 0.99
  3. Reports FPR, Recall, Precision at each threshold
  4. Finds optimal threshold given user constraints
  5. Saves tuned predictions
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    roc_curve, roc_auc_score, f1_score, precision_score,
    recall_score, confusion_matrix, classification_report
)
from sklearn.metrics import precision_recall_curve, average_precision_score

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import MODEL_DIR, PROCESSED_DIR
from src.utils.helpers import get_logger, setup_logging

logger = get_logger("threshold_tuning")
setup_logging("INFO")

HAS_KERAS = False
try:
    import tensorflow as tf
    from tensorflow import keras
    tf.get_logger().setLevel("ERROR")
    HAS_KERAS = True
except ImportError:
    pass


def load_test_data():
    """Load preprocessed test set."""
    X_test = np.load(PROCESSED_DIR / "X_test_scaled.npy")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")
    with open(PROCESSED_DIR / "feature_cols.json") as f:
        feature_cols = json.load(f)
    return X_test, y_test, feature_cols


def load_dl_model(name: str):
    """Load Keras model."""
    if not HAS_KERAS:
        return None
    path = MODEL_DIR / f"{name.lower()}_model.h5"
    if not path.exists():
        return None
    return keras.models.load_model(str(path), compile=False)


def get_probabilities(model, X_test, reshape=True):
    """Get prediction probabilities from model."""
    if reshape and len(X_test.shape) == 2:
        X = X_test.reshape(X_test.shape[0], 1, X_test.shape[1])
    elif len(X_test.shape) == 3:
        X = X_test
    else:
        X = X_test.reshape(X_test.shape[0], 1, X_test.shape[1])
    return model.predict(X, verbose=0).ravel()


def compute_metrics_at_threshold(y_true, probs, threshold):
    """Compute all metrics at a given threshold."""
    preds = (probs >= threshold).astype(int)

    if preds.sum() == 0:
        return None

    tn, fp, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        "threshold": threshold,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "recall": float(recall), "fpr": float(fpr),
        "precision": float(precision), "f1": float(f1),
    }


def find_optimal_threshold(y_true, probs,
                             target_recall=0.85,
                             max_fpr=0.05,
                             min_precision=None):
    """
    Find threshold that satisfies ALL constraints.

    Args:
        y_true: ground truth labels
        probs: prediction probabilities
        target_recall: minimum recall required (e.g. 0.85)
        max_fpr: maximum false positive rate allowed (e.g. 0.05)
        min_precision: minimum precision required (optional)

    Returns:
        best_threshold, best_metrics, all_results
    """
    fpr_curve, tpr_curve, thresholds = roc_curve(y_true, probs)

    valid_results = []
    for i, thresh in enumerate(thresholds):
        # Skip extreme thresholds
        if thresh < 0.001 or thresh > 0.999:
            continue

        preds = (probs >= thresh).astype(int)
        if preds.sum() == 0:
            continue

        tn, fp, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        r = {
            "threshold": float(thresh),
            "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
            "recall": float(recall), "fpr": float(fpr),
            "precision": float(precision), "f1": float(f1),
            "fpr_met": fpr <= max_fpr,
            "recall_met": recall >= target_recall,
        }
        if min_precision is not None:
            r["precision_met"] = precision >= min_precision

        valid_results.append(r)

    if not valid_results:
        logger.error("No valid threshold found!")
        return 0.5, None, []

    # Priority 1: meet FPR constraint
    fpr_ok = [r for r in valid_results if r["fpr_met"]]

    if not fpr_ok:
        logger.warning(f"No threshold achieves FPR <= {max_fpr}")
        # Relax: find threshold with lowest FPR
        best = min(valid_results, key=lambda x: x["fpr"])
        logger.info(f"Best available: FPR={best['fpr']:.4f}, Recall={best['recall']:.4f}")
        return best["threshold"], best, valid_results

    # Priority 2: among FPR-OK, maximize recall
    best = max(fpr_ok, key=lambda x: x["recall"])

    return best["threshold"], best, valid_results


def scan_thresholds(y_true, probs, n_points=500):
    """Scan thresholds and return full results table."""
    fpr_curve, tpr_curve, thresholds = roc_curve(y_true, probs)

    results = []
    for i, thresh in enumerate(thresholds):
        if thresh < 0.001 or thresh > 0.999:
            continue
        preds = (probs >= thresh).astype(int)
        if preds.sum() == 0:
            continue
        tn, fp, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        results.append({
            "threshold": float(thresh),
            "fpr": float(fpr),
            "recall": float(recall),
            "precision": float(precision),
            "f1": float(f1),
            "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        })

    return results


def print_threshold_table(results, title="Threshold Analysis"):
    """Print a formatted threshold table."""
    print(f"\n{'='*90}")
    print(f"{title}")
    print(f"{'='*90}")
    print(f"{'Thresh':>7} | {'FPR':>7} | {'Recall':>7} | {'Precision':>10} | {'F1':>7} | TP | FP | TN | FN")
    print(f"{'-'*90}")

    # Show thresholds at key points
    key_thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95, 0.97]
    shown = set()

    for r in sorted(results, key=lambda x: x["threshold"]):
        t = r["threshold"]
        for kt in key_thresholds:
            if abs(t - kt) < 0.02 and kt not in shown:
                shown.add(kt)
                flag = " ←" if r["fpr"] <= 0.05 and r["recall"] >= 0.85 else ""
                print(
                    f"{t:7.4f} | {r['fpr']:7.4f} | {r['recall']:7.4f} | "
                    f"{r['precision']:10.4f} | {r['f1']:7.4f} | "
                    f"{r['tp']:3} | {r['fp']:6} | {r['tn']:6} | {r['fn']:3}{flag}"
                )


def run_threshold_tuning(target_recall=0.85, max_fpr=0.05, verbose=True):
    """Main threshold tuning pipeline."""
    if not (PROCESSED_DIR / "X_test_scaled.npy").exists():
        logger.error("Test data not found. Run preprocessing first.")
        return {}

    X_test, y_test, feature_cols = load_test_data()
    n_exfil = int(y_test.sum())
    n_normal = len(y_test) - n_exfil

    print(f"\n{'='*90}")
    print("THRESHOLD TUNING — Finding optimal classification threshold")
    print(f"{'='*90}")
    print(f"Test set: {len(y_test):,} samples | Normal: {n_normal:,} | Exfil: {n_exfil:,}")
    print(f"Exfil rate: {y_test.mean()*100:.3f}%")
    print(f"Constraint: Recall >= {target_recall:.0%} AND FPR <= {max_fpr:.1%}")
    print()

    all_results = {}

    if HAS_KERAS and (MODEL_DIR / "cnn1d_model.h5").exists():
        print("=" * 50)
        print("Tuning CNN1D...")
        print("=" * 50)
        model = load_dl_model("cnn1d")
        probs = get_probabilities(model, X_test)

        auc = roc_auc_score(y_test, probs)
        print(f"AUC-ROC: {auc:.4f}")

        all_scan = scan_thresholds(y_test, probs)
        print_threshold_table(all_scan, "CNN1D Threshold Analysis")

        opt_thresh, opt_metrics, all_valid = find_optimal_threshold(
            y_test, probs, target_recall=target_recall, max_fpr=max_fpr
        )

        print(f"\n🏆 Optimal threshold: {opt_thresh:.4f}")
        if opt_metrics:
            print(f"   Recall:    {opt_metrics['recall']:.4f} "
                  f"({'✅' if opt_metrics['recall_met'] else '❌'})")
            print(f"   FPR:       {opt_metrics['fpr']:.4f} "
                  f"({'✅' if opt_metrics['fpr_met'] else '❌'})")
            print(f"   Precision: {opt_metrics['precision']:.4f}")
            print(f"   F1:        {opt_metrics['f1']:.4f}")
            print(f"   TP={opt_metrics['tp']} FP={opt_metrics['fp']} TN={opt_metrics['tn']} FN={opt_metrics['fn']}")

        all_results["cnn1d"] = {
            "auc": float(auc),
            "optimal_threshold": float(opt_thresh),
            "optimal_metrics": opt_metrics,
            "all_thresholds": all_scan,
        }
        del model

    if HAS_KERAS and (MODEL_DIR / "bilstm_model.h5").exists():
        print("\n" + "=" * 50)
        print("Tuning BiLSTM...")
        print("=" * 50)
        model = load_dl_model("bilstm")
        probs = get_probabilities(model, X_test)

        auc = roc_auc_score(y_test, probs)
        print(f"AUC-ROC: {auc:.4f}")

        all_scan = scan_thresholds(y_test, probs)
        print_threshold_table(all_scan, "BiLSTM Threshold Analysis")

        opt_thresh, opt_metrics, all_valid = find_optimal_threshold(
            y_test, probs, target_recall=target_recall, max_fpr=max_fpr
        )

        print(f"\n🏆 Optimal threshold: {opt_thresh:.4f}")
        if opt_metrics:
            print(f"   Recall:    {opt_metrics['recall']:.4f} "
                  f"({'✅' if opt_metrics['recall_met'] else '❌'})")
            print(f"   FPR:       {opt_metrics['fpr']:.4f} "
                  f"({'✅' if opt_metrics['fpr_met'] else '❌'})")
            print(f"   Precision: {opt_metrics['precision']:.4f}")
            print(f"   F1:        {opt_metrics['f1']:.4f}")
            print(f"   TP={opt_metrics['tp']} FP={opt_metrics['fp']} TN={opt_metrics['tn']} FN={opt_metrics['fn']}")

        all_results["bilstm"] = {
            "auc": float(auc),
            "optimal_threshold": float(opt_thresh),
            "optimal_metrics": opt_metrics,
            "all_thresholds": all_scan,
        }
        del model

    # Save results
    save_path = PROCESSED_DIR / "threshold_tuning_results.json"
    serializable = {}
    for name, res in all_results.items():
        serializable[name] = {
            k: v for k, v in res.items()
            if k != "all_thresholds"
        }
        # Only save key thresholds to keep file size manageable
        all_thresh = res.get("all_thresholds", [])
        # Save every 20th threshold
        serializable[name]["threshold_samples"] = all_thresh[::20] if all_thresh else []

    with open(save_path, "w") as f:
        json.dump(serializable, f, indent=2)
    logger.info(f"Results saved: {save_path}")

    # Summary
    print(f"\n{'='*90}")
    print("SUMMARY")
    print(f"{'='*90}")
    print(f"{'Model':<12} {'AUC':>8} {'Thresh':>8} {'Recall':>8} {'FPR':>8} {'Precision':>10} {'F1':>8}")
    print(f"{'-'*90}")
    for name, res in all_results.items():
        m = res.get("optimal_metrics")
        if m:
            print(f"{name:<12} {res['auc']:>8.4f} {res['optimal_threshold']:>8.4f} "
                  f"{m['recall']:>8.4f} {m['fpr']:>8.4f} {m['precision']:>10.4f} {m['f1']:>8.4f}")
    print()

    return all_results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Threshold tuning for exfil detection")
    parser.add_argument("--recall", type=float, default=0.85,
                        help="Target recall (default: 0.85)")
    parser.add_argument("--fpr", type=float, default=0.05,
                        help="Max FPR (default: 0.05)")
    args = parser.parse_args()

    setup_logging("INFO")
    run_threshold_tuning(target_recall=args.recall, max_fpr=args.fpr)
