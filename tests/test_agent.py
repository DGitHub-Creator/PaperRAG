"""Tests for the Agent module."""

import pytest
from unittest.mock import MagicMock, patch


class TestSchemas:
    """Test Agent schemas."""

    def test_intent_schema_in_scope(self):
        from backend.agent.schemas import IntentSchema
        schema = IntentSchema(classification="in_scope", complexity="simple")
        assert schema.classification == "in_scope"
        assert schema.complexity == "simple"

    def test_intent_schema_out_of_scope(self):
        from backend.agent.schemas import IntentSchema
        schema = IntentSchema(classification="out_of_scope", complexity="complex")
        assert schema.classification == "out_of_scope"
        assert schema.complexity == "complex"


class TestPrompts:
    """Test Agent prompts."""

    def test_intent_system_prompt_format(self):
        from backend.agent.prompts import intent_system_prompt, default_intent_instructions, default_kb_description
        formatted = intent_system_prompt.format(
            kb_description=default_kb_description,
            intent_instructions=default_intent_instructions
        )
        assert "in_scope" in formatted
        assert "out_of_scope" in formatted

    def test_agent_system_prompt_format(self):
        from backend.agent.prompts import agent_system_prompt, AGENT_TOOLS_PROMPT, default_kb_description
        formatted = agent_system_prompt.format(
            tools_prompt=AGENT_TOOLS_PROMPT,
            kb_description=default_kb_description
        )
        assert "search_docs" in formatted
        assert "Answer" in formatted
