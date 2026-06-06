"""学生 API 集成测试 — Phase 5。

测试覆盖：
- 双重认证（相册密码 + 姓名/密钥）
- 隐私隔离照片流（Tag 名称匹配）
- my-tags 去重逻辑
- 认证守卫

关键约束（必须严格遵守）：
1. StaticPool + check_same_thread=False 确保 SQLite :memory: 连接共享。
2. AsyncMock 替换 get_storage_service，绝不发起真实网络请求。
"""

import io
import os
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, get_db
from app.dependencies import get_storage_service
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.student import router as student_router
from app.services.aliyun_oss_storage import AliyunOssStorageService


# ============================================================================
# Helpers
# ============================================================================


def _admin_auth(client: TestClient, password: str = "adminpass") -> dict[str, str]:
    """管理员登录，返回 Authorization header。"""
    resp = client.post("/api/admin/auth", json={"password": password})
    assert resp.status_code == 200, f"Admin auth failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _student_auth(
    client: TestClient,
    album_password: str = "adminpass",
    name: str = "张三",
    secret_key: str = "",
) -> dict[str, str]:
    """学生登录，返回 Authorization header。"""
    resp = client.post(
        "/api/student/auth",
        json={
            "album_password": album_password,
            "name": name,
            "secret_key": secret_key,
        },
    )
    assert resp.status_code == 200, f"Student auth failed: {resp.status_code} {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def db_engine():
    """内存 SQLite 引擎 — StaticPool 确保 Session 共享同一数据库。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def mock_storage():
    """Mock 存储服务 — 绝不发起真实网络请求。

    每次 upload 返回不同的 file_key 以避免 UNIQUE 约束冲突。
    """
    storage = AsyncMock(spec=AliyunOssStorageService)

    _counter = 0

    async def _upload(*args, **kwargs):
        nonlocal _counter
        _counter += 1
        return f"images/test_uuid_{_counter:04d}.jpg"

    async def _get_signed_url(file_key, *args, **kwargs):
        return f"https://fake-oss.example.com/signed/{file_key}?sign=mock"

    async def _get_thumbnail_signed_url(file_key, *args, **kwargs):
        return f"https://fake-oss.example.com/thumb/{file_key}?sign=mock_thumb"

    storage.upload.side_effect = _upload
    storage.get_signed_url.side_effect = _get_signed_url
    storage.get_thumbnail_signed_url.side_effect = _get_thumbnail_signed_url
    storage.delete.return_value = True
    storage.exists.return_value = True
    return storage


@pytest.fixture(scope="function")
def test_app(db_engine, mock_storage):
    """创建含学生/管理员/认证路由的测试 FastAPI 应用。"""
    app = FastAPI()

    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(student_router)

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    # ── V2.0: 创建默认标签分组（确保测试中 Tag 创建不报错）───
    with TestingSessionLocal() as session:
        from app.models.tag_group import TagGroup
        if not session.query(TagGroup).filter_by(name="未分类").first():
            session.add(TagGroup(name="未分类"))
            session.commit()
    # ────────────────────────────────────────────────────

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    return app


@pytest.fixture(scope="function")
def client(test_app):
    return TestClient(test_app)


# ============================================================================
# 辅助：通过管理员接口准备完整测试数据
# ============================================================================


def _setup_student(client, admin_headers, name):
    """通过管理员接口创建学生，返回 (student_id, secret_key)。"""
    resp = client.post(
        "/api/admin/students", json={"names": name}, headers=admin_headers
    )
    assert resp.status_code == 201
    data = resp.json()
    return data[0]["id"], data[0]["secret_key"]


def _setup_tag(client, admin_headers, name):
    """通过管理员接口创建标签，返回 tag_id。幂等：若已存在则查询返回。"""
    # 先查是否已存在（student 创建时会自动创建同名 tag）
    resp = client.get("/api/admin/tags", headers=admin_headers)
    if resp.status_code == 200:
        for t in resp.json():
            if t["name"] == name:
                return t["id"]

    # 不存在则创建
    resp = client.post(
        "/api/admin/tags", json={"name": name}, headers=admin_headers
    )
    assert resp.status_code in (201, 409), f"Unexpected tag status: {resp.status_code}"
    if resp.status_code == 201:
        return resp.json()["id"]
    # 409 冲突：再次查询
    resp = client.get("/api/admin/tags", headers=admin_headers)
    for t in resp.json():
        if t["name"] == name:
            return t["id"]
    pytest.fail(f"Tag '{name}' not found after 409 conflict")


def _upload_fake_image(client, admin_headers, filename, content_type, tags_json):
    """通过管理员接口上传模拟图片，返回 image 数据。"""
    fake_data = io.BytesIO(b"fake-image-bytes")
    resp = client.post(
        "/api/admin/images",
        data={"tags": tags_json},
        files=[("files", (filename, fake_data, content_type))],
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.json()["images"][0]


# ============================================================================
# Auth Tests
# ============================================================================


class TestStudentAuth:
    """学生双重认证接口测试。"""

    def test_login_success(self, client):
        """正确的相册密码 + 姓名 + 密钥 → 返回 JWT。"""
        admin_headers = _admin_auth(client)
        sid, secret = _setup_student(client, admin_headers, "张三")

        resp = client.post(
            "/api/student/auth",
            json={"album_password": "adminpass", "name": "张三", "secret_key": secret},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_album_password(self, client):
        """相册密码错误 → 401。"""
        admin_headers = _admin_auth(client)
        _sid, secret = _setup_student(client, admin_headers, "张三")

        resp = client.post(
            "/api/student/auth",
            json={"album_password": "wrongpass", "name": "张三", "secret_key": secret},
        )
        assert resp.status_code == 401
        assert "相册密码错误" in resp.json()["detail"]

    def test_login_wrong_name_or_key(self, client):
        """姓名或密钥错误 → 401。"""
        admin_headers = _admin_auth(client)
        _sid, secret = _setup_student(client, admin_headers, "张三")

        # 错误的姓名
        resp = client.post(
            "/api/student/auth",
            json={
                "album_password": "adminpass",
                "name": "李四",
                "secret_key": secret,
            },
        )
        assert resp.status_code == 401
        assert "姓名或密钥错误" in resp.json()["detail"]

        # 错误的密钥
        resp = client.post(
            "/api/student/auth",
            json={
                "album_password": "adminpass",
                "name": "张三",
                "secret_key": "WRONGK",
            },
        )
        assert resp.status_code == 401
        assert "姓名或密钥错误" in resp.json()["detail"]


# ============================================================================
# Privacy Isolation Tests
# ============================================================================


class TestPrivacyIsolation:
    """隐私隔离核心逻辑测试 — 张三看不到李四的专属照片。"""

    @pytest.fixture(autouse=True)
    def _setup_data(self, client):
        """通过管理员接口准备两个学生、两个标签、两张照片。"""
        self.admin_headers = _admin_auth(client)

        # 创建学生
        self.zhang_id, self.zhang_key = _setup_student(
            client, self.admin_headers, "张三"
        )
        self.li_id, self.li_key = _setup_student(
            client, self.admin_headers, "李四"
        )

        # 创建标签
        _setup_tag(client, self.admin_headers, "张三")
        _setup_tag(client, self.admin_headers, "李四")

        # 上传照片：张三专属
        self.img_zhang = _upload_fake_image(
            client, self.admin_headers,
            "zhang_only.jpg", "image/jpeg",
            '["张三"]',
        )

        # 上传照片：张三+李四合照
        self.img_shared = _upload_fake_image(
            client, self.admin_headers,
            "zhang_li_together.png", "image/png",
            '["张三","李四"]',
        )

        self.client = client

    # ── 帮助方法 ──

    def _get_student_images(self, name, secret_key):
        """以学生身份登录并获取 my-images。"""
        headers = _student_auth(
            self.client,
            album_password="adminpass",
            name=name,
            secret_key=secret_key,
        )
        resp = self.client.get("/api/student/my-images", headers=headers)
        assert resp.status_code == 200
        return resp.json()

    def _image_file_names(self, data):
        return {img["file_name"] for img in data["images"]}

    # ── 测试 ──

    def test_zhang_san_sees_own_and_shared(self):
        """张三能看到自己的专属照片和与李四的合照。"""
        data = self._get_student_images("张三", self.zhang_key)
        assert data["total"] == 2
        file_names = self._image_file_names(data)
        assert "zhang_only.jpg" in file_names
        assert "zhang_li_together.png" in file_names

    def test_li_si_sees_only_shared(self):
        """李四只能看到合照，看不到张三的专属照片。"""
        data = self._get_student_images("李四", self.li_key)
        assert data["total"] == 1
        file_names = self._image_file_names(data)
        assert "zhang_only.jpg" not in file_names
        assert "zhang_li_together.png" in file_names

    def test_images_have_signed_urls(self):
        """返回的每个 ImageResponse 都包含临时签名 url 和缩略图 url。"""
        data = self._get_student_images("张三", self.zhang_key)
        for img in data["images"]:
            assert img["url"].startswith("https://fake-oss")
            assert img.get("thumbnail_url", "").startswith("https://fake-oss")
            assert "file_key" in img
            assert "tags" in img

    def test_student_with_no_photos_gets_empty_list(self, client):
        """没有对应照片的学生返回空列表。"""
        admin_headers = _admin_auth(client)
        sid, secret = _setup_student(client, admin_headers, "王五")  # 无对应 Tag

        headers = _student_auth(client, name="王五", secret_key=secret)
        resp = client.get("/api/student/my-images", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["images"] == []


# ============================================================================
# My-Tags Tests
# ============================================================================


class TestMyTags:
    """my-tags 去重逻辑测试。"""

    @pytest.fixture(autouse=True)
    def _setup_data(self, client):
        self.admin_headers = _admin_auth(client)

        _sid, self.zhang_key = _setup_student(client, self.admin_headers, "张三")
        _sid, self.li_key = _setup_student(client, self.admin_headers, "李四")

        _setup_tag(client, self.admin_headers, "张三")
        _setup_tag(client, self.admin_headers, "李四")
        _setup_tag(client, self.admin_headers, "毕业典礼")

        # 张三的专属照片（含"毕业典礼"标签）
        _upload_fake_image(
            client, self.admin_headers,
            "zhang_grad.jpg", "image/jpeg",
            '["张三","毕业典礼"]',
        )

        # 张三+李四合照（含"毕业典礼"标签）
        _upload_fake_image(
            client, self.admin_headers,
            "group.jpg", "image/jpeg",
            '["张三","李四","毕业典礼"]',
        )

        self.client = client

    def test_my_tags_deduplicated(self, client):
        """my-tags 应包含去重后的所有标签（含'毕业典礼'）。"""
        headers = _student_auth(client, name="张三", secret_key=self.zhang_key)
        resp = client.get("/api/student/my-tags", headers=headers)
        assert resp.status_code == 200
        tags = resp.json()
        tag_names = {t["name"] for t in tags}
        assert tag_names == {"张三", "李四", "毕业典礼"}

    def test_my_tags_for_li_si(self, client):
        """李四只能看到合照上的标签，不包含张三的专属照片标签。"""
        headers = _student_auth(client, name="李四", secret_key=self.li_key)
        resp = client.get("/api/student/my-tags", headers=headers)
        assert resp.status_code == 200
        tags = resp.json()
        tag_names = {t["name"] for t in tags}
        # 李四看不到张三专属的那张（仅"张三"+"毕业典礼"），只能看到合照
        assert tag_names == {"张三", "李四", "毕业典礼"}

    def test_my_tags_for_student_without_photos(self, client):
        """没有可见照片的学生返回空标签列表。"""
        admin_headers = _admin_auth(client)
        _sid, secret = _setup_student(client, admin_headers, "王五")

        headers = _student_auth(client, name="王五", secret_key=secret)

        resp = client.get("/api/student/my-tags", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []


# ============================================================================
# Auth Guard Tests
# ============================================================================


class TestStudentAuthGuard:
    """学生路由认证守卫测试。"""

    def test_my_images_requires_auth_401(self, client):
        """无 token 访问 my-images → 401。"""
        resp = client.get("/api/student/my-images")
        assert resp.status_code == 401

    def test_my_tags_requires_auth_401(self, client):
        """无 token 访问 my-tags → 401。"""
        resp = client.get("/api/student/my-tags")
        assert resp.status_code == 401

    def test_admin_token_rejected_403(self, client):
        """Admin token 访问 student 路由 → 403。"""
        admin_headers = _admin_auth(client)
        resp = client.get("/api/student/my-images", headers=admin_headers)
        assert resp.status_code == 403
