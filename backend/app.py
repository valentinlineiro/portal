import functools
import os
import json
import secrets
import sqlite3
import time
import base64
import hashlib
import urllib.parse

import requests as http_requests
from flask import Flask, jsonify, redirect, request, session
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
app.secret_key = os.environ.get("PORTAL_SESSION_SECRET", "dev-portal-secret-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

HEARTBEAT_TTL = int(os.environ.get("HEARTBEAT_TTL", "60"))
REGISTRY_DB_PATH = os.environ.get("REGISTRY_DB_PATH", "/tmp/portal_registry.sqlite3")
SUPPORTED_MANIFEST_VERSIONS = {1}
ALLOWED_STATUSES = {"stable", "wip", "disabled"}
DEFAULT_ROLE = "member"
OAUTH_CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "")
OAUTH_AUTHORIZE_URL = os.environ.get("OAUTH_AUTHORIZE_URL", "")
OAUTH_TOKEN_URL = os.environ.get("OAUTH_TOKEN_URL", "")
OAUTH_USERINFO_URL = os.environ.get("OAUTH_USERINFO_URL", "")
OAUTH_SCOPE = os.environ.get("OAUTH_SCOPE", "openid profile email")
OAUTH_REDIRECT_URI = os.environ.get("OAUTH_REDIRECT_URI", "")
OAUTH_PROVIDER = os.environ.get("OAUTH_PROVIDER", "oidc")
OAUTH_LOGOUT_URL = os.environ.get("OAUTH_LOGOUT_URL", "")


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                provider TEXT NOT NULL,
                provider_sub TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                UNIQUE(provider, provider_sub)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY(user_id, role_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(role_id) REFERENCES roles(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS apps (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                visibility TEXT NOT NULL DEFAULT 'internal',
                status TEXT NOT NULL DEFAULT 'stable',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_id TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(app_id, subject_type, subject_id, permission)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                metadata_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        conn.executemany(
            "INSERT OR IGNORE INTO roles(name) VALUES (?)",
            [("owner",), ("admin",), ("member",), ("viewer",)],
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


def _oauth_is_configured() -> bool:
    return all([OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL, OAUTH_USERINFO_URL])


def _oauth_redirect_uri() -> str:
    if OAUTH_REDIRECT_URI:
        return OAUTH_REDIRECT_URI
    base = request.url_root.rstrip("/")
    return f"{base}/auth/callback"


def _oauth_logout_url() -> str:
    if OAUTH_LOGOUT_URL:
        return OAUTH_LOGOUT_URL
    parsed = urllib.parse.urlparse(OAUTH_AUTHORIZE_URL)
    if not parsed.scheme or not parsed.netloc or not parsed.path:
        return ""
    if parsed.path.endswith("/auth"):
        logout_path = f"{parsed.path[:-5]}/logout"
    else:
        logout_path = parsed.path.rstrip("/") + "/logout"
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, logout_path, "", "", ""))


def _pkce_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _json_metadata(data: dict | None = None) -> str:
    return json.dumps(data or {}, separators=(",", ":"))


def _log_audit(user_id: str | None, action: str, target_type: str | None = None, target_id: str | None = None, metadata: dict | None = None) -> None:
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (user_id, action, target_type, target_id, metadata_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, target_type, target_id, _json_metadata(metadata), time.time()),
        )


def _upsert_user(email: str, name: str, provider: str, provider_sub: str) -> str:
    now = time.time()
    user_id = f"{provider}:{provider_sub}"
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, provider, provider_sub, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, provider_sub) DO UPDATE SET
                email = excluded.email,
                name = excluded.name,
                updated_at = excluded.updated_at
            """,
            (user_id, email, name, provider, provider_sub, now, now),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO user_roles (user_id, role_id)
            SELECT ?, id FROM roles WHERE name = ?
            """,
            (user_id, DEFAULT_ROLE),
        )
    return user_id


