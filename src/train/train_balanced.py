"""
src/train/train_balanced.py — Improved training with class imbalance handling.

Problem: exfil rate = 0.08% → models predict everything as normal → near-zero precision.

Solutions:
  1. SMOTE oversampling on training data (balance to 10%)
  2. Higher class_weight for exfil class
  3. Focal loss for DL models
"""

import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np
import joblib
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score, confusion_matrix

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import MODEL_DIR, PROCESSED_DIR
from src.utils.helpers import get_logger, setup_logging

logger = get_logger("train_balanced")
setup_logging("INFO")

HAS_KERAS = False
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, callbacks as keras_callbacks
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.backend import epsilon
    HAS_KERAS = True
    tf.get_logger().setLevel("ERROR")
except ImportError:
    pass

HAS_IMBLEARN = False
try:
    from imblearn.over_sampling import SMOTE
    HAS_IMBLEARN = True
    logger.info("imbalanced-learn available — SMOTE will be used")
except ImportError:
    logger.warning("imbalanced-learn not available — install with: pip install imbalanced-learn")


def load_data():
    """Load preprocessed train/test/val numpy arrays."""
    X_train = np.load(PROCESSED_DIR / "X_train_scaled.npy")
    X_test  = np.load(PROCESSED_DIR / "X_test_scaled.npy")
    X_val   = np.load(PROCESSED_DIR / "X_val_scaled.npy")
    y_train = np.load(PROCESSED_DIR / "y_train.npy")
    y_test  = np.load(PROCESSED_DIR / "y_test.npy")
    y_val   = np.load(PROCESSED_DIR / "y_val.npy")
    with open(PROCESSED_DIR / "feature_cols.json") as f:
        feature_cols = json.load(f)
    return X_train, X_test, X_val, y_train, y_test, y_val, feature_cols


def apply_smote(X_train, y_train, target_ratio: float = 0.1, random_state: int = 42):
    """
    Apply SMOTE to balance classes.

    target_ratio=0.1 means minority class = 10% of majority class
    (from 0.08% → ~10% = 112x oversampling of exfil)
    """
    if not HAS_IMBLEARN:
        logger.warning("SMOTE not available — returning original data")
        return X_train, y_train

    # Only oversample exfil class
    n_minority = int((y_train == 1).sum())
    n_majority = int((y_train == 0).sum())

    if n_minority < 10:
        logger.warning("Too few exfil samples for SMOTE")
        return X_train, y_train

    # target_ratio = minority / majority
    sampling_strategy = {1: int(n_majority * target_ratio)}

    smote = SMOTE(
        sampling_strategy=sampling_strategy,
        random_state=random_state,
        k_neighbors=min(5, n_minority - 1),
    )

    X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
    n_new_exfil = int((y_resampled == 1).sum())

    logger.info(f"SMOTE: {n_minority:,} → {n_new_exfil:,} exfil samples "
                f"({n_new_exfil/n_majority*100:.2f}% ratio)")
    return X_resampled, y_resampled


# =============================================================================
# FOCAL LOSS (for better handling of class imbalance)
# =============================================================================

def focal_loss(gamma=2.0, alpha=0.25):
    """Focal loss for extreme class imbalance."""
    def focal_loss_fixed(y_true, y_pred):
        epsilon_v = tf.constant(epsilon(), dtype=y_pred.dtype)
        y_pred = tf.clip_by_value(y_pred, epsilon_v, 1.0 - epsilon_v)

        cross_entropy = -y_true * tf.math.log(y_pred)
        weight = alpha * y_true * tf.pow(1 - y_pred, gamma) + \
                 (1 - alpha) * (1 - y_true) * tf.pow(y_pred, gamma)

        loss = weight * cross_entropy
        return tf.reduce_mean(tf.reduce_sum(loss, axis=-1))
    return focal_loss_fixed


# =============================================================================
# IMPROVED MODELS
# =============================================================================

