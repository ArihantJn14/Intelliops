# alerts/dispatcher.py
import os
import json
import httpx
from datetime import datetime, timezone

SLACK_WEBHOOK = os.getenv('SLACK_WEBHOOK_URL', '')


def send_slack(payload: dict) -> bool:
    if not SLACK_WEBHOOK:
        print('[Alert] No Slack webhook configured. Logging to console.')
        print(json.dumps(payload, indent=2))
        return False
    try:
        r = httpx.post(SLACK_WEBHOOK, json=payload, timeout=5)
        return r.status_code == 200
    except Exception as e:
        print(f'[Alert] Slack send failed: {e}')
        return False


def format_anomaly_alert(event: dict, ai_explanation: str = '') -> dict:
    severity = event.get('severity', 'warning')
    emoji = ':red_circle:' if severity == 'critical' else ':warning:'
    return {
        'text': f'{emoji} IntelliOps Alert — {severity.upper()} on {event.get("host")}',
        'blocks': [
            {'type': 'header', 'text': {'type': 'plain_text', 'text': f'{emoji} Anomaly Detected: {severity.upper()}'}},
            {'type': 'section', 'fields': [
                {'type': 'mrkdwn', 'text': f'*Host:*\n{event.get("host")}'},
                {'type': 'mrkdwn', 'text': f'*Score:*\n{event.get("anomaly_score", 0):.3f}'},
                {'type': 'mrkdwn', 'text': f'*CPU:*\n{event.get("cpu_percent", 0):.1f}%'},
                {'type': 'mrkdwn', 'text': f'*Memory:*\n{event.get("memory_percent", 0):.1f}%'},
                {'type': 'mrkdwn', 'text': f'*Time:*\n{event.get("timestamp", "")}'},
            ]},
            {'type': 'section', 'text': {'type': 'mrkdwn',
                'text': f'*AI Root Cause:*\n{ai_explanation}' if ai_explanation else '_AI analysis pending..._'}},
        ]
    }


def format_predictive_alert(field: str, predicted_peak: float, horizon_min: int, host: str) -> dict:
    return {
        'text': f':crystal_ball: IntelliOps Prediction — {field} will reach {predicted_peak:.0f}% in {horizon_min} min on {host}',
        'blocks': [
            {'type': 'header', 'text': {'type': 'plain_text', 'text': ':crystal_ball: Predictive Warning'}},
            {'type': 'section', 'text': {'type': 'mrkdwn',
                'text': f'*{field}* is forecast to reach *{predicted_peak:.0f}%* in the next *{horizon_min} minutes* on `{host}`.\n\nAct now to prevent an incident.'}},
        ]
    }
