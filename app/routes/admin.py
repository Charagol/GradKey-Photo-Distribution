"""管理员路由 — 学生 / 标签 / 标签分组 / 图片 / 相册设置的 CRUD API。

所有接口均受 get_current_admin JWT 中间件保护。
Image 资源通过 IStorageService 管理阿里云 OSS 文件。
"""

import csv
import io
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_storage_service
from app.middleware.jwt_middleware import get_current_admin
from app.models.image import Image
from app.models.tag import Tag
from app.models.tag_group import DEFAULT_TAG_GROUP_NAME, TagGroup
from app.schemas.admin import (
    DashboardStatsResponse,
    ImageBatchDeleteRequest,
    ImageListResponse,
    ImageResponse,
    ImageTagUpdate,
    StudentCreate,
    StudentResponse,
    StudentUpdate,
    TagCreate,
    TagGroupCreate,
    TagGroupResponse,
    TagGroupUpdate,
    TagResponse,
    TagUpdate,
)
from app.schemas.auth import AlbumPasswordUpdate
from app.services.aliyun_oss_storage import AliyunOssStorageService
from app.services.auth_service import update_album_password
from app.services.student_service import (
    create_student,
    delete_student,
    generate_secret_key,
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


@router.post("/students", response_model=list[StudentResponse], status_code=201)
async def create_students_view(body: StudentCreate, db: Session = Depends(get_db)):
    """创建学生，支持逗号分隔批量导入，自动为每个学生创建同名 Tag。

    V2.0 统一端点:
    - 单人: {"names": "张三"}
    - 多人: {"names": "张三,李四,王五"}
    - 重复 Tag 名静默跳过（不报错）
    - 整个操作在同一事务中完成，all-or-nothing
    """
    # 解析、去重、验证
    raw_names = [n.strip() for n in body.names.split("，") if n.strip()]
    seen: set[str] = set()
    names: list[str] = []
    for n in raw_names:
        if n not in seen:
            seen.add(n)
            names.append(n)

    if not names:
        raise HTTPException(status_code=400, detail="至少需要提供一个姓名")

    created_students: list = []
    try:
        for name in names:
            # 创建学生（暂不提交）
            student = create_student(db, name, auto_commit=False)
            created_students.append(student)

            # 自动创建同名 Tag（若已存在则跳过）
            existing_tag = db.query(Tag).filter(Tag.name == name).first()
            if not existing_tag:
                tag = Tag(name=name)  # before_insert 自动归入"未分类"
                db.add(tag)

        db.commit()
        for s in created_students:
            db.refresh(s)
    except Exception:
        db.rollback()
        raise

    return created_students


@router.get("/students/export")
async def export_students_csv(db: Session = Depends(get_db)):
    """导出学生名单为 CSV 文件（姓名,密钥）。

    注意：此路由必须在 /students/{student_id} 之前注册，
    否则 FastAPI 将 "export" 匹配为 student_id 路径参数。
    """
    students = list_students(db)

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    for s in students:
        writer.writerow([s.name, s.secret_key])

    csv_content = output.getvalue()
    output.close()

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=\"students_export.csv\""},
    )


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
async def dashboard_stats(db: Session = Depends(get_db)):
    """返回管理端仪表盘统计数据：照片数、学生数、标签数、分组数、存储占用。

    storage_bytes 由 Image.file_size 字段 SUM 计算，不回源 OSS。
    """
    from app.models.image import Image
    from app.models.student import Student
    from app.models.tag import Tag
    from app.models.tag_group import TagGroup

    photo_count = db.query(Image).count()
    student_count = db.query(Student).count()
    tag_count = db.query(Tag).count()
    tag_group_count = db.query(TagGroup).count()
    storage_bytes = db.query(func.coalesce(func.sum(Image.file_size), 0)).scalar()

    return DashboardStatsResponse(
        photo_count=photo_count,
        student_count=student_count,
        tag_count=tag_count,
        tag_group_count=tag_group_count,
        storage_bytes=storage_bytes,
    )


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


