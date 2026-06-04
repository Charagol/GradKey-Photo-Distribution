"""Pydantic Schemas 包 — 集中导出所有 Request/Response 模型。"""

from app.schemas.admin import (
    ImageListResponse,
    ImageResponse,
    StudentCreate,
    StudentResponse,
    StudentUpdate,
    TagCreate,
    TagResponse,
)
from app.schemas.auth import AlbumPasswordUpdate, AuthRequest, TokenResponse

__all__ = [
    "AlbumPasswordUpdate",
    "AuthRequest",
    "ImageListResponse",
    "ImageResponse",
    "StudentCreate",
    "StudentResponse",
    "StudentUpdate",
    "TagCreate",
    "TagResponse",
    "TokenResponse",
]
