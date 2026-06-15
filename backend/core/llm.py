"""LLM Provider 抽象 —— 统一的 ChatModel 获取接口。

所有模块通过 get_chat_model(role) 获取 LLM 实例，
config.py 中的 LLM_PROVIDER / LLM_MODEL / LLM_API_KEY / LLM_BASE_URL
决定实际的模型和连接参数。

支持的 role:
  - "grade":    相关性评分模型（LLM_GRADE_MODEL，温度 0）
  - "router":   查询重写策略路由模型（LLM_MODEL，温度 0）
  - "stepback": 查询重写/退步问题/HyDE 生成模型（LLM_MODEL，温度 0.2）
  - "agent":    对话 Agent 模型（LLM_MODEL，温度 0.3）
"""

from langchain.chat_models import init_chat_model

from backend.core.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_GRADE_MODEL,
    LLM_MODEL,
    LLM_PROVIDER,
)
from backend.core.logging_config import get_logger

logger = get_logger(__name__)


def get_chat_model(role: str = "agent"):
    """获取 LLM 实例，根据 role 选择不同模型和温度。

    Args:
        role: 模型用途，决定使用的模型名和温度参数。

    Returns:
        ChatModel 实例。当模型名或 API Key 缺失时，
        返回 ConfigurableModel（延迟到调用时才解析），
        与旧版 init_chat_model 行为一致。
    """
    temperature_map = {
        "grade": 0,
        "router": 0,
        "stepback": 0.2,
        "agent": 0.3,
    }
    model_map = {
        "grade": LLM_GRADE_MODEL,
    }
    temp = temperature_map.get(role, 0.3)
    model_name = model_map.get(role, LLM_MODEL)

    kwargs = dict(
        model=model_name,
        model_provider=LLM_PROVIDER,
        api_key=LLM_API_KEY,
        temperature=temp,
        stream_usage=True,
    )
    if LLM_BASE_URL:
        kwargs["base_url"] = LLM_BASE_URL

    return init_chat_model(**kwargs)
