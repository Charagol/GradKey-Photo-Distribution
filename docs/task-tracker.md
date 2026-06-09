# Development Task Tracker — 毕业季专属相册

---

## 文档维护准则

| 文件 | 职责 | 更新时机 | 版本结束时 |
|------|------|----------|-----------|
| `docs/task-tracker.md` | 施工日志，记录每个 Phase 的完成状态 | 每个 Phase 结束 | 折叠旧版本，保留最近 2 个版本展开 |
| `docs/design-v{N}.md` | 版本蓝图，目标和设计决策 | 大版本开始时创建 | 封存，标注完成日期，不再修改 |
| `docs/technical-overview.md` | 技术快照，写给未来的维护者 | 大版本结束时 | 替换为新快照，反映当前实际架构 |
| `.qoder/specs/*.md` | 大 Plan 的工作草稿 | 大 Plan 时生成 | **全部删除**。诊断报告的结论吸收进 task-tracker 或 technical-overview 后删除 |

---

## 业务逻辑核心规则 (Single Source of Truth)

### 隐私隔离机制

**规则**: `Student.name` 与 `Tag.name` 通过字符串匹配实现逻辑关联。

当学生（如 `张三`）通过「相册密码 + 个人密钥」双重验证登录后:
- 后端查询 `Tag.name == '张三'` 所关联的所有 `Image`
- **仅返回**这些 Image 给学生，实现「只看自己」的隐私隔离

**数据模型**: `Image` 表**不含** `student_id` 外键。Image 是相册级别的公共资源，隐私边界由 Tag 匹配控制。

**扩展预留**: 未来可定义特殊公共 Tag（如 `大合照`）作为共享照片集合。

---

## Phase 进度

> **V1.0** (Phase 0–8, 2026-06-04, 61/61 测试) — 基础架构与核心功能。详见 `docs/design-v1.md`。
> **V2.0** (Phase 9–15, 2026-06-05, 98/98 测试) — 标签分组与沉浸式打标。详见 `docs/design-v2.md`。

---

## 核心接口签名

### IStorageService

```python
class IStorageService(ABC):
    async def upload(self, file_data: bytes, file_name: str, content_type: str) -> str
    async def get_signed_url(self, file_key: str, expires_seconds: int = 900) -> str
    async def delete(self, file_key: str) -> bool
    async def exists(self, file_key: str) -> bool
```

### ITaggingService

```python
class ITaggingService(ABC):
    async def extract_tags(self, image_data: bytes, file_name: str) -> list[str]
```

---

## V3.0 (Phase 16–22) — 缺陷修复与体验优化

### Phase 16: 标签管理页初始加载 Bug 修复

- [x] **根因**: `loadTagGroups()` (admin.js:378) 数据加载后缺失 `renderTagGroups()` 调用
- [x] **修复**: 
  - `loadTagGroups()` 添加 try/catch 错误处理 + `renderTagGroups()` 调用
  - `renderTagGroups()` 内部添加 try/catch + console.error 防静默失败
  - `switchTab()` 中 `loadTagGroups()` 添加 `.catch()` 处理未捕获的 Promise 拒绝
- [x] **验证**: 98/98 全量测试通过

---

### Phase 17: 打标工作台多标签修复 + 学生端缩略图加载修复

**背景**: V3.0 需修复两个 V2.0 遗留的致命缺陷。

#### 任务 1: 打标工作台多标签选择 + 确认按钮模式

- [x] **根因**: 标签点击立即执行 `PUT /api/admin/images/{id}/tags` 并自动推进，每张照片只能打一个标签，破坏合影语义
- [x] **修复**:
  - `state` 新增 `selectedTagIds: []` 字段（工作台待确认标签列表）
  - 新增 `toggleTagSelection(tagId)` — 标签点击切换选中状态（非提交）
  - 新增 `renderConfirmButton()` — 动态渲染确认按钮（0 选中时灰色禁用，N 选中时蓝色可点击显示计数）
  - 新增 `confirmTags()` — 收集全部选中 tag_ids → PUT API 全量替换 → 清除选中 → 自动推进
  - `renderTagPool()` 芯片增加选中态 CSS（蓝底蓝边框高亮）
  - `selectImage()` / `splitImages()` 重置 `selectedTagIds`
  - `renderWorkspace()` 调用 `renderConfirmButton()`
  - `admin.html` 更新提示文案 + 新增 `#confirm-tags-area` 容器
  - 事件委托：标签池点击改为 `toggleTagSelection` + 新增确认按钮 `[data-action="confirm-tags"]` 监听
  - 与 `processingLock` 完整协调（toggle/confirm 均被锁阻塞）
