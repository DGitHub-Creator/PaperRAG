"""
数据库模块 —— SQLAlchemy 引擎、会话工厂与初始化。

本模块负责:
  - 创建 SQLAlchemy 异步/同步引擎（基于 DATABASE_URL 配置）
  - 提供 SessionLocal 会话工厂供 FastAPI 依赖注入使用
  - 提供 get_db 生成器函数（FastAPI Depends 标准用法）
  - 声明 Base（declarative_base），所有 ORM 模型统一继承
  - 提供 init_db() 一键建表函数

所有配置值统一从 backend.core.config 导入。
日志通过 backend.core.logging_config.get_logger 获取标准化 logger。

使用方式:
    from backend.core.database import SessionLocal, Base, init_db, get_db

    # FastAPI 路由依赖注入
    @router.get("/items")
    def list_items(db: Session = Depends(get_db)):
        ...

    # 应用启动时建表
    init_db()
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from backend.core.config import DATABASE_URL
from backend.core.logging_config import get_logger

logger = get_logger(__name__)

# ── 数据库引擎 ──────────────────────────────────────────────────────
# pool_pre_ping=True: 每次从连接池取出连接前先发一个 ping 探测，
# 确保连接未被服务端断开（避免 "connection closed" 错误）。
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
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
    """初始化数据库: 根据 ORM 模型定义自动创建所有表。

    应在应用启动时调用一次（如 app.py 的 @app.on_event("startup") 中）。
    内部延迟导入 models 模块以避免循环引用:
      - models 模块 import Base from database
      - database 的 init_db 在运行时才 import models
      - 这样就打破了循环依赖。

    已有表不会被重复创建（CREATE TABLE IF NOT EXISTS 语义）。
    """
    # 延迟导入，避免循环依赖（models → database → models）
    import backend.core.models as _models  # noqa: F401

    logger.info("开始创建数据库表...")
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表创建/验证完成")
