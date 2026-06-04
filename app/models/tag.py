"""标签模型 — 管理员为照片打标，Tag.name 与学生姓名匹配实现隐私隔离。

    隐私隔离逻辑: 学生「张三」仅能看到 Tag.name == '张三' 的照片集合。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tag(Base):
    """照片标签实体。

    标签由管理员创建，上传照片时分配给 Image（多对多）。
    关键: Tag.name 是隐私隔离的依据 — 与 Student.name 匹配决定可见性。
    """

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name='{self.name}'>"