- [x] **接口行为**: `PUT /api/admin/images/{id}/tags` 不变（全量替换语义），前端一次性提交多个 tag_ids

#### 任务 2: 学生端缩略图加载失败修复

- [x] **根因**: `oss2.Bucket.sign_url` 签名计算不包含 `x-oss-process` 参数；前端 `thumbnailUrl()` 简单字符串拼接 `&x-oss-process=...` → OSS 服务器验证签名时纳入该参数 → 签名不匹配 → 403 Forbidden
- [x] **修复**:
  - `IStorageService` 新增 `get_thumbnail_signed_url(file_key, width=400, height=400, expires_seconds=900)` 抽象方法
  - `AliyunOssStorageService` 实现：`sign_url("GET", key, expires, {"x-oss-process": "image/resize,m_lfit,w_400,h_400"})`，确保 OSS SDK 将参数纳入签名
  - `ImageResponse` 新增 `thumbnail_url: str | None = None` 可选字段（向后兼容，管理员端无需填充）
  - 学生 API `GET /api/student/my-images` 并行调用 `get_signed_url` 和 `get_thumbnail_signed_url` 为每张图片生成两种 URL
  - 前端 `renderPhotoGrid()` 优先使用 `img.thumbnail_url`，降级到 `thumbnailUrl(img.url)` 作为向后兼容回退
  - 新增 4 个 `TestGetThumbnailSignedUrl` 单元测试（返回字符串、params 传递、自定义尺寸、默认有效期）
  - `mock_storage` fixture 更新，新增 `get_thumbnail_signed_url` side_effect

#### 测试覆盖

- [x] **验证**: 102/102 全量测试通过（原 98 + 新增 4 个缩略图测试）
- [x] `test_images_have_signed_urls` 扩展断言 `thumbnail_url` 字段存在

---

### Phase 18: 体验与 UI 优化 — V3.0 Phase 3.3

**背景**: 三个独立的用户体验优化任务，提升管理端和学生端的交互体验。

#### 任务 1: 批量添加学生改为中文全角逗号分隔

- [x] `app/routes/admin.py`: `split(",")` → `split("，")`
- [x] `app/schemas/admin.py`: 更新 `StudentCreate.names` 注释为 "中文全角逗号分隔姓名"
- [x] `static/admin.html`: 标题文案改为 "添加学生（中文逗号批量分隔）"，placeholder 改为 "张三，李四，王五"
- [x] `static/js/admin.js`: 前端容错 `input.value.trim().replace(/,/g, '，')`
- [x] `tests/test_v2_admin_api.py`: 4 处测试用例半角逗号改为全角（3 处数据 + 1 处空白）
- [x] 102/102 全量测试通过

#### 任务 2: 标签选择区域瀑布流布局

- [x] `static/admin.html`: 新增 `.tag-waterfall` CSS 样式块（`column-count: 2; column-gap: 1rem; break-inside: avoid`）
- [x] `static/admin.html`: `#tag-group-panels` class 从 `space-y-4` 改为 `tag-waterfall`
- [x] `static/js/admin.js` `renderTagPool()`: 过滤空标签分组（`if (tags.length === 0) return '';`）
- [x] `static/js/admin.js` `renderTagPool()`: 移除标签计数 `<span>`，标题简化为单行 `<h4>`

#### 任务 3: 学生端多选下载 UI 收敛至统一操作栏

- [x] `static/student.html`: 移除 navbar 中 `#multi-select-toggle-btn`
- [x] `static/student.html`: 标签筛选栏下方新增 `#multi-select-bar` 统一操作栏
- [x] `static/js/student.js`: 新增 `renderMultiSelectBar()` — 状态驱动渲染（普通/多选两模式）
- [x] `static/js/student.js`: `updateSelectionUI()` 简化为调用 `renderMultiSelectBar()`
- [x] `static/js/student.js`: `startDownload()` 清理逻辑移除旧 DOM 操作，改为 `renderMultiSelectBar()`
- [x] `static/js/student.js`: 事件绑定改为 `data-action` 事件委托（`#multi-select-bar-inner`）
- [x] `static/js/student.js`: `loadData()` 末尾调用 `renderMultiSelectBar()`

