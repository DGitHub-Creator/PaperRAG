"""
上传任务进度管理模块。

本模块提供线程安全的上传/删除/批量导入任务状态容器，用于：
  1. 跟踪文档上传和向量化入库的每个阶段进度。
  2. 跟踪文档删除的每个阶段进度。
  3. 跟踪增量批量导入的每个阶段进度。

设计说明：
  - UploadJobManager: 使用进程内存保存任务状态，适合单进程开发部署。
  - RedisJobManager: 使用 Redis 保存任务状态，支持多 worker 和服务重启恢复。
    通过 USE_REDIS_JOB_MANAGER 环境变量切换（默认 false，使用 UploadJobManager）。
  - UploadJobManager 通过 threading.Lock 确保线程安全。
  - RedisJobManager 通过 Redis 单命令原子性确保线程安全。
  - 所有读写操作均返回 deepcopy，防止外部意外修改内部状态。

预定义步骤模板：
  - DEFAULT_STEPS: 单文件上传流程（上传 -> 清理 -> 解析 -> 父块入库 -> 向量入库）
  - DELETE_STEPS: 单文件删除流程（准备 -> BM25 同步 -> 向量删除 -> 父块删除）
  - INGEST_STEPS: 批量导入流程（扫描 -> 解析 -> 父块入库 -> 向量入库 -> BM25 重建）
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import uuid4

import redis

from backend.core.config import REDIS_URL, USE_REDIS_JOB_MANAGER
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 类型别名 ────────────────────────────────────────────────────────

StepStatus = Literal["pending", "running", "completed", "failed"]
"""步骤状态：pending-等待 / running-执行中 / completed-已完成 / failed-失败"""

JobStatus = Literal["pending", "running", "completed", "failed"]
"""任务状态：pending-等待 / running-执行中 / completed-已完成 / failed-失败"""

# ── 预定义步骤模板 ──────────────────────────────────────────────────

DEFAULT_STEPS = [
    ("upload", "文档上传"),
    ("cleanup", "清理旧版本"),
    ("parse", "解析与分块"),
    ("parent_store", "父级分块入库"),
    ("vector_store", "向量化入库"),
]
"""单文件上传的标准处理步骤模板。"""

DELETE_STEPS = [
    ("prepare", "准备删除"),
    ("bm25", "同步 BM25 统计"),
    ("milvus", "删除向量数据"),
    ("parent_store", "删除父级分块"),
]
"""单文件删除的标准处理步骤模板。"""

INGEST_STEPS = [
    ("scan", "扫描文件变更"),
    ("parse", "解析与学术清洗"),
    ("parent_store", "父级分块入库"),
    ("vector_store", "向量化入库"),
    ("bm25", "重建 BM25 索引"),
]
"""批量增量导入的标准处理步骤模板。"""


def _now_iso() -> str:
    """获取当前 UTC 时间的 ISO 8601 格式字符串。

    Returns:
        格式为 "YYYY-MM-DDTHH:MM:SS+00:00" 的时间字符串。
    """
    return datetime.now(UTC).isoformat()


class UploadJobManager:
    """线程安全的上传任务状态容器。

    管理任务的全生命周期：
      - create_job: 创建新任务及步骤模板。
      - update_step: 更新指定步骤的进度（百分比、状态、消息）。
      - complete_step: 将指定步骤标记为完成（百分比 100%）。
      - complete_job: 将所有未失败步骤标记为完成，任务整体标记为完成。
      - fail_job: 将指定步骤和任务整体标记为失败。
      - get_job: 获取单个任务快照。
      - list_jobs: 列出全部任务快照。

    线程安全：所有读写操作由 self._lock 保护，返回 deepcopy。
    """

    def __init__(self):
        """初始化任务管理器。"""
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def create_job(
        self,
        filename: str,
        *,
        steps: list[tuple[str, str]] | None = None,
        current_step: str = "upload",
        message: str = "等待上传",
        completion_step: str = "vector_store",
    ) -> dict:
        """创建一个新的上传/处理任务。

        Args:
            filename: 文件名标识。
            steps: 步骤模板列表，每项为 (key, label) 元组。
                   默认使用 DEFAULT_STEPS。
            current_step: 初始当前步骤键。
            message: 初始状态消息。
            completion_step: 完成步骤键，用于 complete_job 时确定当前步骤显示。

        Returns:
            dict: 新创建的任务快照（deepcopy）。
        """
        steps = steps or DEFAULT_STEPS
        job_id = uuid4().hex
        now = _now_iso()
        job = {
            "job_id": job_id,
            "filename": filename,
            "status": "pending",
            "current_step": current_step,
            "message": message,
            # 完成节点用于区分上传和删除，避免 complete_job 写死最后一步
            "completion_step": completion_step,
            "total_chunks": 0,
            "processed_chunks": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "steps": [
                {
                    "key": key,
                    "label": label,
                    "percent": 0,
                    "status": "pending",
                    "message": "",
                }
                for key, label in steps
            ],
        }
        with self._lock:
            self._jobs[job_id] = job
            logger.debug("任务已创建: job_id=%s, filename=%s", job_id, filename)
            return deepcopy(job)

    def get_job(self, job_id: str) -> dict | None:
        """获取指定任务的状态快照。

        Args:
            job_id: 任务 ID。

        Returns:
            任务字典的 deepcopy，不存在则返回 None。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def update_step(
        self,
        job_id: str,
        step_key: str,
        percent: int,
        status: StepStatus = "running",
        message: str = "",
        *,
        total_chunks: int | None = None,
        processed_chunks: int | None = None,
    ) -> dict | None:
        """更新任务中指定步骤的进度信息。

        Args:
            job_id: 任务 ID。
            step_key: 步骤键（如 "parse", "vector_store"）。
            percent: 进度百分比（0-100），自动 clamp。
            status: 步骤状态，默认 "running"。
            message: 步骤状态描述消息。
            total_chunks: 可选的总体分块数。
            processed_chunks: 可选的已处理分块数。

        Returns:
            更新后的任务快照，任务或步骤不存在则返回 None。
        """
        percent = max(0, min(100, int(percent)))
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            step = self._find_step(job, step_key)
            if not step:
                return None

            step["percent"] = percent
            step["status"] = status
            step["message"] = message
            job["status"] = "failed" if status == "failed" else "running"
            job["current_step"] = step_key
            job["message"] = message
            job["updated_at"] = _now_iso()

            if total_chunks is not None:
                job["total_chunks"] = int(total_chunks)
            if processed_chunks is not None:
                job["processed_chunks"] = int(processed_chunks)

            logger.debug(
                "步骤更新: job_id=%s, step=%s, percent=%d, status=%s",
                job_id, step_key, percent, status,
            )
            return deepcopy(job)

    def complete_step(self, job_id: str, step_key: str, message: str = "") -> dict | None:
        """将指定步骤标记为完成（百分比设为 100%，状态设为 completed）。

        Args:
            job_id: 任务 ID。
            step_key: 步骤键。
            message: 完成描述消息。

        Returns:
            更新后的任务快照。
        """
        return self.update_step(job_id, step_key, 100, "completed", message)

    def complete_job(self, job_id: str, message: str = "文档入库完成") -> dict | None:
        """将任务标记为完成。

        所有非失败步骤均设为 100% 完成，任务整体状态设为 completed。

        Args:
            job_id: 任务 ID。
            message: 任务完成描述消息。

        Returns:
            更新后的任务快照。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            for step in job["steps"]:
                if step["status"] != "failed":
                    step["percent"] = 100
                    step["status"] = "completed"
            job["status"] = "completed"
            job["current_step"] = job.get("completion_step") or job["current_step"]
            job["message"] = message
            job["error"] = None
            job["updated_at"] = _now_iso()

            logger.info("任务完成: job_id=%s, filename=%s", job_id, job.get("filename", ""))
            return deepcopy(job)

    def fail_job(self, job_id: str, step_key: str, error: str) -> dict | None:
        """将任务标记为失败。

        指定步骤和任务整体均设为 failed 状态，并记录错误信息。

        Args:
            job_id: 任务 ID。
            step_key: 发生失败的步骤键。
            error: 错误描述信息。

        Returns:
            更新后的任务快照。
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            step = self._find_step(job, step_key)
            if step:
                step["status"] = "failed"
                step["message"] = error
            job["status"] = "failed"
            job["current_step"] = step_key
            job["message"] = error
            job["error"] = error
            job["updated_at"] = _now_iso()

            logger.error("任务失败: job_id=%s, step=%s, error=%s", job_id, step_key, error)
            return deepcopy(job)

    def list_jobs(self) -> list[dict]:
        """获取所有任务的快照列表。

        Returns:
            所有任务字典的 deepcopy 列表。
        """
        with self._lock:
            return [deepcopy(job) for job in self._jobs.values()]

    @staticmethod
    def _find_step(job: dict, step_key: str) -> dict | None:
        """在任务中按键查找步骤。

        Args:
            job: 任务字典。
            step_key: 步骤键。

        Returns:
            匹配的步骤字典，未找到则返回 None。
        """
        for step in job["steps"]:
            if step["key"] == step_key:
                return step
        return None


