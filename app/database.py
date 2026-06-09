"""数据库引擎与会话管理。

使用 SQLAlchemy 2.0 风格的 engine 和 session 工厂。
V4.0 P7: SQLite WAL 模式 + 连接池参数调优。
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# connect_args 仅 SQLite 需要（多线程访问）
_connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,
    # V4.0 P7-4: 数据库连接池参数
    pool_size=3,
    max_overflow=5,
    pool_pre_ping=True,
)


# V4.0 P7-2: SQLite WAL 模式 — 读不阻塞写，提升并发
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类。所有 Model 继承自此。"""
    pass


def get_db():
    """FastAPI 依赖注入: 获取数据库会话，请求结束时自动关闭。

    Yields:
        Session: SQLAlchemy 会话实例。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