#### 测试覆盖

- [x] **验证**: 102/102 全量测试通过

---

### Phase 19: 缩略图加载失败根因修复

**背景**: Phase 17 的缩略图修复未能解决根本问题 — 学生端缩略图仍然 403。

#### 根因

`oss2.Bucket.sign_url` 的真实签名为 `sign_url(method, key, expires, headers=None, params=None, ...)`，`params` 是第 5 个位置参数。Phase 17 代码将 `{"x-oss-process": ...}` 作为第 4 个位置参数传入，被 SDK 识别为 `headers` 而非 `params`。导致：
- `x-oss-process` 被纳入签名计算（作为 CanonicalizedHeaders）
- 但 **未追加到 URL Query String**（headers 不是查询参数）
- 浏览器发起的请求与签名不匹配 → 403 Forbidden

#### 修复

- [x] `app/services/aliyun_oss_storage.py`: `params={"x-oss-process": ...}` 改为关键字参数传递
- [x] `tests/test_storage.py`: 2 个测试适配（`call_args[0][3]` → `call_args.kwargs["params"]`）
- [x] `docs/phase18-diagnosis.md`: 完整诊断报告

#### 测试覆盖

- [x] **验证**: 102/102 全量测试通过
- [x] 修复后 `thumbnail_url` 应包含 `x-oss-process` 查询参数

---

### Phase 20: 管理端缩略图加载启用

**背景**: Phase 19 诊断发现管理端打标工作台和图片管理均未使用缩略图，加载原图导致带宽浪费严重。

#### 修复

- [x] `app/routes/admin.py` `list_images_view`: 为每张图片调用 `get_thumbnail_signed_url` 填充 `thumbnail_url`
- [x] `static/js/admin.js` `renderUnprocessedGrid()`: `img.url` → `img.thumbnail_url || img.url`
- [x] `static/js/admin.js` `renderProcessedGrid()`: 同上
- [x] `static/js/admin.js` `renderAllImages()`: 同上
- [x] `openEditModal()` 预览保持 `image.url`（原图）不变
- [x] `tests/test_admin_api.py` + `tests/test_v2_admin_api.py`: mock 补充 `get_thumbnail_signed_url`

#### 测试覆盖

- [x] **验证**: 102/102 全量测试通过
- [x] 管理端带宽预计节省 95%+

---

### Phase 21: 管理端 UI 优化三项

**背景**: 三个独立的小型 UI 优化，提升管理端交互体验。

#### 任务 1: 编辑弹窗预览缩略图化

- [x] `openEditModal()` 预览从 `image.url` 改为 `image.thumbnail_url || image.url`
- [x] 与网格渲染保持一致，拖动到桌面得到缩略图而非原图

#### 任务 2: 多选模式隐藏删除按钮

- [x] `state` 新增 `isMultiSelectMode: false`
- [x] `renderAllImages()` 删除按钮在 `isMultiSelectMode` 时添加 `hidden` class
- [x] 为后续 Phase 22 多选功能做前置准备

#### 任务 3: 移除遗留关联标签功能

- [x] `admin.html`: 移除上传区"关联标签"label + `#image-tags` input
- [x] `admin.js` `uploadImages()`: 移除 `tagsInput` 引用、标签解析、`tagsInput.value = ''` 重置
- [x] V2.0 打标工作台已完全替代此功能

#### 测试覆盖

- [x] **验证**: 102/102 全量测试通过（纯前端改动，无后端影响）

---
### Phase 22: 图片管理多选批量删除

**背景**: Phase 21 已预留 `isMultiSelectMode` 状态，本 Phase 实现完整的多选批量删除功能。

#### 后端

- [x] Schema `ImageBatchDeleteRequest(image_ids: list[int])` — 批量删除请求体
- [x] `DELETE /api/admin/images/batch` 端点 → 204
    - 空列表 → 400
    - 部分/全部不存在 → 404
    - 事务包裹：DB 操作 all-or-nothing，OSS 删除 best-effort
- [x] **路由顺序修复**: `/images/batch` 必须在 `/images/{image_id}` 之前注册，否则 FastAPI 将 "batch" 匹配为 path param

#### 前端 HTML

