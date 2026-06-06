"""管理员相关 Pydantic V2 Request/Response 模型。

ImageResponse 是关键模型 — 包含动态生成的临时签名 URL，
因此不使用 from_attributes，而是手动构建。

V2.0: 新增 TagGroup、TagUpdate、ImageTagUpdate、批量学生 Schema。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Student ──


class StudentCreate(BaseModel):
    """创建学生请求 — V3.0 统一接受中文全角逗号分隔姓名。

    Example: {"names": "张三"} 或 {"names": "张三，李四，王五"}
    """

    names: str


class StudentUpdate(BaseModel):
    """修改学生请求。"""

    name: str


class StudentResponse(BaseModel):
    """学生响应（含密钥，仅管理员可见）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    secret_key: str
    created_at: datetime


# ── Tag ──


class TagCreate(BaseModel):
    """创建标签请求。"""

    name: str


class TagResponse(BaseModel):
    """标签响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    group_id: int  # V2.0: 所属分组 ID
    created_at: datetime


class TagUpdate(BaseModel):
    """修改标签所属分组请求。"""

    group_id: int


# ── TagGroup ──


class TagGroupCreate(BaseModel):
    """创建标签分组请求。"""

    name: str


class TagGroupUpdate(BaseModel):
    """修改标签分组请求。"""

    name: str


class TagGroupResponse(BaseModel):
    """标签分组响应（含嵌套标签列表）。

    嵌套策略: TagResponse 不含 group 关系字段，避免无限递归。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    tags: list[TagResponse] = []


# ── Image ──


class ImageTagUpdate(BaseModel):
    """编辑图片标签请求 — 全量替换。"""

    tag_ids: list[int]


class ImageResponse(BaseModel):
    """图片响应 — url 由 storage.get_signed_url() 动态生成。

    V3.0: thumbnail_url 用于学生端网格预览（x-oss-process 参与签名）。"""

    id: int
    file_key: str
    file_name: str | None = None
    content_type: str | None = None
    file_size: int | None = None
    uploaded_at: datetime
    url: str
    thumbnail_url: str | None = None  # V3.0: 缩略图签名 URL
    tags: list[TagResponse] = []


class ImageListResponse(BaseModel):
    """图片列表响应（含签名 URL）。"""

    images: list[ImageResponse]
    total: int


class ImageBatchDeleteRequest(BaseModel):
    """批量删除图片请求 — V3.0 Phase 22。"""

    image_ids: list[int]
