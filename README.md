# IntelliOps — Week 1 Setup Guide

## What you'll have by end of Week 1

```
Your laptop (psutil) → Kafka → FastAPI → browser dashboard
                                    ↓
                                InfluxDB (persistent storage)
```

---

## Prerequisites

- Python 3.10+
- Docker Desktop running
- Cursor IDE

---

## Step 1 — Clone and install

```bash
# Create project folder
mkdir intelliops && cd intelliops

# Copy all files from this starter kit into it, then:
pip install -r requirements.txt
```

---

## Step 2 — Start infrastructure (one command)

```bash
docker-compose up -d
```

Wait ~30 seconds for Kafka to be ready, then verify:

```bash
docker-compose ps
# All 4 services should show "Up"
```

---

## Step 3 — Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

You should see:
```
[Consumer] Subscribed to Kafka topic 'system-metrics'
[API] IntelliOps is running at http://localhost:8000
[API] Live dashboard at http://localhost:8000/dashboard
```

---

## Step 4 — Start the collector (new terminal)

```bash
python collector/collector.py
```

You should see:
```
[IntelliOps Collector] Starting on host 'your-machine-name'
[15:04:22] CPU:  23.4%  MEM:  61.2%  DISK:  44.0%  NET↑: 2104MB
[15:04:27] CPU:  31.1%  MEM:  61.4%  DISK:  44.0%  NET↑: 2105MB
```

---

## Step 5 — See it working

Open your browser:

| URL | What you'll see |
|-----|----------------|
| http://localhost:8000/dashboard | Live terminal-style dashboard |
| http://localhost:8000/metrics/latest | Latest JSON reading |
| http://localhost:8000/metrics/summary | 5-min averages |
| http://localhost:8000/docs | Auto-generated API docs |
| http://localhost:8086 | InfluxDB UI (admin / intelliops123) |

---

## Verify data is reaching InfluxDB

1. Go to http://localhost:8086
2. Login: admin / intelliops123
3. Click "Explore" → select bucket "metrics"
4. Query: `from(bucket:"metrics") |> range(start: -5m)`
5. You should see your CPU/memory readings plotted

---

## Week 1 done — what you now have

- [x] Real metrics flowing from your machine every 5 seconds
- [x] Kafka buffering the stream (restart-safe)
- [x] InfluxDB storing everything persistently
- [x] FastAPI with REST + WebSocket endpoints
- [x] Live dashboard in browser

## Next: Week 2 — Anomaly Detection

Add Isolation Forest to score each reading.
Any reading with score > 0.70 triggers an alert.
