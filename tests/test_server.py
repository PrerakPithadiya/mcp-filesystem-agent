"""
Unit and integration tests for MCP Filesystem server and path sandbox.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from server.sandbox import get_safe_path
from server.mcp_server import (
    create_folder,
    create_file,
    read_file,
    list_folder,
    update_file,
    delete_item,
)


class TestSandboxAndTools(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="mcp_test_ws_")
        self.workspace = Path(self.test_dir).resolve()
        os.environ["WORKSPACE_DIR"] = str(self.workspace)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_sandbox_allows_valid_paths(self):
        safe = get_safe_path("subfolder/file.txt", self.workspace)
        self.assertTrue(str(safe).startswith(str(self.workspace)))

    def test_sandbox_blocks_directory_traversal(self):
        with self.assertRaises(PermissionError):
            get_safe_path("../../outside.txt", self.workspace)

        with self.assertRaises(PermissionError):
            get_safe_path("../secret.txt", self.workspace)

        with self.assertRaises(PermissionError):
            get_safe_path("C:/Windows/System32", self.workspace)

    def test_create_and_list_folder(self):
        res = create_folder("Projects")
        self.assertIn("Successfully created", res)
        self.assertTrue((self.workspace / "Projects").is_dir())

        list_res = list_folder("")
        self.assertIn("Projects", list_res)

    def test_create_and_read_file(self):
        res = create_file("notes.txt", "hello world")
        self.assertIn("Successfully created", res)
        self.assertTrue((self.workspace / "notes.txt").is_file())

        content = read_file("notes.txt")
        self.assertEqual(content, "hello world")

    def test_update_file_overwrite_and_append(self):
        create_file("test.txt", "initial")
        
        # Overwrite
        res = update_file("test.txt", "done", mode="overwrite")
        self.assertIn("Successfully updated", res)
        self.assertEqual(read_file("test.txt"), "done")

        # Append
        res_append = update_file("test.txt", "more content", mode="append")
        self.assertIn("Successfully appended", res_append)
        self.assertIn("done\nmore content", read_file("test.txt"))

    def test_delete_file(self):
        create_file("to_delete.txt", "bye")
        self.assertTrue((self.workspace / "to_delete.txt").exists())

        del_res = delete_item("to_delete.txt")
        self.assertIn("Successfully deleted", del_res)
        self.assertFalse((self.workspace / "to_delete.txt").exists())

    def test_delete_folder_recursive(self):
        create_folder("parent_folder")
        create_file("parent_folder/child.txt", "inner")

        # Without recursive should fail on non-empty folder
        del_fail = delete_item("parent_folder", recursive=False)
        self.assertIn("not empty", del_fail)

        # With recursive should succeed
        del_ok = delete_item("parent_folder", recursive=True)
        self.assertIn("Successfully deleted", del_ok)
        self.assertFalse((self.workspace / "parent_folder").exists())

    def test_self_root_prefix_stripping(self):
        root_name = self.workspace.name
        safe = get_safe_path(f"{root_name}/sub/file.txt", self.workspace)
        self.assertEqual(safe, (self.workspace / "sub" / "file.txt").resolve())

    def test_protected_system_files_protection(self):
        # Create attempt
        res_create = create_file("desktop.ini", "something")
        self.assertIn("protected system file", res_create)

        # Update attempt
        res_update = update_file("desktop.ini", "something")
        self.assertIn("protected system file", res_update)

        # Delete attempt
        res_del = delete_item("desktop.ini")
        self.assertIn("protected system file", res_del)

    def test_list_folder_excludes_protected_files(self):
        # Create a regular file and a desktop.ini directly
        (self.workspace / "normal.txt").write_text("hello", encoding="utf-8")
        (self.workspace / "desktop.ini").write_text("[.ShellClassInfo]", encoding="utf-8")

        listing = list_folder("")
        self.assertIn("normal.txt", listing)
        self.assertNotIn("desktop.ini", listing)


if __name__ == "__main__":
    unittest.main()
