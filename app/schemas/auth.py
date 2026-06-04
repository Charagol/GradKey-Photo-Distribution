"""认证相关 Pydantic V2 Request/Response 模型。"""

from pydantic import BaseModel, Field


class AuthRequest(BaseModel):
    """管理员登录请求。"""

    password: str


class TokenResponse(BaseModel):
    """JWT 令牌响应。"""

    access_token: str
    token_type: str = Field(default="bearer")


class AlbumPasswordUpdate(BaseModel):
    """相册密码更新请求。"""

    password: str
