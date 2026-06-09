# 毕业季专属相册 — 设计文档 V2.0

> **V2.0 设计蓝图 — 已封存** | 完成日期: 2026-06-05 | 测试: 98/98
> 此文件为 V2.0 启动时的设计文档。第 9 节记录了 7 项设计-实施偏差。

---

## Context

V1.0 实现了基础的双重认证 + 隐私隔离架构。V2.0 聚焦于：

1. **标签分组 (TagGroup)** — 将标签归入"寝室/专业/未分类"等分组，支撑打标工作台的聚合展示。
2. **沉浸式打标工作流** — 左右分栏：左侧未处理图片池，右侧标签池（按分组聚合），点击即打标，自动切换下一张。
3. **学生端体验升级** — OSS 缩略图加载、多选模式、队列下载（纯 JS 方案，无 ZIP 依赖）。
4. **批量操作** — 学生批量添加（逗号分隔）+ 自动创建同名 Tag。

---

## 1. 项目目录树 (V2.0 增量)

```
private album/
├── app/
│   ├── models/
│   │   └── tag_group.py              [NEW] TagGroup 模型
│   ├── services/
│   │   ├── aliyun_oss_storage.py     [MOD] (get_thumbnail_url 未实现，改为前端拼接)
│   │   └── student_service.py        [MOD] 新增 auto_commit 参数支持批量事务
│   ├── routes/
│   │   ├── admin.py                  [MOD] 新增批量学生 / 标签分组 / 图片标签编辑
│   │   └── student.py                [UNCHANGED] 前端自行处理缩略图拼接
│   ├── schemas/
│   │   ├── admin.py                  [MOD] 新增 TagGroup*, ImageTagUpdate, TagUpdate
│   │   └── student.py                [UNCHANGED]
│   └── migrations/
│       └── v2_migrate.py             [NEW] V1→V2 数据库迁移脚本
├── static/
│   ├── admin.html                    [REWRITE] 沉浸式打标工作台布局
│   ├── js/
│   │   ├── admin.js                  [REWRITE] 左右分栏打标逻辑 + 标签组管理
│   │   └── student.js                [REWRITE] 多选 + 队列下载 + 缩略图
│   └── student.html                  [REWRITE] 多选工具栏 + 下载进度条 UI
├── docs/
│   ├── task-tracker.md               [APPEND] Phase 9–13
│   ├── graduation-album-design-v2.md [THIS FILE]
│   ├── phase-11-draft.md             [NEW] Phase 11 实施草案
│   └── phase12-implementation-plan.md [NEW] Phase 12 实施方案
└── tests/
    ├── test_tag_group.py             [NEW] 标签分组模型 + 迁移测试
    └── test_v2_admin_api.py          [NEW] V2 新增 API 集成测试 (24 用例)
```

---

## 2. 数据库 ER 图 (V2.0)

```
┌──────────────────────────────────────┐
│            AlbumConfig               │
├──────────────────────────────────────┤
│ id              INTEGER PK           │
│ password_hash   TEXT NN              │
│ created_at      DATETIME             │
│ updated_at      DATETIME             │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│            TagGroup   [NEW]          │
├──────────────────────────────────────┤
│ id              INTEGER PK           │
│ name            TEXT NN U            │
│ created_at      DATETIME             │
└──────────────┬───────────────────────┘
               │ 1:N
               ▼
┌──────────────────────────────────────┐       ┌──────────────────────────────┐
│               Tag                    │       │       image_tags (assoc)     │
├──────────────────────────────────────┤       ├──────────────────────────────┤
│ id              INTEGER PK           │       │ image_id   INTEGER FK ────┐  │
│ name            TEXT NN U            │       │ tag_id     INTEGER FK ──┼──┼──┐
│ group_id        INTEGER FK ──────────┼──►TagGroup                        │  │  │
│ created_at      DATETIME             │       └───────────────────────────┘  │  │
└──────────────────────────────────────┘                                       │  │
                                                                              │  │
┌──────────────────────────────────────┐       ┌──────────────────────────┐   │  │
│             Student                  │       │          Image           │   │  │
├──────────────────────────────────────┤       ├──────────────────────────┤   │  │
│ id              INTEGER PK           │       │ id          INTEGER PK   │   │  │
│ name            TEXT NN              │       │ file_key    TEXT NN U    │◄──┘  │
│ secret_key      TEXT NN              │       │ file_name   TEXT         │◄─────┘
│ created_at      DATETIME             │       │ content_type TEXT        │
└──────────────────────────────────────┘       │ file_size   INTEGER      │
        ▼                                     │ uploaded_at DATETIME     │
        │ (逻辑关联: Student.name == Tag.name)  └──────────────────────────┘
        │                                      Image 不含 student_id
        │                                      隐私隔离通过 Tag 名称匹配
```

