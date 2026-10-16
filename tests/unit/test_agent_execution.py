import asyncio
import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from backend.agent import core
from backend.agent.schemas import IntentSchema
from backend.core.budget import get_budget_status, record_llm_call, reset_budget
from backend.services import conversation_storage


def graph_with_retrieval(monkeypatch):
    @tool("search_knowledge_base", response_format="content_and_artifact")
    def search(query: str) -> tuple[str, dict]:
        """测试中的确定性检索，不调用外部模型或数据库。"""
        return "retrieved evidence", {
            "rag_trace": {"tool_used": True, "tool_name": "search_knowledge_base", "retrieved_chunks": [{"filename": "paper.pdf", "text": "evidence"}]},
            "source_map": {"Source 1": {"filename": "paper.pdf", "chunk_id": "chunk"}},
        }

    model = MagicMock()
    model.bind_tools.return_value = model
    model.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "search_knowledge_base", "args": {"query": "question"}, "id": "search"}]),
        AIMessage(content="", tool_calls=[{"name": "Answer", "args": {"answer": "answer [Source 1]"}, "id": "answer"}]),
    ]
    router = MagicMock()
    router.with_structured_output.return_value = router
    router.invoke.return_value = IntentSchema(classification="in_scope", complexity="simple")
    monkeypatch.setattr("backend.core.llm.get_chat_model", lambda role: router if role == "router" else model)
    monkeypatch.setattr(core, "_make_tools", lambda: [search])
    return core.build_agent(), model


def test_actual_graph_preserves_history_tool_result_trace_and_terminal_answer(monkeypatch):
    graph, model = graph_with_retrieval(monkeypatch)
    reset_budget()
    result = graph.invoke(core._convert_messages_to_agent_input([HumanMessage(content="old"), HumanMessage(content="new")], "new"))
    assert [message.content for message in result["messages"][:2]] == ["old", "new"]
    assert len(result["messages"]) == 5
    assert result["messages"][3].type == "tool"
    assert result["source_map"]["Source 1"]["chunk_id"] == "chunk"
    assert core._turn_result(result)["response"] == "answer [Source 1]"
    assert core._turn_result(result)["citations"][0]["chunk_id"] == "chunk"
    assert get_budget_status()["call_count"] == 3
    assert len(model.invoke.call_args_list[1].args[0]) == 5


def test_non_retrieval_tool_does_not_erase_previous_sources(monkeypatch):
    graph, model = graph_with_retrieval(monkeypatch)
    model.invoke.side_effect = [
        AIMessage(content="", tool_calls=[{"name": "search_knowledge_base", "args": {"query": "q"}, "id": "search"}]),
        AIMessage(content="answer [Source 1]"),
    ]
    reset_budget()
    result = graph.invoke(core._convert_messages_to_agent_input([HumanMessage(content="new")], "new"))
    # 直接再次经过工具节点，模拟其他工具轮次；没有新检索不能覆盖已有来源。
    previous = dict(result)
    previous["messages"] = [AIMessage(content="", tool_calls=[])]
    update = graph.nodes["environment"].invoke(previous)
    assert update["source_map"] == result["source_map"]
    assert update["rag_trace"] == result["rag_trace"]


@pytest.mark.asyncio
async def test_stream_commits_before_done_and_keeps_trace(monkeypatch):
    graph, _ = graph_with_retrieval(monkeypatch)
    storage = MagicMock()
    storage.load.return_value = [HumanMessage(content="old")]
    monkeypatch.setattr(conversation_storage, "ConversationStorage", lambda: storage)
    monkeypatch.setattr(core, "build_agent", lambda: graph)
    events = []
    async for event in core.run_agent_stream("new", "alice", "session"):
        if event == "data: [DONE]\n\n":
            storage.append_turn.assert_called_once()
        events.append(event)
    assert events[-1] == "data: [DONE]\n\n"
    assert any('"type": "trace"' in event for event in events)
    assert any('"supported": true' in event for event in events)
    saved = storage.append_turn.call_args.args
    assert saved[:4] == ("alice", "session", "new", "answer [Source 1]")
    assert saved[4]["tool_used"] is True
    assert saved[4]["source_map"]["Source 1"]["chunk_id"] == "chunk"
    assert saved[4]["citations"][0]["supported"] is True
    storage.save.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["model", "storage"])
async def test_stream_failure_has_one_error_no_done_or_partial_save(monkeypatch, failure):
    storage = MagicMock()
    storage.load.return_value = []
    graph = MagicMock()

    async def invoke(_):
        if failure == "model":
            raise RuntimeError("secret-dsn")
        return {"messages": [AIMessage(content="answer")]}

    graph.ainvoke = invoke
    if failure == "storage":
        storage.append_turn.side_effect = RuntimeError("secret-dsn")
    monkeypatch.setattr(conversation_storage, "ConversationStorage", lambda: storage)
    monkeypatch.setattr(core, "build_agent", lambda: graph)
    events = [event async for event in core.run_agent_stream("new", "alice", "session")]
    assert len(events) == 1
    assert json.loads(events[0][6:])["type"] == "error"
    assert "secret-dsn" not in events[0]
    storage.save.assert_not_called()
    if failure == "model":
        storage.append_turn.assert_not_called()


@pytest.mark.asyncio
async def test_request_budget_is_shared_with_threads_but_isolated_between_requests():
    async def request(tokens):
        reset_budget()
        await asyncio.to_thread(record_llm_call, tokens)
        await asyncio.create_task(asyncio.to_thread(record_llm_call, tokens))
        return get_budget_status()

    first, second = await asyncio.gather(request(10), request(20))
    assert (first["call_count"], first["estimated_tokens"]) == (2, 20)
    assert (second["call_count"], second["estimated_tokens"]) == (2, 40)
