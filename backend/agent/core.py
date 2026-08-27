r"""Document knowledge-base agent (agentic RAG over Milvus store).

Two-layer LangGraph, with the response layer routed by question complexity:

    START -> intent_router --in_scope + simple --> response_agent  --> END
                            \--out_of_scope / empty KB-------------> END

Provides:
  - build_agent(): compile the LangGraph workflow
  - run_agent(): invoke agent with conversation history (sync)
  - run_agent_stream(): invoke agent with streaming output (async)
"""

import asyncio
import json
from typing import Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from backend.core.config import LLM_TIMEOUT_SECONDS
from langgraph.types import Command

from backend.agent.prompts import (
    AGENT_TOOLS_PROMPT,
    agent_system_prompt,
    default_intent_instructions,
    default_kb_description,
    intent_system_prompt,
    intent_user_prompt,
)
from backend.agent.schemas import IntentSchema, State
from backend.agent.verify import extract_outcome
from backend.core.budget import record_llm_call
from backend.core.logging_config import get_logger
from backend.services.tools import (
    get_last_rag_context,
    reset_tool_call_guards,
    search_knowledge_base,
    set_conversation_history,
    set_rag_step_queue,
)

logger = get_logger(__name__)

TERMINAL_TOOLS = {"Answer", "Question"}

# 预算 token 估算：粗略按 4 字符 ≈ 1 token（中英混合场景的经验值）。
_CHARS_PER_TOKEN = 4


def _estimate_tokens(payload) -> int:
    """粗略估算一次 LLM 调用的 token 消耗（输入+输出）。"""
    if isinstance(payload, str):
        return len(payload) // _CHARS_PER_TOKEN
    total = 0
    items = payload if isinstance(payload, (list, tuple)) else [payload]
    for item in items:
        content = item.get("content", "") if isinstance(item, dict) else getattr(item, "content", "")
        if isinstance(content, str):
            total += len(content)
        elif content:
            total += len(str(content))
    return total // _CHARS_PER_TOKEN


def _make_tools():
    from langchain_core.tools import tool

    @tool
    def list_sources() -> str:
        """List all available documents in the knowledge base."""
        return "Sources: [List of documents in knowledge base]"

    @tool
    def Answer(answer: str) -> str:  # noqa: N802
        """Provide your final answer with citations. This is a terminal tool."""
        return answer

    @tool
    def Question(question: str) -> str:  # noqa: N802
        """Ask for clarification. This is a terminal tool."""
        return question

    return [search_knowledge_base, list_sources, Answer, Question]


