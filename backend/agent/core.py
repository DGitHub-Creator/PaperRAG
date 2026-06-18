"""Document knowledge-base agent (agentic RAG over Milvus store).

Two-layer LangGraph, with the response layer routed by question complexity:

    START -> intent_router --in_scope + simple --> response_agent  --> END
                            \--in_scope + complex--> orchestrator   --> END
                            \--out_of_scope / empty KB-------------> END
"""

import logging
from typing import Literal, cast
from langchain.chat_models import init_chat_model
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from backend.agent.schemas import IntentSchema, State
from backend.agent.prompts import (
    intent_system_prompt,
    intent_user_prompt,
    default_intent_instructions,
    default_kb_description,
    agent_system_prompt,
    AGENT_TOOLS_PROMPT,
)

logger = logging.getLogger(__name__)

TERMINAL_TOOLS = {"Answer", "Question"}


def get_retriever():
    """获取 Milvus 检索器 - 使用现有的 PaperRAG 检索逻辑"""
    from backend.rag.rag_utils import retrieve_documents
    return retrieve_documents


def make_retrieval_tools(retrieve_fn, top_k=5):
    """创建检索工具"""
    from langchain_core.tools import tool
    
    @tool
    def search_docs(query: str) -> str:
        """Search the knowledge base for relevant document chunks."""
        results = retrieve_fn(query, top_k=top_k)
        docs = results.get("docs", [])
        if not docs:
            return "No relevant documents found."
        
        output = []
        for i, doc in enumerate(docs, 1):
            source = doc.get("filename", "Unknown")
            page = doc.get("page_number", "N/A")
            text = doc.get("text", "")
            output.append(f"[{i}] locator: {source} (p.{page})  (relevance {doc.get('score', 0):.2f})\n{text}")
        return "\n\n".join(output)
    
    @tool
    def list_sources() -> str:
        """List all available documents in the knowledge base."""
        # 这里需要连接到 Milvus 获取所有文档列表
        return "Sources: [List of documents in knowledge base]"
    
    @tool
    def Answer(answer: str) -> str:
        """Provide your final answer with citations. This is a terminal tool."""
        return answer
    
    @tool
    def Question(question: str) -> str:
        """Ask for clarification. This is a terminal tool."""
        return question
    
    return [search_docs, list_sources, Answer, Question]


def build_agent(config=None, checkpointer=None):
    """构建 Agent 图"""
    from backend.core.config import LLM_MODEL
    
    llm = init_chat_model(LLM_MODEL, temperature=0.0)
    llm_router = llm.with_structured_output(IntentSchema)
    
    retrieve_fn = get_retriever()
    tools = make_retrieval_tools(retrieve_fn)
    tools_by_name = {tool.name: tool for tool in tools}
    llm_with_tools = llm.bind_tools(tools, tool_choice="any")
    
    system_prompt = agent_system_prompt.format(
        tools_prompt=AGENT_TOOLS_PROMPT,
        kb_description=default_kb_description
    )
    
    def llm_call(state: State):
        return {
            "messages": [
                llm_with_tools.invoke(
                    [{"role": "system", "content": system_prompt}] + state["messages"]
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
            if name == "search_docs":
                trace.append({"step": name, "query": tool_call["args"].get("query", "")})
        return {"messages": result, "trace": trace, "retrieved_locators": locators, "evidence": evidence}
    
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
            result = cast(IntentSchema, llm_router.invoke([
                {"role": "system", "content": router_sys},
                {"role": "user", "content": intent_user_prompt.format(question=question)}
            ]))
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
        builder.add_conditional_edges("llm_call", should_continue, {"environment": "environment", END: END})
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