def build_improved_bilstm(input_shape):
    """BiLSTM with focal loss for better imbalance handling."""
    model = Sequential([
        layers.Input(shape=input_shape),
        layers.Bidirectional(layers.LSTM(64, return_sequences=True)),
        layers.Dropout(0.4),
        layers.Bidirectional(layers.LSTM(32, return_sequences=False)),
        layers.Dropout(0.4),
        layers.Dense(64, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.3),
        layers.Dense(1, activation='sigmoid'),
    ])
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss=focal_loss(gamma=2.0, alpha=0.75),
        metrics=['AUC', 'Precision', 'Recall'],
    )
    return model


def build_improved_cnn1d(input_shape):
    """CNN1D with focal loss."""
    model = Sequential([
        layers.Input(shape=input_shape),
        layers.Conv1D(64, kernel_size=1, activation='relu'),
        layers.BatchNormalization(),
        layers.Conv1D(32, kernel_size=1, activation='relu'),
        layers.GlobalAveragePooling1D(),
        layers.Dense(64, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.4),
        layers.Dense(1, activation='sigmoid'),
    ])
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss=focal_loss(gamma=2.0, alpha=0.75),
        metrics=['AUC', 'Precision', 'Recall'],
    )
    return model


def reshape_for_dl(X):
    return X.reshape(X.shape[0], 1, X.shape[1])


