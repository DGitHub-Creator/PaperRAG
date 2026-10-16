from operator import add
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

from pydantic import BaseModel


class IntentSchema(BaseModel):
    """意图分类结构化输出"""
    classification: Literal["in_scope", "out_of_scope"]
    complexity: Literal["simple", "complex"]


class State(TypedDict):
    """Agent 状态字典"""
    messages: Annotated[list, add_messages]
    question_input: dict
    classification_decision: str | None
    trace: Annotated[list, add]
    retrieved_locators: list
    evidence: list
    rag_trace: dict | None
    source_map: dict
