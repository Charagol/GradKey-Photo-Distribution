"""管理员 API 集成测试 — Phase 4。

关键约束（必须严格遵守）：
1. SQLite :memory: 必须使用 StaticPool + check_same_thread=False，
   否则 FastAPI 路由拿到的 Session 会是空数据库。
2. 存储服务必须用 AsyncMock 替换，绝不发起真实 OSS 网络请求。
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

# 确保项目根目录在 sys.path 中，以便导入 app 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base, get_db
from app.dependencies import get_storage_service
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.services.aliyun_oss_storage import AliyunOssStorageService


# ============================================================================
# Helpers
# ============================================================================


def _admin_auth(client: TestClient, password: str = "testpass") -> dict[str, str]:
    """调用认证接口并返回 Authorization header。"""
    resp = client.post("/api/admin/auth", json={"password": password})
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="function")
def db_engine():
    """内存 SQLite 引擎 — 使用 StaticPool 确保所有连接共享同一数据库。

    关键：不加 poolclass=StaticPool 会导致 FastAPI 依赖注入拿到的
    Session 连到一个空数据库（"no such table" 错误）。
    """
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
    """Mock 存储服务 — 绝不发起真实网络请求。"""
    storage = AsyncMock(spec=AliyunOssStorageService)
    storage.upload.return_value = "images/test_uuid_abc123.jpg"
    storage.get_signed_url.return_value = "https://fake-oss.example.com/signed/test_uuid_abc123.jpg?sign=mock"
    storage.delete.return_value = True
    storage.exists.return_value = True
    return storage


@pytest.fixture(scope="function")
def test_app(db_engine, mock_storage):
    """创建带依赖覆盖的测试用 FastAPI 应用。"""
    app = FastAPI()

    # CORS 在集成测试中无需配置
    app.include_router(auth_router)
    app.include_router(admin_router)

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
# Auth Tests
# ============================================================================


class TestAdminAuth:
    """管理员认证接口测试。"""

    def test_auth_first_time_setup(self, client):
        """AlbumConfig 为空时首次请求即设置密码并返回 token。"""
        resp = client.post("/api/admin/auth", json={"password": "firstpass"})
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_auth_correct_password(self, client):
        """已设密码后正确密码登录成功。"""
        client.post("/api/admin/auth", json={"password": "mypass"})
        # 再次用同一密码登录
        resp = client.post("/api/admin/auth", json={"password": "mypass"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_auth_wrong_password_401(self, client):
        """错误密码返回 401。"""
        client.post("/api/admin/auth", json={"password": "correct"})
        resp = client.post("/api/admin/auth", json={"password": "wrong"})
        assert resp.status_code == 401
        assert "密码错误" in resp.json()["detail"]


# ============================================================================
# Student Tests
# ============================================================================


class TestStudentAPI:
    """学生 CRUD 接口测试。"""

    def test_create_and_list_students(self, client):
        """创建学生后列表应包含该学生，且含 secret_key。"""
        headers = _admin_auth(client)
        resp = client.post(
            "/api/admin/students", json={"name": "张三"}, headers=headers
        )
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "张三"
        assert len(created["secret_key"]) == 6

        # 列表
        resp = client.get("/api/admin/students", headers=headers)
        assert resp.status_code == 200
        students = resp.json()
        assert any(s["name"] == "张三" for s in students)

    def test_update_student_name(self, client):
        """修改学生姓名后返回新名字。"""
        headers = _admin_auth(client)
        create_resp = client.post(
            "/api/admin/students", json={"name": "李四"}, headers=headers
        )
        sid = create_resp.json()["id"]

        resp = client.put(
            f"/api/admin/students/{sid}", json={"name": "李四丰"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "李四丰"

    def test_delete_student_204(self, client):
        """删除学生返回 204，GET 列表不再包含。"""
        headers = _admin_auth(client)
        create_resp = client.post(
            "/api/admin/students", json={"name": "王五"}, headers=headers
        )
        sid = create_resp.json()["id"]

        resp = client.delete(f"/api/admin/students/{sid}", headers=headers)
        assert resp.status_code == 204

        # 验证已不在列表
        resp = client.get("/api/admin/students", headers=headers)
        students = resp.json()
        assert not any(s["id"] == sid for s in students)

    def test_reset_student_key(self, client):
        """重置密钥后新旧值不同。"""
        headers = _admin_auth(client)
        create_resp = client.post(
            "/api/admin/students", json={"name": "赵六"}, headers=headers
        )
        sid = create_resp.json()["id"]
        old_key = create_resp.json()["secret_key"]

        resp = client.post(
            f"/api/admin/students/{sid}/reset-key", headers=headers
        )
        assert resp.status_code == 200
        new_key = resp.json()["new_key"]
        assert new_key != old_key
        assert len(new_key) == 6

    def test_student_not_found_404(self, client):
        """操作不存在的学生返回 404。"""
        headers = _admin_auth(client)
        resp = client.put(
            "/api/admin/students/99999", json={"name": "无名"}, headers=headers
        )
        assert resp.status_code == 404

        resp = client.delete("/api/admin/students/99999", headers=headers)
        assert resp.status_code == 404

        resp = client.post("/api/admin/students/99999/reset-key", headers=headers)
        assert resp.status_code == 404


# ============================================================================
# Tag Tests
# ============================================================================


class TestTagAPI:
    """标签 CRUD 接口测试。"""

    def test_create_and_delete_tag(self, client):
        """创建标签 → 列表包含 → 删除 → 列表不包含。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/tags", json={"name": "张三"}, headers=headers
        )
        assert resp.status_code == 201
        tid = resp.json()["id"]

        resp = client.get("/api/admin/tags", headers=headers)
        assert any(t["name"] == "张三" for t in resp.json())

        resp = client.delete(f"/api/admin/tags/{tid}", headers=headers)
        assert resp.status_code == 204

        resp = client.get("/api/admin/tags", headers=headers)
        assert not any(t["id"] == tid for t in resp.json())

    def test_duplicate_tag_409(self, client):
        """重复标签名返回 409。"""
        headers = _admin_auth(client)
        client.post("/api/admin/tags", json={"name": "重复标签"}, headers=headers)
        resp = client.post(
            "/api/admin/tags", json={"name": "重复标签"}, headers=headers
        )
        assert resp.status_code == 409


