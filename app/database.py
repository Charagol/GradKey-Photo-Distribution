"""数据库引擎与会话管理。

使用 SQLAlchemy 2.0 风格的 engine 和 session 工厂。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# connect_args 仅 SQLite 需要（多线程访问）
_connect_args = {"check_same_thread": False} if "sqlite" in settings.database_url else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,
)

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
