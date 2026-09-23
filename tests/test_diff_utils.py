"""
Tests for diff calculation utility in backend/diff_utils.py
"""

import unittest
from backend.diff_utils import compute_file_diff


class TestDiffUtils(unittest.TestCase):
    def test_diff_identical(self):
        content = "hello world\nline two\n"
        diff = compute_file_diff(content, content, "notes.txt")
        self.assertEqual(diff["file_path"], "notes.txt")
        self.assertEqual(diff["stats"]["added"], 0)
        self.assertEqual(diff["stats"]["deleted"], 0)
        for line in diff["lines"]:
            self.assertEqual(line["type"], "context")

    def test_diff_addition(self):
        old_content = "hello world"
        new_content = "hello world\nline two"
        diff = compute_file_diff(old_content, new_content, "notes.txt")
        self.assertEqual(diff["stats"]["added"], 1)
        self.assertEqual(diff["stats"]["deleted"], 0)
        added_lines = [l for l in diff["lines"] if l["type"] == "add"]
        self.assertEqual(len(added_lines), 1)
        self.assertEqual(added_lines[0]["content"], "line two")
        self.assertEqual(added_lines[0]["new_num"], 2)

    def test_diff_deletion(self):
        old_content = "hello\nworld\nline three"
        new_content = "hello\nline three"
        diff = compute_file_diff(old_content, new_content, "notes.txt")
        self.assertEqual(diff["stats"]["deleted"], 1)
        self.assertEqual(diff["stats"]["added"], 0)
        deleted_lines = [l for l in diff["lines"] if l["type"] == "delete"]
        self.assertEqual(len(deleted_lines), 1)
        self.assertEqual(deleted_lines[0]["content"], "world")
        self.assertEqual(deleted_lines[0]["old_num"], 2)

    def test_diff_modification(self):
        old_content = "foo\nbar\nbaz"
        new_content = "foo\nqux\nbaz"
        diff = compute_file_diff(old_content, new_content, "notes.txt")
        self.assertEqual(diff["stats"]["added"], 1)
        self.assertEqual(diff["stats"]["deleted"], 1)
        types = [l["type"] for l in diff["lines"]]
        self.assertIn("delete", types)
        self.assertIn("add", types)

    def test_diff_empty_to_new(self):
        old_content = ""
        new_content = "line 1\nline 2"
        diff = compute_file_diff(old_content, new_content, "created.txt")
        self.assertEqual(diff["stats"]["added"], 2)
        self.assertEqual(diff["stats"]["deleted"], 0)
        self.assertEqual(len(diff["lines"]), 2)
        self.assertTrue(all(l["type"] == "add" for l in diff["lines"]))


if __name__ == "__main__":
    unittest.main()
