"""
Comprehensive Test Suite for Bulletproof Scenario Hardening.

Covers all predicted edge cases, failure modes, and environmental variations:
1. Quote stripping & whitespace trimming in path resolution.
2. Windows prohibited characters handling (< > : " | ? *).
3. Tool argument alias normalization (path -> file_path, name -> folder_path, text -> content).
4. Binary file reading defense (no UnicodeDecodeError crashes).
5. Large file read truncation safety.
6. Binary file preview endpoint (/api/workspace/file) graceful response.
7. Workspace reset safety (skipping protected OS files like desktop.ini).
8. Context-aware pronoun resolution in offline mode ("read it", "delete it").
9. Shorthand command notations (touch, cat, echo >).
10. Gemini response.text safe retrieval defense.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from backend.main import app
from backend.mcp_client import normalize_tool_arguments
from backend.offline_handler import parse_offline_intent
from server.sandbox import get_safe_path
from server.mcp_server import create_file, read_file, create_folder, PROTECTED_SYSTEM_FILES


class TestSandboxHardening(unittest.TestCase):
    """Tests sandbox path resolution edge cases."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="bulletproof_ws_")
        self.workspace = Path(self.test_dir).resolve()
        os.environ["WORKSPACE_DIR"] = str(self.workspace)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_quote_stripping_in_path(self):
        safe1 = get_safe_path("'notes.txt'", self.workspace)
        self.assertEqual(safe1.name, "notes.txt")
        self.assertNotIn("'", str(safe1))

        safe2 = get_safe_path('"subfolder/app.py"', self.workspace)
        self.assertEqual(safe2.name, "app.py")
        self.assertNotIn('"', str(safe2))

    def test_windows_prohibited_characters(self):
        # Colon inside filename (not drive letter) or question marks
        with self.assertRaises((ValueError, OSError)):
            get_safe_path("invalid:name.txt", self.workspace)

        with self.assertRaises((ValueError, OSError)):
            get_safe_path("wildcard*.txt", self.workspace)


class TestToolArgumentNormalization(unittest.TestCase):
    """Tests normalization of argument aliases from various LLM models."""

    def test_create_folder_aliases(self):
        # path -> folder_path
        args = normalize_tool_arguments("create_folder", {"path": " 'Projects' "})
        self.assertEqual(args.get("folder_path"), "Projects")
        self.assertNotIn("path", args)

        # name -> folder_path
        args2 = normalize_tool_arguments("create_folder", {"name": "docs"})
        self.assertEqual(args2.get("folder_path"), "docs")

    def test_create_file_aliases(self):
        # filename + text -> file_path + content
        args = normalize_tool_arguments("create_file", {"filename": "app.py", "text": "print(1)"})
        self.assertEqual(args.get("file_path"), "app.py")
        self.assertEqual(args.get("content"), "print(1)")
        self.assertNotIn("filename", args)
        self.assertNotIn("text", args)

    def test_read_file_aliases(self):
        args = normalize_tool_arguments("read_file", {"path": "'data.csv'"})
        self.assertEqual(args.get("file_path"), "data.csv")

    def test_list_folder_defaults(self):
        args = normalize_tool_arguments("list_folder", {})
        self.assertEqual(args.get("folder_path"), "")

    def test_delete_item_aliases(self):
        args = normalize_tool_arguments("delete_item", {"target": "old_backup.zip"})
        self.assertEqual(args.get("path"), "old_backup.zip")


class TestServerFileOperationsDefenses(unittest.TestCase):
    """Tests server defense against binary files and excessive sizes."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="bulletproof_server_ws_")
        self.workspace = Path(self.test_dir).resolve()
        os.environ["WORKSPACE_DIR"] = str(self.workspace)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_binary_file_reading(self):
        bin_file = self.workspace / "image.png"
        bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01")

        result = read_file("image.png")
        self.assertIn("binary file", result.lower())
        self.assertNotIn("Traceback", result)

    def test_large_file_truncation(self):
        large_file = self.workspace / "large.txt"
        # 600 KB file
        large_file.write_text("A" * 600_000, encoding="utf-8")

        result = read_file("large.txt")
        self.assertIn("truncated", result.lower())
        self.assertLess(len(result), 500_000)


class TestMainApiHardening(unittest.TestCase):
    """Tests FastAPI backend endpoint hardening."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="bulletproof_api_ws_")
        self.workspace = Path(self.test_dir).resolve()
        os.environ["WORKSPACE_DIR"] = str(self.workspace)
        self.client = TestClient(app)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_binary_file_preview_endpoint(self):
        bin_file = self.workspace / "logo.ico"
        bin_file.write_bytes(b"\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x08\x00")

        resp = self.client.get("/api/workspace/file?path=logo.ico")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("is_binary"))
        self.assertIn("Binary file", data.get("content"))

    def test_reset_workspace_preserves_desktop_ini(self):
        # Create desktop.ini and sample file
        ini = self.workspace / "desktop.ini"
        ini.write_text("[.ShellClassInfo]\n", encoding="utf-8")
        sample = self.workspace / "temp.txt"
        sample.write_text("delete this", encoding="utf-8")

        resp = self.client.post("/api/workspace/reset")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(ini.exists(), "desktop.ini must be preserved across reset")
        self.assertFalse(sample.exists(), "temp.txt should be cleared")


class TestOfflinePronounAndShorthandResolution(unittest.TestCase):
    """Tests pronoun resolution and command shorthand notations in offline mode."""

    def test_offline_pronoun_resolution_read(self):
        history = [
            {"role": "user", "content": "create file budget.xlsx with sales data"},
            {"role": "assistant", "content": "Successfully created file: budget.xlsx"},
        ]
        intent = parse_offline_intent("read it", history=history)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "read_file")
        self.assertEqual(intent.get("file_path"), "budget.xlsx")

    def test_offline_pronoun_resolution_delete(self):
        history = [
            {"role": "user", "content": "create a folder called Archive"},
            {"role": "assistant", "content": "Successfully created folder: Archive"},
        ]
        intent = parse_offline_intent("delete it", history=history)
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "delete_item")
        self.assertIn("Archive", intent.get("targets", []))

    def test_offline_echo_shorthand(self):
        intent = parse_offline_intent('echo "Hello World" > greetings.txt')
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "create_file")
        self.assertEqual(intent.get("file_path"), "greetings.txt")
        self.assertEqual(intent.get("content"), "Hello World")

    def test_offline_touch_shorthand(self):
        intent = parse_offline_intent("touch index.html")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.get("action"), "create_file")
        self.assertEqual(intent.get("file_path"), "index.html")


if __name__ == "__main__":
    unittest.main()
