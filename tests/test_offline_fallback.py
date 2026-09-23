"""
Unit and integration tests for Network Error Interception and Local Offline Fallback.
Tests:
1. Network error detection helper (is_network_error).
2. Offline intent parser (parse_offline_intent).
3. Offline execution for folder creation, file creation, reading, listing, and deletion confirmation.
4. Clean conversational response when offline for non-filesystem messages (e.g. 'heyy!').
5. SSE streaming handler behavior during simulated network outage.
"""

import asyncio
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from backend.llm_agent import LLMAgent, PENDING_CONFIRMATIONS
from backend.offline_handler import is_network_error, parse_offline_intent, handle_offline_request


class TestOfflineHandlerHelpers(unittest.TestCase):
    """Tests the network error detection and intent parsing logic."""

    def test_is_network_error_detection(self):
        gai_err = socket.gaierror(11001, "getaddrinfo failed")
        self.assertTrue(is_network_error(gai_err))

        err_with_text = Exception("Failed to connect: [Errno 11001] getaddrinfo failed")
        self.assertTrue(is_network_error(err_with_text))

        dns_err = Exception("socket.gaierror: [Errno -3] Temporary failure in name resolution")
        self.assertTrue(is_network_error(dns_err))

        regular_err = ValueError("Invalid argument")
        self.assertFalse(is_network_error(regular_err))

    def test_parse_create_single_folder(self):
        intent = parse_offline_intent("create a folder called Prerak")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "create_folder")
        self.assertEqual(intent["targets"], ["Prerak"])

    def test_parse_create_multiple_folders(self):
        intent = parse_offline_intent("make 3 folders Prerak, Utsav and Umang")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "create_folder")
        self.assertEqual(set(intent["targets"]), {"Prerak", "Utsav", "Umang"})

    def test_parse_create_file(self):
        intent = parse_offline_intent("create a file named notes.txt with content 'Buy groceries'")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "create_file")
        self.assertEqual(intent["file_path"], "notes.txt")
        self.assertEqual(intent["content"], "Buy groceries")

    def test_parse_read_file(self):
        intent = parse_offline_intent("read file notes.txt")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "read_file")
        self.assertEqual(intent["file_path"], "notes.txt")

    def test_parse_list_folder(self):
        for phrase in ["list files", "ls", "dir", "show workspace"]:
            intent = parse_offline_intent(phrase)
            self.assertIsNotNone(intent, f"Failed to parse '{phrase}'")
            self.assertEqual(intent["action"], "list_folder")

    def test_parse_delete_item(self):
        intent = parse_offline_intent("delete folder Prerak")
        self.assertIsNotNone(intent)
        self.assertEqual(intent["action"], "delete_item")
        self.assertEqual(intent["targets"], ["Prerak"])

    def test_parse_conversational_none(self):
        for phrase in ["heyy!", "hello there", "how are you?", "what is the capital of France?"]:
            intent = parse_offline_intent(phrase)
            self.assertIsNone(intent, f"Conversational phrase '{phrase}' should not parse as filesystem intent")


class TestOfflineAgentExecution(unittest.IsolatedAsyncioTestCase):
    """Tests agent execution when network/DNS fails."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="offline_test_ws_")
        self.workspace = Path(self.test_dir).resolve()
        self.orig_ws = os.environ.get("WORKSPACE_DIR")
        os.environ["WORKSPACE_DIR"] = str(self.workspace)
        PENDING_CONFIRMATIONS.clear()
        self.agent = LLMAgent()

    def tearDown(self):
        PENDING_CONFIRMATIONS.clear()
        if self.orig_ws:
            os.environ["WORKSPACE_DIR"] = self.orig_ws
        else:
            os.environ.pop("WORKSPACE_DIR", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_create_folder_execution(self, mock_send):
        # Simulate [Errno 11001] getaddrinfo failed
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")

        res = await self.agent.chat("create a folder called Prerak", [])
        folder = self.workspace / "Prerak"
        self.assertTrue(folder.is_dir(), "Folder 'Prerak' should have been created locally offline")
        self.assertIn("Offline Execution", res.get("reply", ""))
        self.assertFalse(res.get("requires_confirmation"))

    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_conversational_fallback(self, mock_send):
        # Simulate network error on greeting
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")

        res = await self.agent.chat("heyy!", [])
        reply = res.get("reply", "")
        self.assertNotIn("Errno 11001", reply)
        self.assertIn("Internet Connection", reply)
        self.assertFalse(res.get("requires_confirmation"))

    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_stream_create_folder(self, mock_send):
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")

        events = []
        async for chunk in self.agent.chat_stream("create a folder called Prerak", []):
            events.append(chunk)

        full_stream = "".join(events)
        self.assertNotIn("Errno 11001", full_stream)
        self.assertIn("event: done", full_stream)
        self.assertTrue((self.workspace / "Prerak").is_dir())


    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_create_multiple_folders(self, mock_send):
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")
        res = await self.agent.chat("make 3 folder 1. Prerak 2. Utsav 3. Umang", [])
        self.assertTrue((self.workspace / "Prerak").is_dir())
        self.assertTrue((self.workspace / "Utsav").is_dir())
        self.assertTrue((self.workspace / "Umang").is_dir())
        self.assertIn("Offline Execution", res.get("reply", ""))

    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_delete_confirmation_gate(self, mock_send):
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")
        target_file = self.workspace / "test_delete.txt"
        target_file.write_text("temporary content", encoding="utf-8")
        self.assertTrue(target_file.exists())

        res = await self.agent.chat("delete file test_delete.txt", [])
        self.assertTrue(res.get("requires_confirmation"), "Offline delete must require confirmation")
        self.assertTrue(target_file.exists(), "File must not be deleted before confirmation")
        conf = res.get("confirmation")
        self.assertIsNotNone(conf)

        # Confirm deletion
        resolve_res = await self.agent.resolve_confirmation(conf["id"], confirmed=True)
        self.assertIn("Confirmed", resolve_res.get("reply", ""))
        self.assertFalse(target_file.exists(), "File should be deleted after confirmation")

    @patch("backend.llm_agent.LLMAgent._send_gemini_message_with_retry")
    async def test_offline_create_and_read_file(self, mock_send):
        mock_send.side_effect = socket.gaierror(11001, "getaddrinfo failed")
        create_res = await self.agent.chat("create a file called offline_demo.txt with content 'MCP works offline'", [])
        file_path = self.workspace / "offline_demo.txt"
        self.assertTrue(file_path.is_file())
        self.assertIn("MCP works offline", file_path.read_text(encoding="utf-8"))

        read_res = await self.agent.chat("read file offline_demo.txt", [])
        self.assertIn("MCP works offline", read_res.get("reply", ""))


if __name__ == "__main__":
    unittest.main()
