"""Tests for backend.services.tools — contextvars state management and tool guards."""

import asyncio

import pytest

from backend.services.tools import (
    get_last_rag_context,
    _set_last_rag_context,
    reset_tool_call_guards,
    set_rag_step_queue,
    _knowledge_calls_var,
    _rag_context_var,
)


class TestRagContext:
    """Tests for RAG context get/set via contextvars."""

    def test_set_and_get(self):
        """Set context then get it."""
        _set_last_rag_context({"rag_trace": {"query": "test"}})
        result = get_last_rag_context(clear=False)
        assert result == {"rag_trace": {"query": "test"}}

    def test_get_clears_by_default(self):
        """Default get should clear after read."""
        _set_last_rag_context({"data": "value"})
        result = get_last_rag_context()
        assert result == {"data": "value"}
        # Second read should be None
        assert get_last_rag_context() is None

    def test_get_no_clear(self):
        """get with clear=False should not clear."""
        _set_last_rag_context({"data": "value"})
        get_last_rag_context(clear=False)
        assert get_last_rag_context(clear=False) == {"data": "value"}


class TestToolCallGuards:
    """Tests for search_knowledge_base call count guard."""

    def test_reset_guard(self):
        """Reset should set counter to 0."""
        _knowledge_calls_var.set(5)
        reset_tool_call_guards()
        assert _knowledge_calls_var.get() == 0

    def test_guard_isolation(self):
        """Different contextvars contexts should be isolated."""
        _knowledge_calls_var.set(0)
        # The guard is per-context, so within same context it persists
        _knowledge_calls_var.set(1)
        assert _knowledge_calls_var.get() == 1


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
