import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class AuthApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "registry.sqlite3")
        os.environ["REGISTRY_DB_PATH"] = self.db_path
        os.environ["PORTAL_SESSION_SECRET"] = "test-secret"
        os.environ["OAUTH_CLIENT_ID"] = "client-id"
        os.environ["OAUTH_CLIENT_SECRET"] = "client-secret"
        os.environ["OAUTH_AUTHORIZE_URL"] = "https://idp.example.com/authorize"
        os.environ["OAUTH_TOKEN_URL"] = "https://idp.example.com/token"
        os.environ["OAUTH_USERINFO_URL"] = "https://idp.example.com/userinfo"
        os.environ["OAUTH_REDIRECT_URI"] = "http://localhost:5000/auth/callback"
        os.environ["OAUTH_PROVIDER"] = "oidc"
        self.app_module = importlib.import_module("app")
        self.app_module = importlib.reload(self.app_module)
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()
        for key in (
            "REGISTRY_DB_PATH",
            "PORTAL_SESSION_SECRET",
            "OAUTH_CLIENT_ID",
            "OAUTH_CLIENT_SECRET",
            "OAUTH_AUTHORIZE_URL",
            "OAUTH_TOKEN_URL",
            "OAUTH_USERINFO_URL",
            "OAUTH_REDIRECT_URI",
            "OAUTH_PROVIDER",
        ):
            os.environ.pop(key, None)

    def test_auth_login_redirects_to_provider(self):
        res = self.client.get("/auth/login")
        self.assertEqual(res.status_code, 302)
        location = res.headers.get("Location", "")
        self.assertIn("https://idp.example.com/authorize", location)
        self.assertIn("client_id=client-id", location)
        self.assertIn("state=", location)

    def test_auth_callback_invalid_state(self):
        with self.client.session_transaction() as sess:
            sess["oauth_state"] = "expected"

        res = self.client.get("/auth/callback?code=abc&state=wrong")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"], "invalid_state")

    def test_auth_callback_creates_session_and_user(self):
        with self.client.session_transaction() as sess:
            sess["oauth_state"] = "state-123"
            sess["oauth_next"] = "/"

        token_res = Mock()
        token_res.ok = True
        token_res.json.return_value = {"access_token": "token123"}

        userinfo_res = Mock()
        userinfo_res.ok = True
        userinfo_res.json.return_value = {
            "sub": "abc123",
            "email": "dev@example.com",
            "name": "Dev User",
        }

        with patch.object(self.app_module.http_requests, "post", return_value=token_res), patch.object(
            self.app_module.http_requests,
            "get",
            return_value=userinfo_res,
        ):
            res = self.client.get("/auth/callback?code=ok-code&state=state-123")

        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers.get("Location"), "/")

        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        payload = me.get_json()
        self.assertEqual(payload["email"], "dev@example.com")
        self.assertIn("member", payload["roles"])

        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT id, email FROM users WHERE provider_sub = ?", ("abc123",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], "dev@example.com")

    def test_auth_me_requires_login(self):
        res = self.client.get("/auth/me")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["error"], "unauthorized")


if __name__ == "__main__":
    unittest.main()
