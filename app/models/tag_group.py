"""标签分组模型 — 将标签归入不同分组（寝室/专业/未分类等）。

V2.0 引入分组概念以支撑沉浸式打标工作台的按分组聚合展示。
至少包含一个默认"未分类"分组（由迁移脚本创建）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# 默认分组名 — Tag.before_insert 事件依赖此常量
DEFAULT_TAG_GROUP_NAME = "未分类"


class TagGroup(Base):
    """标签分组实体。

    每个 Tag 必须属于一个分组（nullable=False）。
    删除分组时，组内 Tag 迁移至"未分类"而非级联删除（Phase 10 策略）。
    """

    __tablename__ = "tag_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # 反向关系：一个分组下有多个标签
    tags: Mapped[list["Tag"]] = relationship(
        "Tag", back_populates="group", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<TagGroup id={self.id} name='{self.name}'>"
