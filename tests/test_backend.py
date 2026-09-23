"""
Integration tests for FastAPI backend and endpoints.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.llm_agent import PENDING_CONFIRMATIONS


class TestBackendAPI(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="backend_test_ws_")
        self.workspace = Path(self.test_dir).resolve()
        os.environ["WORKSPACE_DIR"] = str(self.workspace)
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "online")
        self.assertIn("provider", data)
        self.assertIn("workspace", data)
        self.assertIn("workspace_name", data)

    def test_workspace_tree_and_file_preview(self):
        # Create a file directly in test workspace
        test_file = self.workspace / "sample.txt"
        test_file.write_text("Hello MCP backend", encoding="utf-8")

        # Create a system file that should be filtered out
        (self.workspace / "desktop.ini").write_text("[.ShellClassInfo]", encoding="utf-8")

        subfolder = self.workspace / "test_folder"
        subfolder.mkdir()
        (subfolder / "nested.txt").write_text("Nested content", encoding="utf-8")

        # Test tree
        tree_resp = self.client.get("/api/workspace/tree")
        self.assertEqual(tree_resp.status_code, 200)
        tree = tree_resp.json()
        self.assertEqual(tree["name"], self.workspace.name)
        names = [c["name"] for c in tree["children"]]
        self.assertIn("sample.txt", names)
        self.assertIn("test_folder", names)
        self.assertNotIn("desktop.ini", names)

        # Test file preview
        file_resp = self.client.get("/api/workspace/file?path=sample.txt")
        self.assertEqual(file_resp.status_code, 200)
        self.assertEqual(file_resp.json()["content"], "Hello MCP backend")

    def test_traversal_blocked_in_api(self):
        file_resp = self.client.get("/api/workspace/file?path=../../PRD.md")
        self.assertEqual(file_resp.status_code, 403)

    def test_confirm_flow(self):
        # Setup pending confirmation
        conf_id = "test_conf_123"
        to_delete = self.workspace / "delete_me.txt"
        to_delete.write_text("delete this", encoding="utf-8")
        self.assertTrue(to_delete.exists())

        PENDING_CONFIRMATIONS[conf_id] = {
            "tool": "delete_item",
            "arguments": {"path": "delete_me.txt"},
            "prompt": "delete delete_me.txt",
        }

        # Test cancellation first
        cancel_resp = self.client.post("/api/confirm", json={"confirmation_id": conf_id, "confirmed": False})
        self.assertEqual(cancel_resp.status_code, 200)
        self.assertIn("cancelled", cancel_resp.json()["reply"])
        self.assertTrue(to_delete.exists())  # File still exists!

        # Re-queue confirmation and test confirm
        PENDING_CONFIRMATIONS[conf_id] = {
            "tool": "delete_item",
            "arguments": {"path": "delete_me.txt"},
            "prompt": "delete delete_me.txt",
        }

        confirm_resp = self.client.post("/api/confirm", json={"confirmation_id": conf_id, "confirmed": True})
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertIn("Confirmed", confirm_resp.json()["reply"])
        self.assertFalse(to_delete.exists())  # File was deleted!


if __name__ == "__main__":
    unittest.main()
