import time
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL", "60"))

_registry: dict[str, dict] = {}


def _active() -> list[dict]:
    cutoff = time.time() - HEARTBEAT_TTL
    return [v for v in _registry.values() if v["lastHeartbeat"] >= cutoff]


@app.get("/api/registry")
def get_registry():
    return jsonify(_active())


@app.post("/api/registry/register")
def register():
    data = request.get_json(force=True)
    if not data or not data.get("id"):
        return jsonify({"error": "missing id"}), 400
    _registry[data["id"]] = {**data, "lastHeartbeat": time.time()}
    return jsonify({"ok": True})


@app.post("/api/registry/heartbeat/<app_id>")
def heartbeat(app_id: str):
    if app_id not in _registry:
        return jsonify({"error": "not registered"}), 404
    _registry[app_id]["lastHeartbeat"] = time.time()
    return jsonify({"ok": True})


@app.delete("/api/registry/<app_id>")
def unregister(app_id: str):
    _registry.pop(app_id, None)
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
