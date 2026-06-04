"""认证与授权相关单元/集成测试。

使用 sqlite:///:memory: 内存数据库进行完整认证链路测试。
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.database import Base
from app.middleware.jwt_middleware import (
    _get_payload,
    get_current_admin,
    get_current_student,
)
from app.models.album_config import AlbumConfig
from app.models.student import Student
from app.services.auth_service import (
    create_access_token,
    create_admin_token,
    create_student_token,
    decode_access_token,
    update_album_password,
    verify_or_init_album_password,
    verify_student,
)
from app.services.student_service import (
    create_student,
    delete_student,
    generate_secret_key,
    get_student,
    list_students,
    regenerate_key,
    update_student,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def db_engine():
    """创建内存 SQLite 引擎用于测试。"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(db_engine):
    """创建测试用数据库会话，测试后回滚。"""
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=db_engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


# ============================================================================
# AlbumConfig — 密码初始化与验证
# ============================================================================


class TestAlbumPassword:
    """相册密码初始化与验证测试套件。"""

    def test_first_time_setup_password(self, db_session):
        """AlbumConfig 空表时，首次调用即设置密码。"""
        assert db_session.query(AlbumConfig).first() is None

        result = verify_or_init_album_password(db_session, "mypassword")
        assert result is True

        config = db_session.query(AlbumConfig).first()
        assert config is not None
        assert config.password_hash != "mypassword"  # 存的是哈希

    def test_verify_correct_password(self, db_session):
        """正确密码验证通过。"""
        verify_or_init_album_password(db_session, "correct123")
        db_session.commit()

        result = verify_or_init_album_password(db_session, "correct123")
        assert result is True

    def test_verify_wrong_password(self, db_session):
        """错误密码验证失败。"""
        verify_or_init_album_password(db_session, "right")
        db_session.commit()

        result = verify_or_init_album_password(db_session, "wrong")
        assert result is False

    def test_update_password(self, db_session):
        """修改密码后旧密码失效，新密码生效。"""
        verify_or_init_album_password(db_session, "oldpass")
        db_session.commit()

        update_album_password(db_session, "newpass")

        assert verify_or_init_album_password(db_session, "oldpass") is False
        assert verify_or_init_album_password(db_session, "newpass") is True


# ============================================================================
# JWT — 令牌签发与解析
# ============================================================================


class TestJWT:
    """JWT 令牌签发与验证测试套件。"""

    def test_create_admin_token(self):
        """Admin JWT 包含正确 role 和 sub。"""
        token = create_admin_token()
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_create_student_token(self):
        """Student JWT 包含学生姓名作为 sub。"""
        token = create_student_token("张三")
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == "张三"
        assert payload["role"] == "student"
        assert "exp" in payload

    def test_decode_valid_token(self):
        """有效 token 解码成功。"""
        token = create_access_token({"test": "value"}, expires_hours=1)
        payload = decode_access_token(token)
        assert payload["test"] == "value"

    def test_decode_tampered_token(self):
        """篡改 token 返回 401。"""
        token = create_access_token({"sub": "admin"}, expires_hours=1)
        # 翻转最后一个字符
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            decode_access_token(tampered)
        assert exc.value.status_code == 401

    def test_custom_expiry(self):
        """自定义过期时间生效。"""
        token = create_access_token({"x": "y"}, expires_hours=1)
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        # 验证过期时间约在 1 小时后
        import time
        exp = payload["exp"]
        now = int(time.time())
        assert 3000 < exp - now < 4200  # 约 50-70 分钟


# ============================================================================
# 中间件 — Role 校验
# ============================================================================


