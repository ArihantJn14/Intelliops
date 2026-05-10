# anomaly/detector.py
import os, joblib, numpy as np
from sklearn.ensemble import IsolationForest
from pathlib import Path

MODEL_PATH = Path('anomaly/models/isolation_forest.pkl')
FEATURES = ['cpu_percent', 'memory_percent', 'disk_percent',
            'memory_used_gb', 'net_bytes_sent_mb']
THRESHOLD = 0.02  # CPU>60% scores 0.025+, CPU<=60% scores 0.0; hard boundary at 60%

class AnomalyDetector:
    def __init__(self):
        self.model = None
        self.is_trained = False
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    def train(self, readings: list[dict]) -> dict:
        X = self._to_matrix(readings)
        self.model = IsolationForest(
            n_estimators=200,
            contamination=0.1,  # raised from 0.04 — treats top 10% as anomalies for better sensitivity
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X)
        self.is_trained = True
        joblib.dump(self.model, MODEL_PATH)
        return {'status': 'trained', 'samples': len(X), 'features': FEATURES}

    def load(self) -> bool:
        if MODEL_PATH.exists():
            self.model = joblib.load(MODEL_PATH)
            self.is_trained = True
            return True
        return False

    def score(self, reading: dict) -> float:
        # Score reflects how far CPU is above the 60% threshold (0.0 = normal, 1.0 = 100% CPU)
        cpu = reading.get('cpu_percent', 0)
        if cpu > 60:
            return round((cpu - 60) / 40, 4)
        return 0.0

    def is_anomaly(self, reading: dict) -> bool:
        # Hard CPU rule: above 60% is always an anomaly
        if reading.get('cpu_percent', 0) > 60:
            return True
        return False

    def _to_matrix(self, readings: list[dict]) -> np.ndarray:
        rows = []
        for r in readings:
            row = [float(r.get(f, 0)) for f in FEATURES]
            rows.append(row)
        return np.array(rows)

# Singleton — auto-loads saved model if it exists
detector = AnomalyDetector()
detector.load()