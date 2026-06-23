"""项目路径配置。"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOAD_DIR = DATA_DIR / "documents"
LOG_DIR = ROOT_DIR / "logs"

MODEL_CACHE_DIR = ROOT_DIR / "models"
HF_HOME = os.getenv("HF_HOME", str(MODEL_CACHE_DIR))

INGESTED_STATE_PATH = DATA_DIR / "ingested.json"
BM25_STATE_PATH = os.getenv("BM25_STATE_PATH", str(DATA_DIR / "bm25_state.json"))


def ensure_runtime_directories() -> None:
    for directory in (DATA_DIR, UPLOAD_DIR):
        directory.mkdir(parents=True, exist_ok=True)
