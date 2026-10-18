"""数据库连接管理 — 引擎 / 会话 / ORM 基类

设计要点：
1. 所有连接参数都从仓库根的 .env 读取，代码里不硬编码密码。
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

from ..paths import ENV_EXAMPLE as ENV_EXAMPLE_PATH
from ..paths import ENV_FILE

logger = logging.getLogger(__name__)

_ENV_PATH = str(ENV_FILE)
_ENV_EXAMPLE = str(ENV_EXAMPLE_PATH)
ENV_EXISTS = ENV_FILE.is_file()

load_dotenv(_ENV_PATH)

if not ENV_EXISTS:
    logger.warning(
        "未找到配置文件 %s —— 数据库和讯飞密钥都读不到。"
        "请把 .env.example 复制成 .env 再填写（Windows: copy .env.example .env）。",
        _ENV_PATH,
    )

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


def env_hint() -> str:
    """检查配置是否齐全，返回给人看的提示（空字符串表示没问题）

    新机器上最常踩的坑就是「clone 下来没有 .env」，
    光报 Access denied 根本看不出原因，所以单独给一条明确指引。
    """
    if not ENV_EXISTS:
        return (
            "缺少配置文件: " + _ENV_PATH + "\n"
            "  解决: 在仓库根目录执行 copy .env.example .env，\n"
            "        再填入讯飞 APP_ID/API_KEY/API_SECRET 和数据库密码"
        )

    missing = [k for k in ("APP_ID", "API_KEY", "API_SECRET") if not os.getenv(k)]
    if missing:
        return f".env 里缺少讯飞凭证: {', '.join(missing)}（AI/OCR/语音功能会不可用）"

    if not os.getenv("DB_PASSWORD"):
        return ".env 里没有填 DB_PASSWORD，数据库连不上"

    return ""


def env_ready() -> bool:
    """配置是否齐全"""
    return env_hint() == ""


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
        hint = env_hint()
        if hint:
            logger.warning(hint)
        return False
