"""图片模型 — 存储 OSS File Key 及元数据。

设计原则:
- 数据库仅存储 File Key，绝不存储公开 URL。
- 签名 URL 在请求时动态生成，有效期 15 分钟。
- Image 不绑定 Student — 毕业照多为合影，通过 Tag 名称匹配实现隐私隔离。
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.image_tag import image_tags  # noqa: TC001


class Image(Base):
    """相册图片实体。

    存储 OSS 对象 Key 和原始文件元数据。文件以 UUID 策略重命名防止覆盖。
    Tags 通过 image_tags 多对多关联表管理。
    """

    __tablename__ = "image"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=True)
    content_type: Mapped[str] = mapped_column(Text, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # 多对多关联到 Tag
    tags = relationship("Tag", secondary=image_tags, backref="images", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Image id={self.id} file_key='{self.file_key}'>"
