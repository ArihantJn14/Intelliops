# ai/chat.py
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


CHAT_SYSTEM = """You are IntelliOps, an AI assistant for system monitoring. You have access to
real-time system metrics and anomaly history. Answer questions concisely and technically.
If asked about specific metrics, refer to the data provided in the user message.
If data is not available, say so clearly. Never guess metric values."""


def answer(question: str, metrics_context: dict, anomaly_context: list) -> str:
    recent_anomalies = anomaly_context[-5:]
    anomaly_summary = '\n'.join([
        f"  {a.get('timestamp', '')[-8:]} | Score:{a.get('anomaly_score', 0):.2f} | "
        f"{a.get('severity')} | CPU:{a.get('cpu_percent', 0):.1f}%"
        for a in recent_anomalies
    ]) or '  None detected recently'

    context = f"""
CURRENT SYSTEM STATE:
  CPU: {metrics_context.get('cpu', {}).get('avg_percent', 'N/A')}% avg
  Memory: {metrics_context.get('memory', {}).get('avg_percent', 'N/A')}% avg
  Readings in buffer: {metrics_context.get('buffer_size', 'N/A')}

RECENT ANOMALIES:
{anomaly_summary}

USER QUESTION: {question}
"""

    response = get_client().chat.completions.create(
        model='gpt-4o',
        max_tokens=400,
        messages=[
            {'role': 'system', 'content': CHAT_SYSTEM},
            {'role': 'user', 'content': context},
        ],
    )
    return response.choices[0].message.content
