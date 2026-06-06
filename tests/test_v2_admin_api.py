"""Phase 10 — V2.0 管理端 API 集成测试。

测试覆盖：
- TagGroup CRUD (GET/POST/PUT/DELETE) + 嵌套标签 + 删除迁移策略
- 批量学生创建 (统一端点 + 自动标签 + 去重)
- 图片标签全量替换 (PUT /images/{id}/tags)
- 图片 tagged 过滤 (GET /images?tagged=true|false)
- Tag 分组移动 (PUT /tags/{id})

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
from app.services.aliyun_oss_storage import AliyunOssStorageService


# ============================================================================
# Helpers
# ============================================================================


def _admin_auth(client: TestClient, password: str = "testpass") -> dict[str, str]:
    """管理员登录，返回 Authorization header。"""
    resp = client.post("/api/admin/auth", json={"password": password})
    assert resp.status_code == 200, f"Auth failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_tag(client, admin_headers, name):
    """创建标签（幂等），返回 tag 数据字典。"""
    # 先查是否已存在
    resp = client.get("/api/admin/tags", headers=admin_headers)
    for t in resp.json():
        if t["name"] == name:
            return t

    resp = client.post("/api/admin/tags", json={"name": name}, headers=admin_headers)
    assert resp.status_code in (201, 409), f"Tag create failed: {resp.text}"
    if resp.status_code == 201:
        return resp.json()
    # 409 冲突，重新查询
    resp = client.get("/api/admin/tags", headers=admin_headers)
    for t in resp.json():
        if t["name"] == name:
            return t
    pytest.fail(f"Tag '{name}' not found after 409")


def _upload_image(client, admin_headers, filename, tags_json):
    """上传单张图片，返回 image 数据字典。"""
    fake_data = io.BytesIO(b"fake-image-bytes")
    resp = client.post(
        "/api/admin/images",
        data={"tags": tags_json} if tags_json else {},
        files=[("files", (filename, fake_data, "image/jpeg"))],
        headers=admin_headers,
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    return resp.json()["images"][0]


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
        return f"images/test_uuid_v2_{_counter:04d}.jpg"

    async def _get_signed_url(file_key, *args, **kwargs):
        return f"https://fake-oss.example.com/signed/{file_key}?sign=mock"

    async def _get_thumbnail_signed_url(file_key, *args, **kwargs):
        return f"https://fake-oss.example.com/thumb/{file_key}?x-oss-process=image%2Fresize%2Cm_lfit%2Cw_400%2Ch_400&sign=mock"

    storage.upload.side_effect = _upload
    storage.get_signed_url.side_effect = _get_signed_url
    storage.get_thumbnail_signed_url.side_effect = _get_thumbnail_signed_url
    storage.delete.return_value = True
    storage.exists.return_value = True
    return storage


@pytest.fixture(scope="function")
def test_app(db_engine, mock_storage):
    """创建含认证+管理路由的测试 FastAPI 应用。"""
    app = FastAPI()

    app.include_router(auth_router)
    app.include_router(admin_router)

    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )

    # V2.0: 创建默认标签分组
    with TestingSessionLocal() as session:
        from app.models.tag_group import TagGroup
        if not session.query(TagGroup).filter_by(name="未分类").first():
            session.add(TagGroup(name="未分类"))
            session.commit()

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
# TagGroup CRUD Tests
# ============================================================================


class TestTagGroupAPI:
    """标签分组 CRUD 接口测试。"""

    def test_create_tag_group(self, client):
        """创建分组 → 201 且列表包含。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/tag-groups", json={"name": "年级"}, headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "年级"
        assert data["tags"] == []

        # 验证列表
        resp = client.get("/api/admin/tag-groups", headers=headers)
        assert resp.status_code == 200
        names = [g["name"] for g in resp.json()]
        assert "年级" in names

    def test_list_tag_groups_with_nested_tags(self, client):
        """分组列表应包含嵌套的标签。"""
        headers = _admin_auth(client)

        # 创建分组
        client.post("/api/admin/tag-groups", json={"name": "年级"}, headers=headers)

        # 在默认分组下创建标签
        _create_tag(client, headers, "张三")
        _create_tag(client, headers, "李四")

        resp = client.get("/api/admin/tag-groups", headers=headers)
        assert resp.status_code == 200
        groups = resp.json()

        # 默认分组应包含"张三"和"李四"
        default_group = next(g for g in groups if g["name"] == "未分类")
        tag_names = {t["name"] for t in default_group["tags"]}
        assert "张三" in tag_names
        assert "李四" in tag_names

        # "年级"分组应为空
        grade_group = next(g for g in groups if g["name"] == "年级")
        assert grade_group["tags"] == []

    def test_update_tag_group_rename(self, client):
        """重命名分组 → 200。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/tag-groups", json={"name": "年级"}, headers=headers
        )
        gid = resp.json()["id"]

        resp = client.put(
            f"/api/admin/tag-groups/{gid}",
            json={"name": "班级"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "班级"

    def test_delete_tag_group_tags_migrate(self, client):
        """删除分组 → 组内 Tag 迁移至'未分类'。"""
        headers = _admin_auth(client)

        # 创建新分组
        resp = client.post(
            "/api/admin/tag-groups", json={"name": "年级"}, headers=headers
        )
        group_id = resp.json()["id"]

        # 创建标签并移动到该分组
        tag = _create_tag(client, headers, "小明")
        client.put(
            f"/api/admin/tags/{tag['id']}",
            json={"group_id": group_id},
            headers=headers,
        )

        # 删除分组
        resp = client.delete(
            f"/api/admin/tag-groups/{group_id}", headers=headers
        )
        assert resp.status_code == 204

        # 验证标签已迁移到默认分组
        resp = client.get("/api/admin/tags", headers=headers)
        for t in resp.json():
            if t["name"] == "小明":
                # 验证已不在原分组
                assert t["group_id"] != group_id
                break

    def test_duplicate_tag_group_409(self, client):
        """重复分组名 → 409。"""
        headers = _admin_auth(client)

        client.post("/api/admin/tag-groups", json={"name": "年级"}, headers=headers)
        resp = client.post(
            "/api/admin/tag-groups", json={"name": "年级"}, headers=headers
        )
        assert resp.status_code == 409

    def test_delete_default_group_blocked_400(self, client):
        """不能删除默认'未分类'分组。"""
        headers = _admin_auth(client)

        # 找到默认分组
        resp = client.get("/api/admin/tag-groups", headers=headers)
        default_id = next(
            g["id"] for g in resp.json() if g["name"] == "未分类"
        )

        resp = client.delete(
            f"/api/admin/tag-groups/{default_id}", headers=headers
        )
        assert resp.status_code == 400

    def test_tag_group_not_found_404(self, client):
        """操作不存在的分组 → 404。"""
        headers = _admin_auth(client)

        resp = client.put(
            "/api/admin/tag-groups/99999",
            json={"name": "不存在"},
            headers=headers,
        )
        assert resp.status_code == 404

        resp = client.delete("/api/admin/tag-groups/99999", headers=headers)
        assert resp.status_code == 404

    def test_update_tag_group_duplicate_name_409(self, client):
        """重命名为已存在的分组名 → 409。"""
        headers = _admin_auth(client)

        client.post("/api/admin/tag-groups", json={"name": "A组"}, headers=headers)
        resp = client.post("/api/admin/tag-groups", json={"name": "B组"}, headers=headers)
        bid = resp.json()["id"]

        # 将 B 组重命名为 A 组
        resp = client.put(
            f"/api/admin/tag-groups/{bid}",
            json={"name": "A组"},
            headers=headers,
        )
        assert resp.status_code == 409


# ============================================================================
# Student Batch API Tests
# ============================================================================


class TestStudentBatchAPI:
    """V2.0 批量学生创建接口测试。"""

    def test_batch_create_students(self, client):
        """逗号分隔批量创建 → 201 返回多个学生。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/students",
            json={"names": "张三，李四，王五"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 3
        names = {s["name"] for s in data}
        assert names == {"张三", "李四", "王五"}

        # 每个学生的 secret_key 均为 6 位
        for student in data:
            assert len(student["secret_key"]) == 6

    def test_batch_create_single_student(self, client):
        """单个姓名传入也返回列表。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/students",
            json={"names": "张三"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "张三"

    def test_batch_create_auto_tags(self, client):
        """创建学生时自动创建同名 Tag。"""
        headers = _admin_auth(client)

        client.post(
            "/api/admin/students",
            json={"names": "张三，李四"},
            headers=headers,
        )

        # 验证标签已自动创建
        resp = client.get("/api/admin/tags", headers=headers)
        tag_names = {t["name"] for t in resp.json()}
        assert "张三" in tag_names
        assert "李四" in tag_names

    def test_batch_create_dedup(self, client):
        """重复姓名的去重。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/students",
            json={"names": "张三，张三，李四，张三"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        # 去重后只有 2 个
        assert len(data) == 2
        names = {s["name"] for s in data}
        assert names == {"张三", "李四"}

    def test_batch_create_auto_tags_no_duplicate_409(self, client):
        """创建学生时若 Tag 已存在则静默跳过，不报 409。"""
        headers = _admin_auth(client)

        # 先手动创建标签
        _create_tag(client, headers, "张三")

        # 再创建同名学生 — 不应报 409
        resp = client.post(
            "/api/admin/students",
            json={"names": "张三"},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()[0]["name"] == "张三"

    def test_batch_create_empty_names_400(self, client):
        """空的姓名串 → 400。"""
        headers = _admin_auth(client)

        resp = client.post(
            "/api/admin/students",
            json={"names": ""},
            headers=headers,
        )
        assert resp.status_code == 400

        resp = client.post(
            "/api/admin/students",
            json={"names": "   ，   ，   "},
            headers=headers,
        )
        assert resp.status_code == 400


# ============================================================================
# Image Tag Replacement Tests
# ============================================================================


class TestImageTagReplacement:
    """图片标签全量替换接口测试。"""

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.headers = _admin_auth(client)
        self.client = client

        # 创建标签
        self.tag_a = _create_tag(client, self.headers, "张三")
        self.tag_b = _create_tag(client, self.headers, "李四")
        self.tag_c = _create_tag(client, self.headers, "王五")

    def test_replace_image_tags(self, client):
        """全量替换图片标签。"""
        # 上传图片关联 tag_a
        img = _upload_image(client, self.headers, "test.jpg", '["张三"]')
        img_id = img["id"]

        # 替换为 tag_b + tag_c
        resp = client.put(
            f"/api/admin/images/{img_id}/tags",
            json={"tag_ids": [self.tag_b["id"], self.tag_c["id"]]},
            headers=self.headers,
        )
        assert resp.status_code == 200
        tag_names = {t["name"] for t in resp.json()["tags"]}
        assert tag_names == {"李四", "王五"}
        assert "张三" not in tag_names

    def test_clear_image_tags(self, client):
        """传入空 tag_ids → 清空所有标签。"""
        img = _upload_image(client, self.headers, "test.jpg", '["张三","李四"]')
        img_id = img["id"]

        resp = client.put(
            f"/api/admin/images/{img_id}/tags",
            json={"tag_ids": []},
            headers=self.headers,
        )
        assert resp.status_code == 200
        assert resp.json()["tags"] == []

    def test_replace_tags_image_not_found_404(self, client):
        """替换不存在的图片 → 404。"""
        resp = client.put(
            "/api/admin/images/99999/tags",
            json={"tag_ids": [1]},
            headers=self.headers,
        )
        assert resp.status_code == 404

    def test_replace_tags_tag_not_found_400(self, client):
        """替换为不存在的标签 → 400。"""
        img = _upload_image(client, self.headers, "test.jpg", None)
        img_id = img["id"]

        resp = client.put(
            f"/api/admin/images/{img_id}/tags",
            json={"tag_ids": [99999]},
            headers=self.headers,
        )
        assert resp.status_code == 400


# ============================================================================
# Image Tagged Filter Tests
# ============================================================================


class TestImageTaggedFilter:
    """图片 tagged 过滤参数测试。"""

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.headers = _admin_auth(client)
        self.client = client

        # 上传带标签和不带标签的图片各一张
        _create_tag(client, self.headers, "张三")
        self.img_tagged = _upload_image(
            client, self.headers, "tagged.jpg", '["张三"]'
        )
        self.img_untagged = _upload_image(
            client, self.headers, "untagged.jpg", None
        )

    def test_images_tagged_true(self, client):
        """tagged=true → 仅返回有标签的图片。"""
        resp = client.get(
            "/api/admin/images?tagged=true", headers=self.headers
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {img["id"] for img in data["images"]}
        assert self.img_tagged["id"] in ids
        assert self.img_untagged["id"] not in ids

    def test_images_tagged_false(self, client):
        """tagged=false → 仅返回未打标的图片。"""
        resp = client.get(
            "/api/admin/images?tagged=false", headers=self.headers
        )
        assert resp.status_code == 200
        data = resp.json()
        ids = {img["id"] for img in data["images"]}
        assert self.img_untagged["id"] in ids
        assert self.img_tagged["id"] not in ids

    def test_images_no_filter(self, client):
        """不加 tagged 参数 → 返回全部图片。"""
        resp = client.get("/api/admin/images", headers=self.headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2


# ============================================================================
# Tag Move Between Groups Tests
# ============================================================================


class TestTagMoveBetweenGroups:
    """标签分组移动接口测试。"""

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.headers = _admin_auth(client)
        self.client = client

        # 创建额外分组
        resp = client.post(
            "/api/admin/tag-groups", json={"name": "年级"}, headers=self.headers
        )
        self.group_id = resp.json()["id"]

        # 创建标签（默认在"未分类"）
        self.tag = _create_tag(client, self.headers, "张三")

    def test_move_tag_to_group(self, client):
        """将标签移动到其他分组。"""
        resp = client.put(
            f"/api/admin/tags/{self.tag['id']}",
            json={"group_id": self.group_id},
            headers=self.headers,
        )
        assert resp.status_code == 200
        assert resp.json()["group_id"] == self.group_id

        # 验证标签分组列表中的变更
        resp = client.get("/api/admin/tag-groups", headers=self.headers)
        for group in resp.json():
            if group["id"] == self.group_id:
                tag_names = [t["name"] for t in group["tags"]]
                assert "张三" in tag_names

    def test_move_tag_not_found_404(self, client):
        """移动不存在的标签 → 404。"""
        resp = client.put(
            "/api/admin/tags/99999",
            json={"group_id": self.group_id},
            headers=self.headers,
        )
        assert resp.status_code == 404

    def test_move_tag_group_not_found_400(self, client):
        """移动到不存在的分组 → 400。"""
        resp = client.put(
            f"/api/admin/tags/{self.tag['id']}",
            json={"group_id": 99999},
            headers=self.headers,
        )
        assert resp.status_code == 400


# ============================================================================
# Image Batch Delete Tests (V3.0 Phase 22)
# ============================================================================


class TestImageBatchDelete:
    """批量删除图片接口测试。"""

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.headers = _admin_auth(client)
        self.client = client

        # 上传三张测试图片
        self.img1 = _upload_image(client, self.headers, "batch1.jpg", None)
        self.img2 = _upload_image(client, self.headers, "batch2.jpg", None)
        self.img3 = _upload_image(client, self.headers, "batch3.jpg", None)

    def test_batch_delete_empty_ids_400(self, client):
        """空 image_ids → 400。"""
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": []},
            headers=self.headers,
        )
        assert resp.status_code == 400

    def test_batch_delete_not_found_404(self, client):
        """不存在的图片 ID → 404。"""
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": [99999]},
            headers=self.headers,
        )
        assert resp.status_code == 404

    def test_batch_delete_partial_not_found_404(self, client):
        """部分 ID 存在部分不存在 → 404。"""
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": [self.img1["id"], 99999]},
            headers=self.headers,
        )
        assert resp.status_code == 404

    def test_batch_delete_success_204(self, client):
        """正常批量删除 → 204，所有图片被删除。"""
        ids = [self.img1["id"], self.img2["id"]]
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": ids},
            headers=self.headers,
        )
        assert resp.status_code == 204

        # 验证图片已被删除
        resp = client.get("/api/admin/images", headers=self.headers)
        data = resp.json()
        remaining_ids = {img["id"] for img in data["images"]}
        assert self.img1["id"] not in remaining_ids
        assert self.img2["id"] not in remaining_ids
        assert self.img3["id"] in remaining_ids

    def test_batch_delete_all_204(self, client):
        """全部删除 → 204，所有图片被清除。"""
        ids = [self.img1["id"], self.img2["id"], self.img3["id"]]
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": ids},
            headers=self.headers,
        )
        assert resp.status_code == 204

        resp = client.get("/api/admin/images", headers=self.headers)
        assert resp.json()["total"] == 0

    def test_batch_delete_unauthorized(self, client):
        """无认证 → 401。"""
        resp = client.request(
            "DELETE", "/api/admin/images/batch",
            json={"image_ids": [self.img1["id"]]},
        )
        assert resp.status_code == 401
