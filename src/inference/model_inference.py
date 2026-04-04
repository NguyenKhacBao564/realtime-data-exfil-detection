"""
src/inference/model_inference.py — Thread 3: Model Inference + Alert Logging.
Loads model at startup, predicts per window, computes burst_exfil_score, logs alerts.
"""

import threading
import time
import logging
import queue
from typing import Optional, Dict, Any

from src.inference.model_loader import ModelLoader
from src.inference.alert_logger import AlertLogger
from src.features.burst_exfil import burst_exfil_score, get_severity
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
        self.burst_threshold = burst_threshold

        self.model_loader = ModelLoader()
        self.alert_logger = AlertLogger(console_color=True)

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
        """Load scaler and model at startup."""
        import joblib
        import numpy as np
        from pathlib import Path

        # Load scaler
        scaler_path = Path(self.scaler_path or str(MODEL_DIR / "scaler.pkl"))
        if scaler_path.exists():
            self.scaler = joblib.load(scaler_path)
            logger.info(f"[INFERENCE] Scaler loaded: {scaler_path.name}")
        else:
            logger.warning(f"[INFERENCE] Scaler not found: {scaler_path}")
            self.scaler = None

        # Load model
        model_path = Path(self.model_path or str(MODEL_DIR / "isolation_forest.pkl"))
        if model_path.exists():
            self.model_loader.load(model_path)
            logger.info(f"[INFERENCE] Model loaded: {model_path.name}")
        else:
            logger.warning(f"[INFERENCE] Model not found: {model_path} — using burst_score only")
            self.model_loader.model = None

        # Warm up with dummy prediction
        if self.model_loader.model is not None:
            import numpy as np
            try:
                dummy = np.random.randn(1, self.scaler.n_features_in_ if self.scaler else 20)
                _ = self.model_loader.predict(dummy)
                logger.info("[INFERENCE] Model warmup OK")
            except Exception as e:
                logger.warning(f"[INFERENCE] Model warmup failed: {e}")

    def _process_window(self, features: Dict[str, Any]):
        """Process a single window — predict and log."""
        import numpy as np

        self.stats["windows_processed"] += 1

        # 1. Compute burst_exfil_score
        score = burst_exfil_score(features)
        severity = get_severity(score)

        # 2. Model prediction (if model is loaded)
        model_score = None
        prediction = None

        if self.model_loader.model is not None and self.scaler is not None:
            try:
                # Build feature vector from dict
                feature_vector = self._build_feature_vector(features)
                if feature_vector is not None:
                    X = self.scaler.transform([feature_vector])
                    model_score = float(self.model_loader.predict(X)[0])
                    model_name = type(self.model_loader.model).__name__

                    # For sklearn: score > 0 = more normal, score < 0 = anomaly
                    # For keras: probability of exfil
                    if "sklearn" in str(type(self.model_loader.model)):
                        # IsolationForest/OCSVM: score is anomaly score (lower = more anomalous)
                        # We use the raw score
                        pass

            except Exception as e:
                logger.warning(f"[INFERENCE] Model prediction failed: {e}")

        # 3. Determine if alert should fire
        alert_fired = score > self.burst_threshold

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
