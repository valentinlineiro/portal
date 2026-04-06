import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class RegistryApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "registry.sqlite3")
        os.environ["REGISTRY_DB_PATH"] = self.db_path
        os.environ["HEARTBEAT_TTL"] = "60"
        self.app_module = importlib.import_module("app")
        self.app_module = importlib.reload(self.app_module)
        self.client = self.app_module.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()
        os.environ.pop("REGISTRY_DB_PATH", None)
        os.environ.pop("HEARTBEAT_TTL", None)

    def test_registry_lifecycle(self):
        manifest = {
            "manifestVersion": 1,
            "id": "exam-corrector",
            "name": "Exam Corrector",
            "description": "Correccion automatica",
            "route": "exam-corrector",
            "icon": "X",
            "status": "stable",
            "backend": {"pathPrefix": "/exam-corrector/"},
            "scriptUrl": "/apps/exam-corrector/element/main.js",
            "elementTag": "exam-corrector-app",
        }

        res = self.client.post("/api/registry/register", json=manifest)
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/registry")
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], manifest["id"])

        res = self.client.post("/api/registry/heartbeat/exam-corrector")
        self.assertEqual(res.status_code, 200)

        res = self.client.delete("/api/registry/exam-corrector")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/registry")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_registry_filters_stale_entries(self):
        os.environ["HEARTBEAT_TTL"] = "1"
        self.app_module = importlib.reload(self.app_module)
        self.client = self.app_module.app.test_client()

        manifest = {
            "manifestVersion": 1,
            "id": "stale-app",
            "name": "Stale App",
            "description": "Should expire",
            "route": "stale-app",
            "icon": "X",
            "status": "wip",
            "backend": None,
        }

        res = self.client.post("/api/registry/register", json=manifest)
        self.assertEqual(res.status_code, 200)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE registry SET last_heartbeat = 0 WHERE id = ?", ("stale-app",))

        res = self.client.get("/api/registry")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), [])

    def test_register_requires_manifest_version(self):
        manifest = {
            "id": "missing-version",
            "name": "Missing Version",
            "description": "No version set",
            "route": "missing-version",
            "icon": "X",
            "status": "stable",
            "backend": None,
        }

        res = self.client.post("/api/registry/register", json=manifest)
        self.assertEqual(res.status_code, 400)
        payload = res.get_json()
        self.assertEqual(payload["error"], "invalid_manifest")
        self.assertIn("manifestVersion", payload["fieldErrors"])

    def test_register_rejects_unsupported_manifest_version(self):
        manifest = {
            "manifestVersion": 2,
            "id": "unsupported-version",
            "name": "Unsupported Version",
            "description": "Newer than supported",
            "route": "unsupported-version",
            "icon": "X",
            "status": "stable",
            "backend": None,
        }

        res = self.client.post("/api/registry/register", json=manifest)
        self.assertEqual(res.status_code, 422)
        payload = res.get_json()
        self.assertEqual(payload["error"], "unsupported_manifest_version")
        self.assertEqual(payload["manifestVersion"], 2)
        self.assertEqual(payload["supportedVersions"], [1])

    def test_register_rejects_invalid_manifest_fields(self):
        manifest = {
            "manifestVersion": 1,
            "id": "",
            "name": "Bad App",
            "description": "invalid fields",
            "route": "bad-app",
            "icon": "X",
            "status": "broken",
            "backend": {"pathPrefix": ""},
            "scriptUrl": "/apps/bad-app/element/main.js",
        }

        res = self.client.post("/api/registry/register", json=manifest)
        self.assertEqual(res.status_code, 400)
        payload = res.get_json()
        self.assertEqual(payload["error"], "invalid_manifest")
        self.assertIn("id", payload["fieldErrors"])
        self.assertIn("status", payload["fieldErrors"])
        self.assertIn("backend.pathPrefix", payload["fieldErrors"])
        self.assertIn("frontend", payload["fieldErrors"])


if __name__ == "__main__":
    unittest.main()
