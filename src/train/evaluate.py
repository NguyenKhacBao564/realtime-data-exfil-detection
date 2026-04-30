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

CLI:
  python src/train/evaluate.py            # full eval (4 models)
  python src/train/evaluate.py --compare  # so sanh 2 thai cuc: IF_v2 vs CNN1D
"""

import sys
import json
import time
import argparse
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


def run_comparison():
    """
    So sanh 2 thai cuc anomaly vs supervised tren cung test set:
      - Anomaly: IsolationForest v2 (12 upload-related features, train chi tren normal)
      - Supervised: CNN1D final (67 features, train co label)

    Yeu cau san co:
      - models/isolation_forest_v2.pkl, models/scaler_anomaly_v2.pkl, models/isolation_forest_v2.json
      - models/cnn1d_final.h5
      - data/processed/test.csv, X_test_scaled.npy, y_test.npy
      - data/processed/final_results.json (de lay tuned threshold cho CNN1D)

    Outputs:
      - data/processed/comparison_anomaly_vs_supervised.json
      - notebooks/comparison_table.png
      - notebooks/roc_comparison.png
      - docs/comparison_report.md
    """
    import joblib
    import pandas as pd

    print("\n" + "=" * 70)
    print("COMPARISON — IsolationForest v2 (anomaly) vs CNN1D (supervised)")
    print("=" * 70 + "\n")

    # 1. Verify required files
    if_v2_pkl   = MODEL_DIR / "isolation_forest_v2.pkl"
    if_v2_scl   = MODEL_DIR / "scaler_anomaly_v2.pkl"
    if_v2_meta  = MODEL_DIR / "isolation_forest_v2.json"
    cnn1d_path  = MODEL_DIR / "cnn1d_final.h5"
    test_csv    = PROCESSED_DIR / "test.csv"
    x_test_npy  = PROCESSED_DIR / "X_test_scaled.npy"
    y_test_npy  = PROCESSED_DIR / "y_test.npy"

    missing = [str(p) for p in [if_v2_pkl, if_v2_scl, if_v2_meta, cnn1d_path,
                                 test_csv, x_test_npy, y_test_npy] if not p.exists()]
    if missing:
        logger.error("Thieu cac file sau (chay notebook 04 truoc):")
        for m in missing:
            logger.error(f"  - {m}")
        return None

    if not HAS_KERAS:
        logger.error("TensorFlow/Keras khong co — khong load duoc CNN1D.")
        return None

    # 2. Load test data
    test_df = pd.read_csv(test_csv)
    y_test  = test_df["exfil_label"].values
    n_test  = len(y_test)
    n_exfil = int(y_test.sum())
    logger.info(f"Test set: {n_test:,} flows, {n_exfil} exfil ({n_exfil/n_test*100:.3f}%)")

    # 3. IsolationForest v2
    with open(if_v2_meta) as f:
        if_meta = json.load(f)
    if_features = if_meta["feature_names"]
    if_threshold = if_meta["metrics"]["optimal_threshold"]

    iforest = joblib.load(if_v2_pkl)
    scaler_a = joblib.load(if_v2_scl)

    X_if = test_df[if_features].values
    np.nan_to_num(X_if, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
    X_if_s = scaler_a.transform(X_if)

    t0 = time.time()
    raw_if = iforest.decision_function(X_if_s)
    if_infer_time = time.time() - t0
    if_scores = -raw_if
    if_preds  = (if_scores >= if_threshold).astype(int)

    if_metrics = _compute_metrics("IsolationForest_v2", "anomaly",
                                   y_test, if_scores, if_preds, if_threshold,
                                   if_infer_time / n_test)
    logger.info(f"  IF v2:  AUC={if_metrics['auc']:.4f}, F1={if_metrics['f1']:.4f}, "
                f"FPR={if_metrics['fpr']:.4f}")

    # 4. CNN1D
    cnn = keras.models.load_model(str(cnn1d_path), compile=False)
    X_cnn = np.load(x_test_npy)
    if X_cnn.ndim == 2:
        X_cnn = X_cnn.reshape(X_cnn.shape[0], 1, X_cnn.shape[1])

    cnn_threshold = 0.5
    fr_path = PROCESSED_DIR / "final_results.json"
    if fr_path.exists():
        with open(fr_path) as f:
            fr = json.load(f)
        cnn_threshold = fr.get("CNN1D", {}).get("optimal_threshold", 0.5)

    t0 = time.time()
    cnn_probs = cnn.predict(X_cnn, verbose=0).ravel()
    cnn_infer_time = time.time() - t0
    cnn_preds = (cnn_probs >= cnn_threshold).astype(int)

    cnn_metrics = _compute_metrics("CNN1D", "supervised",
                                    y_test, cnn_probs, cnn_preds, cnn_threshold,
                                    cnn_infer_time / n_test)
    logger.info(f"  CNN1D:  AUC={cnn_metrics['auc']:.4f}, F1={cnn_metrics['f1']:.4f}, "
                f"FPR={cnn_metrics['fpr']:.4f}")

    # 5. Save JSON comparison
    comparison = {
        "test_set": {"n_flows": n_test, "n_exfil": n_exfil,
                     "exfil_rate": n_exfil / n_test},
        "anomaly":    if_metrics,
        "supervised": cnn_metrics,
        "verdict": _make_verdict(if_metrics, cnn_metrics),
    }

    out_json = PROCESSED_DIR / "comparison_anomaly_vs_supervised.json"
    with open(out_json, "w") as f:
        json.dump(comparison, f, indent=2)
    logger.info(f"Saved: {out_json}")

    # 6. Plot comparison table + ROC
    NOTEBOOKS_DIR.mkdir(parents=True, exist_ok=True)
    _plot_comparison_table(if_metrics, cnn_metrics,
                           NOTEBOOKS_DIR / "comparison_table.png")
    _plot_roc_comparison(y_test, if_scores, if_metrics["auc"],
                         cnn_probs, cnn_metrics["auc"],
                         NOTEBOOKS_DIR / "roc_comparison.png")

    # 7. Markdown report
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    _write_comparison_md(comparison, DOCS_DIR / "comparison_report.md")

    # 8. Print summary
    print("\n" + "=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    fmt = "{:<22} {:>10} {:>10} {:>10} {:>10} {:>10} {:>14}"
    print(fmt.format("Model", "AUC", "F1", "Precision", "Recall", "FPR", "Infer (us/flow)"))
    print("-" * 90)
    for m in [if_metrics, cnn_metrics]:
        print(fmt.format(
            m["name"], f"{m['auc']:.4f}", f"{m['f1']:.4f}",
            f"{m['precision']:.4f}", f"{m['recall']:.4f}",
            f"{m['fpr']:.4f}", f"{m['inference_us_per_sample']:.2f}",
        ))
    print()
    print("Verdict:", comparison["verdict"])
    print()

    return comparison


def _compute_metrics(name, mtype, y_true, scores, preds, threshold, infer_sec_per_sample):
    """Compute metric dict for comparison."""
    auc_val = roc_auc_score(y_true, scores) if len(np.unique(y_true)) > 1 else 0.5
    tn, fp, fn, tp = confusion_matrix(y_true, preds, labels=[0, 1]).ravel()
    return {
        "name": name,
        "type": mtype,
        "threshold": float(threshold),
        "auc": float(auc_val),
        "f1": float(f1_score(y_true, preds, zero_division=0)),
        "precision": float(precision_score(y_true, preds, zero_division=0)),
        "recall": float(recall_score(y_true, preds, zero_division=0)),
        "fpr": float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0,
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        "inference_us_per_sample": float(infer_sec_per_sample * 1e6),
    }


def _make_verdict(anomaly_m, supervised_m):
    """Bilingual short verdict for the comparison report."""
    diff_auc = supervised_m["auc"] - anomaly_m["auc"]
    if diff_auc > 0.10:
        verdict = (f"Supervised vuot troi (delta AUC = {diff_auc:.3f}). "
                   "Phu hop khi co label tin cay; anomaly chi nen lam lop bo sung "
                   "phat hien zero-day.")
    elif diff_auc > 0.02:
        verdict = (f"Supervised tot hon nhung khong qua nhieu (delta AUC = {diff_auc:.3f}). "
                   "Anomaly van co gia tri khi label thieu hoac noisy.")
    else:
        verdict = (f"Hai phuong phap tuong duong (delta AUC = {diff_auc:.3f}). "
                   "Co the ket hop ensemble.")
    return verdict


def _plot_comparison_table(anomaly_m, supervised_m, save_path: Path):
    """Render bang so sanh dang PNG."""
    metrics_keys = [("auc", "AUC-ROC"), ("f1", "F1"),
                    ("precision", "Precision"), ("recall", "Recall"),
                    ("fpr", "FPR"), ("inference_us_per_sample", "Infer (us)")]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis("off")
    cell_data = []
    for key, label in metrics_keys:
        a_val = anomaly_m[key]
        s_val = supervised_m[key]
        if key == "inference_us_per_sample":
            cell_data.append([label, f"{a_val:.2f}", f"{s_val:.2f}"])
        else:
            cell_data.append([label, f"{a_val:.4f}", f"{s_val:.4f}"])

    table = ax.table(
        cellText=cell_data,
        colLabels=["Metric",
                   f"{anomaly_m['name']}\n(anomaly)",
                   f"{supervised_m['name']}\n(supervised)"],
        cellLoc="center",
        loc="center",
        colWidths=[0.3, 0.35, 0.35],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1.0, 1.8)

    # Header colour
    for j in range(3):
        cell = table[(0, j)]
        cell.set_facecolor("#34495e")
        cell.set_text_props(color="white", fontweight="bold")

    # Highlight winner per row
    for i, (key, _) in enumerate(metrics_keys, start=1):
        a_val = anomaly_m[key]
        s_val = supervised_m[key]
        # Lower-is-better metrics
        lower_better = key in {"fpr", "inference_us_per_sample"}
        if lower_better:
            anomaly_wins = a_val < s_val
        else:
            anomaly_wins = a_val > s_val
        winner_col = 1 if anomaly_wins else 2
        table[(i, winner_col)].set_facecolor("#d5f5e3")

    plt.title("So sanh anomaly vs supervised tren cung test set",
              fontsize=13, fontweight="bold", pad=15)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"Comparison table saved: {save_path}")


def _plot_roc_comparison(y_true, if_scores, if_auc, cnn_scores, cnn_auc, save_path: Path):
    """ROC overlay 2 model."""
    fpr_a, tpr_a, _ = roc_curve(y_true, if_scores)
    fpr_s, tpr_s, _ = roc_curve(y_true, cnn_scores)

    plt.figure(figsize=(8, 7))
    plt.plot(fpr_a, tpr_a, label=f"IsolationForest v2 (anomaly, AUC={if_auc:.4f})",
             color="#3498db", linewidth=2)
    plt.plot(fpr_s, tpr_s, label=f"CNN1D (supervised, AUC={cnn_auc:.4f})",
             color="#e74c3c", linewidth=2)
    plt.plot([0, 1], [0, 1], "k--", alpha=0.4, label="Random")
    plt.axvline(0.05, color="gray", linestyle=":", alpha=0.5, label="FPR=5%")
    plt.xlabel("False Positive Rate", fontsize=11)
    plt.ylabel("True Positive Rate", fontsize=11)
    plt.title("ROC — anomaly vs supervised", fontsize=13, fontweight="bold")
    plt.legend(loc="lower right", fontsize=10)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close()
    logger.info(f"ROC comparison saved: {save_path}")


def _write_comparison_md(comparison: dict, save_path: Path):
    """Markdown report ngan."""
    a = comparison["anomaly"]
    s = comparison["supervised"]
    ts = comparison["test_set"]
    lines = [
        "# So sanh anomaly vs supervised — Exfiltration Detection\n",
        f"> Test set: {ts['n_flows']:,} flows, {ts['n_exfil']} exfil "
        f"({ts['exfil_rate']*100:.3f}%)\n",
        "## Bang metric\n",
        "| Metric | IsolationForest v2 (anomaly) | CNN1D (supervised) |",
        "|---|---|---|",
        f"| AUC-ROC | {a['auc']:.4f} | {s['auc']:.4f} |",
        f"| F1 | {a['f1']:.4f} | {s['f1']:.4f} |",
        f"| Precision | {a['precision']:.4f} | {s['precision']:.4f} |",
        f"| Recall | {a['recall']:.4f} | {s['recall']:.4f} |",
        f"| FPR | {a['fpr']:.4f} | {s['fpr']:.4f} |",
        f"| TP / FP / TN / FN | {a['tp']} / {a['fp']} / {a['tn']} / {a['fn']} | "
        f"{s['tp']} / {s['fp']} / {s['tn']} / {s['fn']} |",
        f"| Threshold | {a['threshold']:.6f} | {s['threshold']:.6f} |",
        f"| Inference (us/flow) | {a['inference_us_per_sample']:.2f} | "
        f"{s['inference_us_per_sample']:.2f} |",
        "",
        "## Verdict\n",
        comparison["verdict"],
        "",
        "## Bang luan diem\n",
        "| Khia canh | Anomaly | Supervised |",
        "|---|---|---|",
        "| Yeu cau du lieu | Chi can normal | Can label exfil |",
        "| Phat hien zero-day | Tot | Han che (overfit pattern hoc duoc) |",
        "| Toc do inference | Rat nhanh (decision_function) | Nhanh (CNN1D nho) |",
        "| Do on dinh | Nhay voi noise trong train | On dinh hon |",
        "| Cong dung trong he thong | Lop bo sung canh bao bat thuong | Detector chinh |",
    ]
    save_path.write_text("\n".join(lines))
    logger.info(f"Comparison report saved: {save_path}")


if __name__ == "__main__":
    setup_logging("INFO")
    parser = argparse.ArgumentParser(
        description="Evaluate exfiltration detection models.")
    parser.add_argument("--compare", action="store_true",
                        help="So sanh IsolationForest v2 vs CNN1D (anomaly vs supervised)")
    args = parser.parse_args()

    if args.compare:
        run_comparison()
    else:
        run_evaluation()
