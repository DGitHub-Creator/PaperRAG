"""Tests for backend.services.tools — contextvars state management and tool guards."""

import asyncio

from backend.services.tools import set_rag_step_queue


class TestRagStepQueue:
    """Tests for RAG step queue injection."""

    def test_set_queue(self):
        """Setting a queue should store it in contextvars."""
        queue = asyncio.Queue()
        set_rag_step_queue(queue)
        from backend.services.tools import _rag_step_queue_var
        assert _rag_step_queue_var.get() is queue

    def test_set_none_clears(self):
        """Setting None should clear the queue."""
        set_rag_step_queue(None)
        from backend.services.tools import _rag_step_queue_var
        assert _rag_step_queue_var.get() is None