def build_agent(config=None, checkpointer=None):
    from backend.core.llm import get_chat_model

    llm = get_chat_model(role="agent")
    llm_router = get_chat_model(role="router").with_structured_output(IntentSchema)

    tools = _make_tools()
    tools_by_name = {t.name: t for t in tools}
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")

    system_prompt = agent_system_prompt.format(
        tools_prompt=AGENT_TOOLS_PROMPT,
        kb_description=default_kb_description,
    )

    def llm_call(state: State):
        prompt_messages = [{"role": "system", "content": system_prompt}] + state["messages"]
        record_llm_call(estimated_tokens=_estimate_tokens(prompt_messages))
        return {
            "messages": [
                llm_with_tools.invoke(
                    prompt_messages,
                    config={"timeout": LLM_TIMEOUT_SECONDS},
                )
            ]
        }

    def tool_node(state: State):
        result, trace, locators, evidence = [], [], [], []
        for tool_call in getattr(state["messages"][-1], "tool_calls", None) or []:
            name = tool_call["name"]
            try:
                observation = tools_by_name[name].invoke(tool_call["args"])
            except Exception as e:
                observation = f"Tool '{name}' failed: {e}"
            result.append(
                {"role": "tool", "content": observation, "tool_call_id": tool_call["id"]}
            )
            if name == "search_knowledge_base":
                trace.append({"step": name, "query": tool_call["args"].get("query", "")})
                # 从请求级上下文提取 source_map / 检索块，供引用校验使用
                ctx = get_last_rag_context(clear=False)
                if ctx:
                    source_map = ctx.get("source_map") or {}
                    for label, locator in source_map.items():
                        locators.append({
                            "source_label": label,
                            "filename": locator.get("filename"),
                            "page": locator.get("page"),
                            "chunk_id": locator.get("chunk_id"),
                        })
                    for chunk in (ctx.get("rag_trace") or {}).get("retrieved_chunks") or []:
                        evidence.append({
                            "chunk_id": chunk.get("chunk_id"),
                            "filename": chunk.get("filename"),
                            "page": chunk.get("page_number"),
                            "text": str(chunk.get("text") or "")[:500],
                        })
        return {
            "messages": result,
            "trace": trace,
            "retrieved_locators": locators,
            "evidence": evidence,
        }

    def should_continue(state: State) -> str:
        tool_calls = getattr(state["messages"][-1], "tool_calls", None)
        if tool_calls:
            if any(tc["name"] in TERMINAL_TOOLS for tc in tool_calls):
                return END
            return "environment"
        return END

    def intent_router(state: State) -> Command[Literal["response_agent", "__end__"]]:
        question = state["question_input"].get("question", "")

        router_sys = intent_system_prompt.format(
            kb_description=default_kb_description,
            intent_instructions=default_intent_instructions,
        )

        try:
            record_llm_call(estimated_tokens=_estimate_tokens(question) + 200)
            result = cast(IntentSchema, llm_router.invoke([
                {"role": "system", "content": router_sys},
                {"role": "user", "content": intent_user_prompt.format(question=question)},
            ], config={"timeout": LLM_TIMEOUT_SECONDS}))
            classification = result.classification
        except Exception as e:
            logger.warning("intent router failed: %s", e)
            classification = "in_scope"

        if classification == "in_scope":
            return Command(
                goto="response_agent",
                update={
                    "classification_decision": "in_scope",
                    "messages": [{"role": "user", "content": question}],
                },
            )

        return Command(
            goto=END,
            update={
                "classification_decision": "out_of_scope",
                "messages": [{"role": "assistant", "content": "该问题超出知识库范围，无法回答。"}],
            },
        )

    def response_agent(state: State):
        msgs = state["messages"]
        builder = StateGraph(State)
        builder.add_node("llm_call", llm_call)
        builder.add_node("environment", tool_node)
        builder.add_edge(START, "llm_call")
        builder.add_conditional_edges(
            "llm_call", should_continue, {"environment": "environment", END: END}
        )
        builder.add_edge("environment", "llm_call")
        research_loop = builder.compile()

        out = research_loop.invoke({"messages": msgs})
        return {
            "messages": out.get("messages", [])[len(msgs):],
            "trace": out.get("trace", []),
            "retrieved_locators": out.get("retrieved_locators", []),
            "evidence": out.get("evidence", []),
        }

    overall_workflow = (
        StateGraph(State)
        .add_node("intent_router", intent_router)
        .add_node("response_agent", response_agent)
        .add_edge(START, "intent_router")
    )
    return overall_workflow.compile(checkpointer=checkpointer)


def _convert_messages_to_agent_input(messages: list, user_text: str) -> dict:
    agent_msgs = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            agent_msgs.append({"role": "system", "content": str(msg.content)})
        elif isinstance(msg, HumanMessage):
            agent_msgs.append({"role": "user", "content": str(msg.content)})
        elif isinstance(msg, AIMessage):
            agent_msgs.append({"role": "assistant", "content": str(msg.content)})

    return {
        "question_input": {"question": user_text},
        "messages": agent_msgs,
        "classification_decision": None,
        "trace": [],
        "retrieved_locators": [],
        "evidence": [],
    }


def _compact_history(messages: list, max_messages: int = 50) -> list:
    """超长对话压缩：前 40 条总结为摘要，保留近期消息。"""
    if len(messages) <= max_messages:
        return messages

    from backend.core.llm import get_chat_model

    model = get_chat_model(role="agent")
    old_conversation = "\n".join(
        [f"{'用户' if msg.type == 'human' else 'AI'}: {msg.content}" for msg in messages[:40]]
    )
    record_llm_call(estimated_tokens=_estimate_tokens(old_conversation) + 300)
    summary = model.invoke(
        f"请总结以下对话的关键信息：\n{old_conversation}\n总结（包含用户信息、重要事实、待办事项）：",
        config={"timeout": LLM_TIMEOUT_SECONDS},
    ).content
    return [SystemMessage(content=f"之前的对话摘要：\n{summary}")] + messages[40:]


