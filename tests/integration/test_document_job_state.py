import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import redis

from backend.services.upload_jobs import RedisJobManager, UploadJobManager


@pytest.fixture(params=["memory", "redis"])
def jobs(request):
    if request.param == "memory":
        yield UploadJobManager()
        return
    url = os.getenv("REFACTOR_TEST_REDIS_URL")
    if not url:
        pytest.skip("需要显式指定 REFACTOR_TEST_REDIS_URL 验证 Redis 状态事务")
    manager = RedisJobManager()
    manager._redis = redis.Redis.from_url(url, decode_responses=True)
    manager._prefix = "quality:" + uuid4().hex + ":"
    try:
        yield manager
    finally:
        keys = list(manager._redis.scan_iter(match=manager._prefix + "*"))
        if keys:
            manager._redis.delete(*keys)
        manager._redis.close()


def test_nested_values_round_trip_and_returned_snapshots_are_independent(jobs):
    job = jobs.create_job("paper.pdf")
    assert jobs.get_job(job["job_id"]) == job
    job["steps"][0]["status"] = "failed"
    assert jobs.get_job(job["job_id"])["steps"][0]["status"] == "pending"
    assert jobs.list_jobs()[0]["error"] is None


def test_terminal_states_cannot_be_reopened_by_late_callbacks(jobs):
    job = jobs.create_job("paper.pdf")
    failed = jobs.fail_job(job["job_id"], "parse", "解析失败")
    assert jobs.complete_job(job["job_id"]) == failed
    assert jobs.update_step(job["job_id"], "vector_store", 80) == failed


def test_success_requires_every_step_and_cannot_be_retroactively_failed(jobs):
    job = jobs.create_job("paper.pdf")
    with pytest.raises(ValueError, match="未完成"):
        jobs.complete_job(job["job_id"])
    for step in job["steps"]:
        jobs.complete_step(job["job_id"], step["key"])
    completed = jobs.complete_job(job["job_id"])
    assert jobs.fail_job(job["job_id"], "parse", "迟到的错误") == completed


def test_concurrent_step_updates_do_not_overwrite_other_steps(jobs):
    job = jobs.create_job("paper.pdf")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(jobs.complete_step, job["job_id"], step["key"]) for step in job["steps"]]
        for future in futures:
            future.result()
    assert jobs.complete_job(job["job_id"])["status"] == "completed"


def test_invalid_mutation_leaves_existing_state_unchanged(jobs):
    job = jobs.create_job("paper.pdf")
    with pytest.raises(ValueError):
        jobs.update_step(job["job_id"], "parse", 10, total_chunks=-1)
    assert jobs.get_job(job["job_id"]) == job
