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
SUPPORTED_MANIFEST_VERSIONS = {1}
ALLOWED_STATUSES = {"stable", "wip", "disabled"}


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


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_manifest(data: object) -> tuple[dict, dict[str, str], int | None]:
    if not isinstance(data, dict):
        return {}, {"manifest": "must be a JSON object"}, None

    field_errors: dict[str, str] = {}
    manifest = data.copy()

    version = manifest.get("manifestVersion")
    if version is None:
        field_errors["manifestVersion"] = "is required"
    elif not isinstance(version, int):
        field_errors["manifestVersion"] = "must be an integer"
    elif version not in SUPPORTED_MANIFEST_VERSIONS:
        return {}, {}, version

    required_string_fields = ("id", "name", "description", "route", "icon")
    for field in required_string_fields:
        if field not in manifest:
            field_errors[field] = "is required"
            continue
        if not _is_non_empty_string(manifest[field]):
            field_errors[field] = "must be a non-empty string"

    status = manifest.get("status")
    if status is None:
        field_errors["status"] = "is required"
    elif status not in ALLOWED_STATUSES:
        field_errors["status"] = f"must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"

    backend = manifest.get("backend")
    if backend is None:
        pass
    elif not isinstance(backend, dict):
        field_errors["backend"] = "must be null or an object"
    else:
        path_prefix = backend.get("pathPrefix")
        if not _is_non_empty_string(path_prefix):
            field_errors["backend.pathPrefix"] = "must be a non-empty string"

    script_url = manifest.get("scriptUrl")
    if script_url is not None and not _is_non_empty_string(script_url):
        field_errors["scriptUrl"] = "must be a non-empty string"

    element_tag = manifest.get("elementTag")
    if element_tag is not None and not _is_non_empty_string(element_tag):
        field_errors["elementTag"] = "must be a non-empty string"

    if (script_url is None) ^ (element_tag is None):
        field_errors["frontend"] = "scriptUrl and elementTag must be provided together"

    permissions = manifest.get("permissions")
    if permissions is not None:
        if not isinstance(permissions, list) or not all(_is_non_empty_string(p) for p in permissions):
            field_errors["permissions"] = "must be an array of non-empty strings"

    publisher = manifest.get("publisher")
    if publisher is not None:
        if not isinstance(publisher, dict):
            field_errors["publisher"] = "must be an object"
        else:
            if not _is_non_empty_string(publisher.get("id")):
                field_errors["publisher.id"] = "must be a non-empty string"
            if not _is_non_empty_string(publisher.get("name")):
                field_errors["publisher.name"] = "must be a non-empty string"

    return manifest, field_errors, None


@app.get("/api/registry")
def get_registry():
    return jsonify(_active())


@app.post("/api/registry/register")
def register():
    data = request.get_json(force=True)
    manifest, field_errors, unsupported_version = _validate_manifest(data)
    if unsupported_version is not None:
        return jsonify(
            {
                "error": "unsupported_manifest_version",
                "manifestVersion": unsupported_version,
                "supportedVersions": sorted(SUPPORTED_MANIFEST_VERSIONS),
            }
        ), 422
    if field_errors:
        return jsonify({"error": "invalid_manifest", "fieldErrors": field_errors}), 400
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
            (manifest["id"], json.dumps(manifest), now),
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
