"""
数据库模块 —— SQLAlchemy 引擎、会话工厂与初始化。

本模块负责:
  - 创建 SQLAlchemy 异步/同步引擎（基于 DATABASE_URL 配置）
  - 提供 SessionLocal 会话工厂供 FastAPI 依赖注入使用
  - 提供 get_db 生成器函数（FastAPI Depends 标准用法）
  - 声明 Base（declarative_base），所有 ORM 模型统一继承
  - 提供 init_db()：Go 接管库只检查就绪；旧库走 Alembic，失败不静默 create_all

所有配置值统一从 backend.core.config 导入。
日志通过 backend.core.logging_config.get_logger 获取标准化 logger。

使用方式:
    from backend.core.database import SessionLocal, Base, init_db, get_db

    # FastAPI 路由依赖注入
    @router.get("/items")
    def list_items(db: Session = Depends(get_db)):
        ...

    # 应用启动时执行迁移
    init_db()
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import DATABASE_URL, DB_MAX_OVERFLOW, DB_POOL_SIZE
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 数据库引擎 ──────────────────────────────────────────────────────
# pool_pre_ping=True: 每次从连接池取出连接前先发一个 ping 探测，
# 确保连接未被服务端断开（避免 "connection closed" 错误）。
# pool_recycle=3600: 每小时回收连接，防止长连接被数据库断开。
# pool_size / max_overflow: 连接池大小，通过环境变量配置。
engine = create_engine(
    DATABASE_URL,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
)
logger.info(f"数据库引擎已创建: {repr(engine.url)}")

# ── 会话工厂 ────────────────────────────────────────────────────────
# autoflush=False:  不在每次查询前自动 flush，由业务逻辑显式控制事务边界。
# autocommit=False: 不自动提交，需要显式调用 db.commit()。
# expire_on_commit=False: 提交后不过期已加载的对象，避免延迟加载时的额外查询。
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)

# ── 声明式基类 ──────────────────────────────────────────────────────
# 所有 ORM 模型类继承自此 Base，SQLAlchemy 据此发现和管理表映射。
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入: 获取数据库会话（生成器）。

    用法（FastAPI 路由）:
        @router.get("/items")
        def list_items(db: Session = Depends(get_db)):
            ...

    每次请求生成一个新的 SessionLocal 会话，请求完成后自动关闭。

    Yields:
        SQLAlchemy Session 实例，用于数据库查询和操作。
    """
    db = SessionLocal()
    logger.debug("数据库会话已创建")
    try:
        yield db
    finally:
        db.close()
        logger.debug("数据库会话已关闭")


def init_db() -> None:
    """Go 接管库只检查版本；旧 Python 库沿用 Alembic，均不回退 create_all。

    历史实现在 alembic 缺失或执行失败时回退 ``Base.metadata.create_all``，
    结果是表被静默建出来、库里却没有 `alembic_version` 行，之后的迁移无法
    安全叠加，schema 真实状态与迁移脚本从此分叉。这里改为直接抛错：
    迁移跑不起来就拒绝启动，并把 alembic 的输出带进异常信息供排查。

    Raises:
        RuntimeError: alembic.ini 不存在、迁移命令失败或超时。
    """
    import subprocess
    import sys
    from pathlib import Path

    with engine.connect() as connection:
        if connection.execute(text("SELECT to_regclass('public.schema_migrations')")).scalar() is not None:
            state = connection.execute(text("SELECT version, dirty FROM public.schema_migrations")).one_or_none()
            # 三份既有 Go 迁移包含 Python 所需基线与执行表；不能在它们之后重放旧建表链。
            if state is None or state.version < 3 or state.dirty:
                raise RuntimeError("Go 数据库迁移尚未完成或处于 dirty 状态，请先运行 dev.py migrate-go")
            logger.info("Go 数据库迁移已就绪，跳过旧 Alembic 启动迁移")
            return

    alembic_ini = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    if not alembic_ini.exists():
        raise RuntimeError(
            f"未找到 {alembic_ini}，无法通过 Alembic 初始化数据库；"
            "已拒绝以 create_all 静默建表（会产生没有版本记录的库）"
        )

    logger.info("alembic.ini found — running alembic upgrade head")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(alembic_ini.parent),
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("alembic upgrade head 超时（60s），数据库或迁移脚本疑似阻塞") from e

    if result.returncode != 0:
        raise RuntimeError(
            f"alembic upgrade head 失败 (rc={result.returncode})\n"
            f"--- stdout ---\n{result.stdout.strip()}\n"
            f"--- stderr ---\n{result.stderr.strip()}"
        )

    logger.info("Alembic migration applied successfully")