def _get_user_roles(user_id: str) -> list[str]:
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT r.name
            FROM roles r
            JOIN user_roles ur ON ur.role_id = r.id
            WHERE ur.user_id = ?
            ORDER BY r.name
            """,
            (user_id,),
        ).fetchall()
    return [row["name"] for row in rows]


def _get_current_user() -> dict | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    with _db() as conn:
        row = conn.execute(
            "SELECT id, email, name, provider FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "provider": row["provider"],
        "roles": _get_user_roles(row["id"]),
    }


def require_auth(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)

    return wrapper


def _validate_manifest(data: object) -> tuple[dict, dict[str, str], int | None]:
    if not isinstance(data, dict):
        return {}, {"manifest": "must be a JSON object"}, None

    field_errors: dict[str, str] = {}
    manifest = data.copy()

    version = manifest.get("manifestVersion")
    if version is None:
        field_errors["manifestVersion"] = "is required"
    elif type(version) is not int:
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
    elif not isinstance(status, str):
        field_errors["status"] = f"must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"
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
@require_auth
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


@app.get("/auth/login")
def auth_login():
    if not _oauth_is_configured():
        return jsonify({"error": "oauth_not_configured"}), 500

    state = secrets.token_urlsafe(24)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _pkce_code_challenge(code_verifier)
    session["oauth_state"] = state
    session["oauth_code_verifier"] = code_verifier
    next_path = request.args.get("next", "/")
    session["oauth_next"] = next_path if isinstance(next_path, str) and next_path.startswith("/") else "/"

    params = {
        "response_type": "code",
        "client_id": OAUTH_CLIENT_ID,
        "redirect_uri": _oauth_redirect_uri(),
        "scope": OAUTH_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    authorize_url = f"{OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    return redirect(authorize_url, code=302)


@app.get("/auth/callback")
def auth_callback():
    if not _oauth_is_configured():
        return jsonify({"error": "oauth_not_configured"}), 500

    if request.args.get("error"):
        return jsonify(
            {
                "error": "oauth_error",
                "provider_error": request.args.get("error"),
                "provider_error_description": request.args.get("error_description", ""),
            }
        ), 400

    expected_state = session.get("oauth_state")
    code_verifier = session.get("oauth_code_verifier")
    received_state = request.args.get("state")
    code = request.args.get("code")
    if not expected_state or not received_state or expected_state != received_state:
        return jsonify({"error": "invalid_state"}), 400
    if not code_verifier:
        return jsonify({"error": "missing_code_verifier"}), 400
    if not code:
        return jsonify({"error": "missing_code"}), 400

    token_response = http_requests.post(
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _oauth_redirect_uri(),
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "code_verifier": code_verifier,
        },
        timeout=10,
    )
    if not token_response.ok:
        return jsonify({"error": "token_exchange_failed"}), 502
    token_payload = token_response.json()
    access_token = token_payload.get("access_token")
    id_token = token_payload.get("id_token")
    if not access_token:
        return jsonify({"error": "missing_access_token"}), 502

    userinfo_response = http_requests.get(
        OAUTH_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if not userinfo_response.ok:
        return jsonify({"error": "userinfo_fetch_failed"}), 502
    userinfo = userinfo_response.json()

    provider_sub = userinfo.get("sub")
    email = userinfo.get("email")
    name = userinfo.get("name") or email or str(provider_sub or "")
    if not provider_sub or not email:
        return jsonify({"error": "invalid_userinfo"}), 502

    user_id = _upsert_user(email=email, name=name, provider=OAUTH_PROVIDER, provider_sub=provider_sub)
    session.pop("oauth_state", None)
    session.pop("oauth_code_verifier", None)
    if id_token:
        session["oauth_id_token"] = id_token
    next_path = session.pop("oauth_next", "/")
    session["user_id"] = user_id
    _log_audit(user_id, "login", "auth", OAUTH_PROVIDER, {"email": email})
    return redirect(next_path if isinstance(next_path, str) and next_path.startswith("/") else "/", code=302)


@app.get("/auth/logout")
@app.post("/auth/logout")
def auth_logout():
    user_id = session.get("user_id")
    id_token_hint = session.get("oauth_id_token")
    next_path = request.args.get("next", "/")
    if not isinstance(next_path, str) or not next_path.startswith("/"):
        next_path = "/"

    session.clear()
    if user_id:
        _log_audit(user_id, "logout", "auth", OAUTH_PROVIDER)

    logout_url = _oauth_logout_url()
    if logout_url:
        post_logout_redirect_uri = f"{request.url_root.rstrip('/')}{next_path}"
        params = {
            "client_id": OAUTH_CLIENT_ID,
            "post_logout_redirect_uri": post_logout_redirect_uri,
        }
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        return redirect(f"{logout_url}?{urllib.parse.urlencode(params)}", code=302)

    if request.method == "POST":
        return jsonify({"ok": True})
    return redirect(next_path, code=302)


@app.get("/auth/me")
@require_auth
def auth_me():
    user = _get_current_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(user)


if __name__ == "__main__":
    _init_db()
    app.run(host="0.0.0.0", port=5000)


_init_db()
