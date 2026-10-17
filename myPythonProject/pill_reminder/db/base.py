"""数据库连接管理 — 引擎 / 会话 / ORM 基类

设计要点：
1. 所有连接参数都从 pill_reminder/.env 读取，代码里不硬编码密码。
2. 引擎是「懒加载」的：只有真正执行 SQL 时才建立连接，
   这样数据库没启动也不会导致 import 阶段就崩掉。
3. 对外主要用 session_scope() 上下文管理器，自动 commit / rollback / close，
   避免忘记提交或忘记关连接。
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# .env 位于 pill_reminder/ 下，本文件在 pill_reminder/db/ 下，所以往上两级
_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
)
load_dotenv(_ENV_PATH)

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT") or 3306)
DB_USER = os.getenv("DB_USER", "dev_app")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "pill_reminder")
DB_ECHO = (os.getenv("DB_ECHO", "0") or "0") == "1"


def build_url(driver: str = "mysql+pymysql") -> str:
    """拼出 SQLAlchemy 连接串（密码里的特殊字符会被正确转义）"""
    return (
        f"{driver}://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    )


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """获取全局唯一的引擎实例（首次调用时创建）"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            build_url(),
            pool_pre_ping=True,   # 取连接前先探活，防止 MySQL 8 小时断连
            pool_recycle=3600,    # 连接最多复用 1 小时
            pool_size=5,
            max_overflow=10,
            echo=DB_ECHO,
        )
        logger.info("数据库引擎已创建: %s:%s/%s", DB_HOST, DB_PORT, DB_NAME)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def new_session() -> Session:
    """新建一个会话（调用方负责 close）"""
    return get_session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """事务上下文：正常结束自动提交，抛异常自动回滚，最后一定关闭。

    用法::

        with session_scope() as session:
            session.add(obj)
    """
    session = new_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖注入用（只读场景，需要写入请在接口内自行 commit）"""
    session = new_session()
    try:
        yield session
    finally:
        session.close()


def ping() -> bool:
    """探活：数据库连得上返回 True"""
    from sqlalchemy import text

    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - 探活要吞掉所有异常
        logger.warning("数据库连接失败: %s", exc)
        return False
