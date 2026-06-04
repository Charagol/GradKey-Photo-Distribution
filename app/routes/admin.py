"""管理员路由 — 学生 / 标签 / 图片 / 相册设置的 CRUD API。

所有接口均受 get_current_admin JWT 中间件保护。
Image 资源通过 IStorageService 管理阿里云 OSS 文件。
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_storage_service
from app.middleware.jwt_middleware import get_current_admin
from app.models.image import Image
from app.models.tag import Tag
from app.schemas.admin import (
    ImageListResponse,
    ImageResponse,
    StudentCreate,
    StudentResponse,
    StudentUpdate,
    TagCreate,
    TagResponse,
)
from app.schemas.auth import AlbumPasswordUpdate
from app.services.aliyun_oss_storage import AliyunOssStorageService
from app.services.auth_service import update_album_password
from app.services.student_service import (
    create_student,
    delete_student,
    list_students,
    regenerate_key,
    update_student,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(get_current_admin)],
)


# ═══════════════════════════════════════════════════════════════════════════
# Student CRUD
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/students", response_model=list[StudentResponse])
async def list_students_view(db: Session = Depends(get_db)):
    """列出所有学生（含个人密钥，仅管理员可见）。"""
    return list_students(db)


@router.post("/students", response_model=StudentResponse, status_code=201)
async def create_student_view(body: StudentCreate, db: Session = Depends(get_db)):
    """创建学生，自动生成 6 位个人密钥。"""
    return create_student(db, body.name)


@router.put("/students/{student_id}", response_model=StudentResponse)
async def update_student_view(
    student_id: int, body: StudentUpdate, db: Session = Depends(get_db)
):
    """修改学生姓名。"""
    try:
        return update_student(db, student_id, body.name)
    except ValueError:
        raise HTTPException(status_code=404, detail="学生不存在")


@router.delete("/students/{student_id}", status_code=204)
async def delete_student_view(student_id: int, db: Session = Depends(get_db)):
    """删除学生。"""
    try:
        delete_student(db, student_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="学生不存在")
    return Response(status_code=204)


@router.post("/students/{student_id}/reset-key")
async def reset_student_key(student_id: int, db: Session = Depends(get_db)):
    """重置学生个人密钥，返回新密钥。"""
    try:
        new_key = regenerate_key(db, student_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="学生不存在")
    return {"student_id": student_id, "new_key": new_key}


# ═══════════════════════════════════════════════════════════════════════════
# Tag CRUD
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/tags", response_model=list[TagResponse])
async def list_tags_view(db: Session = Depends(get_db)):
    """列出所有标签，按创建时间倒序。"""
    return db.query(Tag).order_by(Tag.created_at.desc()).all()


@router.post("/tags", response_model=TagResponse, status_code=201)
async def create_tag_view(body: TagCreate, db: Session = Depends(get_db)):
    """创建标签。标签名为唯一约束，重复时返回 409。"""
    existing = db.query(Tag).filter(Tag.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="标签已存在")
    tag = Tag(name=body.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag_view(tag_id: int, db: Session = Depends(get_db)):
    """删除标签。关联的 image_tags 记录自动级联删除。"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    db.delete(tag)
    db.commit()
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════════
# Image Management
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/images", response_model=ImageListResponse)
async def list_images_view(
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """列出所有图片，动态注入临时签名 URL。"""
    images = db.query(Image).order_by(Image.uploaded_at.desc()).all()
    result: list[ImageResponse] = []

    for img in images:
        url = await storage.get_signed_url(img.file_key)
        result.append(
            ImageResponse(
                id=img.id,
                file_key=img.file_key,
                file_name=img.file_name,
                content_type=img.content_type,
                file_size=img.file_size,
                uploaded_at=img.uploaded_at,
                url=url,
                tags=[TagResponse.model_validate(t) for t in img.tags],
            )
        )

    return ImageListResponse(images=result, total=len(result))


@router.post("/images", response_model=ImageListResponse, status_code=201)
async def upload_images_view(
    files: list[UploadFile] = File(...),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """批量上传图片并可选地关联标签。

    Args:
        files: 要上传的图片文件列表。
        tags: JSON 数组字符串，如 '["张三","李四"]'，标签名须已存在于数据库中。
    """
    # 解析 tags JSON
    tag_names: list[str] = []
    if tags:
        try:
            tag_names = json.loads(tags)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="tags 参数需为有效的 JSON 数组")

    # 解析 Tag 对象（须已存在）
    tag_objs: list[Tag] = []
    for name in tag_names:
        tag = db.query(Tag).filter(Tag.name == name).first()
        if tag is None:
            raise HTTPException(status_code=400, detail=f"标签 '{name}' 不存在")
        tag_objs.append(tag)

    # 上传文件至 OSS + 写 Image 记录
    created_images: list[Image] = []
    for file in files:
        file_data = await file.read()
        content_type = file.content_type or "application/octet-stream"
        file_key = await storage.upload(file_data, file.filename or "untitled", content_type)

        image = Image(
            file_key=file_key,
            file_name=file.filename,
            content_type=content_type,
            file_size=len(file_data),
        )
        for tag_obj in tag_objs:
            image.tags.append(tag_obj)

        db.add(image)
        created_images.append(image)

    db.commit()
    for img in created_images:
        db.refresh(img)

    # 构建响应（含签名 URL）
    result: list[ImageResponse] = []
    for img in created_images:
        url = await storage.get_signed_url(img.file_key)
        result.append(
            ImageResponse(
                id=img.id,
                file_key=img.file_key,
                file_name=img.file_name,
                content_type=img.content_type,
                file_size=img.file_size,
                uploaded_at=img.uploaded_at,
                url=url,
                tags=[TagResponse.model_validate(t) for t in img.tags],
            )
        )

    return ImageListResponse(images=result, total=len(result))


@router.delete("/images/{image_id}", status_code=204)
async def delete_image_view(
    image_id: int,
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """删除图片：先从 OSS 删除对象，再删数据库记录。"""
    image = db.query(Image).filter(Image.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="图片不存在")

    # 先尝试 OSS 删除（best-effort）
    try:
        await storage.delete(image.file_key)
    except Exception:
        logger.warning("OSS 删除失败 (file_key=%s)", image.file_key, exc_info=True)

    db.delete(image)
    db.commit()
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════════
# Album Settings
# ═══════════════════════════════════════════════════════════════════════════


@router.put("/album-password")
async def update_album_password_view(
    body: AlbumPasswordUpdate, db: Session = Depends(get_db)
):
    """修改相册密码。"""
    update_album_password(db, body.password)
    return {"message": "相册密码已更新"}
