"""
IntelliOps — FastAPI Backend
Week 1: REST endpoints + real-time WebSocket stream.

Run with:
    uvicorn api.main:app --reload --port 8000
"""

import asyncio
import json
from collections import deque
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from api.consumer import metrics_buffer, buffer_lock, start_consumer_thread, anomaly_buffer
from api.influx_queries import query_history

app = FastAPI(
    title="IntelliOps API",
    description="Real-time system monitoring with AI predictions",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Start the Kafka consumer thread when FastAPI boots (optional — skipped if Kafka is unavailable)."""
    try:
        start_consumer_thread()
    except Exception as e:
        print(f"[API] Kafka consumer not started ({e}). Use /ingest for direct metric ingestion.")
    print("[API] IntelliOps is running at http://localhost:8000")
    print("[API] Live dashboard at http://localhost:8000/dashboard")


# ── REST Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    with buffer_lock:
        size = len(metrics_buffer)
    return {
        "status": "ok",
        "buffer_size": size,
        "message": "IntelliOps is running",
    }


@app.get("/metrics")
def get_metrics(limit: int = Query(default=50, le=500)):
    with buffer_lock:
        data = list(metrics_buffer)[-limit:]
    return {
        "count": len(data),
        "metrics": data,
    }


@app.get("/metrics/latest")
def get_latest():
    with buffer_lock:
        if not metrics_buffer:
            return {"error": "No data yet — is the collector running?"}
        return metrics_buffer[-1]


@app.get("/metrics/summary")
def get_summary():
    with buffer_lock:
        recent = list(metrics_buffer)[-60:]

    if not recent:
        return {"error": "No data yet"}

    def avg(key):
        vals = [r[key] for r in recent if key in r]
        return round(sum(vals) / len(vals), 1) if vals else None

    def peak(key):
        vals = [r[key] for r in recent if key in r]
        return round(max(vals), 1) if vals else None

    return {
        "window": f"{len(recent)} readings (~{len(recent) * 5}s)",
        "cpu": {
            "avg_percent": avg("cpu_percent"),
            "peak_percent": peak("cpu_percent"),
        },
        "memory": {
            "avg_percent": avg("memory_percent"),
            "peak_percent": peak("memory_percent"),
        },
        "disk": {
            "current_percent": recent[-1].get("disk_percent") if recent else None,
        },
        "latest_timestamp": recent[-1].get("timestamp") if recent else None,
    }


@app.get("/metrics/history")
def get_history(
    field: str = Query(default="cpu_percent"),
    hours: int = Query(default=1, le=24),
):
    data = query_history(field, hours)
    return {"field": field, "hours": hours, "count": len(data), "data": data}


# ── Anomaly Endpoints ──────────────────────────────────────────────────────────

@app.get("/anomalies")
def get_anomalies(limit: int = Query(default=20, le=200)):
    """Return the most recent detected anomalies. Newest first."""
    events = list(anomaly_buffer)[-limit:]
    events.reverse()
    return {"count": len(events), "anomalies": events}


@app.get("/anomalies/latest/explanation")
def get_latest_explanation():
    """Return the AI explanation for the most recent anomaly."""
    events = list(anomaly_buffer)
    anomalies = [e for e in events if e.get('is_anomaly')]
    if not anomalies:
        return {'explanation': 'No anomalies detected yet.'}
    latest = anomalies[-1]
    return {
        'detected_at': latest.get('timestamp'),
        'severity': latest.get('severity'),
        'score': latest.get('score'),
        'explanation': latest.get('ai_explanation', 'Analysis pending...'),
    }


@app.post("/ingest")
def ingest_metrics(data: dict):
    """Direct metric ingestion — bypasses Kafka. Used by collector_direct.py on low-RAM hosts."""
    from api.consumer import write_to_influx
    from anomaly.detector import detector

    try:
        write_to_influx(data)
    except Exception as e:
        print(f"[Ingest] InfluxDB write failed: {e}")

    score = detector.score(data)
    data['anomaly_score'] = round(score, 4)

    with buffer_lock:
        metrics_buffer.append(data)

    if detector.is_anomaly(data):
        severity = 'critical' if score > 0.85 else 'warning'
        anomaly_event = {**data, 'severity': severity, 'detected_at': data['timestamp'], 'is_anomaly': True}
        try:
            from ai.explainer import explain_anomaly
            with buffer_lock:
                history = list(metrics_buffer)[-10:]
            anomaly_event['ai_explanation'] = explain_anomaly(anomaly_event, history)
        except Exception as e:
            anomaly_event['ai_explanation'] = f'AI analysis unavailable: {e}'
        anomaly_buffer.append(anomaly_event)
        print(f'[Ingest] ANOMALY score:{score:.3f} CPU:{data.get("cpu_percent")}%')

    return {"status": "ok", "anomaly_score": data['anomaly_score']}


@app.post("/train")
def train_model():
    """Trigger model training from the API (useful during development)."""
    from api.influx_queries import query_multi_field
    from anomaly.detector import detector, FEATURES
    data = query_multi_field(FEATURES, hours=24)
    min_len = min(len(v) for v in data.values())
    readings = [{f: data[f][i]['value'] for f in FEATURES} for i in range(min_len)]
    result = detector.train(readings)
    return result


# ── AI Chat Endpoint ──────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str


@app.post("/chat")
def chat(req: ChatRequest):
    """Natural language query interface for system health."""
    try:
        from ai.chat import answer
        metrics_ctx = get_summary()
        with buffer_lock:
            metrics_ctx['buffer_size'] = len(metrics_buffer)
        anomaly_ctx = list(anomaly_buffer)
        response = answer(req.question, metrics_ctx, anomaly_ctx)
        return {'question': req.question, 'answer': response}
    except Exception as e:
        return {'question': req.question, 'answer': f'Error: {e}'}


# ── Forecast Endpoints ────────────────────────────────────────────────────────

@app.post("/forecast/train")
def forecast_train(field: str = Query(default="cpu_percent")):
    """Train a Prophet forecasting model on the last 24h of InfluxDB data."""
    try:
        from forecast.prophet_model import cpu_forecaster, memory_forecaster
        forecaster = cpu_forecaster if field == "cpu_percent" else memory_forecaster
        result = forecaster.train(hours=24)
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/forecast")
def get_forecast(field: str = Query(default="cpu_percent"), periods: int = Query(default=6, le=24)):
    """Return next `periods` x 5-minute predictions for the given field."""
    from forecast.prophet_model import cpu_forecaster, memory_forecaster
    forecaster = cpu_forecaster if field == "cpu_percent" else memory_forecaster
    return forecaster.predict(periods=periods)


# ── WebSocket — live stream ────────────────────────────────────────────────────

@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    await websocket.accept()
    print("[WS] Client connected")

    last_buffer_len = 0
    try:
        while True:
            with buffer_lock:
                current_len = len(metrics_buffer)
                has_new = current_len > last_buffer_len
                if has_new:
                    latest = metrics_buffer[-1]

            if has_new:
                await websocket.send_text(json.dumps(latest))
                last_buffer_len = current_len

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        print("[WS] Client disconnected")


# ── Built-in mini dashboard ───────────────────────────────────────────────────

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
  <title>IntelliOps — Live Dashboard</title>
  <style>
    body { font-family: monospace; background: #0f0f0f; color: #e0e0e0; padding: 24px; }
    h1 { color: #22c55e; font-size: 18px; }
    .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 20px 0; }
    .card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; padding: 16px; }
    .val { font-size: 32px; font-weight: bold; margin: 4px 0; }
    .label { font-size: 11px; color: #888; }
    .ok { color: #22c55e; }
    .warn { color: #eab308; }
    .danger { color: #ef4444; }
    #log { background: #111; padding: 12px; border-radius: 8px; font-size: 12px;
           height: 200px; overflow-y: auto; border: 1px solid #222; }
    .status { font-size: 12px; color: #555; margin-top: 8px; }
  </style>
</head>
<body>
  <h1>IntelliOps — Live System Monitor</h1>
  <div class="grid">
    <div class="card"><div class="label">CPU Usage</div><div class="val" id="cpu">--</div></div>
    <div class="card"><div class="label">Memory Usage</div><div class="val" id="mem">--</div></div>
    <div class="card"><div class="label">Disk Usage</div><div class="val" id="disk">--</div></div>
  </div>
  <div class="label" style="margin-bottom:6px">Live event log</div>
  <div id="log"></div>
  <div class="status" id="status">Connecting to WebSocket...</div>

  <script>
    const ws = new WebSocket("ws://localhost:8000/ws/metrics");
    const log = document.getElementById("log");

    function colorClass(val) {
      if (val > 85) return "danger";
      if (val > 65) return "warn";
      return "ok";
    }

    ws.onopen = () => {
      document.getElementById("status").textContent = "Connected — receiving live data";
    };

    ws.onmessage = (e) => {
      const d = JSON.parse(e.data);
      const cpu = d.cpu_percent.toFixed(1);
      const mem = d.memory_percent.toFixed(1);
      const disk = d.disk_percent.toFixed(1);

      document.getElementById("cpu").textContent = cpu + "%";
      document.getElementById("cpu").className = "val " + colorClass(d.cpu_percent);
      document.getElementById("mem").textContent = mem + "%";
      document.getElementById("mem").className = "val " + colorClass(d.memory_percent);
      document.getElementById("disk").textContent = disk + "%";

      const line = document.createElement("div");
      line.textContent = `[${d.timestamp.slice(11,19)}] CPU ${cpu}%  MEM ${mem}%  DISK ${disk}%`;
      log.prepend(line);
      if (log.children.length > 50) log.lastChild.remove();
    };

    ws.onerror = () => {
      document.getElementById("status").textContent = "Connection error — is the API running?";
    };
  </script>
</body>
</html>
"""

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return DASHBOARD_HTML