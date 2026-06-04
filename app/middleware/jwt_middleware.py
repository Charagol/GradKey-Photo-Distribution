"""JWT 中间件 — FastAPI 依赖注入函数。

提供 get_current_admin 和 get_current_student 两个注入函数，
从 Authorization: Bearer <token> 头提取并验证 JWT，校验 role 字段。
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import decode_access_token

#: Bearer Token 提取器。
_bearer_scheme = HTTPBearer()


def _get_payload(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """从请求头提取并验证 JWT，返回解码后的 payload。

    Args:
        credentials: HTTPBearer 提取的凭证对象。

    Returns:
        dict: JWT payload。

    Raises:
        HTTPException: 401 若 token 无效。
    """
    return decode_access_token(credentials.credentials)


def get_current_admin(
    payload: dict = Depends(_get_payload),
) -> dict:
    """提取并验证管理员 JWT。

    要求 JWT payload 中 role == "admin"，否则返回 403。

    Args:
        payload: 解码后的 JWT payload。

    Returns:
        dict: {"sub": "admin", "role": "admin", "exp": ...}

    Raises:
        HTTPException: 403 若 role 不为 admin。
    """
    if payload.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限",
        )
    return payload


def get_current_student(
    payload: dict = Depends(_get_payload),
) -> dict:
    """提取并验证学生 JWT。

    要求 JWT payload 中 role == "student"，否则返回 403。

    Args:
        payload: 解码后的 JWT payload。

    Returns:
        dict: {"sub": "student_name", "role": "student", "exp": ...}

    Raises:
        HTTPException: 403 若 role 不为 student。
    """
    if payload.get("role") != "student":
        raise HTTPException(
            status_code=403,
            detail="需要学生身份",
        )
    return payload
