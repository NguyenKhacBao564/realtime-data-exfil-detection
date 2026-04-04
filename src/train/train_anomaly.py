"""
src/train/train_anomaly.py — Train anomaly detection models.

Trains:
  1. Isolation Forest (cont=0.05, n_estimators=200)
  2. One-Class SVM (kernel='rbf', nu=0.05)

Training data: NORMAL traffic only (exfil_label=0 from train set)
"""

import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.svm import OneClassSVM
from sklearn.metrics import (
    roc_auc_score, f1_score, precision_score, recall_score,
    confusion_matrix, classification_report
)

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import MODEL_DIR, PROCESSED_DIR
from src.utils.helpers import get_logger, setup_logging

logger = get_logger("train_anomaly")
setup_logging("INFO")


def load_data():
    """Load preprocessed train/test/val numpy arrays."""
    logger.info("Loading preprocessed data...")

    X_train = np.load(PROCESSED_DIR / "X_train_scaled.npy")
    X_test  = np.load(PROCESSED_DIR / "X_test_scaled.npy")
    X_val   = np.load(PROCESSED_DIR / "X_val_scaled.npy")
    y_train = np.load(PROCESSED_DIR / "y_train.npy")
    y_test  = np.load(PROCESSED_DIR / "y_test.npy")
    y_val   = np.load(PROCESSED_DIR / "y_val.npy")

    with open(PROCESSED_DIR / "feature_cols.json") as f:
        feature_cols = json.load(f)

    logger.info(f"  Train: {X_train.shape}, Test: {X_test.shape}, Val: {X_val.shape}")
    logger.info(f"  Features: {len(feature_cols)}")

    return X_train, X_test, X_val, y_train, y_test, y_val, feature_cols


def get_normal_only(X, y):
    """Return only normal (y=0) samples for anomaly training."""
    mask = y == 0
    return X[mask], y[mask]


def train_isolation_forest(X_normal, X_test, y_test):
    """Train and evaluate Isolation Forest."""
    logger.info("=" * 60)
    logger.info("Training Isolation Forest...")
    t0 = time.time()

    model = IsolationForest(
        contamination=0.05,
        n_estimators=200,
        max_samples=256,
        random_state=42,
        n_jobs=-1,
        verbose=0,
    )
    model.fit(X_normal)

    elapsed = time.time() - t0
    logger.info(f"  Trained in {elapsed:.1f}s")

    # Evaluate
    path = MODEL_DIR / "isolation_forest.pkl"
    joblib.dump(model, path)
    logger.info(f"  Saved: {path}")

    metrics = evaluate_anomaly_model(model, X_test, y_test, "IsolationForest")
    return model, metrics


def train_oneclass_svm(X_normal, X_test, y_test, subsample: int = 50000):
    """Train and evaluate One-Class SVM."""
    logger.info("=" * 60)
    logger.info("Training One-Class SVM...")
    t0 = time.time()

    # Subsample if dataset is too large (OCSVM is O(n²))
    if len(X_normal) > subsample:
        rng = np.random.RandomState(42)
        idx = rng.choice(len(X_normal), subsample, replace=False)
        X_train_sub = X_normal[idx]
        logger.info(f"  Subsampled to {subsample:,} samples (OCSVM is slow)")
    else:
        X_train_sub = X_normal

    model = OneClassSVM(
        kernel='rbf',
        gamma='scale',
        nu=0.05,
        verbose=False,
    )
    model.fit(X_train_sub)

    elapsed = time.time() - t0
    logger.info(f"  Trained in {elapsed:.1f}s")

    # Evaluate
    path = MODEL_DIR / "oneclass_svm.pkl"
    joblib.dump(model, path)
    logger.info(f"  Saved: {path}")

    metrics = evaluate_anomaly_model(model, X_test, y_test, "OneClassSVM")
    return model, metrics


def evaluate_anomaly_model(model, X_test, y_test, model_name: str):
    """
    Evaluate an anomaly model on test set.

    Anomaly models: score = decision_function(X)
      - Higher score = more normal
      - Lower score = more anomalous (exfiltration)

    We flip the sign so that HIGH score = exfiltration for consistency.
    """
    # Get raw anomaly scores (higher = more normal)
    raw_scores = model.decision_function(X_test)

    # Flip: high raw_score → low, so that exfil gets high score
    scores = -raw_scores

    # Binary predictions (threshold at 0)
    preds = (scores > 0).astype(int)

    # Metrics
    results = {}
    try:
        results["auc_roc"] = float(roc_auc_score(y_test, scores))
    except ValueError:
        results["auc_roc"] = None

    results["f1"]           = float(f1_score(y_test, preds, zero_division=0))
    results["precision"]     = float(precision_score(y_test, preds, zero_division=0))
    results["recall"]       = float(recall_score(y_test, preds, zero_division=0))
    results["model_name"]   = model_name

    tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
    results["tn"] = int(tn)
    results["fp"] = int(fp)
    results["fn"] = int(fn)
    results["tp"] = int(tp)

    if (fp + tn) > 0:
        results["fpr"] = float(fp / (fp + tn))
    else:
        results["fpr"] = None

    logger.info(f"  [{model_name}] AUC={results['auc_roc']:.4f}  "
                f"F1={results['f1']:.4f}  Prec={results['precision']:.4f}  "
                f"Rec={results['recall']:.4f}  FPR={results['fpr']:.4f}")
    logger.info(f"  Confusion: TP={tp} FP={fp} TN={tn} FN={fn}")

    return results


def run_training():
    """Main training pipeline for anomaly models."""
    print("\n" + "=" * 70)
    print("ANOMALY MODEL TRAINING — Isolation Forest + One-Class SVM")
    print("=" * 70 + "\n")

    # Load data
    X_train, X_test, X_val, y_train, y_test, y_val, feature_cols = load_data()
    print()

    # Extract normal-only data for training
    X_train_normal, y_train_normal = get_normal_only(X_train, y_train)
    logger.info(f"Normal training samples: {len(X_train_normal):,}")

    # Train models
    results = {}
    print()

    if_model, if_metrics = train_isolation_forest(X_train_normal, X_test, y_test)
    results["isolation_forest"] = if_metrics
    print()

    ocsvm_model, ocsvm_metrics = train_oneclass_svm(X_train_normal, X_test, y_test)
    results["oneclass_svm"] = ocsvm_metrics
    print()

    # Save results
    out_path = PROCESSED_DIR / "anomaly_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved: {out_path}")

    print("\n" + "=" * 70)
    print("ANOMALY TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nIsolation Forest — AUC: {results['isolation_forest']['auc_roc']:.4f}  "
          f"F1: {results['isolation_forest']['f1']:.4f}")
    print(f"One-Class SVM     — AUC: {results['oneclass_svm']['auc_roc']:.4f}  "
          f"F1: {results['oneclass_svm']['f1']:.4f}")
    print(f"\nModels saved: {MODEL_DIR}/")

    return results


if __name__ == "__main__":
    from src.utils.helpers import setup_logging
    setup_logging("INFO")
    run_training()
