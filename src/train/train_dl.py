"""
src/train/train_dl.py — Train deep learning models (BiLSTM + CNN1D).

Trains:
  1. BiLSTM — temporal patterns in window sequences
  2. CNN1D — local patterns in feature space

Training data: FULL labeled set (normal + exfil)
Shape: (N, 1, n_features) for Keras
"""

import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import MODEL_DIR, PROCESSED_DIR
from src.utils.helpers import get_logger, setup_logging

logger = get_logger("train_dl")
setup_logging("INFO")

HAS_KERAS = False
try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers, callbacks as keras_callbacks
    from tensorflow.keras.models import Sequential
    HAS_KERAS = True
    tf.get_logger().setLevel("ERROR")
    logger.info(f"TensorFlow version: {tf.__version__}")
except ImportError:
    logger.warning("TensorFlow not available — DL training skipped")


# =============================================================================
# MODEL ARCHITECTURES
# =============================================================================

def build_bilstm(input_shape: tuple) -> keras.Model:
    """
    BiLSTM: learns temporal patterns in window sequences.

    Architecture:
      Input → BiLSTM(64) → Dropout → BiLSTM(32) → Dropout
            → Dense(64, relu) → BatchNorm → Dense(1, sigmoid)
    """
    model = Sequential([
        layers.Input(shape=input_shape),

        layers.Bidirectional(layers.LSTM(64, return_sequences=True)),
        layers.Dropout(0.3),

        layers.Bidirectional(layers.LSTM(32, return_sequences=False)),
        layers.Dropout(0.3),

        layers.Dense(64, activation='relu'),
        layers.BatchNormalization(),
        layers.Dropout(0.3),

        layers.Dense(1, activation='sigmoid'),
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['AUC', 'Precision', 'Recall'],
    )
    return model


def build_cnn1d(input_shape: tuple) -> keras.Model:
    """
    CNN1D: learns local patterns in feature space.

    Architecture:
      Input → Conv1D(64, k=1) → BatchNorm → Conv1D(32, k=1)
            → Flatten → Dense(64, relu) → Dropout → Dense(1, sigmoid)
    """
    model = Sequential([
        layers.Input(shape=input_shape),

        layers.Conv1D(64, kernel_size=1, activation='relu'),
        layers.BatchNormalization(),

        layers.Conv1D(32, kernel_size=1, activation='relu'),
        layers.Flatten(),

        layers.Dense(64, activation='relu'),
        layers.Dropout(0.3),

        layers.Dense(1, activation='sigmoid'),
    ])

    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['AUC', 'Precision', 'Recall'],
    )
    return model


def reshape_for_dl(X: np.ndarray) -> np.ndarray:
    """Reshape (N, n_features) → (N, 1, n_features) for Keras."""
    return X.reshape(X.shape[0], 1, X.shape[1])


def get_class_weights(y: np.ndarray):
    """Compute class weights to handle imbalance."""
    n_pos = y.sum()
    n_neg = len(y) - n_pos
    total = n_pos + n_neg
    return {
        0: total / (2 * n_neg),
        1: total / (2 * n_pos),
    }


def train_model(
    model: keras.Model,
    X_train: np.ndarray, y_train: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_test: np.ndarray, y_test: np.ndarray,
    model_name: str,
    epochs: int = 30,
    batch_size: int = 256,
) -> dict:
    """Train a Keras model with early stopping."""
    logger.info(f"Training {model_name}...")
    t0 = time.time()

    class_weight = get_class_weights(y_train)

    # Callbacks
    early_stop = keras_callbacks.EarlyStopping(
        monitor='val_auc',
        patience=5,
        restore_best_weights=True,
        mode='max',
        verbose=1,
    )

    checkpoint = keras_callbacks.ModelCheckpoint(
        str(MODEL_DIR / f"{model_name.lower()}_best.h5"),
        monitor='val_auc',
        save_best_only=True,
        mode='max',
        verbose=0,
    )

    reduce_lr = keras_callbacks.ReduceLROnPlateau(
        monitor='val_loss',
        factor=0.5,
        patience=3,
        min_lr=1e-6,
        verbose=0,
    )

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=batch_size,
        class_weight=class_weight,
        callbacks=[early_stop, checkpoint, reduce_lr],
        verbose=1,
    )

    elapsed = time.time() - t0
    logger.info(f"  Trained in {elapsed:.1f}s ({len(history.history['loss'])} epochs)")

    # Save final model
    final_path = MODEL_DIR / f"{model_name.lower()}_model.h5"
    model.save(str(final_path))
    logger.info(f"  Saved: {final_path}")

    # Evaluate
    metrics = evaluate_dl_model(model, X_test, y_test, model_name)
    metrics["training_time_s"] = elapsed
    metrics["epochs_trained"] = len(history.history['loss'])

    # Save history
    hist_path = PROCESSED_DIR / f"{model_name.lower()}_history.json"
    with open(hist_path, "w") as f:
        json.dump({k: [float(v) for v in vals] for k, vals in history.history.items()}, f)

    return metrics


