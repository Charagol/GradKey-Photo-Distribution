"""相册配置模型 — 全局单例表，存储相册密码哈希。"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AlbumConfig(Base):
    """相册全局配置单例表。

    该表仅维护一行记录，存储相册密码的 bcrypt 哈希。
    管理员通过 API 更新密码时，该行数据原地更新。
    """

    __tablename__ = "album_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AlbumConfig id={self.id}>"