@router.put("/tags/{tag_id}", response_model=TagResponse)
async def update_tag_view(tag_id: int, body: TagUpdate, db: Session = Depends(get_db)):
    """修改标签所属分组。"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if tag is None:
        raise HTTPException(status_code=404, detail="标签不存在")

    group = db.query(TagGroup).filter(TagGroup.id == body.group_id).first()
    if group is None:
        raise HTTPException(status_code=400, detail="分组不存在")

    tag.group_id = group.id
    db.commit()
    db.refresh(tag)
    return tag


# ═══════════════════════════════════════════════════════════════════════════
# TagGroup CRUD
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/tag-groups", response_model=list[TagGroupResponse])
async def list_tag_groups_view(db: Session = Depends(get_db)):
    """列出所有标签分组（含嵌套的标签列表）。"""
    return db.query(TagGroup).order_by(TagGroup.id).all()


@router.post("/tag-groups", response_model=TagGroupResponse, status_code=201)
async def create_tag_group_view(body: TagGroupCreate, db: Session = Depends(get_db)):
    """创建标签分组。"""
    existing = db.query(TagGroup).filter(TagGroup.name == body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="分组已存在")
    group = TagGroup(name=body.name)
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.put("/tag-groups/{group_id}", response_model=TagGroupResponse)
async def update_tag_group_view(
    group_id: int, body: TagGroupUpdate, db: Session = Depends(get_db)
):
    """重命名标签分组。"""
    group = db.query(TagGroup).filter(TagGroup.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="分组不存在")

    # 检查新名称是否被其他分组占用
    conflict = (
        db.query(TagGroup)
        .filter(TagGroup.name == body.name, TagGroup.id != group_id)
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="分组名已存在")

    group.name = body.name
    db.commit()
    db.refresh(group)
    return group


@router.delete("/tag-groups/{group_id}", status_code=204)
async def delete_tag_group_view(group_id: int, db: Session = Depends(get_db)):
    """删除标签分组，组内 Tag 迁移至"未分类"。

    禁止删除默认"未分类"分组。
    """
    group = db.query(TagGroup).filter(TagGroup.id == group_id).first()
    if group is None:
        raise HTTPException(status_code=404, detail="分组不存在")
    if group.name == DEFAULT_TAG_GROUP_NAME:
        raise HTTPException(status_code=400, detail="不能删除默认'未分类'分组")

    # 查找/创建默认分组（防御性）
    default_group = (
        db.query(TagGroup)
        .filter(TagGroup.name == DEFAULT_TAG_GROUP_NAME)
        .first()
    )
    if default_group is None:
        default_group = TagGroup(name=DEFAULT_TAG_GROUP_NAME)
        db.add(default_group)
        db.flush()

    default_group_id = default_group.id

    # 将该分组下的所有 Tag 迁移至默认分组（绕过 ORM 避免 session 状态冲突）
    db.query(Tag).filter(Tag.group_id == group_id).update(
        {Tag.group_id: default_group_id}, synchronize_session=False
    )

    # 清除 session 缓存（防止 ORM 用过期状态复写迁移结果）
    db.expire_all()

    db.delete(group)
    db.commit()
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════════════════
# Image Management
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/images", response_model=ImageListResponse)
async def list_images_view(
    tagged: bool | None = None,
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """列出图片，动态注入临时签名 URL。

    V2.0 tagged 参数:
    - None (默认): 返回全部图片
    - true: 仅返回已有标签的图片
    - false: 仅返回未打标的图片（沉浸式打标工作台未处理池）
    """
    query = db.query(Image)
    if tagged is True:
        query = query.filter(Image.tags.any())
    elif tagged is False:
        query = query.filter(~Image.tags.any())

    images = query.order_by(Image.uploaded_at.desc()).all()
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


@router.delete("/images/batch", status_code=204)
async def batch_delete_images_view(
    body: ImageBatchDeleteRequest,
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """批量删除图片 — V3.0 Phase 22。

    事务包裹：所有 DB 操作在单一事务中，all-or-nothing。
    OSS 删除 best-effort（单张失败不影响整体）。
    """
    if not body.image_ids:
        raise HTTPException(status_code=400, detail="image_ids 不能为空")

    # 验证所有 ID 存在
    images = db.query(Image).filter(Image.id.in_(body.image_ids)).all()
    found_ids = {img.id for img in images}
    missing = set(body.image_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"图片不存在: {sorted(missing)}",
        )

    # OSS 删除（best-effort）+ DB 删除
    for img in images:
        try:
            await storage.delete(img.file_key)
        except Exception:
            logger.warning("OSS 批量删除失败 (file_key=%s)", img.file_key, exc_info=True)
        db.delete(img)

    db.commit()
    return Response(status_code=204)


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


@router.put("/images/{image_id}/tags", response_model=ImageResponse)
async def update_image_tags_view(
    image_id: int,
    body: ImageTagUpdate,
    db: Session = Depends(get_db),
    storage: AliyunOssStorageService = Depends(get_storage_service),
):
    """编辑图片标签 — 全量替换。

    V2.0 沉浸式打标核心接口:
    - 传入 tag_ids 列表，完全替换该图片的标签关联
    - 传入空列表可清空所有标签
    """
    image = db.query(Image).filter(Image.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail="图片不存在")

    # 验证所有 tag_id 有效
    if body.tag_ids:
        tags = db.query(Tag).filter(Tag.id.in_(body.tag_ids)).all()
        found_ids = {t.id for t in tags}
        requested_ids = set(body.tag_ids)
        if found_ids != requested_ids:
            missing = requested_ids - found_ids
            raise HTTPException(
                status_code=400, detail=f"标签不存在: {sorted(missing)}"
            )
    else:
        tags = []

    # SQLAlchemy M:N collection replace — 自动管理 image_tags 表
    image.tags = tags
    db.commit()
    db.refresh(image)

    url = await storage.get_signed_url(image.file_key)
    return ImageResponse(
        id=image.id,
        file_key=image.file_key,
        file_name=image.file_name,
        content_type=image.content_type,
        file_size=image.file_size,
        uploaded_at=image.uploaded_at,
        url=url,
        tags=[TagResponse.model_validate(t) for t in image.tags],
    )


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