**关键变更**：
- **TagGroup** 表：新增分组维度，至少包含一个默认"未分类"组。
- **Tag.group_id**：新增外键指向 `tag_group.id`，默认指向"未分类"组。
- **Image 不含 student_id**：V1.0 已确立，V2.0 保持不变。

**迁移策略**：
1. 创建 `tag_group` 表。
2. 插入默认分组 `{name: "未分类"}`。
3. ALTER `tag` 表添加 `group_id` 列，所有现有 Tag 的 `group_id` 设为"未分类"组的 ID。

---

## 3. 核心接口签名 (V2.0 增量)

### IStorageService 新增方法

```python
async def get_thumbnail_url(self, file_key: str, width: int = 400) -> str:
    """利用 OSS x-oss-process 参数生成缩略图签名 URL。
    不增加后端存储，OSS 实时处理并返回。
    格式: {signed_url}?x-oss-process=image/resize,w_{width}
    """
```

**架构决策**：缩略图 URL 通过 `x-oss-process=image/resize,m_lfit,w_400,h_400` 动态生成，无需额外存储或 Lambda 触发器。OSS 对 `image/resize` 的处理延迟 <100ms。

> **实际实施偏差**: `get_thumbnail_url()` 未在后端实现。采用**前端拼接**方案：
> ```js
> function thumbnailUrl(url) {
>     const sep = url.includes('?') ? '&' : '?';
>     return `${url}${sep}x-oss-process=image/resize,m_lfit,w_400,h_400`;
> }
> ```
> 理由：OSS 签名 URL 已包含所有参数，前端直接追加处理参数无需额外后端调用，且不产生额外签名开销。

### ITaggingService

V2.0 保持不变。`ManualTaggingService.extract_tags()` 继续返回空列表。

---

## 4. API 路由设计 (V2.0 增量)

### V1.0 路由保留不变，以下为新增/修改

### 管理员路由增量 (`/api/admin`)

| 方法 | 路径 | 说明 |
|------|------|------|
| **修改** POST | `/api/admin/students` | **统一端点**：V2.0 改为 `{"names": "张三,李四,王五"}` 逗号分隔批量 + 自动创建同名 Tag（取代原单条接口和 batch 端点） |
| GET | `/api/admin/tag-groups` | 标签分组列表（含嵌套 tags） |
| POST | `/api/admin/tag-groups` | 创建分组 |
| PUT | `/api/admin/tag-groups/{id}` | 修改分组名称 |
| DELETE | `/api/admin/tag-groups/{id}` | 删除分组（组内 Tag 迁移至"未分类"） |
| PUT | `/api/admin/tags/{id}` | 修改标签所属分组 |
| **新增** PUT | `/api/admin/images/{id}/tags` | 编辑图片标签（body: `{"tag_ids": [1, 3, 5]}`），全量替换 |
| **修改** GET | `/api/admin/images?tagged=true\|false` | 新增 `tagged` 查询参数：`false` 返回未打标图片，`true` 返回已打标图片，缺省返回全部 |

### 学生路由增量 (`/api/student`)

| 方法 | 路径 | 说明 |
|------|------|------|
| **无变更** | `/api/student/*` | V2.0 学生路由未修改。缩略图 URL 由前端自行拼接，无需后端新增字段。 |

---

## 5. 前端页面设计 (V2.0)

### 5.1 `admin.html` — 沉浸式打标工作台

**布局架构**：

