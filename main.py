"""PaperRAG 入口 —— 直接运行 python main.py 启动服务。"""

import uvicorn

from backend.core.config import APP_ENV

if __name__ == "__main__":
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=8000,
        reload=APP_ENV != "production",
    )
