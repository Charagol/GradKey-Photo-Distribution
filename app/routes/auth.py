"""认证路由 — POST /api/admin/auth。

独立 router，不在 admin_router 中（否则需要 token 才能登录）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.auth import AuthRequest, TokenResponse
from app.services.auth_service import create_admin_token, verify_or_init_album_password

router = APIRouter(prefix="/api/admin", tags=["auth"])


@router.post("/auth", response_model=TokenResponse)
async def admin_login(body: AuthRequest, db: Session = Depends(get_db)):
    """管理员登录 / 首次设置相册密码。

    AlbumConfig 为空时为首次使用，任意密码将被设为相册密码。
    之后需使用已设置的密码登录。
    """
    if not verify_or_init_album_password(db, body.password):
        raise HTTPException(status_code=401, detail="密码错误")

    token = create_admin_token()
    return TokenResponse(access_token=token, token_type="bearer")
