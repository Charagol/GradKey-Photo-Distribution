"""认证服务 — JWT 签发/验证与相册密码管理。

使用 passlib[bcrypt] 进行密码哈希，python-jose 处理 JWT。
"""

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.models.album_config import AlbumConfig
from app.models.student import Student

#: bcrypt 密码上下文，用于哈希和验证。
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash_password(plain: str) -> str:
    """对明文密码进行 bcrypt 哈希。

    Args:
        plain: 明文密码。

    Returns:
        str: bcrypt 哈希字符串。
    """
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。

    Args:
        plain: 明文密码。
        hashed: bcrypt 哈希值。

    Returns:
        bool: 匹配返回 True。
    """
    return _pwd_context.verify(plain, hashed)


def verify_or_init_album_password(db: Session, password: str) -> bool:
    """验证相册密码；若 AlbumConfig 为空则首次设置密码。

    Args:
        db: 数据库会话。
        password: 明文密码。

    Returns:
        bool: 密码有效或首次设置成功返回 True，否则 False。
    """
    config = db.query(AlbumConfig).first()

    if config is None:
        # 表为空 → 首次设置密码
        config = AlbumConfig(password_hash=_hash_password(password))
        db.add(config)
        db.commit()
        return True

    return _verify_password(password, config.password_hash)


def update_album_password(db: Session, new_password: str) -> None:
    """更新相册密码（原地覆盖哈希值）。

    Args:
        db: 数据库会话。
        new_password: 新明文密码。
    """
    config = db.query(AlbumConfig).first()
    if config is None:
        raise HTTPException(
            status_code=400,
            detail="相册密码尚未初始化",
        )
    config.password_hash = _hash_password(new_password)
    db.commit()


def create_access_token(data: dict, expires_hours: int | None = None) -> str:
    """签发 JWT 访问令牌。

    Args:
        data: JWT payload 数据。
        expires_hours: 有效期（小时），默认使用全局配置。

    Returns:
        str: 编码后的 JWT 字符串。
    """
    to_encode = data.copy()
    expire_hours = expires_hours if expires_hours is not None else settings.jwt_expire_hours
    expire = datetime.now(timezone.utc) + timedelta(hours=expire_hours)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """解码并验证 JWT 访问令牌。

    Args:
        token: JWT 字符串。

    Returns:
        dict: 解码后的 payload。

    Raises:
        HTTPException: 401 若 token 无效或已过期。
    """
    try:
        payload: dict = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="无效或已过期的认证令牌",
        )


def create_admin_token() -> str:
    """签发管理员 JWT。

    Returns:
        str: 管理员 JWT（24小时有效）。
    """
    return create_access_token({"sub": "admin", "role": "admin"})


def create_student_token(student_name: str) -> str:
    """签发学生 JWT。

    Args:
        student_name: 学生姓名，作为 JWT sub。

    Returns:
        str: 学生 JWT（24小时有效）。
    """
    return create_access_token({"sub": student_name, "role": "student"})


def verify_student(db: Session, name: str, secret_key: str) -> Student | None:
    """通过姓名和密钥验证学生身份。

    Args:
        db: 数据库会话。
        name: 学生姓名。
        secret_key: 学生个人密钥。

    Returns:
        Student | None: 验证通过返回 Student 对象，否则 None。
    """
    student = db.query(Student).filter(Student.name == name).first()
    if student and student.secret_key == secret_key:
        return student
    return None
