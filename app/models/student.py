"""学生模型 — 存储学生姓名与个人密钥，用于双重验证。

注: Student 与 Tag 通过 name 字段逻辑关联，实现隐私隔离。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Student(Base):
    """学生实体。

    存储学生姓名和个人密钥。学生验证后仅能看到打有自己姓名 Tag 的照片。
    Image 表不含 student_id 外键 — 隐私隔离通过 Tag 名称匹配实现。
    """

    __tablename__ = "student"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Student id={self.id} name='{self.name}'>"
