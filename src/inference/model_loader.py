"""
src/inference/model_loader.py — Load trained models (.pkl / .h5).
"""

import joblib
import numpy as np
from pathlib import Path
from typing import Union

# Try importing keras — may not be available in all envs
try:
    from tensorflow import keras
    HAS_KERAS = True
except ImportError:
    HAS_KERAS = False
from src.utils.helpers import get_logger

logger = get_logger("model_loader")


class ModelLoader:
    """
    Unified model loader — handles both sklearn (.pkl) and Keras (.h5) models.
    """

    def __init__(self, model_path: Path = None):
        self.model = None
        self.model_type = None  # "sklearn" or "keras"
        self.model_path = model_path

    def load(self, path: Union[str, Path]) -> "ModelLoader":
        """
        Load a model from file.

        Args:
            path: Path to .pkl or .h5 file

        Returns:
            self for chaining
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Model not found: {path}")

        suffix = path.suffix.lower()

        if suffix == ".pkl":
            self.model = joblib.load(path)
            if isinstance(self.model, dict) and self.model.get("model_type") == "runtime_window_rf":
                self.model_type = "runtime_window"
                estimator = self.model.get("model")
                logger.info(
                    f"Loaded runtime window model: {path.name} "
                    f"({type(estimator).__name__})"
                )
            else:
                self.model_type = "sklearn"
                logger.info(f"Loaded sklearn model: {path.name} ({type(self.model).__name__})")

        elif suffix == ".h5" or suffix == ".keras":
            if not HAS_KERAS:
                raise ImportError("TensorFlow/Keras not installed. Cannot load .h5 model.")
            self.model = keras.models.load_model(path, compile=False)
            self.model_type = "keras"
            logger.info(f"Loaded Keras model: {path.name}")

        else:
            raise ValueError(f"Unknown model format: {suffix}")

        self.model_path = path
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Run prediction on feature vector(s).

        Args:
            X: Feature array, shape (n_samples, n_features)
               For sklearn: uses decision_function or predict
               For keras: uses predict

        Returns:
            Array of predictions:
              - sklearn: +1 (normal) or -1 (anomaly) for IsolationForest/OCSVM
              - keras: probability of exfiltration (0-1)
        """
        if self.model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        if self.model_type == "sklearn":
            if hasattr(self.model, "decision_function"):
                scores = self.model.decision_function(X)
                # decision_function: higher = more normal
                # Convert to binary: score > threshold → normal(0), else anomaly(1)
                return scores
            elif hasattr(self.model, "predict_proba"):
                probs = self.model.predict_proba(X)
                return probs[:, 1] if probs.ndim == 2 and probs.shape[1] > 1 else probs.flatten()
            elif hasattr(self.model, "predict"):
                return self.model.predict(X)
            else:
                raise AttributeError(f"Sklearn model has no predict/decision_function")

        elif self.model_type == "runtime_window":
            estimator = self.model.get("model")
            if estimator is None:
                raise RuntimeError("Runtime window model artifact has no estimator")
            if hasattr(estimator, "predict_proba"):
                probs = estimator.predict_proba(X)
                return probs[:, 1] if probs.ndim == 2 and probs.shape[1] > 1 else probs.flatten()
            return estimator.predict(X)

        elif self.model_type == "keras":
            preds = self.model.predict(X, verbose=0)
            # preds shape: (n, 1) or (n,)
            preds = preds.flatten()
            return preds

    def predict_binary(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """
        Binary prediction: 0 = normal, 1 = exfiltration.

        For sklearn anomaly models: uses decision_function with auto-threshold.
        For keras: uses probability with given threshold.
        """
        if self.model_type == "runtime_window":
            threshold = float(self.model.get("threshold", threshold))
            probs = self.predict(X)
            return (probs >= threshold).astype(int)
        elif self.model_type == "sklearn":
            scores = self.predict(X)
            # Auto-threshold: median of scores
            threshold = np.median(scores)
            return (scores < threshold).astype(int)
        else:
            probs = self.predict(X)
            return (probs > threshold).astype(int)

    def summary(self) -> str:
        """Get model summary string."""
        if self.model is None:
            return "No model loaded"
        if self.model_type == "keras":
            return f"Keras model: {self.model_path.name}"
        if self.model_type == "runtime_window":
            return f"Runtime window model: {self.model_path.name}"
        else:
            return f"Sklearn model: {type(self.model).__name__}"


# Convenience loaders
def load_sklearn_model(path: Union[str, Path]):
    """Load a sklearn model (.pkl)."""
    loader = ModelLoader()
    return loader.load(path)


def load_keras_model(path: Union[str, Path]):
    """Load a Keras model (.h5)."""
    loader = ModelLoader()
    return loader.load(path)
