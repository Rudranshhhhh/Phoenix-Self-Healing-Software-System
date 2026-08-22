"""
Phoenix Sample App — Intentionally Breakable Flask App

Endpoint triggers:
  GET /health        → Returns 200 (healthy) or 500 (broken)
  GET /break-health  → Forces /health to return 500
  GET /restore-health→ Restores /health to return 200
  GET /crash         → Exits process immediately (container crash)
  GET /leak          → Spikes memory consumption indefinitely (memory leak)
  GET /cpu           → Spikes CPU to 100% (infinite loop thread)
  GET /db            → Queries PostgreSQL dependency
  GET /cache         → Reads/writes Redis dependency
"""
from __future__ import annotations

import os
import sys
import time
import thread
import logging
from flask import Flask, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sample-app")

# Global health status toggle
_is_healthy = True

# Global memory leak leak-list to prevent garbage collection
_memory_leak_bucket = []


@app.get("/health")
def health():
    global _is_healthy
    if _is_healthy:
        return jsonify({"status": "healthy", "service": "sample-backend"}), 200
    else:
        return jsonify({"status": "unhealthy", "error": "Internal Server Error"}), 500


@app.get("/break-health")
def break_health():
    global _is_healthy
    _is_healthy = False
    logger.warning("🩺 Sample App: Health endpoint broken manually")
    return jsonify({"message": "Health endpoint broken successfully."}), 200


@app.get("/restore-health")
def restore_health():
    global _is_healthy
    _is_healthy = True
    logger.info("🩺 Sample App: Health endpoint restored manually")
    return jsonify({"message": "Health endpoint restored successfully."}), 200


@app.get("/crash")
def crash():
    logger.critical("💥 Sample App: Simulating immediate process exit")
    # Gracefully notify logs, then kill process
    sys.stdout.flush()
    os._exit(1)


@app.get("/leak")
def leak():
    logger.warning("💧 Sample App: Simulating memory leak...")
    # Allocate approximately 150MB of memory by appending large strings
    global _memory_leak_bucket
    for i in range(15):
        # ~10MB string replication
        _memory_leak_bucket.append("X" * (10 * 1024 * 1024))
    logger.warning("💧 Sample App: Leak complete. Bucket size is now %d items", len(_memory_leak_bucket))
    return jsonify({"message": "Allocated ~150MB memory. Memory leak active."}), 200


@app.get("/cpu")
def cpu_spike():
    logger.warning("🔥 Sample App: Simulating CPU spike...")
    # Spawn a background thread that does intensive calculations indefinitely
    def _cpu_burner():
        logger.info("🔥 Background burner started")
        while True:
            # Busy-wait loop
            _ = 23908 * 92384

    import threading
    t = threading.Thread(target=_cpu_burner, daemon=True)
    t.start()
    return jsonify({"message": "CPU burner thread launched."}), 200


@app.get("/db")
def db_check():
    import psycopg2
    try:
        url = os.getenv("DATABASE_URL", "postgresql://sampleuser:samplepassword@postgres:5432/sampledb")
        conn = psycopg2.connect(url, connect_timeout=3)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        return jsonify({"database": "connected"}), 200
    except Exception as exc:
        logger.error("DB query failed: %s", exc)
        return jsonify({"database": "disconnected", "error": str(exc)}), 500


@app.get("/cache")
def cache_check():
    import redis
    try:
        url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        r = redis.from_url(url, socket_timeout=3)
        r.ping()
        return jsonify({"redis": "connected"}), 200
    except Exception as exc:
        logger.error("Redis ping failed: %s", exc)
        return jsonify({"redis": "disconnected", "error": str(exc)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
