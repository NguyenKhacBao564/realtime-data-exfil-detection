"""
src/train/evaluate.py — Evaluation: ROC curves, confusion matrices, metric comparison.

Evaluates all 4 models on test set:
  1. Isolation Forest (.pkl)
  2. One-Class SVM (.pkl)
  3. BiLSTM (.h5)
  4. CNN1D (.h5)

Outputs:
  - notebooks/roc_curves.png
  - notebooks/confusion_matrices.png
  - data/processed/evaluation_results.json
  - docs/metrics_report.md
"""

import sys
import json
import warnings
from pathlib import Path

import numpy as np
from sklearn.metrics import (
    roc_curve, auc, roc_auc_score,
    f1_score, precision_score, recall_score,
    confusion_matrix, classification_report
)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import MODEL_DIR, PROCESSED_DIR, NOTEBOOKS_DIR, DOCS_DIR
from src.utils.helpers import get_logger, setup_logging

logger = get_logger("evaluate")
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
    """Load test set."""
    X_test = np.load(PROCESSED_DIR / "X_test_scaled.npy")
    y_test = np.load(PROCESSED_DIR / "y_test.npy")
    with open(PROCESSED_DIR / "feature_cols.json") as f:
        feature_cols = json.load(f)
    return X_test, y_test, feature_cols


def load_anomaly_model(name: str):
    """Load a sklearn anomaly model."""
    import joblib
    path = MODEL_DIR / f"{name}.pkl"
    if not path.exists():
        return None
    return joblib.load(path)


def load_dl_model(name: str):
    """Load a Keras model. Prefers _final (tuned threshold) models."""
    if not HAS_KERAS:
        return None
    # Prefer final (tuned) model if it exists
    final_path = MODEL_DIR / f"{name.lower()}_final.h5"
    if final_path.exists():
        return keras.models.load_model(str(final_path), compile=False)
    # Fall back to original model
    path = MODEL_DIR / f"{name.lower()}_model.h5"
    if not path.exists():
        return None
    return keras.models.load_model(str(path))


