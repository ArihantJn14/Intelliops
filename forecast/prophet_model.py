# forecast/prophet_model.py
import json
import numpy as np
import pandas as pd
from pathlib import Path
from api.influx_queries import query_history

MODEL_DIR = Path('forecast/models/')
MODEL_DIR.mkdir(parents=True, exist_ok=True)


class CPUForecaster:
    def __init__(self, field: str = 'cpu_percent'):
        self.field = field
        self.model = None  # stores {'coef': [...], 'intercept': float, 'std': float, 'trained_at': str}
        self.model_path = MODEL_DIR / f'simple_{field}.json'

    def train(self, hours: int = 24) -> dict:
        raw = query_history(self.field, hours=hours)
        if not raw:
            return {'status': 'error', 'message': 'No data in InfluxDB'}

        df = pd.DataFrame(raw)
        df.columns = ['ds', 'y']
        df['ds'] = pd.to_datetime(df['ds'])
        df = df.dropna().sort_values('ds').reset_index(drop=True)

        if len(df) < 10:
            return {'status': 'error', 'message': f'Not enough data: {len(df)} points'}

        # Numeric time index in minutes from start
        t = np.array([(ts - df['ds'].iloc[0]).total_seconds() / 60 for ts in df['ds']])
        y = df['y'].values

        # Fit degree-2 polynomial to capture trend + curve
        coef = np.polyfit(t, y, deg=2).tolist()

        # Residual std for confidence bands
        y_fit = np.polyval(coef, t)
        std = float(np.std(y - y_fit))

        self.model = {
            'coef': coef,
            'std': std,
            'last_t': float(t[-1]),
            'trained_at': df['ds'].iloc[-1].isoformat(),
        }
        with open(self.model_path, 'w') as f:
            json.dump(self.model, f)

        return {'status': 'trained', 'field': self.field, 'samples': len(df)}

    def load(self) -> bool:
        if self.model_path.exists():
            with open(self.model_path, 'r') as f:
                self.model = json.load(f)
            return True
        return False

    def predict(self, periods: int = 6) -> dict:
        if self.model is None:
            return {'error': 'Model not trained. Call /forecast/train first.'}

        coef = self.model['coef']
        std = self.model['std']
        last_t = self.model['last_t']

        # Predict at 5-min intervals ahead of last training point
        future_t = [last_t + (i + 1) * 5 for i in range(periods)]
        predictions = []
        for t in future_t:
            yhat = float(np.clip(np.polyval(coef, t), 0, 100))
            lower = float(np.clip(yhat - 1.96 * std, 0, 100))
            upper = float(np.clip(yhat + 1.96 * std, 0, 100))
            # Approximate time by offsetting from trained_at
            trained_at = pd.Timestamp(self.model['trained_at'])
            point_time = trained_at + pd.Timedelta(minutes=(t - last_t))
            predictions.append({
                'time': point_time.isoformat(),
                'predicted': round(yhat, 1),
                'lower': round(lower, 1),
                'upper': round(upper, 1),
            })

        peak = max(p['predicted'] for p in predictions)
        will_exceed_80 = any(p['predicted'] > 80 for p in predictions)

        return {
            'field': self.field,
            'periods': periods,
            'horizon_minutes': periods * 5,
            'will_exceed_80_percent': will_exceed_80,
            'predicted_peak': round(peak, 1),
            'predictions': predictions,
        }


# Singletons
cpu_forecaster = CPUForecaster(field='cpu_percent')
memory_forecaster = CPUForecaster(field='memory_percent')

cpu_forecaster.load()
memory_forecaster.load()