```
┌─────────────────────────────────────────────────────┐
│  Navbar: [🎓 管理后台]     [退出]                     │
├─────────────┬───────────────────────────────────────┤
│  Sidebar    │  打标工作台 (仅当未处理池非空时显示)      │
│             │  ┌──────────────┐ ┌──────────────────┐ │
│  👤 学生     │  │  未处理池     │ │  标签池 (按分组)  │ │
│  🏷️ 标签分组 │  │  ┌────┐     │ │  ┌────────────┐  │ │
│  🖼️ 打标台   │  │  │照片│ ←当前│ │  │ 🏢 寝室     │  │ │
│  ⚙️ 设置     │  │  └────┘     │ │  │  [张三][李四] │  │ │
│             │  │  共 12 张    │ │  │  [王五]      │  │ │
│             │  └──────────────┘ │  ├────────────┤  │ │
│             │                   │  │ 🎓 专业     │  │ │
│             │                   │  │  [计算机]    │  │ │
│             │                   │  │  [法学]      │  │ │
│             │                   │  ├────────────┤  │ │
│             │                   │  │ 📦 未分类   │  │ │
│             │                   │  │  [毕业典礼]  │  │ │
│             │                   │  └────────────┘  │ │
│             ├───────────────────────────────────────┤
│             │  已打标图片网格 (下方，始终可见)         │
│             │  ┌────┐ ┌────┐ ┌────┐ ┌────┐          │
│             │  │照片│ │照片│ │照片│ │照片│  ...      │
│             │  └────┘ └────┘ └────┘ └────┘          │
│             │  点击已打标图片 → 弹出标签编辑弹窗       │
└─────────────┴───────────────────────────────────────┘
```

**极简打标交互流程**：

1. 管理员进入"打标台" Tab。
2. 系统自动 GET `/api/admin/images?tagged=false` 加载未处理池。
3. 系统自动 GET `/api/admin/tag-groups` + `/api/admin/tags` 加载标签池（按分组聚合）。
4. 左侧自动选中第一张未处理图片。
5. 管理员点击右侧某标签 → 前端立即调用 PUT `/api/admin/images/{id}/tags` 关联该标签。
6. 该图片从左侧消失，自动选中下一张。
7. 当未处理池为空 → 打标工作台 UI 整体隐藏，显示 "所有图片已标注完毕"。
8. 下方已打标网格中点击图片 → 弹出轻量弹窗显示当前标签 + 可用的全部标签（勾选框），提交后局部更新。

**标签组管理**：侧边栏新增"标签分组" Tab，支持增删改，删除分组时组内 Tag 迁移至"未分类"。

### 5.2 `student.html` — 多选与队列下载

**缩略图加载**：照片网格的 `img.src` 使用后端返回的 `thumbnail_url`（基于 `x-oss-process=image/resize,w_400`），Lightbox 中点击后加载 `url`（高清原图）。

**多选模式**：

```
┌─────────────────────────────────────┐
│  Navbar: [🎓 毕业相册]     [多选]    │
├─────────────────────────────────────┤
│  选中 3 张后浮现下载栏：              │
│  ┌──────────────────────────────┐   │
│  │ ✓ 已选 3 张   [下载 (78MB)]  │   │
│  └──────────────────────────────┘   │
│                                      │
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐        │
│  │ ✓  │ │ ✓  │ │ ✓  │ │    │  ...   │
│  │照片│ │照片│ │照片│ │照片│        │
│  └────┘ └────┘ └────┘ └────┘        │
│                                      │
│  选中态：边框高亮 + 半透明遮罩 + ✓ 图标  │
└─────────────────────────────────────┘
```

**队列下载方案（纯 JS，无 ZIP 依赖）**：

```javascript
// 伪代码架构
class DownloadQueue {
    constructor(images) {
        this.queue = images;          // 待下载的 ImageResponse[]
        this.current = 0;
        this.total = images.length;
        this.aborted = false;
    }

    async start() {
        // UI: 显示 "正在下载 1/5 — photo.jpg"
        for (const img of this.queue) {
            if (this.aborted) break;
            const blob = await fetch(img.url).then(r => r.blob());
            triggerNativeDownload(blob, img.file_name);
            this.current++;
            // UI: 更新进度 "正在下载 3/5 — photo2.jpg"
            // 每张之间间隔 300ms，给浏览器时间触发原生下载弹窗
            await sleep(300);
        }
        // UI: "下载完成！"
    }
}
```