def evaluate_model(model, X_test_dl, y_test, name, model_type="dl"):
    """Evaluate model and return metrics dict."""
    if model_type == "dl":
        probs = model.predict(X_test_dl, verbose=0).ravel()
    else:
        raw = model.decision_function(X_test_dl)
        probs = -raw  # flip sign

    preds = (probs >= 0.5).astype(int)

    results = {}
    results["auc"] = roc_auc_score(y_test, probs) if len(np.unique(y_test)) > 1 else 0.5
    results["f1"] = f1_score(y_test, preds, zero_division=0)
    results["precision"] = precision_score(y_test, preds, zero_division=0)
    results["recall"] = recall_score(y_test, preds, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
    results.update({"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)})
    results["fpr"] = fp / (fp + tn) if (fp + tn) > 0 else 0
    results["name"] = name

    logger.info(f"  [{name}] AUC={results['auc']:.4f} F1={results['f1']:.4f} "
                f"Prec={results['precision']:.4f} Rec={results['recall']:.4f} FPR={results['fpr']:.4f}")
    logger.info(f"  Confusion: TP={tp} FP={fp} TN={tn} FN={fn}")

    return results


def train_with_smote():
    """Main training pipeline with SMOTE oversampling."""
    if not HAS_KERAS:
        logger.error("TensorFlow not available")
        return {}

    print("\n" + "=" * 70)
    print("IMPROVED TRAINING — SMOTE + Focal Loss")
    print("=" * 70 + "\n")

    X_train, X_test, X_val, y_train, y_test, y_val, feature_cols = load_data()
    logger.info(f"Original: Train {len(y_train):,} (exfil={y_train.mean()*100:.3f}%)")

    # Apply SMOTE
    X_train_sm, y_train_sm = apply_smote(X_train, y_train, target_ratio=0.1)
    logger.info(f"After SMOTE: Train {len(y_train_sm):,} (exfil={y_train_sm.mean()*100:.2f}%)")

    # Reshape for Keras
    X_train_dl = reshape_for_dl(X_train_sm)
    X_test_dl  = reshape_for_dl(X_test)
    X_val_dl   = reshape_for_dl(X_val)

    results = {}

    # ── Improved BiLSTM ──
    print()
    logger.info("=" * 60)
    logger.info("Training Improved BiLSTM (Focal Loss + SMOTE)...")
    t0 = time.time()
    model_bilstm = build_improved_bilstm(input_shape=(1, len(feature_cols)))

    early_stop = keras_callbacks.EarlyStopping(
        monitor='val_auc', patience=5, restore_best_weights=True, mode='max', verbose=1)
    reduce_lr = keras_callbacks.ReduceLROnPlateau(
        monitor='val_loss', factor=0.5, patience=3, min_lr=1e-6, verbose=0)

    # Compute focal-friendly class weights
    # alpha=0.75 gives more weight to minority class
    class_weight = {0: 1.0, 1: 10.0}

    history = model_bilstm.fit(
        X_train_dl, y_train_sm,
        validation_data=(X_val_dl, y_val),
        epochs=30,
        batch_size=512,
        class_weight=class_weight,
        callbacks=[early_stop, reduce_lr],
        verbose=1,
    )

    bilstm_path = MODEL_DIR / "bilstm_model.h5"
    model_bilstm.save(str(bilstm_path))
    logger.info(f"  Saved: {bilstm_path}")
    results["bilstm"] = evaluate_model(model_bilstm, X_test_dl, y_test, "BiLSTM-Focal+SMOTE", "dl")
    results["bilstm"]["training_time_s"] = time.time() - t0
    results["bilstm"]["epochs"] = len(history.history['loss'])

    # ── Improved CNN1D ──
    print()
    logger.info("=" * 60)
    logger.info("Training Improved CNN1D (Focal Loss + SMOTE)...")
    t0 = time.time()
    model_cnn1d = build_improved_cnn1d(input_shape=(1, len(feature_cols)))

    history2 = model_cnn1d.fit(
        X_train_dl, y_train_sm,
        validation_data=(X_val_dl, y_val),
        epochs=30,
        batch_size=512,
        class_weight=class_weight,
        callbacks=[early_stop, reduce_lr],
        verbose=1,
    )

    cnn1d_path = MODEL_DIR / "cnn1d_model.h5"
    model_cnn1d.save(str(cnn1d_path))
    logger.info(f"  Saved: {cnn1d_path}")
    results["cnn1d"] = evaluate_model(model_cnn1d, X_test_dl, y_test, "CNN1D-Focal+SMOTE", "dl")
    results["cnn1d"]["training_time_s"] = time.time() - t0
    results["cnn1d"]["epochs"] = len(history2.history['loss'])

    # ── Isolation Forest on SMOTE-balanced data ──
    print()
    logger.info("=" * 60)
    logger.info("Training Isolation Forest on SMOTE-balanced data...")
    X_train_normal_sm = X_train_sm[y_train_sm == 0]

    t0 = time.time()
    if_model = IsolationForest(
        contamination=0.10,
        n_estimators=200,
        max_samples=256,
        random_state=42,
        n_jobs=-1,
    )
    if_model.fit(X_train_normal_sm)
    logger.info(f"  Trained on {len(X_train_normal_sm):,} normal samples (SMOTE-balanced)")

    if_path = MODEL_DIR / "isolation_forest.pkl"
    joblib.dump(if_model, if_path)
    logger.info(f"  Saved: {if_path}")
    results["isolation_forest_smote"] = evaluate_model(
        if_model, X_test, y_test, "IF-SMOTE-balanced", "anomaly")

    # Save results
    out_path = PROCESSED_DIR / "balanced_results.json"
    serializable = {k: {kk: vv for kk, vv in v.items() if kk not in ["scores", "preds"]}
                   for k, v in results.items()}
    with open(out_path, "w") as f:
        json.dump(serializable, f, indent=2)
    logger.info(f"Results saved: {out_path}")

    print("\n" + "=" * 70)
    print("IMPROVED TRAINING COMPLETE")
    print("=" * 70)
    for name, res in sorted(results.items(), key=lambda x: -x[1]["auc"]):
        print(f"  {name:<30} AUC={res['auc']:.4f}  F1={res['f1']:.4f}  "
              f"Prec={res['precision']:.4f}  Rec={res['recall']:.4f}")

    return results


if __name__ == "__main__":
    setup_logging("INFO")
    train_with_smote()
