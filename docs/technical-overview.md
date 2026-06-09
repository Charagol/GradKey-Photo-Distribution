# 技术架构深度解析 — 毕业季专属相册 V4.0

> 面向开发者、架构师及后续维护者的技术决策文档。
> V4.0 正式版 | 113 测试全量通过 | 2026-06-10

---

## 目录

1. [架构全景](#架构全景)
2. [核心架构决策：SSOT 隐私隔离](#核心架构决策ssot-隐私隔离)
3. [性能设计：OSS 缩略图策略](#性能设计oss-缩略图策略)
4. [可靠性设计：前端下载队列](#可靠性设计前端下载队列)
5. [数据模型](#数据模型)
6. [API 设计](#api-设计)
7. [前端架构](#前端架构)
8. [部署架构](#部署架构)
9. [测试策略](#测试策略)
10. [V4.0 设计-实施偏差](#v40-设计-实施偏差)

---

## 架构全景

```
┌──────────────────────────────────────────────────────────┐
│                      浏览器 (SPA)                         │
│  ┌──────────────────┐  ┌──────────────────┐              │
│  │  admin.html       │  │  student.html    │              │
│  │  + admin.js       │  │  + student.js    │              │
│  │  (Tailwind 本地化)│  │  (Tailwind 本地化)│              │
│  │  · 仪表盘 Tab     │  │  · 多选下载      │              │
│  │  · 批量打标       │  │  · Lightbox      │              │
│  │  · TTL 缓存 30min │  │  · 标签筛选      │              │
│  │  · 离线提示 Banner│  │  · 离线提示      │              │
│  └────────┬──────────┘  └────────┬─────────┘              │
└───────────┼──────────────────────┼────────────────────────┘
            │ REST API (JWT)       │ REST API (JWT)
            ▼                      ▼
┌──────────────────────────────────────────────────────────┐
│               FastAPI (Python) — V4.0.0                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │  admin.py    │ │  auth.py     │ │  student.py  │     │
│  │  · 仪表盘统计│ │  · 管理员登录│ │  · 隐私隔离查询│    │
│  │  · CSV 导出  │ │  · 学生登录  │ │  · Lightbox URL│   │
│  │  · 批量删除  │ └──────────────┘ │  · 标签筛选    │     │
│  └──────┬───────┘                  └──────┬───────┘     │
│         │                                 │              │
│  ┌──────┴─────────────────────────────────┴───────┐     │
│  │            Services 层                          │     │
│  │  AliyunOssStorage │ AuthService │ StudentService│     │
│  │  · 签名 URL 1h TTL│ · JWT HS256│ · 密钥生成    │     │
│  └──────────┬────────┴──────┬──────┴──────┬────────┘     │
│             │               │             │               │
│  ┌──────────┴───────────────┴─────────────┴────────┐     │
│  │    SQLAlchemy ORM + SQLite (WAL mode)           │     │
│  │    pool_size=3, max_overflow=5, pool_pre_ping   │     │
│  │    启动时 Base.metadata.create_all 自动建表      │     │
│  └─────────────────────────────────────────────────┘     │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP (oss2 SDK)
                           ▼
┌──────────────────────────────────────────────────────────┐
│               阿里云 OSS (对象存储)                        │
│  - 原图存储 (UUID 命名防覆盖)                              │
│  - 签名 URL 动态生成 (1h TTL, V4.0 延长)                  │
│  - x-oss-process 实时缩略图 (w_400/w_1200)               │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│               Docker 容器层 (V4.0 新增)                    │
│  Dockerfile: python:3.11-slim + uvicorn                  │
│  docker-compose.yml: 单服务 + env_file + ./data volume   │
│  一行启动: docker-compose up -d                          │
└──────────────────────────────────────────────────────────┘
```

**V4.0 新增**:
- **管理端仪表盘**: 存储概览 + 数据统计 + CSV 导出，默认首页
- **批量打标**: 多选照片一键打标 + 点击分组全选组内标签
- **容错层**: 上传指数退避重试、`offline`/`online` 事件 banner、图片加载失败 debounced toast
- **性能层**: 前端 30min TTL 缓存、SQLite WAL 模式、Tailwind 本地化、DB 连接池
- **Docker 层**: `docker-compose up -d`，启动自动建表

---

## 核心架构决策：SSOT 隐私隔离

### 问题

毕业季照片多为合影，同一张照片可能包含多位学生。传统的 `image.student_id` 外键设计无法表达"一张照片多人可见"的语义。

### 方案

**SSOT (Single Source of Truth) — `Student.name = Tag.name` 逻辑匹配**。

```
┌──────────┐         ┌──────────────┐         ┌──────────┐
│  Student  │         │  image_tags  │         │   Tag    │
│          │         │  (多对多)     │         │          │
│  name    │ ═══════ │              │ ═══════ │  name    │
│  secret  │  逻辑   │  image_id    │         │  group   │── TagGroup
│          │  匹配   │  tag_id      │         │          │
└──────────┘         └──────────────┘         └──────────┘
                              │
                              ▼
                        ┌──────────┐
                        │  Image   │
                        │          │
                        │  file_key│── 阿里云 OSS
                        └──────────┘
```

**关键特性**:
- `Image` 表**不含** `student_id` 外键
- `Student` 与 `Tag` 通过 `name` 字段逻辑关联，无数据库级约束
- 管理员为照片打标时，若标签名为学生姓名，则该学生自动可见该照片
- 支持合影语义：照片可同时打上 `张三`、`李四` 的标签，两人均可见

**V4.0 学生端筛选优化**: `renderTagFilter()` 自动跳过与学生本人同名的标签。隐私隔离已保证所有照片属本人，「全部」即等于「自己的照片」，本人姓名标签筛选冗余。

---

## 性能设计：OSS 缩略图策略

### 分级策略 (V4.0)

| 场景 | 尺寸 | URL 类型 | 字段 |
|------|------|---------|------|
| 网格 (学生端/管理端) | 400px | `thumbnail_url` | `thumbnail_url` |
| Lightbox (学生端) | 1200px | `lightbox_url` | `lightbox_url` |
| 编辑弹窗预览 | 400px | `thumbnail_url` | `thumbnail_url` |
| 原图下载 | 原尺寸 | `url` | `url` |

**签名 URL 有效期 (V4.0 P7-1 延长)**: `oss_signed_url_expires` 从 900s → 3600s (1h)，覆盖前端 30min 缓存窗口，确保缓存命中时签名未过期。

### 实现

```python
async def get_thumbnail_signed_url(
    self, file_key: str, width: int = 400, height: int = 400,
    expires_seconds: int = 3600,  # V4.0: 1h TTL
) -> str:
    process_value = f"image/resize,m_lfit,w_{width},h_{height}"
    url: str = await asyncio.to_thread(
        self._bucket.sign_url,
        "GET",
        file_key,
        expires_seconds,
        params={"x-oss-process": process_value},  # 关键字参数，参与签名
    )
    return url
```

**V3.0 根因修复**: `oss2.Bucket.sign_url` 的 `params` 参数必须以**关键字参数**传入（第 5 位置参数），确保 `x-oss-process` 正确追加到 URL Query String 并参与签名计算。

---

## 可靠性设计：前端下载队列

（V3.0 设计，V4.0 无变更）

**单线程队列下载 + 400ms 间隔**，确保浏览器将每次下载视为独立用户操作。

```javascript
async function startDownload() {
    const urls = getSelectedImageUrls();
    state.downloadAborted = false;
    for (let i = 0; i < urls.length; i++) {
        if (state.downloadAborted) break;
        const resp = await fetch(urls[i]);
        const blob = await resp.blob();
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = extractFilename(urls[i]);
        a.click();
        URL.revokeObjectURL(blobUrl);
        await sleep(400);  // 防拦截核心机制
    }
}
```

**前置条件**: 必须在 OSS 控制台配置 CORS（见 README.md）。

---

## 数据模型

### ER 图（V4.0 无模型变更）

```
┌─────────────────┐
│   album_config   │  单行配置表
├─────────────────┤
│ id      INTEGER  │  PK
│ password_hash    │  bcrypt 哈希
│ created_at       │
│ updated_at       │
└─────────────────┘

┌─────────────────┐       ┌──────────────────┐       ┌─────────────────┐
│     student      │       │    image_tags    │       │      tag        │
├─────────────────┤       ├──────────────────┤       ├─────────────────┤
│ id      INTEGER  │ PK    │ image_id  INTEGER│ FK    │ id      INTEGER │ PK
│ name    TEXT     │       │ tag_id    INTEGER│ FK    │ name    TEXT    │ UNIQUE
│ secret_key TEXT  │       └────────┬─────────┘       │ group_id INTEGER│ FK
│ created_at       │                │                  │ created_at      │
└─────────────────┘                │ 多对多            └────────┬────────┘
       ↑                           │                          │
       │ 逻辑匹配                   ▼                          │ FK
       │ (name = name)    ┌─────────────────┐       ┌─────────────────┐
       └──────────────────│     image        │       │   tag_group     │
                          ├─────────────────┤       ├─────────────────┤
                          │ id      INTEGER  │ PK    │ id      INTEGER │ PK
                          │ file_key TEXT    │ UNIQUE│ name    TEXT    │ UNIQUE
                          │ file_name TEXT   │       │ created_at      │
                          │ content_type     │       └─────────────────┘
                          │ file_size INTEGER│
                          │ uploaded_at      │
                          └─────────────────┘
```

### 关键设计决策

| 决策 | 原因 |
|---|---|
| `Image.file_key` 而非 URL | 签名 URL 有时效性，不可持久化 |
| `Tag.group_id NOT NULL` | 所有标签必须归属分组，`before_insert` 自动注入默认分组 |
| 删除 TagGroup → Tag 迁移 | 非级联删除，组内 Tag 迁移至"未分类"分组 |
| `Student.secret_key` 明文存储 | 个人密钥用于身份验证，明文便于管理员分发 |
| V4.0 零模型变更 | 所有新功能在应用层实现，数据模型保持稳定 |

---

## API 设计

### 认证体系

```
                     ┌─────────────┐
                     │ POST /api/   │  管理员登录 (相册密码)
                     │ admin/auth   │
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │ POST /api/  │  学生登录 (相册密码 + 姓名 + 密钥)
                     │ student/auth│
                     └──────┬──────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
     ┌─────────────────┐        ┌─────────────────┐
     │  Admin JWT       │        │  Student JWT     │
     │  role: admin     │        │  role: student   │
     │  sub: admin      │        │  sub: {name}     │
     └────────┬────────┘        └────────┬────────┘
              │                          │
              ▼                          ▼
     /api/admin/*               /api/student/*
```

### 关键端点

| 方法 | 路径 | Phase | 说明 |
|---|---|---|---|
| POST | `/api/admin/auth` | V1 | 管理员登录 |
| POST | `/api/admin/students` | V2 | 批量创建学生（全角逗号分隔） |
| POST | `/api/admin/tag-groups` | V2 | 创建标签分组 |
| PUT | `/api/admin/tag-groups/{id}` | V2 | 重命名分组 |
| DELETE | `/api/admin/tag-groups/{id}` | V2 | 删除分组（标签迁移至"未分类"） |
| PUT | `/api/admin/tags/{id}` | V2 | 移动标签到其他分组 |
| DELETE | `/api/admin/tags/{id}` | V1 | 删除标签 |
| PUT | `/api/admin/images/{id}/tags` | V2 | 图片标签全量替换 |
| GET | `/api/admin/images?tagged=` | V3 | 按打标状态筛选，响应含 `thumbnail_url` |
| DELETE | `/api/admin/images/batch` | V3 | 批量删除图片（多选模式） |
| GET | `/api/student/my-images` | V1 | 按姓名匹配标签查询图片，含 `thumbnail_url` + `lightbox_url` |
| GET | `/api/student/my-tags` | V2 | 学生可见标签列表（去重） |
| POST | `/api/student/auth` | V1 | 学生登录 |
| GET | `/api/admin/dashboard/stats` | V4 P5 | 新增：存储/照片/学生/标签/分组统计 |
| GET | `/api/admin/students/export` | V4 P5 | 新增：CSV 导出（姓名,密钥）带 BOM |

**V4.0 新增**:
- `GET /api/admin/dashboard/stats` — 聚合 COUNT + COALESCE(SUM(file_size))
- `GET /api/admin/students/export` — UTF-8 BOM CSV，表头 `"姓名","密钥"`
- `lightbox_url` 字段 (V4 P2) — 学生端每张图片附加 w_1200 签名 URL

---

## 前端架构

### 管理端 (`admin.js`)

**设计模式**: State-Driven Rendering（状态驱动渲染）

```
                ┌──────────────────────────────────┐
                │     state 对象 (唯一数据源)         │
                │                                   │
                │  allImages, unprocessed, processed │
                │  currentImageId, tagGroups        │
                │  students, processingLock         │
                │  selectedTagIds         ← V3.0    │
                │  editingImageId         ← V3.0    │
                │  isMultiSelectMode      ← V3.0    │
                │  selectedImageIds       ← V3.0    │
                │                         ← V4.0:   │
                │  isBatchImageMode       ← P4      │
                │  batchSelectedImageIds  ← P4      │
                │  dashboardData          ← P5      │
                │  currentTab: 'dashboard'← P5      │
                └────────┬──────────────────────────┘
                         │
            ┌────────────┼──────────────────┐
            ▼            ▼                  ▼
      renderWorkspace  renderDashboard    renderStudents
      renderTagPool    renderAllImages    ...
```

**附加状态（非 state 对象内）**:
- `window._imagesLoadedAt` — V4.0 P7-1 图片列表 TTL 缓存时间戳（30min）
- `window._imgLoadFailedReported` — V4.0 P6 图片加载失败 debounced toast 标志位
- `window._networkBannerEl` — V4.0 P6 离线 banner DOM 引用

**关键机制**:
- **事件委托**: 容器级事件监听，避免重新绑定
- **processingLock**: 打标操作防抖
- **自动分流**: `allImages → unprocessed (tags=[]) + processed (tags>0)`
- **TTL 缓存**: `loadImages()` 30min 内复用数据，上传/删除/标签编辑后强制刷新
- **重试机制**: 上传网络错误指数退避（1s/2s/4s），最大 3 次

### 学生端 (`student.js`)

- **多选模式**: `isMultiSelectMode` + `selectedIds: Set`
- **队列下载**: 400ms 间隔防拦截
- **标签筛选**: 自动跳过本人姓名标签（隐私隔离冗余）
- **容错**: 离线提示 banner + 图片加载失败 toast

### V3.0 → V4.0 关键模式变更

| 模块 | V3.0 | V4.0 |
|------|------|------|
| 登录态存储 | `sessionStorage` | `localStorage` + JWT exp 校验 |
| Lightbox | 加载原图（3-10MB） | w_1200 缩略图 + 引导文案 |
| 打标工作台 | 单张 toggle + 确认 | 新增批量模式：多选照片 + 分组全选标签 |
| 管理端首页 | 打标工作台 | 仪表盘（默认首页） |
| 学生端筛选 | 全部 + 本人姓名 | 全部（隐私隔离后本人即全部） |
| 图片管理 | 每次切 Tab 重新请求 | 30min 前端 TTL 缓存 |
| 网络容错 | 无 | 上传重试（3 次指数退避）、断网 banner、OSS 不可达 toast |
| 管理端登录 | 静态错误文字 | toast 浮窗反馈 |
| SQLite | journal_mode=delete | WAL 模式 |
| Tailwind CSS | CDN 引用 | 本地化（static/tailwind.js） |
| 数据库初始化 | 依赖手动迁移 | 启动时自动建表 |
| 部署 | 手动 uvicorn | Docker Compose 一键部署 |
| CDN 加速 | — | 评估后搁置（收益/成本比过低） |

---

## 部署架构 (V4.0 新增)

### Docker 单容器部署

```
┌─────────────────────────────────────────┐
│             docker-compose.yml           │
│  ┌───────────────────────────────────┐  │
│  │  album 容器 (python:3.11-slim)     │  │
│  │  WORKDIR /app                     │  │
│  │                                   │  │
│  │  uvicorn app.main:app :8000       │  │
│  │                                   │  │
│  │  ┌─────────────────────────────┐  │  │
│  │  │  ./data/album.db (volume)   │  │  │
│  │  │  宿主机持久化，容器销毁不丢  │  │  │
│  │  └─────────────────────────────┘  │  │
│  └───────────────────────────────────┘  │
│                                         │
│  env_file: .env  (OSS/JWT 配置注入)      │
│  restart: unless-stopped               │
│  ports: 8000:8000                      │
└─────────────────────────────────────────┘
```

**启动流程**:
1. `docker-compose up -d` → 构建镜像 → 启动容器
2. FastAPI `startup` 事件 → `Base.metadata.create_all(bind=engine)` 自动建表
3. 应用就绪，访问 `http://localhost:8000`

**环境变量**:
- `.env` 通过 `env_file` 注入，不打包进镜像
- Docker 部署需设置 `DATABASE_URL=sqlite:///data/album.db`
- `./data` 目录通过 volume 挂载至容器内 `/app/data`

---

## 测试策略

### 覆盖范围

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_admin_api.py` | 16 | 管理端 CRUD、认证、图片上传/删除 |
| `test_student_api.py` | ~19 | 学生端认证、隐私隔离、lightbox_url 字段 |
| `test_v2_admin_api.py` | 35 | V2-V4：TagGroup CRUD、批量学生、图片标签替换、批量删除、仪表盘统计、CSV 导出 |
| `test_storage.py` | 12 | OSS 上传/签名/删除/缩略图单元测试 |
| `test_tag_group.py` | 13 | 模型 + 迁移验证 |
| `test_auth.py` / `test_tagging.py` | ~18 | 认证 + 打标服务 |

**总计: 113 测试用例**（V3.0 108 → V4.0 +5 P5 仪表盘/CSV 测试）

### 测试基础设施

- **数据库**: SQLite 内存模式 (`StaticPool`, `check_same_thread=False`)，每个测试独立隔离
- **OSS Mock**: `AsyncMock(spec=AliyunOssStorageService)`，测试环境绝不发起真实网络请求
- **迁移测试**: `test_migration_idempotent` 验证幂等性, `test_migration_preserves_*` 验证数据完整性
- **Batch delete 测试**: 覆盖空列表/不存在/部分不存在/成功/全量/未认证 6 种场景
- **Dashboard/CSV 测试 (V4.0)**: 空库统计、有数据统计、CSV BOM + 表头验证、未认证 401

### 运行测试

```bash
# 全量测试
pytest tests/ -v

# 仅 V2.0+ 测试
pytest tests/test_v2_admin_api.py -v

# 带覆盖率
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## V4.0 设计-实施偏差

| 偏差项 | 设计 (design-v4.md) | 实施 (task-tracker.md) | 理由 |
|--------|---------------------|------------------------|------|
| P3 CDN 加速 | 实施 | 搁置 | 收益/成本比过低，缩略图 50KB 延迟差不可感知 |
| P7 浏览器缓存 | 未在设计蓝图列出 | 并入 P7（含签名 URL 有效期延长） | 性能调优子任务，与 WAL/Tailwind 本地化同批 |
| P9 Docker 测试修复 | 无 | 6 项 bug 修复 | Docker 部署后实测发现的体验/可靠性问题 |

---

*最后更新: 2026-06-10 · V4.0 正式版*