- [x] 上传卡片与图片网格之间新增 `#image-multi-select-bar` 容器
    - 未激活时仅显示「开启多选」按钮
    - 激活后显示全选/取消全选/计数/删除选中/取消 操作栏

#### 前端 JS

- [x] `state` 新增 `selectedImageIds: Set` — 选中的图片 ID 集合
- [x] `renderImageMultiSelectBar()` — 根据 `isMultiSelectMode` 状态渲染操作栏
- [x] `toggleMultiSelectMode()` — 进入/退出多选模式，重置选中集
- [x] `selectAllImages()` / `deselectAllImages()` — 全选/取消全选
- [x] `batchDeleteSelected()` — confirm 确认 → DELETE API → reload + 退出多选
- [x] `renderAllImages()` — 多选模式下 card 叠加 indigo ring + 勾选徽章，`data-image-id` 属性
- [x] `switchTab()` — 离开图片 Tab 时重置 `isMultiSelectMode` + `selectedImageIds`
- [x] `bindEvents()` — `#image-manage-grid` 事件委托（card 点击选/取消选 + 删除按钮），`#image-multi-select-bar-inner` 事件委托（`data-action` 按钮）
- [x] 移除 `renderAllImages()` 中旧的独立 `.delete-image-btn` 逐个绑定，统一改为事件委托

#### 测试覆盖

- [x] `TestImageBatchDelete` 6 个用例（空列表/不存在/部分不存在/成功/全部/未认证）
- [x] **验证**: 59/59 全量测试通过（新增 6 用例 + 原有 53 保持通过）

---

## V4.0 (Phase 23+) — 工程化与体验大版本

### Phase 23: V4.0 P1 — 登录 localStorage 持久化 + JWT exp 校验

**背景**: V3.0 使用 sessionStorage 存储 JWT，学生关闭标签页后登录态丢失，刷新页面即被迫重登。V4.0 P1 迁移至 localStorage 并增加过期校验。

#### 存储迁移

- [x] `static/js/admin.js`: 4 处 `sessionStorage` → `localStorage`（初始化/L47、登出/L74、登录成功/L96）+ 另外 2 处同区块（初始化和登出各包含 1 个 getItem/removeItem）
- [x] `static/js/student.js`: 7 处 `sessionStorage` → `localStorage`（init×2/L38-L39、clearToken×2/L69-L70、login×2/L116-L117）+ L5 头部注释更新

#### JWT exp 校验

- [x] 新增 `isTokenExpired(token)` 函数（两个文件各自实现）
  - 解析 `payload.exp` 与 `Math.floor(Date.now() / 1000)` 对比
  - 缺 `exp` 字段 → `!payload.exp` → 视为过期
  - 非 JWT 格式 / `atob` 失败 / `JSON.parse` 失败 → `catch` → 视为过期
- [x] 初始化流程改造：`admin.js` 和 `student.js` 均在 `DOMContentLoaded` 中校验 token 有效性，过期则清除 localStorage 后进登录页
- [x] 后端零改动

#### 测试覆盖

- [x] 108/108 全量测试通过（纯前端改动，后端行为不变）

---

### Phase 24: V4.0 P2 — Lightbox w_1200 缩略图 + 引导文案

**背景**: Lightbox 加载原图（3-10MB）导致加载延迟和带宽浪费。V4.0 P2 改为 w_1200 缩略图，移除「查看原图」入口，引导用户走向多选下载。

#### 后端

- [x] `ImageResponse` schema 新增 `lightbox_url: str | None = None` 字段
- [x] `GET /api/student/my-images` 新增 `get_thumbnail_signed_url(file_key, width=1200)` 调用，填充 `lightbox_url`

#### 前端

- [x] `updateLightboxContent()`: `img.url` → `img.lightbox_url \|\| img.thumbnail_url`（优先 w_1200，降级 w_400）
- [x] `student.html` Lightbox 底部新增引导文案：「如需要高清原图，请使用多选下载功能」
- [x] 无「查看原图」按钮 — 学生需要原图的唯一场景是本地保存，即多选队列下载

#### 测试覆盖

- [x] `test_images_have_signed_urls` 新增 `lightbox_url` 字段断言
- [x] 108/108 全量测试通过

---

### Phase 25: V4.0 P4 — 批量打标 (多选照片 + 分组全选标签)

**背景**: 当一位同学出现在多张合影中，需要对多张照片打上同一标签。V4.0 P4 提供两个方向的批量操作。