def evaluate_anomaly(model, X_test, y_test, name: str):
    """
    Evaluate an anomaly model.
    For sklearn anomaly: decision_function gives anomaly score.
    Higher = more normal → flip sign so higher = more exfil.
    """
    raw_scores = model.decision_function(X_test)
    scores = -raw_scores  # flip: high score = exfil
    preds = (scores > 0).astype(int)

    results = {"name": name, "type": "anomaly", "scores": scores, "preds": preds}
    results["auc"] = roc_auc_score(y_test, scores) if len(np.unique(y_test)) > 1 else 0.5
    results["f1"] = f1_score(y_test, preds, zero_division=0)
    results["precision"] = precision_score(y_test, preds, zero_division=0)
    results["recall"] = recall_score(y_test, preds, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
    results.update({"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)})
    results["fpr"] = fp / (fp + tn) if (fp + tn) > 0 else 0
    results["fpr_curve"] = compute_fpr_curve(y_test, scores)
    return results


def evaluate_supervised(model, X_test, y_test, name: str):
    """
    Evaluate a supervised model.
    X_test is (N, 1, n_features) for Keras.
    Uses tuned thresholds from final_results.json when available,
    otherwise falls back to 0.5.
    """
    if len(X_test.shape) == 3:
        # Keras expects (N, 1, n_features)
        probs = model.predict(X_test, verbose=0).ravel()
    else:
        probs = model.predict(X_test, verbose=0).ravel()

    # Try to load tuned threshold
    threshold = 0.5
    tuned_threshold_path = PROCESSED_DIR / "final_results.json"
    if tuned_threshold_path.exists():
        try:
            with open(tuned_threshold_path) as f:
                fr = json.load(f)
            # Match model name to result key
            key = name  # e.g. "CNN1D"
            if key in fr and "optimal_threshold" in fr[key]:
                threshold = fr[key]["optimal_threshold"]
                logger.info(f"  Using tuned threshold {threshold:.4f} for {name}")
        except Exception:
            pass

    preds = (probs >= threshold).astype(int)

    results = {
        "name": name,
        "type": "supervised",
        "scores": probs,
        "preds": preds,
        "threshold_used": threshold,
    }
    results["auc"] = roc_auc_score(y_test, probs) if len(np.unique(y_test)) > 1 else 0.5
    results["f1"] = f1_score(y_test, preds, zero_division=0)
    results["precision"] = precision_score(y_test, preds, zero_division=0)
    results["recall"] = recall_score(y_test, preds, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_test, preds, labels=[0, 1]).ravel()
    results.update({"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)})
    results["fpr"] = fp / (fp + tn) if (fp + tn) > 0 else 0
    results["fpr_curve"] = compute_fpr_curve(y_test, probs)
    return results


def compute_fpr_curve(y_true, scores, num_points=200):
    """Compute FPR at various thresholds for sensitivity analysis."""
    fpr_vals, tpr_vals, thresholds = roc_curve(y_true, scores)
    return {"fpr": fpr_vals.tolist(), "tpr": tpr_vals.tolist(),
            "thresholds": thresholds.tolist()}


def plot_roc_curves(all_results: list, save_path: Path):
    """Plot ROC curves for all 4 models on 1 plot."""
    plt.figure(figsize=(10, 8))
    colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12"]
    linestyles = ["-", "--", "-.", ":"]

    for i, res in enumerate(all_results):
        if res is None:
            continue
        fpr_data = res["fpr_curve"]
        fpr = np.array(fpr_data["fpr"])
        tpr = np.array(fpr_data["tpr"])
        # Ensure AUC is valid
        try:
            auc_val = roc_auc_score(
                np.load(PROCESSED_DIR / "y_test.npy"),
                res["scores"]
            )
        except Exception:
            auc_val = 0.5

        label = f"{res['name']} (AUC = {auc_val:.4f})"
        plt.plot(fpr, tpr, label=label, color=colors[i % len(colors)],
                 linestyle=linestyles[i % len(linestyles)], linewidth=2)

    plt.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Random (AUC = 0.5000)")
    plt.xlabel("False Positive Rate", fontsize=12)
    plt.ylabel("True Positive Rate", fontsize=12)
    plt.title("ROC Curves — Exfiltration Detection Models", fontsize=14, fontweight="bold")
    plt.legend(loc="lower right", fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"ROC curves saved: {save_path}")


def plot_confusion_matrices(all_results: list, save_path: Path):
    """Plot 2×2 grid of confusion matrices for all models."""
    valid_results = [r for r in all_results if r is not None]
    n = len(valid_results)
    cols = 2
    rows = (n + 1) // cols

    fig, axes = plt.subplots(rows, cols, figsize=(10, 4 * rows))
    if n == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for idx, res in enumerate(valid_results):
        ax = axes[idx]
        cm = np.array([[res["tn"], res["fp"]], [res["fn"], res["tp"]]])

        sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", ax=ax,
                    xticklabels=["Normal", "Exfil"],
                    yticklabels=["Normal", "Exfil"],
                    annot_kws={"size": 14})
        ax.set_title(f"{res['name']}", fontsize=12, fontweight="bold")
        ax.set_xlabel("Predicted")
        ax.set_ylabel("Actual")

    # Hide unused subplots
    for idx in range(n, len(axes)):
        axes[idx].axis("off")

    plt.suptitle("Confusion Matrices — All Models", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Confusion matrices saved: {save_path}")


def write_metrics_report(all_results: list, save_path: Path):
    """Write markdown metrics report."""
    lines = [
        "# Metrics Report — Exfiltration Detection\n",
        "> Generated automatically by `src/train/evaluate.py`\n",
        "## Summary Table\n",
        "| Model | Type | AUC-ROC | F1 | Precision | Recall | FPR | TP | FP | TN | FN |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for res in all_results:
        if res is None:
            continue
        lines.append(
            f"| {res['name']} | {res['type']} | "
            f"{res['auc']:.4f} | {res['f1']:.4f} | "
            f"{res['precision']:.4f} | {res['recall']:.4f} | "
            f"{res['fpr']:.4f} | {res['tp']} | {res['fp']} | "
            f"{res['tn']} | {res['fn']} |"
        )

    lines.append("\n## Anomaly vs Supervised Comparison\n")
    lines.append("### Anomaly-Based Models (train on NORMAL only)")
    lines.append("| Pros | Cons |")
    lines.append("|---|---|")
    lines.append("| No labeled exfil data needed | Lower AUC than supervised |")
    lines.append("| Detects zero-day attacks | Higher false positive rate |")
    lines.append("| Interpretable anomaly score | Sensitive to noise in training data |")

    lines.append("\n### Supervised Models (train on labeled data)")
    lines.append("| Pros | Cons |")
    lines.append("|---|---|")
    lines.append("| Higher AUC and F1 | Requires labeled exfil data |")
    lines.append("| Lower false positive rate | Cannot detect novel attack patterns |")
    lines.append("| More stable | Risk of overfitting to training distribution |")

    lines.append("\n## burst_exfil_score Threshold Analysis\n")
    lines.append("| Threshold | Alert Condition | Notes |")
    lines.append("|---|---|---|")
    lines.append("| 0.5 | Low suspicion | Many false positives expected |")
    lines.append("| 0.6 | Medium suspicion | Balance between recall and precision |")
    lines.append("| 0.7 | High suspicion (default) | Recommended threshold |")
    lines.append("| 0.8 | Very high suspicion | Low false positives, may miss subtle exfil |")

    lines.append("\n## Recommendation\n")
    anomaly_results = [r for r in all_results if r and r["type"] == "anomaly"]
    supervised_results = [r for r in all_results if r and r["type"] == "supervised"]

    if anomaly_results and supervised_results:
        best_anomaly = max(anomaly_results, key=lambda r: r["auc"])
        best_supervised = max(supervised_results, key=lambda r: r["auc"])

        lines.append(f"- **Best anomaly model:** {best_anomaly['name']} "
                     f"(AUC={best_anomaly['auc']:.4f}, F1={best_anomaly['f1']:.4f})")
        lines.append(f"- **Best supervised model:** {best_supervised['name']} "
                     f"(AUC={best_supervised['auc']:.4f}, F1={best_supervised['f1']:.4f})")
        lines.append(f"- **Recommendation:** Use {best_supervised['name']} as primary "
                     f"detector, {best_anomaly['name']} as secondary detector for zero-day.")

    content = "\n".join(lines)
    with open(save_path, "w") as f:
        f.write(content)
    logger.info(f"Metrics report saved: {save_path}")


def run_evaluation():
    """Main evaluation pipeline."""
    if not (PROCESSED_DIR / "X_test_scaled.npy").exists():
        logger.error("Preprocessed data not found. Run preprocessing first!")
        return {}

    print("\n" + "=" * 70)
    print("MODEL EVALUATION — All 4 Models")
    print("=" * 70 + "\n")

    # Load data
    X_test, y_test, feature_cols = load_test_data()
    logger.info(f"Test set: {X_test.shape[0]:,} samples, {y_test.mean()*100:.3f}% exfil")

    # Load models
    models = {}
    if (MODEL_DIR / "isolation_forest.pkl").exists():
        models["Isolation Forest"] = ("anomaly", "isolation_forest.pkl")
    if (MODEL_DIR / "oneclass_svm.pkl").exists():
        models["One-Class SVM"] = ("anomaly", "oneclass_svm.pkl")
    if HAS_KERAS and (MODEL_DIR / "bilstm_final.h5").exists():
        models["BiLSTM"] = ("supervised", "bilstm_final.h5")
    elif HAS_KERAS and (MODEL_DIR / "bilstm_model.h5").exists():
        models["BiLSTM"] = ("supervised", "bilstm_model.h5")
    if HAS_KERAS and (MODEL_DIR / "cnn1d_final.h5").exists():
        models["CNN1D"] = ("supervised", "cnn1d_final.h5")
    elif HAS_KERAS and (MODEL_DIR / "cnn1d_model.h5").exists():
        models["CNN1D"] = ("supervised", "cnn1d_model.h5")

    if not models:
        logger.error("No trained models found in models/ — train models first!")
        return {}

    # Evaluate
    all_results = []
    print()

    for name, (mtype, fname) in models.items():
        logger.info(f"Evaluating {name}...")
        try:
            if mtype == "anomaly":
                model = load_anomaly_model(fname.replace(".pkl", ""))
                if model is not None:
                    res = evaluate_anomaly(model, X_test, y_test, name)
                    all_results.append(res)
            elif mtype == "supervised":
                model = load_dl_model(fname)
                if model is not None:
                    # Reshape for Keras if needed
                    if len(X_test.shape) == 2:
                        X_dl = X_test.reshape(X_test.shape[0], 1, X_test.shape[1])
                    else:
                        X_dl = X_test
                    res = evaluate_supervised(model, X_dl, y_test, name)
                    all_results.append(res)
        except Exception as e:
            logger.error(f"  Failed to evaluate {name}: {e}")

    if not all_results:
        logger.error("No models could be evaluated.")
        return {}

    # Plots
    print()
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)

    plot_roc_curves(all_results, NOTEBOOKS_DIR / "roc_curves.png")
    plot_confusion_matrices(all_results, NOTEBOOKS_DIR / "confusion_matrices.png")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    write_metrics_report(all_results, DOCS_DIR / "metrics_report.md")

    # Save JSON results
    serializable_results = []
    for res in all_results:
        r = {k: v for k, v in res.items() if k not in ["scores", "preds"]}
        serializable_results.append(r)

    out_path = PROCESSED_DIR / "evaluation_results.json"
    with open(out_path, "w") as f:
        json.dump({"models": serializable_results, "n_test": int(len(y_test)),
                   "exfil_rate_test": float(y_test.mean())}, f, indent=2)
    logger.info(f"Results saved: {out_path}")

    # Print summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"\n{'Model':<20} {'AUC-ROC':>10} {'F1':>10} {'Prec':>10} {'Rec':>10} {'FPR':>10}")
    print("-" * 70)
    for res in all_results:
        print(f"{res['name']:<20} {res['auc']:>10.4f} {res['f1']:>10.4f} "
              f"{res['precision']:>10.4f} {res['recall']:>10.4f} {res['fpr']:>10.4f}")
    print()

    return {r["name"]: r for r in all_results}


if __name__ == "__main__":
    setup_logging("INFO")
    run_evaluation()