class RedisJobManager:
    """基于 Redis 的任务状态管理器（支持多 worker / 服务重启恢复）。

    接口与 UploadJobManager 完全兼容，可无缝切换。
    使用 Redis HASH 存储任务数据，TTL 24 小时自动清理。
    键格式: paperrag:job:{job_id} → {field: value}
    """

    _REDIS_PREFIX = "paperrag:job:"
    _REDIS_TTL = 86400

    def __init__(self):
        self._redis: redis.Redis | None = None

    def _get_client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    def _key(self, job_id: str) -> str:
        return f"{self._REDIS_PREFIX}{job_id}"

    @staticmethod
    def _job_dict(job_id: str, filename: str, steps: list[tuple[str, str]],
                  current_step: str, message: str, completion_step: str) -> dict:
        now = datetime.now(UTC).isoformat()
        return {
            "job_id": job_id,
            "filename": filename,
            "status": "pending",
            "current_step": current_step,
            "message": message,
            "completion_step": completion_step,
            "total_chunks": 0,
            "processed_chunks": 0,
            "error": None,
            "created_at": now,
            "updated_at": now,
            "steps": [
                {"key": k, "label": lbl, "percent": 0, "status": "pending", "message": ""}
                for k, lbl in steps
            ],
        }

    def create_job(self, filename: str, *,
                   steps: list[tuple[str, str]] | None = None,
                   current_step: str = "upload",
                   message: str = "等待上传",
                   completion_step: str = "vector_store") -> dict:
        steps = steps or DEFAULT_STEPS
        job_id = uuid4().hex
        job = self._job_dict(job_id, filename, steps, current_step, message, completion_step)
        r = self._get_client()
        r.hset(self._key(job_id), mapping=job)
        r.expire(self._key(job_id), self._REDIS_TTL)
        logger.debug("Redis 任务已创建: job_id=%s, filename=%s", job_id, filename)
        return deepcopy(job)

    def get_job(self, job_id: str) -> dict | None:
        r = self._get_client()
        raw = r.hgetall(self._key(job_id))
        if not raw:
            return None
        raw["steps"] = json.loads(raw.get("steps", "[]"))
        raw["total_chunks"] = int(raw.get("total_chunks", 0))
        raw["processed_chunks"] = int(raw.get("processed_chunks", 0))
        return deepcopy(raw)

    def update_step(self, job_id: str, step_key: str,
                    percent: int, status: StepStatus = "running",
                    message: str = "", *,
                    total_chunks: int | None = None,
                    processed_chunks: int | None = None) -> dict | None:
        percent = max(0, min(100, int(percent)))
        r = self._get_client()
        key = self._key(job_id)
        raw = r.hgetall(key)
        if not raw:
            return None
        steps: list[dict] = json.loads(raw.get("steps", "[]"))
        step = next((s for s in steps if s["key"] == step_key), None)
        if not step:
            return None
        step["percent"] = percent
        step["status"] = status
        step["message"] = message
        raw["status"] = "failed" if status == "failed" else "running"
        raw["current_step"] = step_key
        raw["message"] = message
        raw["updated_at"] = datetime.now(UTC).isoformat()
        if total_chunks is not None:
            raw["total_chunks"] = str(int(total_chunks))
        if processed_chunks is not None:
            raw["processed_chunks"] = str(int(processed_chunks))
        raw["steps"] = json.dumps(steps, ensure_ascii=False)
        r.hset(key, mapping=raw)
        return self.get_job(job_id)

    def complete_step(self, job_id: str, step_key: str, message: str = "") -> dict | None:
        return self.update_step(job_id, step_key, 100, "completed", message)

    def complete_job(self, job_id: str, message: str = "文档入库完成") -> dict | None:
        r = self._get_client()
        key = self._key(job_id)
        raw = r.hgetall(key)
        if not raw:
            return None
        steps: list[dict] = json.loads(raw.get("steps", "[]"))
        for step in steps:
            if step["status"] != "failed":
                step["percent"] = 100
                step["status"] = "completed"
        raw["status"] = "completed"
        raw["current_step"] = raw.get("completion_step") or raw.get("current_step", "")
        raw["message"] = message
        raw["error"] = ""
        raw["updated_at"] = datetime.now(UTC).isoformat()
        raw["steps"] = json.dumps(steps, ensure_ascii=False)
        r.hset(key, mapping=raw)
        logger.info("Redis 任务完成: job_id=%s, filename=%s", job_id, raw.get("filename", ""))
        return self.get_job(job_id)

    def fail_job(self, job_id: str, step_key: str, error: str) -> dict | None:
        r = self._get_client()
        key = self._key(job_id)
        raw = r.hgetall(key)
        if not raw:
            return None
        steps: list[dict] = json.loads(raw.get("steps", "[]"))
        step = next((s for s in steps if s["key"] == step_key), None)
        if step:
            step["status"] = "failed"
            step["message"] = error
        raw["status"] = "failed"
        raw["current_step"] = step_key
        raw["message"] = error
        raw["error"] = error
        raw["updated_at"] = datetime.now(UTC).isoformat()
        raw["steps"] = json.dumps(steps, ensure_ascii=False)
        r.hset(key, mapping=raw)
        logger.error("Redis 任务失败: job_id=%s, step=%s, error=%s", job_id, step_key, error)
        return self.get_job(job_id)

    def list_jobs(self) -> list[dict]:
        r = self._get_client()
        cursor = 0
        jobs = []
        while True:
            cursor, keys = r.scan(cursor=cursor, match=f"{self._REDIS_PREFIX}*", count=100)
            for key in keys:
                raw = r.hgetall(key)
                if raw:
                    raw["steps"] = json.loads(raw.get("steps", "[]"))
                    raw["total_chunks"] = int(raw.get("total_chunks", 0))
                    raw["processed_chunks"] = int(raw.get("processed_chunks", 0))
                    jobs.append(raw)
            if cursor == 0:
                break
        return jobs


# ── 模块级单例（根据 USE_REDIS_JOB_MANAGER 配置自动选择实现）───────────────

_ManagerClass = RedisJobManager if USE_REDIS_JOB_MANAGER else UploadJobManager

upload_job_manager: UploadJobManager | RedisJobManager = _ManagerClass()
"""文件上传任务管理器单例（全进程共享）。按配置使用内存或 Redis 实现。"""

delete_job_manager: UploadJobManager | RedisJobManager = _ManagerClass()
"""文件删除任务管理器单例（全进程共享）。按配置使用内存或 Redis 实现。"""
