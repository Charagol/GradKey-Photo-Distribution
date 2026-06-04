"""数据模型包 — 集中导入所有模型，方便 Base.metadata.create_all() 调用。"""

from app.models.album_config import AlbumConfig  # noqa: F401
from app.models.image import Image  # noqa: F401
from app.models.image_tag import image_tags  # noqa: F401
from app.models.student import Student  # noqa: F401
from app.models.tag_group import TagGroup  # noqa: F401
from app.models.tag import Tag  # noqa: F401
