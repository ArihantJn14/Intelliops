# api/tasks.py
from api.celery_app import app
from anomaly.detector import detector
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import os
import socket


@app.task(name='score_and_alert')
def score_and_alert(reading: dict) -> dict:
    from ai.explainer import explain_anomaly
    from alerts.dispatcher import send_slack, format_anomaly_alert
    from api.consumer import metrics_buffer, buffer_lock

    score = detector.score(reading)
    is_anomaly = detector.is_anomaly(reading)

    result = {
        'score': round(score, 4),
        'is_anomaly': is_anomaly,
        'severity': 'critical' if score > 0.85 else ('warning' if is_anomaly else 'normal'),
    }

    if is_anomaly:
        with buffer_lock:
            history = list(metrics_buffer)[-10:]

        try:
            explanation = explain_anomaly(reading, history)
            result['ai_explanation'] = explanation
            reading['ai_explanation'] = explanation
            print(f"[AI] Explanation generated for anomaly on {reading.get('host')}")
        except Exception as e:
            result['ai_explanation'] = f'AI analysis unavailable: {e}'
            print(f"[AI] Error: {e}")

        _write_anomaly(reading, score, result['severity'])
        send_slack(format_anomaly_alert(reading, result.get('ai_explanation', '')))
        print(f"[Celery] ANOMALY scored {score:.3f} on {reading.get('host')}")

    return result


@app.task(name='run_forecast_check')
def run_forecast_check():
    """Called by Celery Beat every 5 min. Sends predictive alert if CPU forecast exceeds 80%."""
    from forecast.prophet_model import cpu_forecaster
    from alerts.dispatcher import send_slack, format_predictive_alert

    if cpu_forecaster.model is None:
        print('[Forecast] Model not trained yet, skipping check.')
        return {'status': 'skipped', 'reason': 'model not trained'}

    result = cpu_forecaster.predict(periods=6)
    if result.get('will_exceed_80_percent'):
        payload = format_predictive_alert(
            field='cpu_percent',
            predicted_peak=result['predicted_peak'],
            horizon_min=result['horizon_minutes'],
            host=socket.gethostname(),
        )
        sent = send_slack(payload)
        print(f'[Forecast] Predictive alert sent: {sent}, peak={result["predicted_peak"]:.1f}%')
    else:
        print(f'[Forecast] All clear. Peak predicted: {result.get("predicted_peak", 0):.1f}%')
    return result


@app.task(name='retrain_models')
def retrain_models():
    """Called by Celery Beat weekly. Retrains forecast models on fresh data."""
    from forecast.prophet_model import cpu_forecaster, memory_forecaster
    cpu_result = cpu_forecaster.train(hours=24)
    mem_result = memory_forecaster.train(hours=24)
    print(f'[Retrain] CPU: {cpu_result}, Memory: {mem_result}')
    return {'cpu': cpu_result, 'memory': mem_result}


def _write_anomaly(reading: dict, score: float, severity: str):
    try:
        client = InfluxDBClient(
            url=os.getenv('INFLUX_URL', 'http://localhost:8086'),
            token=os.getenv('INFLUX_TOKEN', 'intelliops-super-secret-token'),
            org=os.getenv('INFLUX_ORG', 'intelliops'),
        )
        point = (
            Point('anomaly_events')
            .tag('host', reading.get('host', 'unknown'))
            .tag('severity', severity)
            .field('score', score)
            .field('cpu_percent', float(reading.get('cpu_percent', 0)))
            .field('memory_percent', float(reading.get('memory_percent', 0)))
        )
        client.write_api(write_options=SYNCHRONOUS).write(
            bucket=os.getenv('INFLUX_BUCKET', 'metrics'),
            org=os.getenv('INFLUX_ORG', 'intelliops'),
            record=point,
        )
        client.close()
    except Exception as e:
        print(f"[Celery] InfluxDB write failed: {e}")
