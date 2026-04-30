"""
src/inference/model_inference.py — Thread 3: Model Inference + Alert Logging.
Loads model at startup, predicts per window, computes burst_exfil_score, logs alerts.
"""

import threading
import time
import logging
import queue
import numpy as np
from typing import Optional, Dict, Any

from src.inference.model_loader import ModelLoader
from src.inference.alert_logger import AlertLogger
from src.features.burst_exfil import burst_exfil_score, get_severity
from src.features.runtime_features import build_runtime_feature_vector
from src.utils.config import MODEL_DIR, BURST_EXFIL_THRESHOLD, SCALER_PATH
from src.utils.helpers import get_logger

logger = get_logger("inference")


class InferenceThread(threading.Thread):
    """
    Thread 3: Inference + Alert Logging.

    Startup:
      1. Load scaler
      2. Load model (default: isolation_forest.pkl)
      3. Warm up: 1 dummy prediction

    Per-window:
      1. Pop feature dict from feature_queue
      2. Compute burst_exfil_score
      3. Scale features
      4. Run model prediction
      5. If alert → log + print
      6. Else → INFO log
    """

    def __init__(
        self,
        feature_queue,
        stop_event: threading.Event,
        model_path: Optional[str] = None,
        scaler_path: Optional[str] = None,
        burst_threshold: float = BURST_EXFIL_THRESHOLD,
    ):
        super().__init__(name="Inference", daemon=True)
        self.feature_queue = feature_queue
        self.stop_event = stop_event
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.burst_threshold = BURST_EXFIL_THRESHOLD if burst_threshold is None else burst_threshold

        self.model_loader = ModelLoader()
        self.alert_logger = AlertLogger(console_color=True)
        self._model_skip_logged = False

        self.stats = {
            "windows_processed": 0,
            "alerts_triggered": 0,
            "start_time": None,
        }
        self._lock = threading.Lock()

    def run(self):
        """Main loop."""
        logger.info("[INFERENCE] Thread starting...")
        self.stats["start_time"] = time.time()

        # Load model and scaler at startup
        self._load_model()

        # Process features
        while not self.stop_event.is_set():
            try:
                # Get next window features
                try:
                    features = self.feature_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                self._process_window(features)

            except Exception as e:
                logger.error(f"[INFERENCE] Error: {e}")

        # Drain remaining queue on shutdown
        logger.info("[INFERENCE] Shutdown — draining remaining features...")
        while True:
            try:
                features = self.feature_queue.get_nowait()
                self._process_window(features)
            except queue.Empty:
                break

        elapsed = time.time() - (self.stats["start_time"] or time.time())
        logger.info(f"[INFERENCE] Thread stopped. "
                    f"processed={self.stats['windows_processed']} "
                    f"alerts={self.stats['alerts_triggered']}")

    def _load_model(self):
        """Load scaler and model at startup. Gracefully handles all errors."""
        import joblib
        import numpy as np
        from pathlib import Path

        # Load scaler
        scaler_path = Path(self.scaler_path or str(MODEL_DIR / "scaler.pkl"))
        if scaler_path.exists():
            try:
                self.scaler = joblib.load(scaler_path)
                logger.info(f"[INFERENCE] Scaler loaded: {scaler_path.name}")
            except Exception as e:
                logger.warning(f"[INFERENCE] Scaler load failed: {e} — proceeding without scaler")
                self.scaler = None
        else:
            logger.warning(f"[INFERENCE] Scaler not found: {scaler_path}")
            self.scaler = None

        # Load model
        default_runtime_model = MODEL_DIR / "runtime_window_rf.pkl"
        if self.model_path:
            model_path = Path(self.model_path)
        elif default_runtime_model.exists():
            model_path = default_runtime_model
        else:
            model_path = MODEL_DIR / "isolation_forest.pkl"
        if model_path.exists():
            try:
                self.model_loader.load(model_path)
                logger.info(f"[INFERENCE] Model loaded: {model_path.name}")
            except Exception as e:
                # Keras 3.x custom objects issue — try with compile=False
                logger.warning(f"[INFERENCE] Model load failed: {e}")
                try:
                    from tensorflow import keras
                    self.model_loader.model = keras.models.load_model(
                        model_path, compile=False
                    )
                    self.model_loader.model_type = "keras"
                    logger.info(f"[INFERENCE] Model loaded (compile=False): {model_path.name}")
                except Exception as e2:
                    logger.warning(f"[INFERENCE] Keras load also failed: {e2} — using burst_score only")
                    self.model_loader.model = None
        else:
            logger.warning(f"[INFERENCE] Model not found: {model_path} — using burst_score only")
            self.model_loader.model = None

        # Warm up with dummy prediction
        if self.model_loader.model is not None:
            try:
                if self.model_loader.model_type == "runtime_window":
                    n_feats = len(self.model_loader.model.get("feature_names", [])) or 17
                else:
                    n_feats = self.scaler.n_features_in_ if self.scaler else 20
                dummy = np.random.randn(1, n_feats).astype(np.float32)
                _ = self.model_loader.predict(dummy)
                logger.info("[INFERENCE] Model warmup OK")
            except Exception as e:
                logger.warning(f"[INFERENCE] Model warmup failed: {e} — disabling model")
                self.model_loader.model = None

    def _process_window(self, features: Dict[str, Any]):
        """Process a single window — predict and log."""
        self.stats["windows_processed"] += 1

        # 1. Compute burst_exfil_score
        score = burst_exfil_score(features)
        severity = get_severity(score)

        # 2. Runtime model prediction when the loaded model is compatible with
        # live packet-window features. CICFlowMeter-trained DL models are still
        # skipped because their 67-feature input space does not match.
        model_score, prediction = self._predict_runtime_window(features)

        # 3. Determine if alert should fire
        alert_fired = score > self.burst_threshold or prediction == 1
        if prediction == 1 and score < 0.70:
            severity = "MEDIUM"

        if alert_fired:
            self.stats["alerts_triggered"] += 1
            self.alert_logger.log_alert(
                features=features,
                burst_score=score,
                model_score=model_score,
                prediction=prediction,
                severity=severity,
            )
        else:
            self.alert_logger.log_info(features=features, burst_score=score)

    def _predict_runtime_window(self, features: Dict[str, Any]):
        """Predict on live window features when the loaded model is compatible."""
        if self.model_loader.model is None:
            return None, None

        vec = build_runtime_feature_vector(features).reshape(1, -1)
        model_type = self.model_loader.model_type

        if model_type == "runtime_window":
            expected = self.model_loader.model.get("feature_names", [])
            if expected and len(expected) != vec.shape[1]:
                logger.warning(
                    "[INFERENCE] Runtime model feature mismatch: "
                    f"expected={len(expected)} got={vec.shape[1]} — using burst_score only"
                )
                return None, None
            model_score = float(self.model_loader.predict(vec)[0])
            threshold = float(self.model_loader.model.get("threshold", 0.5))
            return model_score, int(model_score >= threshold)

        # Best-effort support for sklearn models trained on the same runtime
        # vector. Skip CICFlowMeter models cleanly instead of crashing.
        estimator = self.model_loader.model
        expected = getattr(estimator, "n_features_in_", None)
        if expected != vec.shape[1]:
            if not self._model_skip_logged:
                logger.warning(
                    "[INFERENCE] Loaded model is not compatible with live window features "
                    f"(expected={expected}, got={vec.shape[1]}) — using burst_score only"
                )
                self._model_skip_logged = True
            return None, None

        try:
            raw_score = float(self.model_loader.predict(vec)[0])
            if 0.0 <= raw_score <= 1.0:
                return raw_score, int(raw_score >= 0.5)
            return raw_score, int(raw_score < 0.0)
        except Exception as e:
            logger.warning(f"[INFERENCE] Runtime prediction failed: {e} — using burst_score only")
            return None, None

    def _build_feature_vector(self, features: Dict[str, Any]) -> Optional[np.ndarray]:
        """
        Build a feature vector from a window features dict.
        Uses the same features as the model was trained on.
        Returns None if insufficient data.
        """
        import numpy as np

        # These must match the training feature columns
        # We'll use the most important features that can be computed from window data
        keys = [
            "request_count",
            "total_fwd_bytes",
            "total_bwd_bytes",
            "total_bytes",
            "upload_download_ratio",
            "burst_count",
            "burst_ratio",
            "request_rate",
            "inter_request_time_mean",
            "inter_request_time_std",
            "mean_payload_size",
            "std_payload_size",
            "psh_flag_count",
            "ack_flag_count",
            "syn_flag_count",
            "window_duration",
        ]

        # Fallback: if key missing, use 0
        vec = []
        for key in keys:
            val = features.get(key, 0.0)
            if val is None:
                val = 0.0
            vec.append(float(val))

        return np.array(vec)

    def get_stats(self) -> dict:
        """Get inference statistics."""
        with self._lock:
            stats = self.stats.copy()
        stats["alert_summary"] = self.alert_logger.summary()
        return stats
