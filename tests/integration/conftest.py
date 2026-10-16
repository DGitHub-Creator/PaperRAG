import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def isolated_pg_factory():
    url = os.getenv("REFACTOR_TEST_DATABASE_URL")
    if not url:
        pytest.skip("需要显式指定本轮隔离数据库 REFACTOR_TEST_DATABASE_URL")
    if not (make_url(url).database or "").startswith("quality_"):
        pytest.fail("拒绝在非 quality_ 隔离库执行存储验收")
    engine = create_engine(url)
    try:
        yield sessionmaker(engine)
    finally:
        engine.dispose()
