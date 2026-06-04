"""Image ↔ Tag 多对多关联表。

该表是一个纯关联表（无额外列），连接 Image 和 Tag 的多对多关系。
"""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.database import Base

image_tags = Table(
    "image_tags",
    Base.metadata,
    Column("image_id", Integer, ForeignKey("image.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)
