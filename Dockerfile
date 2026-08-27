# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────
# PaperRAG 多阶段构建
#
# Targets:
#   backend — Python API 服务（含前端 dist 作为兜底静态资源）
#   nginx   — 静态资源 + 反向代理（生产推荐入口）
#
# 构建:
#   docker build --target backend -t paperrag-backend .
#   docker build --target nginx   -t paperrag-nginx   .
# ──────────────────────────────────────────────────────────────────────

# ── Stage 1: 前端构建（Vite → dist/）──────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# 先装依赖（利用层缓存，仅 lockfile 变化时重建）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ── Stage 2: backend 运行时 ───────────────────────────────────────────
FROM python:3.12-slim AS backend
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# uv 用于从 lockfile 可复现安装依赖
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# 先装依赖（仅 pyproject/lock 变化时重建该层）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# 复制源码与运行时资源
COPY backend/ ./backend/
COPY main.py alembic.ini ./
COPY alembic/ ./alembic/
COPY scripts/ ./scripts/
# 前端 dist 作为后端直连部署时的兜底静态资源（nginx 模式下不依赖）
COPY --from=frontend-builder /build/dist ./frontend/dist

# 非 root 用户运行
RUN useradd --create-home --uid 1000 paperrag \
    && mkdir -p /app/data /app/logs /app/models \
    && chown -R paperrag:paperrag /app
USER paperrag

ENV PATH="/app/.venv/bin:$PATH" \
    HF_HOME=/app/models \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 单 worker 起步：嵌入模型常驻内存 + 进程内状态（限流/统计）
# 多副本扩展请通过 compose replicas / k8s，而非增加 worker 数
CMD ["uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

# ── Stage 3: nginx 运行时（静态资源 + 反向代理）───────────────────────
FROM nginx:alpine AS nginx

COPY --from=frontend-builder /build/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O /dev/null http://localhost/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
