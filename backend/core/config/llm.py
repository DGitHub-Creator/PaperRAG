"""LLM 模型配置。"""

import os

from backend.core.config.paths import ROOT_DIR

VERSION = "0.1.0"
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()

ARK_API_KEY = os.getenv("ARK_API_KEY", "")
MODEL = os.getenv("MODEL", "")
GRADE_MODEL = os.getenv("GRADE_MODEL", "gpt-4.1")
FAST_MODEL = os.getenv("FAST_MODEL", "")
BASE_URL = os.getenv("BASE_URL", "")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", os.getenv("MODEL_PROVIDER", "openai"))
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or ARK_API_KEY
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "") or BASE_URL
LLM_MODEL = os.getenv("LLM_MODEL", "") or MODEL
LLM_GRADE_MODEL = os.getenv("LLM_GRADE_MODEL", "") or GRADE_MODEL

MAX_LLM_CALLS_PER_QUERY = int(os.getenv("MAX_LLM_CALLS_PER_QUERY", "6"))
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
LLM_COST_PER_1K_TOKENS = float(os.getenv("LLM_COST_PER_1K_TOKENS", "0.01"))
MAX_COST_PER_QUERY = float(os.getenv("MAX_COST_PER_QUERY", "0.05"))