#### Direction A: 多选照片批量打标

- [x] `state` 新增 `isBatchImageMode: false` + `batchSelectedImageIds: new Set()`
- [x] `admin.html` 新增 `#batch-image-bar` 容器（位于 `#unprocessed-pool` 内）
- [x] `renderBatchImageBar()` — 状态驱动渲染：非批量模式显示「批量模式」入口按钮；批量模式显示全选/取消全选/已选计数/确认打标/取消
- [x] `enterBatchImageMode()` / `exitBatchImageMode()` — 切换批量模式，重置选中集合
- [x] `selectAllUnprocessed()` / `deselectAllUnprocessed()` — 全选/取消全选待打标图片
- [x] `toggleBatchImageSelection(imageId)` — 单张图片选中/取消切换
- [x] `batchConfirmTags()` — 串行 `PUT /api/admin/images/{id}/tags` 逐张打标，`processingLock` 保护，失败时 toast 报告具体图片；**全部完成后统一清空 `selectedTagIds`**
- [x] `renderUnprocessedGrid()` — 批量模式下缩略图叠加 indigo 半透明遮罩 + 白色 ✓ 圆形复选框 + 选中项 indigo ring
- [x] `renderWorkspace()` 调用 `renderBatchImageBar()`
- [x] `toggleTagSelection()` — 批量模式下联动调用 `renderBatchImageBar()` 刷新确认按钮状态
- [x] 事件委托: `#unprocessed-pool` 容器监听批量栏按钮；`#unprocessed-grid` 在批量模式下点击触发 `toggleBatchImageSelection` 而非 `selectImage`
- [x] `switchTab()` / `splitImages()` — 离开工作台或数据重载时重置批量模式

#### Direction B: 点击分组标题全选/取消全选组内标签

- [x] `toggleGroupTags(groupId)` — 若组内全部标签已选中 → 取消全选；否则 → 补选所有组内未选中标签
- [x] `renderTagPool()` — 分组标题添加 `cursor-pointer hover:text-indigo-600 select-none` + `data-action="toggle-group-tags"` + `data-group-id`；全选状态高亮（`text-indigo-700` + `✓` 标记）
- [x] 事件委托: `#tag-pool` 优先检查分组标题点击 → `toggleGroupTags`；否则走原有 tag chip 逻辑

#### 测试覆盖

- [x] 108/108 全量测试通过

---

## 项目总结

### 开发规模

| 指标 | 数值 |
|---|---|
| 总 Phase 数 | 26 |
| 后端代码 (Python) | ~2000 行 |
| 前端代码 (HTML + JS) | ~2000 行 |
| 测试用例 | 108 (全量通过) |
| 数据模型 | 6 个表 |
| API 端点 | 22+ |

### 架构亮点

1. **SSOT 隐私隔离**: `Student.name = Tag.name` 逻辑匹配，零外键耦合，天然支持合影语义
2. **沉浸式打标工作台**: 状态驱动渲染 + 事件委托 + processingLock 防抖，V3.0 新增多标签 toggle + 确认按钮模式，完整支持合影语义
3. **前端队列下载**: Blob fetch + 400ms 间隔 + 可取消标志位，绕过浏览器批量下载拦截
4. **OSS 动静分离 + 缩略图签名修复 (V3.0)**: 数据库仅存 File Key，签名 URL 动态生成；Phase 17/19 根因修复 `sign_url` 传参 — `x-oss-process` 以关键字 `params=` 传入 SDK，确保 OSS 签名计算包含参数，全链路 403 终结
5. **图片管理批量删除 (V3.0)**: 多选模式 + 事件委托 + 批量 DELETE 端点，卡片叠加 indigo 选中态，切换 Tab 自动重置
6. **零构建步骤**: Vanilla JS + Tailwind CDN，无 npm/webpack，解压即用

### 技术债务与未来方向

- **未分类接口抽象**: `IStorageService`/`ITaggingService` 接口已定义但未用于多态，预留未来多云/AI 扩展
- **AI 自动打标**: `ManualTaggingService` 返回空列表，预留 InsightFace/CLIP 集成接口
- **并发扩展**: SQLite 适合单机/内网场景，如需多用户高并发可迁移至 PostgreSQL

---

*最后更新: 2026-06-09 | V4.0 P4 完成*