def evaluate_dl_model(
    model: keras.Model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    model_name: str,
) -> dict:
    """Evaluate a Keras model on test set."""
    from sklearn.metrics import (
        roc_auc_score, f1_score, precision_score, recall_score,
        confusion_matrix
    )

    preds_prob = model.predict(X_test, verbose=0).ravel()
    preds = (preds_prob >= 0.5).astype(int)

    results = {}
    try:
        results["auc_roc"] = float(roc_auc_score(y_test, preds_prob))
    except ValueError:
        results["auc_roc"] = None

    results["f1"]           = float(f1_score(y_test, preds, zero_division=0))
    results["precision"]    = float(precision_score(y_test, preds, zero_division=0))
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
    """Main DL training pipeline."""
    if not HAS_KERAS:
        logger.error("TensorFlow not available. Install with: pip install tensorflow")
        return {}

    print("\n" + "=" * 70)
    print("DEEP LEARNING TRAINING — BiLSTM + CNN1D")
    print("=" * 70 + "\n")

    # Load data
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

    # Reshape for Keras: (N, n_features) → (N, 1, n_features)
    X_train_dl = reshape_for_dl(X_train)
    X_test_dl  = reshape_for_dl(X_test)
    X_val_dl   = reshape_for_dl(X_val)
    logger.info(f"  DL shape: {X_train_dl.shape}")

    results = {}
    print()

    # --- BiLSTM ---
    logger.info("=" * 60)
    model_bilstm = build_bilstm(input_shape=(1, len(feature_cols)))
    model_bilstm.summary(print_fn=logger.info)
    print()

    bilstm_metrics = train_model(
        model_bilstm,
        X_train_dl, y_train,
        X_val_dl, y_val,
        X_test_dl, y_test,
        model_name="BiLSTM",
        epochs=30,
        batch_size=256,
    )
    results["bilstm"] = bilstm_metrics
    print()

    # --- CNN1D ---
    logger.info("=" * 60)
    model_cnn1d = build_cnn1d(input_shape=(1, len(feature_cols)))
    model_cnn1d.summary(print_fn=logger.info)
    print()

    cnn1d_metrics = train_model(
        model_cnn1d,
        X_train_dl, y_train,
        X_val_dl, y_val,
        X_test_dl, y_test,
        model_name="CNN1D",
        epochs=30,
        batch_size=256,
    )
    results["cnn1d"] = cnn1d_metrics
    print()

    # Save combined results
    out_path = PROCESSED_DIR / "dl_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Results saved: {out_path}")

    print("\n" + "=" * 70)
    print("DEEP LEARNING TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nBiLSTM — AUC: {results['bilstm']['auc_roc']:.4f}  "
          f"F1: {results['bilstm']['f1']:.4f}  Epochs: {results['bilstm']['epochs_trained']}")
    print(f"CNN1D — AUC: {results['cnn1d']['auc_roc']:.4f}  "
          f"F1: {results['cnn1d']['f1']:.4f}  Epochs: {results['cnn1d']['epochs_trained']}")
    print(f"\nModels saved: {MODEL_DIR}/")

    return results


if __name__ == "__main__":
    setup_logging("INFO")
    run_training()
