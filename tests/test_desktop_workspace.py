"""
Comprehensive Test Suite for Windows Desktop Workspace (Option A).

Tests all layers:
1. Sandbox path validation & redundant prefix stripping (e.g. 'Desktop/file.txt' -> 'file.txt')
2. OS system file protection (desktop.ini, thumbs.db, etc.)
3. CRUD tool operations on desktop
4. FastAPI endpoints (/api/health, /api/workspace/tree, /api/workspace/file)
5. End-to-end LLM agent tool calling & confirmation flow on desktop
6. Live Windows Desktop probe verification
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Any, List

from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT, get_workspace_path
from backend.main import app, _build_tree
from backend.llm_agent import LLMAgent, PENDING_CONFIRMATIONS
from server.sandbox import get_default_workspace, get_safe_path
from server.mcp_server import (
    create_folder,
    create_file,
    read_file,
    list_folder,
    update_file,
    delete_item,
    PROTECTED_SYSTEM_FILES,
)


class BaseDesktopTestCase(unittest.TestCase):
    """Base setup that simulates an isolated Windows Desktop folder with desktop.ini."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mock_desktop_ws_")
        # Simulate a OneDrive / Windows Desktop folder name
        self.desktop_dir = Path(self.temp_dir) / "Desktop"
        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        # Create standard Windows desktop.ini
        self.desktop_ini = self.desktop_dir / "desktop.ini"
        self.desktop_ini.write_text("[.ShellClassInfo]\nIconResource=C:\\Windows\\System32\\imageres.dll,-183\n", encoding="utf-8")

        self.orig_workspace_env = os.environ.get("WORKSPACE_DIR")
        os.environ["WORKSPACE_DIR"] = str(self.desktop_dir)
        PENDING_CONFIRMATIONS.clear()
        from backend.mcp_client import mcp_client_service
        mcp_client_service._server_params = None

    def tearDown(self):
        PENDING_CONFIRMATIONS.clear()
        from backend.mcp_client import mcp_client_service
        mcp_client_service._server_params = None
        if self.orig_workspace_env is not None:
            os.environ["WORKSPACE_DIR"] = self.orig_workspace_env
        else:
            os.environ.pop("WORKSPACE_DIR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)


class TestDesktopSandboxAndPrefixNormalization(BaseDesktopTestCase):
    """Validates sandbox resolution and path normalization when Desktop is workspace root."""

    def test_workspace_points_to_desktop(self):
        ws = get_default_workspace()
        self.assertEqual(ws, self.desktop_dir.resolve())
        self.assertEqual(ws.name.lower(), "desktop")

    def test_strip_leading_desktop_prefix(self):
        """When user/LLM passes 'Desktop/file.txt', it must resolve to 'file.txt' at desktop root."""
        safe = get_safe_path("Desktop/my_notes.txt", self.desktop_dir)
        expected = self.desktop_dir / "my_notes.txt"
        self.assertEqual(safe, expected.resolve())

    def test_strip_case_insensitive_desktop_prefix(self):
        """Should handle 'desktop/file.txt' or 'DESKTOP/file.txt'."""
        safe1 = get_safe_path("desktop/sub/file.txt", self.desktop_dir)
        expected1 = self.desktop_dir / "sub" / "file.txt"
        self.assertEqual(safe1, expected1.resolve())

        safe2 = get_safe_path("DESKTOP/another.txt", self.desktop_dir)
        expected2 = self.desktop_dir / "another.txt"
        self.assertEqual(safe2, expected2.resolve())

    def test_desktop_root_only_input(self):
        """When input is literally 'Desktop' or 'desktop', it should resolve to the workspace root itself."""
        safe = get_safe_path("Desktop", self.desktop_dir)
        self.assertEqual(safe, self.desktop_dir.resolve())

    def test_absolute_path_within_desktop(self):
        """Specifying absolute path to an item on Desktop must succeed."""
        abs_path = str(self.desktop_dir / "document.pdf")
        safe = get_safe_path(abs_path, self.desktop_dir)
        self.assertEqual(safe, Path(abs_path).resolve())

    def test_sandbox_blocks_escape_from_desktop(self):
        """Attempting to access parent directories, Windows system folders, or other drives must raise PermissionError."""
        with self.assertRaises(PermissionError):
            get_safe_path("../secret.txt", self.desktop_dir)

        with self.assertRaises(PermissionError):
            get_safe_path("../../Windows/System32", self.desktop_dir)

        with self.assertRaises(PermissionError):
            get_safe_path("C:/Windows/System32/cmd.exe", self.desktop_dir)


class TestDesktopSystemFileProtection(BaseDesktopTestCase):
    """Validates that desktop.ini, thumbs.db, and other OS files cannot be corrupted."""

    def test_desktop_ini_protected_from_creation(self):
        res = create_file("desktop.ini", "malicious content")
        self.assertIn("protected system file", res.lower())

    def test_desktop_ini_protected_from_update(self):
        res = update_file("desktop.ini", "new content", mode="overwrite")
        self.assertIn("protected system file", res.lower())

    def test_desktop_ini_protected_from_deletion(self):
        res = delete_item("desktop.ini")
        self.assertIn("protected system file", res.lower())
        self.assertTrue(self.desktop_ini.exists(), "desktop.ini must not be deleted")

    def test_bulk_wipe_preserves_desktop_ini(self):
        """When user says 'delete everything', desktop.ini must be preserved."""
        # Create regular files
        create_file("file1.txt", "content 1")
        create_file("file2.txt", "content 2")
        create_folder("FolderA")

        res = delete_item("everything")
        self.assertIn("Successfully deleted", res)
        # desktop.ini must still exist!
        self.assertTrue(self.desktop_ini.exists(), "desktop.ini must survive workspace cleanup")
        # Regular files must be gone
        self.assertFalse((self.desktop_dir / "file1.txt").exists())
        self.assertFalse((self.desktop_dir / "file2.txt").exists())
        self.assertFalse((self.desktop_dir / "FolderA").exists())

    def test_list_folder_omits_desktop_ini(self):
        """Listing the desktop folder must not include desktop.ini or thumbs.db."""
        create_file("MyDocument.docx", "data")
        # Create a mock thumbs.db
        (self.desktop_dir / "thumbs.db").write_text("dummy", encoding="utf-8")

        listing = list_folder("")
        self.assertIn("MyDocument.docx", listing)
        self.assertNotIn("desktop.ini", listing)
        self.assertNotIn("thumbs.db", listing)


class TestDesktopCRUDOperations(BaseDesktopTestCase):
    """Validates all filesystem CRUD tools when running inside the desktop workspace."""

    def test_create_and_list_folder(self):
        res = create_folder("Work Projects")
        self.assertIn("Successfully created", res)
        folder = self.desktop_dir / "Work Projects"
        self.assertTrue(folder.is_dir())

        list_out = list_folder("")
        self.assertIn("Work Projects", list_out)

    def test_create_nested_folder(self):
        res = create_folder("Marketing/2026/Campaigns")
        self.assertIn("Successfully created", res)
        nested = self.desktop_dir / "Marketing" / "2026" / "Campaigns"
        self.assertTrue(nested.is_dir())

    def test_create_and_read_file(self):
        res = create_file("ideas.txt", "1. AI agent\n2. MCP integration\n")
        self.assertIn("Successfully created", res)
        file_path = self.desktop_dir / "ideas.txt"
        self.assertTrue(file_path.is_file())

        content = read_file("ideas.txt")
        self.assertEqual(content, "1. AI agent\n2. MCP integration\n")

    def test_create_file_with_desktop_prefix(self):
        """If user or LLM specifies 'Desktop/test.txt', it creates 'test.txt' on Desktop root."""
        res = create_file("Desktop/quick_note.txt", "test")
        self.assertIn("Successfully created", res)
        self.assertTrue((self.desktop_dir / "quick_note.txt").is_file())
        self.assertFalse((self.desktop_dir / "Desktop").exists())

    def test_update_file_overwrite_and_append(self):
        create_file("todo.txt", "buy coffee")
        
        # Append
        res_app = update_file("todo.txt", "buy milk", mode="append")
        self.assertIn("Successfully appended", res_app)
        self.assertIn("buy coffee\nbuy milk", read_file("todo.txt"))

        # Overwrite
        res_ov = update_file("todo.txt", "all done", mode="overwrite")
        self.assertIn("Successfully updated", res_ov)
        self.assertEqual(read_file("todo.txt"), "all done")

    def test_delete_file_and_recursive_folder(self):
        create_file("temp.log", "debug logs")
        self.assertTrue((self.desktop_dir / "temp.log").is_file())
        del_file = delete_item("temp.log")
        self.assertIn("Successfully deleted", del_file)
        self.assertFalse((self.desktop_dir / "temp.log").exists())

        # Folder delete
        create_folder("OldProject")
        create_file("OldProject/file.txt", "data")
        # Without recursive must fail
        del_fail = delete_item("OldProject", recursive=False)
        self.assertIn("not empty", del_fail)
        # With recursive must succeed
        del_ok = delete_item("OldProject", recursive=True)
        self.assertIn("Successfully deleted", del_ok)
        self.assertFalse((self.desktop_dir / "OldProject").exists())


class TestDesktopFastAPIEndpoints(BaseDesktopTestCase):
    """Validates FastAPI backend integration with Desktop workspace."""

    def setUp(self):
        super().setUp()
        self.client = TestClient(app)

    def test_health_check_returns_desktop_workspace(self):
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "online")
        self.assertEqual(data["workspace_name"], "Desktop")
        self.assertEqual(data["workspace"], str(self.desktop_dir.resolve()))

    def test_tree_excludes_desktop_ini_and_has_desktop_name(self):
        create_file("resume.pdf", "sample resume content")
        create_folder("Photos")
        create_file("Photos/vacation.jpg", "image data")

        resp = self.client.get("/api/workspace/tree")
        self.assertEqual(resp.status_code, 200)
        tree = resp.json()
        self.assertEqual(tree["name"], "Desktop")
        names = [c["name"] for c in tree["children"]]
        self.assertIn("resume.pdf", names)
        self.assertIn("Photos", names)
        # desktop.ini must be omitted
        self.assertNotIn("desktop.ini", names)

    def test_file_preview_endpoint(self):
        create_file("hello.txt", "Hello from Desktop preview!")
        resp = self.client.get("/api/workspace/file?path=hello.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["content"], "Hello from Desktop preview!")

    def test_file_preview_traversal_blocked(self):
        resp = self.client.get("/api/workspace/file?path=../../Windows/win.ini")
        self.assertEqual(resp.status_code, 403)


class TestLiveWindowsDesktopVerification(unittest.TestCase):
    """Performs a non-destructive probe test on the user's actual configured Windows Desktop."""

    def test_live_desktop_crud_probe(self):
        ws = get_workspace_path()
        self.assertTrue(ws.exists(), f"Configured workspace directory {ws} must exist.")
        self.assertTrue(ws.is_dir(), f"Configured workspace directory {ws} must be a directory.")

        probe_file_name = "__mcp_verification_probe_test__.tmp"
        probe_path = ws / probe_file_name

        try:
            # 1. Create probe
            res_create = create_file(probe_file_name, "Probe test verification content")
            self.assertIn("Successfully created", res_create)
            self.assertTrue(probe_path.exists(), "Probe file must physically exist on the Windows desktop.")

            # 2. Read probe
            content = read_file(probe_file_name)
            self.assertEqual(content, "Probe test verification content")

            # 3. Update probe
            res_up = update_file(probe_file_name, "Appended line", mode="append")
            self.assertIn("Successfully appended", res_up)
            self.assertEqual(read_file(probe_file_name), "Probe test verification content\nAppended line")

            # 4. List folder check
            listing = list_folder("")
            self.assertIn(probe_file_name, listing)

            # 5. Delete probe
            res_del = delete_item(probe_file_name)
            self.assertIn("Successfully deleted", res_del)
            self.assertFalse(probe_path.exists(), "Probe file must be cleanly deleted from the Windows desktop.")
        finally:
            if probe_path.exists():
                probe_path.unlink(missing_ok=True)


class TestDesktopChatbotAgentIntegration(unittest.IsolatedAsyncioTestCase):
    """End-to-end integration tests using LLMAgent with Gemini tool calling against Desktop workspace."""

    async def asyncSetUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mock_desktop_agent_ws_")
        self.desktop_dir = Path(self.temp_dir) / "Desktop"
        self.desktop_dir.mkdir(parents=True, exist_ok=True)
        self.desktop_ini = self.desktop_dir / "desktop.ini"
        self.desktop_ini.write_text("[.ShellClassInfo]\n", encoding="utf-8")

        self.orig_workspace_env = os.environ.get("WORKSPACE_DIR")
        os.environ["WORKSPACE_DIR"] = str(self.desktop_dir)
        PENDING_CONFIRMATIONS.clear()
        self.agent = LLMAgent()

    async def asyncTearDown(self):
        PENDING_CONFIRMATIONS.clear()
        if self.orig_workspace_env is not None:
            os.environ["WORKSPACE_DIR"] = self.orig_workspace_env
        else:
            os.environ.pop("WORKSPACE_DIR", None)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def chat(self, message: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        return await self.agent.chat(message, history or [])

    async def test_agent_creates_folder_cleanly_on_desktop(self):
        """Prompt mentioning 'on my desktop' must create the folder directly on Desktop root."""
        res = await self.chat("Create a folder on my desktop called ClientPresentations")
        target_dir = self.desktop_dir / "ClientPresentations"
        self.assertTrue(target_dir.is_dir(), "Folder 'ClientPresentations' must exist directly in desktop root.")
        self.assertFalse((self.desktop_dir / "Desktop").exists(), "Must not create a nested Desktop/Desktop folder.")

    async def test_agent_creates_and_reads_file_on_desktop(self):
        """Prompt creating a file on desktop followed by reading it back."""
        create_res = await self.chat("Make a file named report.txt on my desktop with 'Q3 Performance: Excellent'")
        file_path = self.desktop_dir / "report.txt"
        self.assertTrue(file_path.is_file(), "File 'report.txt' must exist in desktop root.")
        self.assertIn("Q3 Performance", file_path.read_text(encoding="utf-8"))

        read_res = await self.chat("Read report.txt from my desktop")
        self.assertIn("Q3 Performance", read_res.get("reply", ""))

    async def test_agent_delete_confirmation_gate_on_desktop(self):
        """Deleting an item from desktop must trigger confirmation gate and not delete until confirmed."""
        test_file = self.desktop_dir / "obsolete.txt"
        test_file.write_text("Remove this soon", encoding="utf-8")

        del_res = await self.chat("Delete obsolete.txt from my desktop")
        self.assertTrue(del_res.get("requires_confirmation"), "Must require confirmation for delete action.")
        conf = del_res.get("confirmation")
        self.assertIsNotNone(conf)
        self.assertTrue(test_file.exists(), "File must NOT be deleted before confirmation.")

        # Resolve confirmation
        resolve_res = await self.agent.resolve_confirmation(conf["id"], confirmed=True)
        self.assertIn("Confirmed", resolve_res.get("reply", ""))
        self.assertFalse(test_file.exists(), "File must be deleted after confirmation.")


if __name__ == "__main__":
    unittest.main()
