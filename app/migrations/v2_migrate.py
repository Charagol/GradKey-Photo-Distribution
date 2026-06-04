"""V1 → V2 数据库迁移脚本。

SQLite 对 ALTER TABLE 支持有限（不支持添加带 FK 的列），
因此采用"创建新表 → 数据迁移 → 删除旧表 → 重命名"的标准重建策略。

迁移内容:
1. 创建 tag_group 表，插入默认"未分类"分组
2. 重建 tag 表（新增 group_id 外键列）
3. 重建 image_tags 表（确保 FK 引用指向新 tag 表）

所有操作在单个事务中完成，失败自动回滚。
通过 sqlite_master 检查实现幂等。
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.database import engine as default_engine

logger = logging.getLogger(__name__)

DEFAULT_GROUP_NAME = "未分类"


def is_migration_applied(engine: Engine) -> bool:
    """检查 tag_group 表是否已存在（判断是否已执行迁移）。"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='tag_group'"
            )
        )
        return result.fetchone() is not None


def run_v2_migration(engine: Engine = None) -> bool:
    """执行 V1 → V2 数据库迁移。

    采用 SQLite 标准表重建流程:
    - PRAGMA foreign_keys = OFF / ON 包裹整个事务
    - tag_group 表: 新建 + 插入默认分组
    - tag 表: 重建（新增 group_id FK）
    - image_tags 表: 重建（FK 引用指向新 tag 表）

    Args:
        engine: SQLAlchemy 引擎，默认使用 app.database.engine。

    Returns:
        True: 执行了迁移。
        False: 已迁移，跳过（幂等）。

    Raises:
        RuntimeError: 迁移失败。
    """
    if engine is None:
        engine = default_engine

    if is_migration_applied(engine):
        logger.info("V2 迁移已执行，跳过。")
        return False

    logger.info("开始 V2 数据库迁移...")

    with engine.connect() as conn:
        # 必须使用 connection-level 事务
        trans = conn.begin()

        try:
            # ── Step 0: 禁用外键约束 ──
            conn.execute(text("PRAGMA foreign_keys = OFF"))

            # ── Step 1: 创建 tag_group 表 ──
            logger.info("  创建 tag_group 表...")
            conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS tag_group ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  name TEXT NOT NULL UNIQUE,"
                    "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )

            # ── Step 2: 插入默认"未分类"分组 ──
            logger.info("  插入默认'未分类'分组...")
            result = conn.execute(
                text("INSERT INTO tag_group (name) VALUES (:name)"),
                {"name": DEFAULT_GROUP_NAME},
            )
            default_group_id = result.lastrowid
            logger.info("  默认分组 id=%d", default_group_id)

            # ── Step 3: 统计现有标签数 ──
            tag_count_result = conn.execute(
                text("SELECT COUNT(*) FROM tag")
            )
            tag_count = tag_count_result.fetchone()[0]
            logger.info("  现有标签数: %d", tag_count)

            # ── Step 4: 重建 tag 表（新增 group_id 列）──
            logger.info("  重建 tag 表（新增 group_id FK）...")
            conn.execute(
                text(
                    "CREATE TABLE tag_v2 ("
                    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "  name TEXT NOT NULL UNIQUE,"
                    "  group_id INTEGER NOT NULL REFERENCES tag_group(id),"
                    "  created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO tag_v2 (id, name, created_at, group_id)"
                    " SELECT id, name, created_at, :gid FROM tag"
                ),
                {"gid": default_group_id},
            )
            conn.execute(text("DROP TABLE tag"))
            conn.execute(text("ALTER TABLE tag_v2 RENAME TO tag"))
            logger.info("  tag 表重建完成，%d 个标签已迁移", tag_count)

            # ── Step 5: 重建 image_tags 表 ──
            logger.info("  重建 image_tags 表...")
            conn.execute(
                text(
                    "CREATE TABLE image_tags_v2 ("
                    "  image_id INTEGER NOT NULL REFERENCES image(id)"
                    "    ON DELETE CASCADE,"
                    "  tag_id INTEGER NOT NULL REFERENCES tag(id)"
                    "    ON DELETE CASCADE,"
                    "  PRIMARY KEY (image_id, tag_id)"
                    ")"
                )
            )
            conn.execute(
                text("INSERT INTO image_tags_v2 SELECT * FROM image_tags")
            )
            conn.execute(text("DROP TABLE image_tags"))
            conn.execute(text("ALTER TABLE image_tags_v2 RENAME TO image_tags"))
            logger.info("  image_tags 表重建完成")

            # ── Step 6: 启用外键约束并提交 ──
            conn.execute(text("PRAGMA foreign_keys = ON"))

            trans.commit()
            logger.info(
                "V2 迁移完成: 创建默认分组 '%s' (id=%d), %d 个标签已迁移",
                DEFAULT_GROUP_NAME,
                default_group_id,
                tag_count,
            )
            return True

        except Exception:
            trans.rollback()
            logger.exception("V2 迁移失败，事务已回滚")
            raise RuntimeError("V2 迁移失败，数据库未变更。请检查日志。") from None
        finally:
            # 确保无论成功与否都恢复 FK 设置
            try:
                conn.execute(text("PRAGMA foreign_keys = ON"))
            except Exception:
                pass


# ── CLI 入口 ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # 导入所有模型确保元数据完整（对直接操作 engine 非必需，但作为良好实践保留）
    from app.models import *  # noqa: F401, F403

    try:
        migrated = run_v2_migration()
        if not migrated:
            print("数据库已是最新 V2 结构，无需迁移。")
        sys.exit(0)
    except RuntimeError as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