# ============================================================================
# Image Tests
# ============================================================================


class TestImageAPI:
    """图片管理接口测试（Mock OSS）。"""

    def test_list_images_initially_empty(self, client):
        """初始图片列表为空。"""
        headers = _admin_auth(client)
        resp = client.get("/api/admin/images", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["images"] == []

    def test_upload_image_with_tags(self, client):
        """上传图片并关联标签，响应含 url 和 tags。"""
        headers = _admin_auth(client)

        # 先创建标签
        client.post("/api/admin/tags", json={"name": "张三"}, headers=headers)
        client.post("/api/admin/tags", json={"name": "李四"}, headers=headers)

        # 上传图片
        fake_jpeg = io.BytesIO(b"\xff\xd8\xff\x00\x01fake-jpeg-data")
        resp = client.post(
            "/api/admin/images",
            data={"tags": '["张三","李四"]'},
            files=[("files", ("photo.jpg", fake_jpeg, "image/jpeg"))],
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        img = data["images"][0]
        assert img["file_name"] == "photo.jpg"
        assert img["url"].startswith("https://fake-oss")
        # TagResponse.model_validate 会正确转换
        tag_names = [t["name"] for t in img["tags"]]
        assert "张三" in tag_names
        assert "李四" in tag_names

    def test_delete_image_from_db(self, client):
        """删除图片后 GET 列表不再包含。"""
        headers = _admin_auth(client)

        fake_png = io.BytesIO(b"\x89PNG\r\n\x1a\nfake-png-data")
        resp = client.post(
            "/api/admin/images",
            files=[("files", ("test.png", fake_png, "image/png"))],
            headers=headers,
        )
        assert resp.status_code == 201
        img_id = resp.json()["images"][0]["id"]

        resp = client.delete(f"/api/admin/images/{img_id}", headers=headers)
        assert resp.status_code == 204

        resp = client.get("/api/admin/images", headers=headers)
        data = resp.json()
        assert not any(i["id"] == img_id for i in data["images"])


# ============================================================================
# Settings Tests
# ============================================================================


class TestAlbumSettings:
    """相册设置接口测试。"""

    def test_update_album_password(self, client):
        """更新密码后新密码生效，旧密码失效。"""
        headers = _admin_auth(client, password="oldpass")

        # 修改密码
        resp = client.put(
            "/api/admin/album-password",
            json={"password": "newpass"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert "已更新" in resp.json()["message"]

        # 新密码可登录
        resp = client.post("/api/admin/auth", json={"password": "newpass"})
        assert resp.status_code == 200

        # 旧密码失效
        resp = client.post("/api/admin/auth", json={"password": "oldpass"})
        assert resp.status_code == 401


# ============================================================================
# Auth Guard Tests
# ============================================================================


class TestAuthGuard:
    """认证守卫测试 — 验证所有管理员路由受 JWT 保护。"""

    def test_admin_route_requires_auth_401(self, client):
        """无 token 访问管理员路由返回 401。"""
        resp = client.get("/api/admin/students")
        assert resp.status_code == 401

        resp = client.get("/api/admin/tags")
        assert resp.status_code == 401

        resp = client.get("/api/admin/images")
        assert resp.status_code == 401
