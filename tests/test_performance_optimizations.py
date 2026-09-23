import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from backend.mcp_client import MCPClientService, normalize_tool_arguments
from backend import config
from backend.llm_agent import LLMAgent


class TestPerformanceOptimizations(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        import tempfile, os
        self.temp_dir = tempfile.mkdtemp(prefix="test_perf_ws_")
        self.orig_ws = os.environ.get("WORKSPACE_DIR")
        os.environ["WORKSPACE_DIR"] = self.temp_dir
        self.client_service = MCPClientService(Path(self.temp_dir))
        self.agent = LLMAgent()

    async def asyncTearDown(self):
        import shutil, os
        if self.orig_ws is not None:
            os.environ["WORKSPACE_DIR"] = self.orig_ws
        else:
            os.environ.pop("WORKSPACE_DIR", None)
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    async def test_direct_tool_execution_is_default_and_fast(self):
        """Direct in-process FastMCP execution must be the primary transport and complete in < 100ms."""
        # Call create_folder and create_file directly
        t0 = time.time()
        res = await self.client_service.call_tool("create_folder", {"folder_path": "perf_test_folder"})
        elapsed = time.time() - t0

        self.assertIn("Successfully created", res)
        # Should take less than 150ms (typically 5-15ms), not 1.4s like stdio subprocess
        self.assertLess(elapsed, 0.15, f"Direct tool execution took too long: {elapsed:.3f}s")

        # Cleanup
        del_res = await self.client_service.call_tool("delete_item", {"path": "perf_test_folder", "recursive": True})
        self.assertIn("Successfully deleted", del_res)

    async def test_streaming_token_pacing_is_snappy(self):
        """Streaming generator token pacing should emit tokens rapidly without artificial 3s delays."""
        mcp_tools = await self.client_service.list_tools()
        sample_words = "The quick brown fox jumps over the lazy dog " * 5  # 45 words
        mock_response = MagicMock(function_calls=[], text=sample_words)

        with patch("backend.llm_agent.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_chat = MagicMock()
            mock_chat.send_message.return_value = mock_response
            mock_client.chats.create.return_value = mock_chat
            mock_client_cls.return_value = mock_client

            t0 = time.time()
            events = []
            async for chunk in self.agent._chat_gemini_stream("test message", [], mcp_tools):
                events.append(chunk)
            elapsed = time.time() - t0

            # 45 words with 0.002s sleep should finish in under 0.25s
            self.assertLess(elapsed, 0.25, f"Streaming took {elapsed:.3f}s, expected < 0.25s")
            self.assertTrue(any("event: done" in ev for ev in events))

    def test_default_gemini_model_is_fast_lite(self):
        """GEMINI_MODEL default should be gemini-3.1-flash-lite, the fastest responsive model."""
        with patch.dict("os.environ", {}, clear=False):
            # If not specified in env, default should be gemini-3.1-flash-lite
            if "GEMINI_MODEL" in config.os.environ:
                del config.os.environ["GEMINI_MODEL"]
            model = config.get_gemini_model()
            self.assertEqual(model, "gemini-3.1-flash-lite")

    async def test_fail_fast_on_consumer_suspended_or_auth_error(self):
        """Agent should not stall retrying when receiving a 403 CONSUMER_SUSPENDED error."""
        mock_chat = MagicMock()
        mock_chat.send_message.side_effect = Exception("403 PERMISSION_DENIED: Consumer has been suspended. (CONSUMER_SUSPENDED)")

        t0 = time.time()
        with self.assertRaises(Exception) as ctx:
            await self.agent._send_gemini_message_with_retry(mock_chat, "test message")
        elapsed = time.time() - t0

        # Must fail immediately without sleeping or looping 4 times
        self.assertLess(elapsed, 0.2, f"Fail-fast took {elapsed:.2f}s, expected < 0.2s")
        self.assertIn("CONSUMER_SUSPENDED", str(ctx.exception))

    async def test_quick_retry_on_rate_limit(self):
        """Rate limit retry should not sleep 25 seconds across 4 attempts."""
        mock_chat = MagicMock()
        mock_chat.send_message.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED"),
            MagicMock(text="Success on retry")
        ]

        t0 = time.time()
        res = await self.agent._send_gemini_message_with_retry(mock_chat, "test message")
        elapsed = time.time() - t0

        # Should retry once quickly (<= 1.5s), not wait 2.5s + 5.0s + 7.5s
        self.assertLess(elapsed, 2.0, f"Rate-limit retry took {elapsed:.2f}s, expected < 2.0s")
        self.assertEqual(res.text, "Success on retry")

    def test_candidate_models_priority(self):
        """Candidate models in llm_agent must prioritize gemini-3.1-flash-lite and gemini-3.6-flash."""
        from backend import llm_agent
        # Check source or inspect candidate priority in method
        with open(llm_agent.__file__, "r", encoding="utf-8") as f:
            content = f.read()

        # Both occurrences of candidate_models should place gemini-3.1-flash-lite first or after config
        self.assertIn('"gemini-3.1-flash-lite", "gemini-3.6-flash"', content)


if __name__ == "__main__":
    unittest.main()