class TestMiddleware:
    """JWT 中间件 role 校验测试套件。"""

    @pytest.fixture
    def test_app(self):
        """创建最小化 FastAPI 应用用于中间件测试。"""
        app = FastAPI()

        @app.get("/admin")
        def admin_route(_=Depends(get_current_admin)):
            return {"ok": True}

        @app.get("/student")
        def student_route(_=Depends(get_current_student)):
            return {"ok": True}

        return app

    @pytest.fixture
    def client(self, test_app):
        return TestClient(test_app)

    def test_admin_middleware_accepts_admin_token(self, client):
        """Admin token 可通过 admin 中间件。"""
        token = create_admin_token()
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_admin_middleware_rejects_student_token(self, client):
        """Student token 访问 admin 路由返回 403。"""
        token = create_student_token("张三")
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_student_middleware_accepts_student_token(self, client):
        """Student token 可通过 student 中间件。"""
        token = create_student_token("张三")
        resp = client.get("/student", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_student_middleware_rejects_admin_token(self, client):
        """Admin token 访问 student 路由返回 403。"""
        token = create_admin_token()
        resp = client.get("/student", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_missing_token_returns_401(self, client):
        """无 token 请求返回 401（HTTPBearer 拒绝）。"""
        resp = client.get("/student")
        assert resp.status_code == 401


# ============================================================================
# 学生服务 — CRUD + 密钥
# ============================================================================


class TestStudentService:
    """学生服务 CRUD 与密钥生成测试套件。"""

    @pytest.fixture(autouse=True)
    def _setup_db(self, db_session):
        """确保测试间无数据残留。"""
        db_session.query(Student).delete()
        db_session.commit()

    def test_create_student_auto_generates_key(self, db_session):
        """创建学生自动生成 6 位密钥，不含 0/O/1/I。"""
        student = create_student(db_session, "张三")

        assert student.name == "张三"
        assert len(student.secret_key) == 6
        # 验证不含易混淆字符
        assert "0" not in student.secret_key
        assert "O" not in student.secret_key
        assert "1" not in student.secret_key
        assert "I" not in student.secret_key
        # 验证全部为有效字符
        valid_set = set("ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
        assert all(ch in valid_set for ch in student.secret_key)

    def test_secret_key_is_random(self):
        """连续生成的密钥不同。"""
        keys = {generate_secret_key() for _ in range(100)}
        # 30^6 = 729,000,000 种组合，100次碰撞概率极低
        assert len(keys) == 100

    def test_student_crud_flow(self, db_session):
        """学生增删改查全流程。"""
        # Create
        s = create_student(db_session, "张三")
        assert s.id is not None
        assert s.name == "张三"

        # Read
        found = get_student(db_session, s.id)
        assert found is not None
        assert found.name == "张三"

        # Update
        updated = update_student(db_session, s.id, "张三丰")
        assert updated.name == "张三丰"

        # List
        all_students = list_students(db_session)
        assert len(all_students) == 1
        assert all_students[0].name == "张三丰"

        # Delete
        delete_student(db_session, s.id)
        assert get_student(db_session, s.id) is None

    def test_regenerate_key_changes_value(self, db_session):
        """重置密钥后值与之前不同。"""
        s = create_student(db_session, "李四")
        old_key = s.secret_key

        new_key = regenerate_key(db_session, s.id)
        assert new_key != old_key
        assert len(new_key) == 6

        # 验证数据库中已更新
        refreshed = get_student(db_session, s.id)
        assert refreshed.secret_key == new_key

    def test_verify_student_by_name_and_key(self, db_session):
        """学生姓名+密钥验证测试。"""
        s = create_student(db_session, "王五")

        # 正确匹配
        result = verify_student(db_session, "王五", s.secret_key)
        assert result is not None
        assert result.id == s.id

        # 姓名错误
        result = verify_student(db_session, "赵六", s.secret_key)
        assert result is None

        # 密钥错误
        result = verify_student(db_session, "王五", "WRONG")
        assert result is None

    def test_update_student_raises_on_not_found(self, db_session):
        """更新不存在的学生抛出 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            update_student(db_session, 99999, "无名")

    def test_delete_student_raises_on_not_found(self, db_session):
        """删除不存在的学生抛出 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            delete_student(db_session, 99999)
