import os
import json
import sqlite3
import time
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL", "60"))
REGISTRY_DB_PATH = os.environ.get("REGISTRY_DB_PATH", "/tmp/portal_registry.sqlite3")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(REGISTRY_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registry (
                id TEXT PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                last_heartbeat REAL NOT NULL
            )
            """
        )


def _active() -> list[dict]:
    cutoff = time.time() - HEARTBEAT_TTL
    with _db() as conn:
        rows = conn.execute(
            "SELECT manifest_json, last_heartbeat FROM registry WHERE last_heartbeat >= ?",
            (cutoff,),
        ).fetchall()

    active_apps: list[dict] = []
    for row in rows:
        manifest = json.loads(row["manifest_json"])
        manifest["lastHeartbeat"] = row["last_heartbeat"]
        active_apps.append(manifest)
    return active_apps


@app.get("/api/registry")
def get_registry():
    return jsonify(_active())


@app.post("/api/registry/register")
def register():
    data = request.get_json(force=True)
    if not data or not data.get("id"):
        return jsonify({"error": "missing id"}), 400
    now = time.time()
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO registry (id, manifest_json, last_heartbeat)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                manifest_json = excluded.manifest_json,
                last_heartbeat = excluded.last_heartbeat
            """,
            (data["id"], json.dumps(data), now),
        )
    return jsonify({"ok": True})


@app.post("/api/registry/heartbeat/<app_id>")
def heartbeat(app_id: str):
    now = time.time()
    with _db() as conn:
        result = conn.execute(
            "UPDATE registry SET last_heartbeat = ? WHERE id = ?",
            (now, app_id),
        )
    if result.rowcount == 0:
        return jsonify({"error": "not registered"}), 404
    return jsonify({"ok": True})


@app.delete("/api/registry/<app_id>")
def unregister(app_id: str):
    with _db() as conn:
        conn.execute("DELETE FROM registry WHERE id = ?", (app_id,))
    return jsonify({"ok": True})


if __name__ == "__main__":
    _init_db()
    app.run(host="0.0.0.0", port=5000)


_init_db()