def _set_history_context(messages: list) -> None:
    """把最近 2 轮 Q&A 摘要写入请求级上下文，供 RAG 检索做历史感知。"""
    pairs = []
    for msg in messages[-4:]:
        if isinstance(msg, HumanMessage):
            pairs.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage) and msg.content:
            pairs.append(f"AI: {str(msg.content)[:500]}")
    set_conversation_history("\n".join(pairs))


def _extract_response(result: dict) -> str:
    if isinstance(result, dict):
        msgs = result.get("messages", [])
        for msg in reversed(msgs):
            content = getattr(msg, "content", "")
            if content:
                return content
    return ""


def run_agent(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
) -> dict:
    from backend.core.budget import reset_budget
    from backend.services.conversation_storage import ConversationStorage

    storage = ConversationStorage()
    agent = build_agent()

    messages = storage.load(user_id, session_id)

    reset_budget()
    get_last_rag_context(clear=True)
    reset_tool_call_guards()

    messages = _compact_history(messages)
    _set_history_context(messages)
    messages.append(HumanMessage(content=user_text))

    agent_input = _convert_messages_to_agent_input(messages, user_text)
    result = agent.invoke(agent_input, config={"configurable": {"thread_id": session_id}, "timeout": LLM_TIMEOUT_SECONDS})

    response_content = _extract_response(result)

    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None
    source_map = rag_context.get("source_map") if rag_context else None

    outcome = extract_outcome(
        result.get("messages", []) if isinstance(result, dict) else [],
        source_map=source_map,
    )

    messages.append(AIMessage(content=response_content))
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)

    return {
        "response": response_content,
        "rag_trace": rag_trace,
        "source_map": source_map,
        "citations": outcome.get("citations", []),
        "unsupported": outcome.get("unsupported", []),
    }


async def run_agent_stream(
    user_text: str,
    user_id: str = "default_user",
    session_id: str = "default_session",
):
    from backend.core.budget import reset_budget
    from backend.services.conversation_storage import ConversationStorage

    storage = ConversationStorage()
    agent = build_agent()

    messages = storage.load(user_id, session_id)

    reset_budget()
    get_last_rag_context(clear=True)
    reset_tool_call_guards()

    output_queue: asyncio.Queue = asyncio.Queue()

    class _RagStepProxy:
        def put_nowait(self, step: dict) -> None:
            output_queue.put_nowait({"type": "rag_step", "step": step})

    set_rag_step_queue(_RagStepProxy())

    messages = _compact_history(messages)
    _set_history_context(messages)
    messages.append(HumanMessage(content=user_text))

    agent_input = _convert_messages_to_agent_input(messages, user_text)

    full_response = ""
    result = {}

    async def _agent_worker():
        nonlocal full_response, result
        try:
            result = await agent.ainvoke(
                agent_input,
                config={"configurable": {"thread_id": session_id}},
            )

            response_content = _extract_response(result)
            full_response = response_content

            await output_queue.put({"type": "content", "content": response_content})
        except Exception as e:
            logger.exception("Agent worker exception")
            await output_queue.put({"type": "error", "content": str(e)})
        finally:
            await output_queue.put(None)

    agent_task = asyncio.create_task(_agent_worker())

    try:
        while True:
            event = await output_queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    except GeneratorExit:
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        raise
    finally:
        set_rag_step_queue(None)
        if not agent_task.done():
            agent_task.cancel()

    rag_context = get_last_rag_context(clear=True)
    rag_trace = rag_context.get("rag_trace") if rag_context else None
    source_map = rag_context.get("source_map") if rag_context else None

    outcome = extract_outcome(
        result.get("messages", []) if isinstance(result, dict) else [],
        source_map=source_map,
    )

    citation_event = {
        "type": "citations",
        "citations": outcome.get("citations", []),
        "unsupported": outcome.get("unsupported", []),
    }
    yield f"data: {json.dumps(citation_event, ensure_ascii=False)}\n\n"

    trace_event = {"type": "trace", "rag_trace": rag_trace}
    if source_map:
        trace_event["source_map"] = source_map
    if rag_trace or source_map:
        yield f"data: {json.dumps(trace_event, ensure_ascii=False)}\n\n"

    yield "data: [DONE]\n\n"

    messages.append(AIMessage(content=full_response))
    extra_message_data = [None] * (len(messages) - 1) + [{"rag_trace": rag_trace}]
    storage.save(user_id, session_id, messages, extra_message_data=extra_message_data)

    logger.info("流式对话完成: user=%s, session=%s, response_len=%d", user_id, session_id, len(full_response))
