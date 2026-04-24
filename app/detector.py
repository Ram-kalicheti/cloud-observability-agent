import numpy as np
from sklearn.ensemble import IsolationForest
from datetime import datetime, UTC


class AnomalyDetector:

    def __init__(self, contamination=0.1):
        # bump this down if too many false positives in prod
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_trained = False

    def train(self, log_data: list[dict]) -> None:
        # fewer than ~100 samples and the model flags too aggressively
        features = self._extract_features(log_data)
        self.model.fit(features)
        self.is_trained = True
        print(f"[detector] trained on {len(log_data)} entries")

    def detect(self, log_entry: dict) -> dict:
        if not self.is_trained:
            raise RuntimeError("call train() before detect()")

        features = self._extract_features([log_entry])
        score = self.model.decision_function(features)[0]
        prediction = self.model.predict(features)[0]

        # decision_function is negative for anomalies, flip it so higher = worse
        return {
            "timestamp": log_entry.get("timestamp", datetime.now(UTC).isoformat()),
            "is_anomaly": bool(prediction == -1),
            "severity_score": round(float(-score), 4),
            "log_entry": log_entry,
        }

    def _extract_features(self, log_data: list[dict]) -> np.ndarray:
        features = []
        for entry in log_data:
            features.append([
                entry.get("error_count", 0),     # sudden spike = crash loop
                entry.get("latency_ms", 0),       # creep upward = downstream issue
                entry.get("memory_used_mb", 0),   # near limit = cold start or leak
                entry.get("request_count", 0),    # sharp drop = upstream cutoff
            ])
        return np.array(features)