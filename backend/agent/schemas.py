from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class IntentSchema(BaseModel):
    """意图分类结构化输出"""
    classification: Literal["in_scope", "out_of_scope"]
    complexity: Literal["simple", "complex"]


class State(TypedDict):
    """Agent 状态字典"""
    messages: list
    question_input: dict
    classification_decision: Optional[str]
    trace: list
    retrieved_locators: list
    evidence: list
