"""管理员相关 Pydantic V2 Request/Response 模型。

ImageResponse 是关键模型 — 包含动态生成的临时签名 URL，
因此不使用 from_attributes，而是手动构建。
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Student ──


class StudentCreate(BaseModel):
    """创建学生请求。"""

    name: str


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
    created_at: datetime


# ── Image ──


class ImageResponse(BaseModel):
    """图片响应 — url 由 storage.get_signed_url() 动态生成。"""

    id: int
    file_key: str
    file_name: str | None = None
    content_type: str | None = None
    file_size: int | None = None
    uploaded_at: datetime
    url: str
    tags: list[TagResponse] = []


class ImageListResponse(BaseModel):
    """图片列表响应（含签名 URL）。"""

    images: list[ImageResponse]
    total: int
