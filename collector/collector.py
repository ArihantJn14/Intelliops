"""
IntelliOps — Metric Collector
Reads system metrics every N seconds and pushes them to a Kafka topic.
Run this on any machine you want to monitor (your laptop, a server, a VM).

Usage:
    python collector/collector.py
"""

import json
import os
import socket
import time
from datetime import datetime, timezone

import psutil
from dotenv import load_dotenv
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

load_dotenv()

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "system-metrics")
INTERVAL = int(os.getenv("COLLECT_INTERVAL_SECONDS", "5"))
HOST = os.getenv("HOST_NAME", socket.gethostname())


def make_producer() -> KafkaProducer:
    """Connect to Kafka with retries."""
    for attempt in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKER,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3,
                retry_backoff_ms=500,
            )
            print(f"[Collector] Connected to Kafka at {KAFKA_BROKER}")
            return producer
        except NoBrokersAvailable:
            print(f"[Collector] Kafka not ready, retrying ({attempt+1}/10)...")
            time.sleep(3)
    raise RuntimeError("Could not connect to Kafka after 10 attempts.")


def collect_metrics() -> dict:
    """
    Gather a single snapshot of system metrics.
    Returns a flat dict — easy to serialize to JSON and store in InfluxDB.
    """
    cpu = psutil.cpu_percent(interval=1)          # blocks 1s for accurate reading
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()

    # Per-CPU breakdown (useful for detecting uneven load)
    per_cpu = psutil.cpu_percent(percpu=True)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": HOST,

        # CPU
        "cpu_percent": cpu,
        "cpu_count": psutil.cpu_count(),
        "cpu_per_core": per_cpu,

        # Memory
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024 ** 3), 2),
        "memory_total_gb": round(mem.total / (1024 ** 3), 2),
        "memory_available_gb": round(mem.available / (1024 ** 3), 2),

        # Disk
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),

        # Network (cumulative since boot — useful for rate-of-change calculations)
        "net_bytes_sent_mb": round(net.bytes_sent / (1024 ** 2), 2),
        "net_bytes_recv_mb": round(net.bytes_recv / (1024 ** 2), 2),
        "net_packets_sent": net.packets_sent,
        "net_packets_recv": net.packets_recv,
    }


def on_send_success(record_metadata):
    pass  # silent success — remove 'pass' and add print() for debugging


def on_send_error(exc):
    print(f"[Collector] ERROR sending to Kafka: {exc}")


def main():
    print(f"[IntelliOps Collector] Starting on host '{HOST}'")
    print(f"  Kafka broker : {KAFKA_BROKER}")
    print(f"  Topic        : {TOPIC}")
    print(f"  Interval     : every {INTERVAL}s")
    print("-" * 50)

    producer = make_producer()

    while True:
        try:
            metrics = collect_metrics()
            (
                producer
                .send(TOPIC, value=metrics)
                .add_callback(on_send_success)
                .add_errback(on_send_error)
            )
            producer.flush()

            # Human-readable console output
            print(
                f"[{metrics['timestamp'][11:19]}] "
                f"CPU: {metrics['cpu_percent']:5.1f}%  "
                f"MEM: {metrics['memory_percent']:5.1f}%  "
                f"DISK: {metrics['disk_percent']:5.1f}%  "
                f"NET↑: {metrics['net_bytes_sent_mb']:.0f}MB"
            )

        except Exception as e:
            print(f"[Collector] Unexpected error: {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
