"""标签模型 — 管理员为照片打标，Tag.name 与学生姓名匹配实现隐私隔离。

    隐私隔离逻辑: 学生「张三」仅能看到 Tag.name == '张三' 的照片集合。

    V2.0: Tag 归入 TagGroup（分组）。before_insert 事件确保新 Tag 自动
    归入默认"未分类"分组，向后兼容 V1.0 的 Tag(name=...) 调用方式。
"""

from datetime import datetime

from sqlalchemy import (DateTime, ForeignKey, Integer, Text, event, func,
                        text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.tag_group import DEFAULT_TAG_GROUP_NAME


class Tag(Base):
    """照片标签实体。

    标签由管理员创建，上传照片时分配给 Image（多对多）。
    关键: Tag.name 是隐私隔离的依据 — 与 Student.name 匹配决定可见性。
    """

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # ── V2.0: 标签分组 ──────────────────────────────────
    group_id: Mapped[int] = mapped_column(
        ForeignKey("tag_group.id"), nullable=False
    )
    group: Mapped["TagGroup"] = relationship(
        "TagGroup", back_populates="tags"
    )
    # ────────────────────────────────────────────────────

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} name='{self.name}'>"


# ── V2.0: 自动注入默认分组（向后兼容核心机制） ──────────

@event.listens_for(Tag, "before_insert")
def _set_default_tag_group(mapper, connection, target):
    """确保新 Tag 自动归入默认"未分类"分组。

    此事件在 Tag 被 INSERT 到数据库前触发。
    若调用者未显式设置 group_id，则自动查找/创建默认分组。
    这使得所有现有的 Tag(name=...) 调用无需任何修改即可工作。
    """
    if target.group_id is not None:
        return

    result = connection.execute(
        text("SELECT id FROM tag_group WHERE name = :name LIMIT 1"),
        {"name": DEFAULT_TAG_GROUP_NAME},
    )
    row = result.fetchone()
    if row:
        target.group_id = row[0]
    else:
        # 默认分组不存在时自动创建（测试/边缘场景的自愈能力）
        result = connection.execute(
            text("INSERT INTO tag_group (name) VALUES (:name)"),
            {"name": DEFAULT_TAG_GROUP_NAME},
        )
        target.group_id = result.lastrowid
