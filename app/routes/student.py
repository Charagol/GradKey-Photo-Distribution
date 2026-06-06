"""学生路由 — 双重认证登录 + 隐私隔离照片流。

核心隐私逻辑：
- 学生登录后，仅能看到 Tag.name == 自己姓名 所关联的照片。
- GET /my-images: 查询匹配 Tag → 获取关联 Image → 注入签名 URL。
- GET /my-tags:  收集可见照片上的所有 Tag（去重），用于前端过滤按钮。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_storage_service
from app.middleware.jwt_middleware import get_current_student
from app.models.image import Image
from app.models.tag import Tag
from app.schemas.admin import ImageListResponse, ImageResponse, TagResponse
from app.schemas.auth import TokenResponse
from app.schemas.student import StudentAuthRequest
from app.services.aliyun_oss_storage import AliyunOssStorageService
from app.services.auth_service import (
    create_student_token,
    verify_or_init_album_password,
    verify_student,
)

router = APIRouter(prefix="/api/student", tags=["student"])


# ═══════════════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════════════


@router.post("/auth", response_model=TokenResponse)
async def student_login(body: StudentAuthRequest, db: Session = Depends(get_db)):
    """学生双重验证登录。

    第一重 — 相册密码（防路人）。
    第二重 — 姓名 + 个人密钥（防偷窥）。
    """
    # 第一重：相册密码
    if not verify_or_init_album_password(db, body.album_password):
        raise HTTPException(status_code=401, detail="相册密码错误")

    # 第二重：学生姓名 + 密钥
    student = verify_student(db, body.name, body.secret_key)
    if student is None:
        raise HTTPException(status_code=401, detail="姓名或密钥错误")

    token = create_student_token(body.name)
    return TokenResponse(access_token=token, token_type="bearer")


# ═══════════════════════════════════════════════════════════════════════════
# Privacy-Isolated Image Feed
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/my-images", response_model=ImageListResponse)
async def my_images(
    payload: dict = Depends(get_current_student),
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """获取当前学生的可见照片流（隐私隔离）。

    逻辑：从 JWT sub 提取学生姓名 → 查找 Tag.name == 姓名 的标签
    → 获取该标签关联的所有 Image → 注入临时签名 URL → 按时间倒序返回。
    """
    student_name: str = payload["sub"]

    # 查找与学生同名的 Tag
    matching_tags = db.query(Tag).filter(Tag.name == student_name).all()
    if not matching_tags:
        return ImageListResponse(images=[], total=0)

    tag_ids = [t.id for t in matching_tags]

    # 通过 image_tags 关联表获取去重后的 Image 列表
    images = (
        db.query(Image)
        .join(Image.tags)
        .filter(Tag.id.in_(tag_ids))
        .distinct()
        .order_by(Image.uploaded_at.desc())
        .all()
    )

    # 构建响应（含签名 URL + 缩略图 URL）
    result: list[ImageResponse] = []
    for img in images:
        url = await storage.get_signed_url(img.file_key)
        thumbnail_url = await storage.get_thumbnail_signed_url(img.file_key)
        result.append(
            ImageResponse(
                id=img.id,
                file_key=img.file_key,
                file_name=img.file_name,
                content_type=img.content_type,
                file_size=img.file_size,
                uploaded_at=img.uploaded_at,
                url=url,
                thumbnail_url=thumbnail_url,
                tags=[TagResponse.model_validate(t) for t in img.tags],
            )
        )

    return ImageListResponse(images=result, total=len(result))


# ═══════════════════════════════════════════════════════════════════════════
# Available Tag Filters
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/my-tags", response_model=list[TagResponse])
async def my_tags(
    payload: dict = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """获取当前学生可见照片上的所有标签（去重）。

    前端用于标签筛选按钮 — 学生能看到自己与其他人的合影标签。
    """
    student_name: str = payload["sub"]

    # 查找与学生同名的 Tag
    student_tag = db.query(Tag).filter(Tag.name == student_name).first()
    if not student_tag:
        return []

    # 获取该学生可见的所有 Image
    visible_images = (
        db.query(Image)
        .join(Image.tags)
        .filter(Tag.id == student_tag.id)
        .all()
    )

    # 收集所有 Tag 并去重
    tag_id_set: set[int] = set()
    for img in visible_images:
        for tag in img.tags:
            tag_id_set.add(tag.id)

    if not tag_id_set:
        return []

    tags = (
        db.query(Tag)
        .filter(Tag.id.in_(tag_id_set))
        .order_by(Tag.created_at.desc())
        .all()
    )
    return tags
