# ai/explainer.py
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    return _client


def build_context(anomaly: dict, history: list) -> str:
    last_10 = history[-10:] if len(history) >= 10 else history
    history_lines = []
    for r in last_10:
        ts = r.get('timestamp', '')[-8:]
        history_lines.append(
            f"  {ts} | CPU: {r.get('cpu_percent', 0):.1f}%"
            f" | MEM: {r.get('memory_percent', 0):.1f}%"
            f" | DISK: {r.get('disk_percent', 0):.1f}%"
        )
    history_str = '\n'.join(history_lines)

    return f"""
HOST: {anomaly.get('host', 'unknown')}
ANOMALY DETECTED AT: {anomaly.get('timestamp', 'unknown')}
ANOMALY SCORE: {anomaly.get('anomaly_score', 0):.3f}
SEVERITY: {anomaly.get('severity', 'warning').upper()}

CURRENT METRICS:
  CPU:    {anomaly.get('cpu_percent', 0):.1f}%
  Memory: {anomaly.get('memory_percent', 0):.1f}%  (used: {anomaly.get('memory_used_gb', 0):.1f} GB)
  Disk:   {anomaly.get('disk_percent', 0):.1f}%
  Net sent: {anomaly.get('net_bytes_sent_mb', 0):.0f} MB

RECENT METRIC HISTORY (last 50 seconds):
{history_str}
"""


SYSTEM_PROMPT = """You are an expert Site Reliability Engineer (SRE) with 10 years of experience.
You analyze server anomalies and provide clear, actionable root-cause analysis.

Your response MUST follow this exact format with these three sections:

WHAT HAPPENED:
[2-3 sentences explaining the most likely root cause. Be specific — name the exact resource or process under stress. Make a definitive assessment based on the metrics.]

DO RIGHT NOW:
[2-3 specific, concrete commands or actions the engineer should take immediately. Use bullet points. Include actual commands where relevant.]

PREVENT NEXT TIME:
[1-2 architectural or configuration changes that would prevent this class of incident.]"""


def explain_anomaly(anomaly: dict, history: list) -> str:
    context = build_context(anomaly, history)
    response = get_client().chat.completions.create(
        model='gpt-4o',
        max_tokens=600,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': context},
        ],
    )
    return response.choices[0].message.content
