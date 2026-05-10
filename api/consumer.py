"""
IntelliOps — Kafka Consumer + InfluxDB Writer
Runs as a background thread inside the FastAPI process.
Reads from Kafka → writes to InfluxDB → fills in-memory buffer for fast API reads.
"""

import json
import os
import threading
from collections import deque
from datetime import datetime

from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from kafka import KafkaConsumer

load_dotenv()

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "system-metrics")
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "intelliops-super-secret-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "intelliops")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "metrics")

# ── In-memory ring buffer ──────────────────────────────────────────────────────
metrics_buffer: deque = deque(maxlen=500)
buffer_lock = threading.Lock()

# ── Anomaly buffer ─────────────────────────────────────────────────────────────
anomaly_buffer: deque = deque(maxlen=200)


# ── InfluxDB setup ─────────────────────────────────────────────────────────────
_influx_client = None
_write_api = None


def get_write_api():
    global _influx_client, _write_api
    if _write_api is None:
        _influx_client = InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
        )
        _write_api = _influx_client.write_api(write_options=SYNCHRONOUS)
    return _write_api


def write_to_influx(data: dict):
    point = (
        Point("system_metrics")
        .tag("host", data.get("host", "unknown"))
        .field("cpu_percent", float(data["cpu_percent"]))
        .field("memory_percent", float(data["memory_percent"]))
        .field("memory_used_gb", float(data["memory_used_gb"]))
        .field("disk_percent", float(data["disk_percent"]))
        .field("net_bytes_sent_mb", float(data["net_bytes_sent_mb"]))
        .field("net_bytes_recv_mb", float(data["net_bytes_recv_mb"]))
    )
    get_write_api().write(bucket=INFLUX_BUCKET, org=INFLUX_ORG, record=point)


def consume():
    """Main Kafka consumer loop. Runs forever in a daemon thread."""
    from anomaly.detector import detector  # imported here to avoid circular imports

    try:
        consumer = KafkaConsumer(
            TOPIC,
            bootstrap_servers=KAFKA_BROKER,
            auto_offset_reset="latest",
            enable_auto_commit=True,
            group_id="intelliops-api-group",
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
    except Exception as e:
        print(f"[Consumer] Cannot connect to Kafka ({e}). Use /ingest endpoint instead.")
        return
    print(f"[Consumer] Subscribed to Kafka topic '{TOPIC}'")

    for message in consumer:
        data = message.value
        try:
            # 1. Write to InfluxDB (persistent storage)
            write_to_influx(data)

            # 2. Append to in-memory buffer (for fast API reads)
            with buffer_lock:
                metrics_buffer.append(data)

            # 3. Score and update buffer in-process (so /anomalies endpoint works)
            from anomaly.detector import detector
            score = detector.score(data)
            data['anomaly_score'] = round(score, 4)

            if detector.is_anomaly(data):
                severity = 'critical' if score > 0.85 else 'warning'
                anomaly_event = {
                    **data,
                    'severity': severity,
                    'detected_at': data['timestamp'],
                    'is_anomaly': True,
                }

                # Generate AI explanation in-process so it lands in the shared buffer
                try:
                    from ai.explainer import explain_anomaly
                    with buffer_lock:
                        history = list(metrics_buffer)[-10:]
                    explanation = explain_anomaly(anomaly_event, history)
                    anomaly_event['ai_explanation'] = explanation
                    print(f'[AI] Explanation generated for anomaly')
                except Exception as e:
                    anomaly_event['ai_explanation'] = f'AI analysis unavailable: {e}'
                    print(f'[AI] Error: {e}')

                anomaly_buffer.append(anomaly_event)
                print(f'[ANOMALY] Score:{score:.3f} CPU:{data["cpu_percent"]}% MEM:{data["memory_percent"]}%')


        except Exception as e:
            print(f"[Consumer] Error processing message: {e}")


def start_consumer_thread():
    """Call this once at FastAPI startup."""
    t = threading.Thread(target=consume, daemon=True, name="kafka-consumer")
    t.start()
    print("[Consumer] Background thread started.")