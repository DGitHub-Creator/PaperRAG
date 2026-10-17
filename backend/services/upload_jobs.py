"""上传/删除任务状态：两种实际存储复用同一套状态转换；Redis 保存可重放输入，进程启动时恢复未完成的局部文档任务。"""

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import uuid4
import json

import redis

from backend.core.config import REDIS_URL, REDIS_KEY_PREFIX, USE_REDIS_JOB_MANAGER

StepStatus = Literal["pending", "running", "completed", "failed"]
JobStatus = StepStatus
TERMINAL = {"completed", "failed"}

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
    return datetime.now(UTC).isoformat()


class UploadJobManager:
    def __init__(self, namespace: str = "upload"):
        self._jobs: dict[str, dict] = {}
        self._lock = Lock()

    def _insert(self, job: dict) -> None:
        with self._lock:
            self._jobs[job["job_id"]] = deepcopy(job)

    def create_job(self, filename: str, *, steps=None, current_step="upload", message="等待上传", completion_step="vector_store", context: dict | None = None) -> dict:
        steps = DEFAULT_STEPS if steps is None else steps
        keys = [key for key, _ in steps]
        if len(set(keys)) != len(keys) or current_step not in keys or completion_step not in keys:
            raise ValueError("任务步骤必须唯一，初始/完成步骤必须存在")
        now = _now_iso()
        job = {
            "job_id": uuid4().hex, "filename": filename, "status": "pending",
            "current_step": current_step, "completion_step": completion_step, "message": message,
            "context": deepcopy(context),
            "total_chunks": 0, "processed_chunks": 0, "error": None,
            "created_at": now, "updated_at": now,
            "steps": [{"key": key, "label": label, "percent": 0, "status": "pending", "message": ""} for key, label in steps],
        }
        self._insert(job)
        return deepcopy(job)

    def set_context(self, job_id: str, context: dict) -> dict | None:
        def change(job):
            job["context"] = deepcopy(context)
        return self._mutate(job_id, change)

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            return deepcopy(self._jobs.get(job_id))

    def _mutate(self, job_id: str, change: Callable[[dict], None]) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if job["status"] not in TERMINAL:
                # 先改副本，校验失败时不能留下半次修改。
                job = deepcopy(job)
                change(job)
                job["updated_at"] = _now_iso()
                self._jobs[job_id] = job
            return deepcopy(job)

    @staticmethod
    def _find_step(job: dict, step_key: str) -> dict:
        for step in job["steps"]:
            if step["key"] == step_key:
                return step
        raise ValueError(f"任务步骤不存在: {step_key}")

    def update_step(self, job_id: str, step_key: str, percent: int, status: StepStatus = "running", message: str = "", *, total_chunks=None, processed_chunks=None):
        if status not in {"pending", "running", "completed", "failed"}:
            raise ValueError("无效的步骤状态")

        def change(job):
            step = self._find_step(job, step_key)
            if step["status"] == "completed":
                return
            step.update(percent=max(0, min(100, int(percent))), status=status, message=message)
            job.update(status="failed" if status == "failed" else "running", current_step=step_key, message=message)
            if status == "failed":
                job["error"] = message
            for field, value in [("total_chunks", total_chunks), ("processed_chunks", processed_chunks)]:
                if value is not None:
                    if int(value) < 0:
                        raise ValueError("分块数量不得为负数")
                    job[field] = int(value)
        return self._mutate(job_id, change)

    def complete_step(self, job_id: str, step_key: str, message: str = ""):
        return self.update_step(job_id, step_key, 100, "completed", message)

    def complete_job(self, job_id: str, message: str = "文档入库完成"):
        def change(job):
            if any(step["status"] != "completed" for step in job["steps"]):
                raise ValueError("任务尚有未完成步骤，不能标记成功")
            job.update(status="completed", current_step=job["completion_step"], message=message, error=None)
        return self._mutate(job_id, change)

    def fail_job(self, job_id: str, step_key: str, error: str):
        def change(job):
            step = self._find_step(job, step_key)
            step.update(status="failed", message=error)
            job.update(status="failed", current_step=step_key, message=error, error=error)
        return self._mutate(job_id, change)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            return deepcopy(list(self._jobs.values()))


class RedisJobManager(UploadJobManager):
    """WATCH 事务保护整条状态，避免并发更新覆盖；不回退到内存伪装持久化。"""

    _REDIS_TTL = 86400

    def __init__(self, namespace: str = "upload"):
        self._redis: redis.Redis | None = None
        self._prefix = f"{REDIS_KEY_PREFIX}:job:{namespace}:"

    def _get_client(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return self._redis

    def _key(self, job_id: str) -> str:
        return self._prefix + job_id

    @staticmethod
    def _encode(job: dict) -> dict:
        return {key: json.dumps(value, ensure_ascii=False) for key, value in job.items()}

    @staticmethod
    def _decode(raw: dict) -> dict | None:
        return {key: json.loads(value) for key, value in raw.items()} if raw else None

    def _insert(self, job: dict) -> None:
        with self._get_client().pipeline() as pipe:
            pipe.hset(self._key(job["job_id"]), mapping=self._encode(job))
            pipe.expire(self._key(job["job_id"]), self._REDIS_TTL)
            pipe.execute()

    def get_job(self, job_id: str) -> dict | None:
        return self._decode(self._get_client().hgetall(self._key(job_id)))

    def _mutate(self, job_id: str, change: Callable[[dict], None]) -> dict | None:
        key = self._key(job_id)
        for _ in range(8):
            with self._get_client().pipeline() as pipe:
                try:
                    pipe.watch(key)
                    job = self._decode(pipe.hgetall(key))
                    if job is None or job["status"] in TERMINAL:
                        return job
                    change(job)
                    job["updated_at"] = _now_iso()
                    pipe.multi()
                    pipe.hset(key, mapping=self._encode(job))
                    pipe.expire(key, self._REDIS_TTL)
                    pipe.execute()
                    return job
                except redis.WatchError:
                    continue
        raise RuntimeError("任务状态并发冲突，请重试")

    def list_jobs(self) -> list[dict]:
        client = self._get_client()
        jobs = []
        for key in client.scan_iter(match=f"{self._prefix}*", count=100):
            job = self._decode(client.hgetall(key))
            if job is not None:
                jobs.append(job)
        return jobs


_ManagerClass = RedisJobManager if USE_REDIS_JOB_MANAGER else UploadJobManager
upload_job_manager = _ManagerClass(namespace="upload")
delete_job_manager = _ManagerClass(namespace="delete")
