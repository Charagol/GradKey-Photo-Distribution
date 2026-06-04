"""标签分组模型与迁移验证测试 — Phase 9。

测试覆盖：
- TagGroup 模型 CRUD 与约束
- Tag.group_id 自动注入（before_insert 事件）
- Tag ↔ TagGroup 双向 relationship
- V1→V2 迁移脚本数据完整性
"""

import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import Base
from app.models.tag_group import DEFAULT_TAG_GROUP_NAME, TagGroup
from app.models.tag import Tag


# ============================================================================
# Model Tests — 使用 V2 ORM 模型
# ============================================================================


@pytest.fixture(scope="function")
def db_session():
    """V2 模型测试会话 — 自动创建所有表（含 tag_group 和 tag 新结构）。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


class TestTagGroupModel:
    """TagGroup 基础模型测试。"""

    def test_create_tag_group(self, db_session: Session):
        """创建分组，验证字段和 __repr__。"""
        group = TagGroup(name="寝室")
        db_session.add(group)
        db_session.commit()
        db_session.refresh(group)

        assert group.id is not None
        assert group.name == "寝室"
        assert group.created_at is not None
        assert isinstance(group.created_at, datetime)
        assert "寝室" in repr(group)

    def test_tag_group_unique_name(self, db_session: Session):
        """重复分组名触发 IntegrityError。"""
        db_session.add(TagGroup(name="专业"))
        db_session.commit()

        db_session.add(TagGroup(name="专业"))
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()

    def test_tag_group_name_not_null(self, db_session: Session):
        """空名称触发约束错误。"""
        db_session.add(TagGroup(name=None))
        with pytest.raises(Exception):
            db_session.commit()


class TestTagWithGroup:
    """Tag ↔ TagGroup 关联测试。"""

    def test_tag_auto_default_group(self, db_session: Session):
        """核心: 不设 group_id → before_insert 自动归入"未分类"。

        此测试不预先创建任何 TagGroup，依赖 before_insert 事件的自愈能力。
        """
        tag = Tag(name="张三")
        db_session.add(tag)
        db_session.commit()
        db_session.refresh(tag)

        assert tag.group_id is not None
        assert tag.group is not None
        assert tag.group.name == DEFAULT_TAG_GROUP_NAME

    def test_tag_auto_default_group_when_group_exists(self, db_session: Session):
        """已有 TagGroup 时，自动分配也不冲突。"""
        default = TagGroup(name=DEFAULT_TAG_GROUP_NAME)
        db_session.add(default)
        db_session.commit()

        tag = Tag(name="李四")
        db_session.add(tag)
        db_session.commit()
        db_session.refresh(tag)

        assert tag.group_id == default.id

    def test_tag_explicit_group(self, db_session: Session):
        """显式指定 group_id。"""
        dorm = TagGroup(name="寝室")
        db_session.add(dorm)
        db_session.commit()

        tag = Tag(name="王五", group_id=dorm.id)
        db_session.add(tag)
        db_session.commit()
        db_session.refresh(tag)

        assert tag.group_id == dorm.id
        assert tag.group.name == "寝室"

    def test_tag_group_tags_relationship(self, db_session: Session):
        """TagGroup.tags 反向关系：通过分组访问标签列表。"""
        group = TagGroup(name="寝室")
        db_session.add(group)
        db_session.commit()

        tag1 = Tag(name="张三", group_id=group.id)
        tag2 = Tag(name="李四", group_id=group.id)
        db_session.add_all([tag1, tag2])
        db_session.commit()

        db_session.refresh(group)
        assert len(group.tags) == 2
        names = {t.name for t in group.tags}
        assert names == {"张三", "李四"}

    def test_tag_group_relationship(self, db_session: Session):
        """Tag.group 正向关系：通过标签访问所属分组。"""
        group = TagGroup(name="专业")
        db_session.add(group)
        db_session.commit()

        tag = Tag(name="计算机", group_id=group.id)
        db_session.add(tag)
        db_session.commit()
        db_session.refresh(tag)

        assert tag.group is not None
        assert tag.group.name == "专业"


# ============================================================================
# Migration Tests — 使用隔离的 V1 schema + 原始 SQL
# ============================================================================

V1_CREATE_TABLES = [
    # tag 表 — V1.0 结构（无 group_id，无 tag_group）
    """
    CREATE TABLE tag (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # image 表 — 必须存在，因为 image_tags 引用它
    """
    CREATE TABLE image (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_key TEXT NOT NULL UNIQUE,
        file_name TEXT,
        content_type TEXT,
        file_size INTEGER,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # image_tags 表 — V1.0 结构
    """
    CREATE TABLE image_tags (
        image_id INTEGER NOT NULL REFERENCES image(id) ON DELETE CASCADE,
        tag_id INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
        PRIMARY KEY (image_id, tag_id)
    )
    """,
]


def _create_v1_schema(engine):
    """在给定引擎上手动创建 V1.0 数据库结构。"""
    with engine.connect() as conn:
        for ddl in V1_CREATE_TABLES:
            conn.execute(text(ddl))
        conn.commit()


@pytest.fixture(scope="function")
def v1_engine():
    """独立的 V1.0 数据库引擎 — 不使用 Base.metadata，手动建表。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_v1_schema(engine)
    return engine


class TestMigration:
    """V1 → V2 迁移脚本数据完整性测试。"""

    def test_migration_from_v1_schema(self, v1_engine):
        """核心: V1 数据 → 迁移 → 验证 V2 结构 + 数据完整性。"""
        from app.migrations.v2_migrate import run_v2_migration

        # 插入 V1.0 测试数据
        with v1_engine.connect() as conn:
            conn.execute(text("INSERT INTO tag (id, name) VALUES (1, '张三')"))
            conn.execute(text("INSERT INTO tag (id, name) VALUES (2, '李四')"))
            conn.execute(text(
                "INSERT INTO image (id, file_key, file_name, content_type, file_size) "
                "VALUES (1, 'img/001.jpg', 'photo1.jpg', 'image/jpeg', 1024)"
            ))
            conn.execute(text(
                "INSERT INTO image (id, file_key, file_name, content_type, file_size) "
                "VALUES (2, 'img/002.jpg', 'photo2.jpg', 'image/jpeg', 2048)"
            ))
            conn.execute(text(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (1, 1)"
            ))
            conn.execute(text(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (1, 2)"
            ))
            conn.execute(text(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (2, 1)"
            ))
            conn.commit()

        # 执行迁移
        result = run_v2_migration(v1_engine)
        assert result is True

        # 验证 tag_group 表存在且含默认分组
        with v1_engine.connect() as conn:
            groups = conn.execute(text("SELECT * FROM tag_group")).fetchall()
            assert len(groups) == 1
            assert groups[0].name == DEFAULT_TAG_GROUP_NAME
            default_gid = groups[0].id

            # 验证 tag 表有 group_id 列，所有 tag 归入默认分组
            tags = conn.execute(
                text("SELECT id, name, group_id FROM tag ORDER BY id")
            ).fetchall()
            assert len(tags) == 2
            assert tags[0].name == "张三"
            assert tags[0].group_id == default_gid
            assert tags[1].name == "李四"
            assert tags[1].group_id == default_gid

            # 验证 FK 约束生效 — 无效 group_id 应被拒绝
            with pytest.raises(Exception):
                conn.execute(text(
                    "INSERT INTO tag (name, group_id) VALUES ('无效', 999)"
                ))
                conn.commit()

    def test_migration_idempotent(self, v1_engine):
        """重复执行迁移不报错，返回 False。"""
        from app.migrations.v2_migrate import run_v2_migration

        result1 = run_v2_migration(v1_engine)
        assert result1 is True  # 第一次：执行迁移

        result2 = run_v2_migration(v1_engine)
        assert result2 is False  # 第二次：跳过

        # 数据结构仍正确
        with v1_engine.connect() as conn:
            groups = conn.execute(text("SELECT * FROM tag_group")).fetchall()
            assert len(groups) == 1

    def test_migration_empty_tags(self):
        """V1.0 数据库无 Tag 时迁移正常，仅创建 tag_group 和默认分组。"""
        from app.migrations.v2_migrate import run_v2_migration

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        _create_v1_schema(engine)

        result = run_v2_migration(engine)
        assert result is True

        with engine.connect() as conn:
            groups = conn.execute(text("SELECT * FROM tag_group")).fetchall()
            assert len(groups) == 1
            assert groups[0].name == DEFAULT_TAG_GROUP_NAME

            tags = conn.execute(text("SELECT COUNT(*) FROM tag")).fetchone()
            assert tags[0] == 0

            # 验证 tag 表新结构存在
            columns = conn.execute(text("PRAGMA table_info('tag')")).fetchall()
            col_names = {col.name for col in columns}
            assert "group_id" in col_names

    def test_migration_preserves_image_tags(self, v1_engine):
        """迁移后 image_tags 关联数据完整不丢失。"""
        from app.migrations.v2_migrate import run_v2_migration

        with v1_engine.connect() as conn:
            conn.execute(text("INSERT INTO tag (id, name) VALUES (1, '张三')"))
            conn.execute(text("INSERT INTO tag (id, name) VALUES (2, '李四')"))
            conn.execute(text(
                "INSERT INTO image (id, file_key, file_name, content_type, file_size) "
                "VALUES (1, 'img/001.jpg', 'photo1.jpg', 'image/jpeg', 1024)"
            ))
            conn.execute(text(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (1, 1)"
            ))
            conn.execute(text(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (1, 2)"
            ))
            conn.commit()

        run_v2_migration(v1_engine)

        # 验证 image_tags 数据完整
        with v1_engine.connect() as conn:
            rows = conn.execute(
                text("SELECT image_id, tag_id FROM image_tags ORDER BY image_id, tag_id")
            ).fetchall()
            assert len(rows) == 2
            assert (rows[0].image_id, rows[0].tag_id) == (1, 1)
            assert (rows[1].image_id, rows[1].tag_id) == (1, 2)

            # 验证 FK 级联仍有效: 删除 image → image_tags 关联被清除
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.execute(text("DELETE FROM image WHERE id = 1"))
            conn.commit()
            remaining = conn.execute(
                text("SELECT COUNT(*) FROM image_tags")
            ).fetchone()[0]
            assert remaining == 0

    def test_migration_preserves_tag_ids(self, v1_engine):
        """迁移后 Tag.id 保持不变。"""
        from app.migrations.v2_migrate import run_v2_migration

        with v1_engine.connect() as conn:
            conn.execute(text("INSERT INTO tag (id, name) VALUES (10, '保留ID')"))
            conn.commit()

        run_v2_migration(v1_engine)

        with v1_engine.connect() as conn:
            tag = conn.execute(
                text("SELECT id, name FROM tag WHERE id = 10")
            ).fetchone()
            assert tag is not None
            assert tag.name == "保留ID"
