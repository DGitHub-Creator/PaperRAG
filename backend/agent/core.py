"""单次知识库对话：路由、工具循环、按轮追加与提交后完成事件。"""

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
from backend.core.budget import budget_ok, record_llm_call
from backend.core.logging_config import get_logger
from backend.services.tools import (
    search_knowledge_base,
    set_conversation_history,
    set_rag_step_queue,
)
from backend.schemas.schemas import RagTrace

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
        from backend.core.dependencies import get_milvus_manager
        rows = get_milvus_manager().query_all(output_fields=["filename"])
        names = sorted({row["filename"] for row in rows if row.get("filename")})
        return json.dumps({"filenames": names[:100], "truncated": len(names) > 100}, ensure_ascii=False)

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
        if not budget_ok():
            raise RuntimeError("本轮模型调用预算已耗尽")
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
        rag_context = {"rag_trace": state.get("rag_trace"), "source_map": state.get("source_map", {})}
        for tool_call in getattr(state["messages"][-1], "tool_calls", None) or []:
            name = tool_call["name"]
            try:
                if name == "search_knowledge_base" and any(item.get("step") == name for item in state.get("trace", []) + trace):
                    raise RuntimeError("本轮已执行知识库检索，禁止重复调用")
                observation = tools_by_name[name].invoke({**tool_call, "type": "tool_call"})
            except Exception as e:
                raise RuntimeError(f"工具执行失败: {name}") from e
            result.append(observation)
            if name == "search_knowledge_base":
                trace.append({"step": name, "query": tool_call["args"].get("query", "")})
                # 从工具返回的 artifact 提取来源，不依赖子任务 ContextVar 反传。
                ctx = observation.artifact
                if ctx:
                    rag_context = ctx
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
            "rag_trace": rag_context.get("rag_trace"),
            "source_map": rag_context.get("source_map", {}),
        }

    def should_continue(state: State) -> str:
        tool_calls = getattr(state["messages"][-1], "tool_calls", None)
        if tool_calls:
            if any(tc["name"] in TERMINAL_TOOLS for tc in tool_calls):
                return END
            return "environment"
        return END

    def intent_router(state: State) -> Command[Literal["llm_call", "__end__"]]:
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
                goto="llm_call",
                update={
                    "classification_decision": "in_scope",
                },
            )

        return Command(
            goto=END,
            update={
                "classification_decision": "out_of_scope",
                "messages": [{"role": "assistant", "content": "该问题超出知识库范围，无法回答。"}],
            },
        )

    graph = StateGraph(State)
    graph.add_node("intent_router", intent_router)
    graph.add_node("llm_call", llm_call)
    graph.add_node("environment", tool_node)
    graph.add_edge(START, "intent_router")
    graph.add_conditional_edges("llm_call", should_continue, {"environment": "environment", END: END})
    graph.add_edge("environment", "llm_call")
    return graph.compile(checkpointer=checkpointer)


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
        "rag_trace": None,
        "source_map": {},
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


def _set_history_context(messages: list) -> str:
    """把最近 2 轮 Q&A 摘要写入请求级上下文，供 RAG 检索做历史感知。"""
    pairs = []
    for msg in messages[-4:]:
        if isinstance(msg, HumanMessage):
            pairs.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage) and msg.content:
            pairs.append(f"AI: {str(msg.content)[:500]}")
    history = "\n".join(pairs)
    set_conversation_history(history)
    return history


def _reset_turn() -> None:
    from backend.core.budget import reset_budget
    reset_budget()


def _prepare_input(storage, user_text: str, user_id: str, session_id: str) -> tuple[dict, str]:
    messages = _compact_history(storage.load(user_id, session_id))
    history = _set_history_context(messages)
    messages.append(HumanMessage(content=user_text))
    return _convert_messages_to_agent_input(messages, user_text), history


def _turn_result(result: dict) -> dict:
    source_map = result.get("source_map") or {}
    outcome = extract_outcome(result.get("messages", []), source_map=source_map)
    response = outcome["answer"]
    if not response:
        raise RuntimeError("模型未返回有效回答")
    trace = result.get("rag_trace")
    if trace is not None or source_map or outcome["citations"] or outcome["unsupported"]:
        if trace is None:
            trace = {"tool_used": False, "tool_name": ""}
        trace = RagTrace.model_validate({
            **trace,
            "source_map": source_map,
            "citations": outcome["citations"] + outcome["unsupported"],
        }).model_dump(exclude_none=True)
    return {
        "response": response,
        "rag_trace": trace,
        "source_map": source_map,
        "citations": outcome["citations"],
        "unsupported": outcome["unsupported"],
    }


def run_agent(user_text: str, user_id: str = "default_user", session_id: str = "default_session") -> dict:
    from backend.services.conversation_storage import ConversationStorage

    storage = ConversationStorage()
    _reset_turn()
    agent_input, history = _prepare_input(storage, user_text, user_id, session_id)
    set_conversation_history(history)
    result = build_agent().invoke(agent_input, config={"timeout": LLM_TIMEOUT_SECONDS})
    response = _turn_result(result)
    storage.append_turn(user_id, session_id, user_text, response["response"], response["rag_trace"])
    return response


async def run_agent_stream(user_text: str, user_id: str = "default_user", session_id: str = "default_session"):
    from backend.services.conversation_storage import ConversationStorage

    output_queue: asyncio.Queue = asyncio.Queue(maxsize=128)

    class _RagStepProxy:
        def put_nowait(self, step: dict) -> None:
            output_queue.put_nowait({"type": "rag_step", "step": step})

    async def worker():
        # ContextVar 的写入不会从子任务反传；检索追踪必须通过图状态显式返回。
        set_rag_step_queue(_RagStepProxy())
        try:
            storage = ConversationStorage()
            _reset_turn()
            agent_input, history = await asyncio.to_thread(_prepare_input, storage, user_text, user_id, session_id)
            set_conversation_history(history)
            async with asyncio.timeout(LLM_TIMEOUT_SECONDS):
                result = await build_agent().ainvoke(agent_input)
            response = _turn_result(result)
            await asyncio.to_thread(storage.append_turn, user_id, session_id, user_text, response["response"], response["rag_trace"])
            await output_queue.put({"type": "content", "content": response["response"]})
            await output_queue.put({"type": "citations", "citations": response["citations"], "unsupported": response["unsupported"]})
            if response["rag_trace"] or response["source_map"]:
                await output_queue.put({"type": "trace", "rag_trace": response["rag_trace"], "source_map": response["source_map"]})
            await output_queue.put({"type": "done"})
        except Exception:
            logger.exception("流式对话失败: user=%s, session=%s", user_id, session_id)
            await output_queue.put({"type": "error", "content": "Internal server error"})
        finally:
            set_rag_step_queue(None)
            if not asyncio.current_task().cancelling():
                await output_queue.put(None)

    task = asyncio.create_task(worker())
    try:
        while True:
            event = await output_queue.get()
            if event is None:
                break
            if event["type"] == "done":
                yield "data: [DONE]\n\n"
            else:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    finally:
        if not task.done():
            task.cancel()
        # 正常结束、客户端断开和父任务取消都必须等待子任务收尾。
        await asyncio.gather(task, return_exceptions=True)
