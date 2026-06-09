# 技术架构深度解析 — 毕业季专属相册 V3.0

> 面向开发者、架构师及后续维护者的技术决策文档。

---

## 目录

1. [架构全景](#架构全景)
2. [核心架构决策：SSOT 隐私隔离](#核心架构决策ssot-隐私隔离)
3. [性能设计：OSS 缩略图策略](#性能设计oss-缩略图策略)
4. [可靠性设计：前端下载队列](#可靠性设计前端下载队列)
5. [数据模型](#数据模型)
6. [API 设计](#api-设计)
7. [前端架构](#前端架构)
8. [测试策略](#测试策略)

---

## 架构全景

```
┌──────────────────────────────────────────────────────────┐
│                      浏览器 (SPA)                         │
│  ┌──────────────────┐  ┌──────────────────┐              │
│  │  admin.html       │  │  student.html    │              │
│  │  + admin.js       │  │  + student.js    │              │
│  │  (Tailwind CDN)   │  │  (Tailwind CDN)  │              │
│  └────────┬──────────┘  └────────┬─────────┘              │
└───────────┼──────────────────────┼────────────────────────┘
            │ REST API (JWT)       │ REST API (JWT)
            ▼                      ▼
┌──────────────────────────────────────────────────────────┐
│                  FastAPI (Python 3.10+)                   │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐     │
│  │  admin.py    │ │  auth.py     │ │  student.py  │     │
│  │  (管理端 API)│ │  (认证 API)  │ │  (学生端 API)│     │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘     │
│         │                │                │              │
│  ┌──────┴────────────────┴────────────────┴───────┐     │
│  │            Services 层                          │     │
│  │  AliyunOssStorage │ AuthService │ StudentService│     │
│  └──────────┬────────┴──────┬──────┴──────┬────────┘     │
│             │               │             │               │
│  ┌──────────┴───────────────┴─────────────┴────────┐     │
│  │         SQLAlchemy ORM + SQLite                 │     │
│  └─────────────────────────────────────────────────┘     │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP (oss2 SDK)
                           ▼
┌──────────────────────────────────────────────────────────┐
│               阿里云 OSS (对象存储)                        │
│  - 原图存储 (UUID 命名防覆盖)                              │
│  - 签名 URL 动态生成 (15min TTL)                          │
│  - x-oss-process 实时缩略图                               │
└──────────────────────────────────────────────────────────┘
```

**设计原则**:
- **动静分离**: 数据库仅存 File Key + 元数据，图片二进制永不流经应用服务器
- **无框架前端**: 零构建步骤，Vanilla JS + Tailwind CDN，开箱即用
- **单文件数据库**: SQLite，零配置部署，适合内网/小规模场景

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
│  secret  │  逻辑    │  image_id    │         │  group   │── TagGroup
│          │  匹配    │  tag_id      │         │          │
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

**验证流程**:
1. 学生提交「相册密码 + 姓名 + 个人密钥」
2. 成功验证后，后端查询 `Tag.name == 学生姓名` 关联的所有 `Image`
3. 仅返回这些图片的签名 URL

**扩展预留**: 可定义特殊 Tag（如 `大合照`）通过白名单逻辑作为共享照片集合。

---

## 性能设计：OSS 缩略图策略

### 问题

原图通常为 3-10MB，在网格视图中加载数十张原图会造成严重的带宽和渲染延迟。

### 方案

使用阿里云 OSS `x-oss-process` 图片处理能力，后端生成签名缩略图 URL。

**实现** (`app/services/aliyun_oss_storage.py`):

```python
async def get_thumbnail_signed_url(
    self, file_key: str, width: int = 400, height: int = 400,
    expires_seconds: int = 900,
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

**V3.0 根因修复 (Phase 17/19)**:

`oss2.Bucket.sign_url(method, key, expires, headers=None, params=None, ...)` 的真实签名为 5 参数形式，`params` 是第 5 个位置参数。初版实现将 `x-oss-process` 作为第 4 个位置参数传入，被 SDK 识别为 `headers` 而非 `params`：
- `x-oss-process` 被纳入签名计算（作为 CanonicalizedHeaders）
- 但未追加到 URL Query String → 浏览器请求签名不匹配 → 403

修复后使用 `params=` **关键字参数**，确保：
- OSS SDK 将 `x-oss-process` 正确追加到 URL 查询字符串
- 签名计算覆盖该参数，服务端验证通过

**为什么后端生成而非前端拼接？**

| 维度 | 前端拼接 (V2.0) | 后端签名 (V3.0) |
|---|---|---|
| 安全性 | 签名不覆盖 process 参数 → 403 | 签名覆盖所有参数 → 200 |
| API 响应体积 | 不变 | 新增 `thumbnail_url` 字段 (~150 字符/图) |
| 灵活性 | 前端自由调整 | 需后端配合 |

**应用范围 (V3.0)**:
- 学生端图片网格：`thumbnail_url`（400px）
- 管理端打标工作台：`thumbnail_url`（400px）
- 管理端图片管理：`thumbnail_url`（400px）
- 管理端编辑弹窗预览：`thumbnail_url`（400px）
- Lightbox 全屏预览：原图 `url`

**OSS 处理流程**:
1. 浏览器请求带 `x-oss-process` 参数的签名 URL
2. OSS 在 Edge 节点实时缩放图片（首次 < 100ms，后续缓存命中 < 10ms）
3. 返回缩放后的图片数据

---

## 可靠性设计：前端下载队列

### 问题

浏览器对批量下载有严格的并发限制：
- 同时打开多个 `<a download>` 会被浏览器拦截
- `window.open()` 批量调用会被弹窗拦截器阻止
- 直接并发 fetch 会导致 TCP 连接耗尽

### 方案

**单线程队列下载 + 400ms 间隔**，确保浏览器将每次下载视为独立用户操作。

**实现** (`static/js/student.js`):

```javascript
async function startDownload() {
    const urls = getSelectedImageUrls();  // 获取签名 URL 列表
    state.downloadAborted = false;

    for (let i = 0; i < urls.length; i++) {
        if (state.downloadAborted) break;

        // 1. fetch blob（跨域需 OSS CORS 配置）
        const resp = await fetch(urls[i]);
        const blob = await resp.blob();

        // 2. 创建临时 Object URL
        const blobUrl = URL.createObjectURL(blob);

        // 3. 触发下载
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = extractFilename(urls[i]);
        a.click();

        // 4. 清理 + 间隔
        URL.revokeObjectURL(blobUrl);
        await sleep(400);  // 防拦截核心机制
    }
}
```

**防拦截机制**:
- **400ms 间隔**: 确保浏览器不会将多次下载识别为自动化行为
- **Blob 方式**: 先 fetch 到内存再 `<a download>`，而非直接 `window.open(url)`，避免弹窗拦截
- **可取消**: `downloadAborted` 标志位，点击取消按钮立即停止
- **进度反馈**: 实时更新进度条 (`currentIndex / total`)

**前置条件**: 必须在 OSS 控制台配置 CORS（见 README.md），否则 `fetch` 跨域请求会被浏览器拦截。

---

## 数据模型

### ER 图

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
| `Image.file_key` 而非 URL | 签名 URL 有时效性，不可持久化。存储 Key 即可随时生成签名 URL |
| `Tag.group_id NOT NULL` | 所有标签必须归属分组。通过 `before_insert` 事件自动注入默认分组，确保向后兼容 |
| 删除 TagGroup → Tag 迁移 | 非级联删除，组内 Tag 迁移至"未分类"分组。保护已有打标数据 |
| `Student.secret_key` 明文存储 | 个人密钥用于身份验证而非密码安全，明文存储便于管理员查看分发 |
| `AlbumConfig` 单行表 | 相册级配置（密码）仅需一行，无需复杂配置表 |

---

## API 设计

### 认证体系

```
                     ┌─────────────┐
                     │  POST /auth  │  管理员登录 (相册密码)
                     └──────┬──────┘
                            │
                     ┌──────▼──────┐
                     │  POST /api/ │  学生登录 (相册密码 + 姓名 + 密钥)
                     │  student/   │
                     │  auth       │
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

| 方法 | 路径 | 说明 | V2.0 | V3.0 |
|---|---|---|---|---|
| POST | `/api/admin/students` | 批量创建学生（全角逗号分隔姓名） | ✅ | |
| POST | `/api/admin/tag-groups` | 创建标签分组 | ✅ | |
| PUT | `/api/admin/tag-groups/{id}` | 重命名分组 | ✅ | |
| DELETE | `/api/admin/tag-groups/{id}` | 删除分组（标签迁移至"未分类"） | ✅ | |
| PUT | `/api/admin/tags/{id}` | 移动标签到其他分组 | ✅ | |
| DELETE | `/api/admin/tags/{id}` | 删除标签 | 已有 | |
| PUT | `/api/admin/images/{id}/tags` | 图片标签替换（替换全部 tag_ids） | ✅ | |
| GET | `/api/admin/images?tagged=true` | 按打标状态筛选图片，响应含 `thumbnail_url` | ✅ | ✅ |
| DELETE | `/api/admin/images/batch` | 批量删除图片（多选模式） | | ✅ |
| GET | `/api/student/images` | 按学生姓名匹配标签查询图片，响应含 `thumbnail_url` | 已有 | ✅ |

---

## 前端架构

### 管理端 (`admin.js`)

**设计模式**: State-Driven Rendering（状态驱动渲染）

```
                ┌─────────────────────────┐
                │     state 对象            │  (唯一数据源)
                │                          │
                │  allImages               │
                │  unprocessed             │
                │  processed               │
                │  currentImageId          │
                │  tagGroups               │
                │  students                │
                │  processingLock          │
                │  selectedTagIds   ← V3.0 │
                │  editingImageId          │
                │  isMultiSelectMode ← V3.0│
                │  selectedImageIds  ← V3.0│
                └────────┬─────────────────┘
                         │
            ┌────────────┼───────────────┐
            ▼            ▼               ▼
      renderWorkspace  renderTagGroups  renderStudents
      renderProcessed  renderAllImages  ...
```

**关键机制**:
- **事件委托**: 容器级事件监听 (e.g., `#unprocessed-grid`)，避免重新绑定
- **processingLock**: 打标操作防抖，防止并发 API 调用导致状态混乱
- **自动分流**: `allImages → unprocessed (tags=[]) + processed (tags>0)`
- **V3.0 多标签模式**: `selectedTagIds` 批量选中 → confirm 一次性提交 → 自动推进
- **V3.0 图片批量删除**: `isMultiSelectMode` + `selectedImageIds` → 批量 DELETE 端点 → 退出多选

### 学生端 (`student.js`)

**多选模式**:
- `isMultiSelectMode: false` → 正常浏览，点击打开 Lightbox
- `isMultiSelectMode: true` → 点击切换选中/取消，显示选区栏
- `selectedIds: Set` 跟踪选中图片 ID

**队列下载**: 见 [可靠性设计：前端下载队列](#可靠性设计前端下载队列)

---

## 测试策略

### 覆盖范围

| 测试文件 | 用例数 | 覆盖内容 |
|---|---|---|
| `test_admin_api.py` | 16 | 管理端 CRUD、认证、图片上传/删除 |
| `test_student_api.py` | ~19 | 学生端认证、隐私隔离、图片查看 |
| `test_v2_admin_api.py` | 30 | V2.0/V3.0：TagGroup CRUD、批量学生、图片标签替换、tagged 筛选、标签移动、批量删除 |
| `test_storage.py` | 12 | OSS 上传/签名/删除/缩略图单元测试 |
| `test_tag_group.py` | 13 | 模型 + 迁移验证 |
| `test_auth.py` / `test_tagging.py` | ~18 | 认证 + 打标服务 |

**总计: 108 测试用例**

### 测试基础设施

- **数据库**: SQLite 内存模式 (`StaticPool`, `check_same_thread=False`)，每个测试独立隔离
- **OSS Mock**: `AsyncMock(spec=AliyunOssStorageService)`，测试环境绝不发起真实网络请求
- **迁移测试**: `test_migration_idempotent` 验证幂等性, `test_migration_preserves_*` 验证数据完整性
- **Batch delete 测试**: 覆盖空列表/不存在/部分不存在/成功/全量/未认证 6 种场景

### 运行测试

```bash
# 全量测试
pytest tests/ -v

# 仅 V2.0/V3.0 测试
pytest tests/test_v2_admin_api.py -v

# 带覆盖率
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

*最后更新: 2026-06-09 · V3.0 正式版*
