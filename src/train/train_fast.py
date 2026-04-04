"""
src/train/train_fast.py — Fast training with subsampled data.

Dataset too large (2.17M) → subsample to 200K rows.
Batch size 2048, epochs 10.
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

logger = get_logger("train_fast")
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
except ImportError:
    pass


def load_data():
    X_train = np.load(PROCESSED_DIR / "X_train_scaled.npy")
    X_test  = np.load(PROCESSED_DIR / "X_test_scaled.npy")
    X_val   = np.load(PROCESSED_DIR / "X_val_scaled.npy")
    y_train = np.load(PROCESSED_DIR / "y_train.npy")
    y_test  = np.load(PROCESSED_DIR / "y_test.npy")
    y_val   = np.load(PROCESSED_DIR / "y_val.npy")
    with open(PROCESSED_DIR / "feature_cols.json") as f:
        feature_cols = json.load(f)
    return X_train, X_test, X_val, y_train, y_test, y_val, feature_cols


def subsample_balanced(X, y, target_n=200000, random_state=42):
    """Subsample to target_n rows, preserving class ratio."""
    rng = np.random.RandomState(random_state)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())

    target_pos = min(n_pos, int(target_n * 0.1))
    target_neg = target_n - target_pos

    pos_idx = rng.choice(np.where(y == 1)[0], size=target_pos, replace=False)
    neg_idx = rng.choice(np.where(y == 0)[0], size=target_neg, replace=False)

    idx = np.concatenate([pos_idx, neg_idx])
    rng.shuffle(idx)
    return X[idx], y[idx]


def focal_loss(gamma=2.0, alpha=0.75):
    def _focal(y_true, y_pred):
        eps = tf.constant(epsilon(), dtype=y_pred.dtype)
        y_pred = tf.clip_by_value(y_pred, eps, 1.0 - eps)
        cross_entropy = -y_true * tf.math.log(y_pred)
        weight = alpha * y_true * tf.pow(1 - y_pred, gamma) + \
                 (1 - alpha) * (1 - y_true) * tf.pow(y_pred, gamma)
        return tf.reduce_mean(tf.reduce_sum(weight * cross_entropy, axis=-1))
    return _focal


def build_model(model_type, input_shape):
    if model_type == "bilstm":
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
    else:  # cnn1d
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


def evaluate(model, X_test_dl, y_test, name, model_type="dl"):
    if model_type == "dl":
        probs = model.predict(X_test_dl, verbose=0).ravel()
    else:
        raw = model.decision_function(X_test_dl)
        probs = -raw

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


def run():
    if not HAS_KERAS:
        logger.error("TensorFlow not available")
        return {}

    print("\n" + "=" * 70)
    print("FAST TRAINING — Subsampled Data + Focal Loss + SMOTE")
    print("=" * 70 + "\n")

    X_train, X_test, X_val, y_train, y_test, y_val, feature_cols = load_data()
    logger.info(f"Original: {len(y_train):,} samples (exfil={y_train.mean()*100:.3f}%)")

    # Apply SMOTE first (only on subsample for speed)
    n_subsample = 200000
    X_sub, y_sub = subsample_balanced(X_train, y_train, target_n=n_subsample)
    logger.info(f"Subsampled: {len(y_sub):,} (exfil={y_sub.mean()*100:.2f}%)")

    if HAS_IMBLEARN:
        smote = SMOTE(sampling_strategy={1: int(len(y_sub) * 0.1)}, random_state=42, k_neighbors=5)
        X_sub, y_sub = smote.fit_resample(X_sub, y_sub)
        logger.info(f"After SMOTE: {len(y_sub):,} (exfil={y_sub.mean()*100:.2f}%)")

    # Reshape for Keras
    X_train_dl = X_sub.reshape(X_sub.shape[0], 1, X_sub.shape[1])
    X_test_dl  = X_test.reshape(X_test.shape[0], 1, X_test.shape[1])
    X_val_dl   = X_val.reshape(X_val.shape[0], 1, X_val.shape[1])

    results = {}
    input_shape = (1, len(feature_cols))

    # ── BiLSTM ──
    print()
    logger.info("=" * 60)
    logger.info("Training BiLSTM (Focal Loss)...")
    t0 = time.time()

    model_bilstm = build_model("bilstm", input_shape)

    early_stop = keras_callbacks.EarlyStopping(
        monitor='val_auc', patience=5, restore_best_weights=True, mode='max', verbose=1)
    reduce_lr = keras_callbacks.ReduceLROnPlateau(
        monitor='val_loss', factor=0.5, patience=3, min_lr=1e-6, verbose=0)

    history = model_bilstm.fit(
        X_train_dl, y_sub,
        validation_data=(X_val_dl, y_val),
        epochs=10,
        batch_size=2048,
        class_weight={0: 1.0, 1: 10.0},
        callbacks=[early_stop, reduce_lr],
        verbose=1,
    )

    bilstm_path = MODEL_DIR / "bilstm_model.h5"
    model_bilstm.save(str(bilstm_path))
    logger.info(f"  Saved: {bilstm_path} ({time.time()-t0:.0f}s, {len(history.history['loss'])} epochs)")
    results["bilstm"] = evaluate(model_bilstm, X_test_dl, y_test, "BiLSTM-Focal+SMOTE", "dl")

    # ── CNN1D ──
    print()
    logger.info("=" * 60)
    logger.info("Training CNN1D (Focal Loss)...")
    t0 = time.time()

    model_cnn1d = build_model("cnn1d", input_shape)

    history2 = model_cnn1d.fit(
        X_train_dl, y_sub,
        validation_data=(X_val_dl, y_val),
        epochs=10,
        batch_size=2048,
        class_weight={0: 1.0, 1: 10.0},
        callbacks=[early_stop, reduce_lr],
        verbose=1,
    )

    cnn1d_path = MODEL_DIR / "cnn1d_model.h5"
    model_cnn1d.save(str(cnn1d_path))
    logger.info(f"  Saved: {cnn1d_path} ({time.time()-t0:.0f}s, {len(history2.history['loss'])} epochs)")
    results["cnn1d"] = evaluate(model_cnn1d, X_test_dl, y_test, "CNN1D-Focal+SMOTE", "dl")

    # ── Isolation Forest on SMOTE-balanced data ──
    print()
    logger.info("=" * 60)
    logger.info("Training Isolation Forest on SMOTE-balanced data...")

    X_normal = X_sub[y_sub == 0]
    if_model = IsolationForest(
        contamination=0.10,
        n_estimators=200,
        max_samples=256,
        random_state=42,
        n_jobs=-1,
    )
    if_model.fit(X_normal)
    if_path = MODEL_DIR / "isolation_forest.pkl"
    joblib.dump(if_model, if_path)
    logger.info(f"  Saved: {if_path}")
    results["isolation_forest"] = evaluate(if_model, X_test, y_test, "IF-SMOTE-balanced", "anomaly")

    # Save results
    out_path = PROCESSED_DIR / "fast_training_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved: {out_path}")

    print("\n" + "=" * 70)
    print("FAST TRAINING COMPLETE")
    print("=" * 70)
    for name, res in sorted(results.items(), key=lambda x: -x[1]["auc"]):
        print(f"  {name:<30} AUC={res['auc']:.4f}  F1={res['f1']:.4f}  "
              f"Prec={res['precision']:.4f}  Rec={res['recall']:.4f}")

    return results


if __name__ == "__main__":
    setup_logging("INFO")
    run()