**关键设计决策**：
- 不使用 ZIP 打包：移动端浏览器对 ZIP 支持不一致，且无法显示单文件下载进度。
- 使用 `<a download>` 或 `URL.createObjectURL` 触发原生下载：浏览器自带下载管理器，移动端也能正确处理。
- 300ms 间隔：防止浏览器将并发下载省去为单文件，给每个下载独立的用户确认机会。
- 选中照片估算总大小：`totalSize = selected.reduce((sum, i) => sum + (i.file_size || 0), 0)`。

---

## 6. 构建顺序 (V2.0)

```
Phase 9:  数据库迁移与模型更新
          (TagGroup 模型、Tag.group_id、迁移脚本、测试)
    ↓
Phase 10: 管理端 API 升级
          (批量学生 + 标签分组 CRUD + 图片标签编辑 + get_thumbnail_url)
    ↓
Phase 11: 管理端前端重构 — 沉浸式打标工作台
          (左右分栏 UI、标签组管理、标签编辑弹窗)
    ↓
Phase 12: 学生端前端重构 — 多选与队列下载
          (缩略图、多选模式、下载队列)
    ↓
Phase 13: V2 集成测试与文档最终化
```

---

## 7. 关键设计决策 (V2.0 增量)

| 决策 | 理由 |
|------|------|
| OSS `x-oss-process` 缩略图 | 零额外存储、零后端处理负载，OSS 实时处理 <100ms |
| 纯 JS 队列下载（无 ZIP） | 移动端兼容性好，浏览器原生下载管理，单文件失败不影响其他 |
| 打标工作台分离未处理/已处理 | 极简交互：不可逆的视觉清除感驱动效率 |
| 标签分组默认"未分类" | 向后兼容 V1.0 数据，零配置上手 |
| 创建学生自动建 Tag | 减少管理员操作步骤，确保隐私隔离链完整 |
| 删除分组将 Tag 迁移而非级联删除 | 避免意外丢失标签关联数据 |

---

## 8. 验证方案 (V2.0)

1. `pytest tests/ -v` — 全量 98 用例全部通过 (V1.0 74 + V2.0 24)
2. 数据库迁移回滚测试：`test_migration_idempotent` 验证幂等性，`test_migration_preserves_image_tags` 验证数据完整性 ✓
3. `uvicorn app.main:app --reload` 启动服务
4. 进入 `/admin` 验证打标工作台：上传 → 未处理池 → 点击标签逐张标注 → 池清空后 UI 隐藏
5. 进入 `/student` 验证：缩略图加载 → 多选 → 队列下载 → 手机端实际测试
6. OSS `x-oss-process` URL 在浏览器和移动端均正常渲染

---

## 9. 实施偏差记录 (Design vs Implementation)

| 设计项 | 原始设计 | 实际实施 | 理由 |
|---|---|---|---|
| 批量学生端点 | `POST /api/admin/students/batch` | 统一 `POST /api/admin/students` + `{"names": "..."}` | 简化 API，单人和批量用同一端点，通过 names 字段区分 |
| 缩略图 URL | 后端 `get_thumbnail_url()` + `thumbnail_url` 字段 | 前端 `thumbnailUrl()` 拼接 OSS 参数 | OSS 签名 URL 已含全部参数，前端拼接无额外开销 |
| `tag_group_service.py` | 独立服务层 | 逻辑内联于 `routes/admin.py` | TagGroup CRUD 逻辑简单，无需抽离独立服务 |
| `DownloadQueue` 类 | ES6 Class | 函数式 `startDownload()` + `abortDownload()` | 状态由 `state` 对象管理，函数式足够清晰 |
| `ImageThumbnailResponse` | 新增 Schema | 未创建 | 前端自处理缩略图，后端无需新增字段 |
| admin 侧边栏 | 4 个 Tab | 5 个 Tab（新增"图片管理"） | 保留独立图片上传/管理页面，与打标工作台分离 |
| 下载间隔 | 设计 300ms | 实施 400ms | 实测 400ms 在 Chrome/Safari 上防拦截效果更稳定 |
