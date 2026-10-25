import unittest
import asyncio
from openai.types.chat import ChatCompletionMessage
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function

from compaction import (
    normalize_message,
    estimate_tokens,
    prune_past_tool_outputs,
    compact_session_history,
)


class TestCompaction(unittest.TestCase):
    def setUp(self):
        self.tool_call = ChatCompletionMessageToolCall(
            id="call_test_123",
            type="function",
            function=Function(name="test_tool", arguments='{"query": "antigravity"}'),
        )
        self.asst_obj = ChatCompletionMessage(
            role="assistant",
            content=None,
            tool_calls=[self.tool_call],
        )

    def test_normalize_message(self):
        # 1. Dict passes through
        d = {"role": "user", "content": "hello"}
        self.assertEqual(normalize_message(d), d)

        # 2. ChatCompletionMessage converted to dict
        normalized = normalize_message(self.asst_obj)
        self.assertIsInstance(normalized, dict)
        self.assertEqual(normalized["role"], "assistant")
        self.assertEqual(len(normalized["tool_calls"]), 1)
        self.assertEqual(normalized["tool_calls"][0]["id"], "call_test_123")

    def test_estimate_tokens_with_chat_completion_message(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "문서를 작성해주세요."},
            self.asst_obj,
            {"role": "tool", "tool_call_id": "call_test_123", "name": "test_tool", "content": "Done."},
        ]
        tokens = estimate_tokens(messages)
        self.assertGreater(tokens, 10)

    def test_prune_past_tool_outputs_with_chat_completion_message(self):
        """
        Verify that prune_past_tool_outputs does not raise AttributeError
        when messages contain ChatCompletionMessage objects from previous tool calls.
        """
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "1차 질문: 이전 작업"},
            self.asst_obj,
            {
                "role": "tool",
                "tool_call_id": "call_test_123",
                "name": "test_tool",
                "content": "A" * 2000,  # exceeds max_content_chars
            },
            {"role": "assistant", "content": "1차 답변 완료"},
            {"role": "user", "content": "2차 질문: pdf문서 만들어줘"},
        ]

        pruned = prune_past_tool_outputs(messages, max_content_chars=500)
        self.assertTrue(pruned)
        # Message at index 2 should now be normalized
        self.assertIsInstance(messages[2], dict)
        # Tool message at index 3 should be truncated
        self.assertLess(len(messages[3]["content"]), 1000)
        self.assertIn("중략", messages[3]["content"])

    def test_compact_session_history_with_chat_completion_message(self):
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "1차 요청"},
            self.asst_obj,
            {"role": "tool", "tool_call_id": "call_test_123", "name": "test_tool", "content": "결과"},
            {"role": "assistant", "content": "1차 완료"},
            {"role": "user", "content": "2차 요청"},
            {"role": "assistant", "content": "2차 진행중"},
            {"role": "user", "content": "3차 요청"},
        ]

        success = asyncio.run(compact_session_history(messages, context_limit=4000, client=None))
        self.assertTrue(success)
        # All messages must now be dicts
        for m in messages:
            self.assertIsInstance(m, dict)
            self.assertIn("role", m)


if __name__ == "__main__":
    unittest.main()
