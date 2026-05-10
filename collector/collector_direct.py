"""
IntelliOps — Direct Collector (no Kafka)
Collects system metrics every N seconds and POSTs directly to the FastAPI /ingest endpoint.
Use this on EC2 t2.micro where Kafka can't run due to limited RAM.

Usage:
    python collector/collector_direct.py
"""

import os
import socket
import time
from datetime import datetime, timezone

import psutil
import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")
INTERVAL = int(os.getenv("COLLECT_INTERVAL_SECONDS", "5"))
HOST = os.getenv("HOST_NAME", socket.gethostname())
INGEST_URL = f"{API_URL}/ingest"


def collect_metrics() -> dict:
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    per_cpu = psutil.cpu_percent(percpu=True)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "cpu_percent": cpu,
        "cpu_count": psutil.cpu_count(),
        "cpu_per_core": per_cpu,
        "memory_percent": mem.percent,
        "memory_used_gb": round(mem.used / (1024 ** 3), 2),
        "memory_total_gb": round(mem.total / (1024 ** 3), 2),
        "memory_available_gb": round(mem.available / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "disk_used_gb": round(disk.used / (1024 ** 3), 1),
        "disk_total_gb": round(disk.total / (1024 ** 3), 1),
        "net_bytes_sent_mb": round(net.bytes_sent / (1024 ** 2), 2),
        "net_bytes_recv_mb": round(net.bytes_recv / (1024 ** 2), 2),
        "net_packets_sent": net.packets_sent,
        "net_packets_recv": net.packets_recv,
    }


def main():
    print(f"[IntelliOps Direct Collector] Starting on host '{HOST}'")
    print(f"  API endpoint : {INGEST_URL}")
    print(f"  Interval     : every {INTERVAL}s")
    print("-" * 50)

    with httpx.Client(timeout=10.0) as client:
        while True:
            try:
                metrics = collect_metrics()
                resp = client.post(INGEST_URL, json=metrics)
                resp.raise_for_status()
                print(
                    f"[{metrics['timestamp'][11:19]}] "
                    f"CPU: {metrics['cpu_percent']:5.1f}%  "
                    f"MEM: {metrics['memory_percent']:5.1f}%  "
                    f"DISK: {metrics['disk_percent']:5.1f}%  "
                    f"NET↑: {metrics['net_bytes_sent_mb']:.0f}MB"
                )
            except httpx.ConnectError:
                print(f"[Collector] API not reachable at {INGEST_URL}, retrying...")
            except Exception as e:
                print(f"[Collector] Error: {e}")

            time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
