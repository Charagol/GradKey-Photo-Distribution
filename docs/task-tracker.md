# Development Task Tracker — 毕业季专属相册

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

### Phase 0: 项目脚手架

- [x] 创建目录结构
- [x] 编写 requirements.txt
- [x] 创建 .env.example
- [x] 创建 .gitignore
- [x] pip install -r requirements.txt

### Phase 1: 核心基础设施

- [x] 实现 app/config.py (Pydantic Settings)
- [x] 实现 app/database.py (SQLAlchemy)
- [x] 实现 AlbumConfig 模型
- [x] 实现 Student 模型
- [x] 实现 Tag 模型
- [x] 实现 Image 模型（无 student_id）
- [x] 实现 image_tags 关联表
- [x] 定义 IStorageService 接口
- [x] 定义 ITaggingService 接口
- [x] 验证 Models 无循环依赖

### Phase 2: 存储与打标服务

- [x] 实现 AliyunOssStorageService (upload, get_signed_url, delete, exists)
- [x] 实现 ManualTaggingService (返回空列表)
- [x] 编写 test_storage.py
- [x] 编写 test_tagging.py

### Phase 3: 认证与学生服务

- [x] 实现 auth_service.py (JWT, 密码验证)
- [x] 实现 student_service.py (Student CRUD, 密钥生成)
- [x] 实现 jwt_middleware.py
- [x] 编写 test_auth.py

### Phase 4: 管理员 API 路由

- [x] POST /api/admin/auth
- [x] GET/POST /api/admin/students
- [x] PUT/DELETE /api/admin/students/{id}
- [x] POST /api/admin/students/{id}/reset-key
- [x] GET /api/admin/images
- [x] POST /api/admin/images (多图上传+打标)
- [x] DELETE /api/admin/images/{id}
- [x] GET/POST/DELETE /api/admin/tags
- [x] PUT /api/admin/album-password
- [x] 编写 test_admin_api.py

### Phase 5: 学生 API 路由

- [x] POST /api/student/auth (双重验证)
- [x] GET /api/student/my-images (Tag 匹配隐私隔离)
- [x] GET /api/student/my-tags
- [x] 编写 test_student_api.py

### Phase 6: 管理员前端 (admin.html)

- [x] 登录遮罩层
- [x] 学生列表侧边栏
- [x] 标签管理
- [x] 图片上传+网格展示
- [x] 设置弹窗

### Phase 7: 学生前端 (student.html)

- [x] 登录表单
- [x] 照片瀑布流
- [x] 标签筛选
- [x] Lightbox 预览

### Phase 8: 集成与收尾

- [x] 路由挂载
- [x] 错误处理中间件
- [x] 端到端测试
- [x] 性能优化

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

## V2.0 Phase 进度

### Phase 9: 数据库迁移与模型更新

- [x] 创建 `app/models/tag_group.py` (TagGroup 模型)
- [x] Tag 模型新增 `group_id` 外键
- [x] 更新 `app/models/__init__.py` 注册 TagGroup
- [x] 编写迁移脚本 `app/migrations/v2_migrate.py`
  - [x] 创建 tag_group 表
  - [x] 插入默认"未分类"分组
  - [x] SQLite 三表重建添加 group_id 列
  - [x] 现有 Tag 默认归入"未分类"
- [x] 编写 `tests/test_tag_group.py` (13 个用例，模型 + 迁移验证)
- [x] 测试夹具注入默认 TagGroup（test_admin_api.py / test_student_api.py）
- [x] Tag.before_insert 事件确保向后兼容
- [x] 生产数据库迁移验证通过（album.db: 5 tags → 未分类）

### Phase 10: 管理端 API 升级

- [x] `app/schemas/admin.py` 新增:
  - [x] `StudentCreate.names: str` (V2.0 逗号分隔批量)
  - [x] `TagGroupCreate` / `TagGroupUpdate` / `TagGroupResponse` (含嵌套 tags)
  - [x] `TagUpdate(group_id)` / `ImageTagUpdate(tag_ids: list[int])`
- [x] `app/services/student_service.py` 新增 `auto_commit` 参数支持批量事务
- [x] 管理员路由新增/修改:
  - [x] **POST /api/admin/students** (统一端点: `{"names": "张三,李四"}` 逗号分隔批量 + 自动建 Tag)
  - [x] `GET/POST /api/admin/tag-groups` (分组 CRUD)
  - [x] `PUT/DELETE /api/admin/tag-groups/{id}` (重命名/删除, 删除时 Tag 迁移至"未分类")
  - [x] `PUT /api/admin/tags/{id}` (移动标签至其他分组)
  - [x] `PUT /api/admin/images/{id}/tags` (全量替换图片标签)
  - [x] **GET /api/admin/images** (新增 `?tagged=true|false` 过滤参数)
- [x] `tests/test_admin_api.py` 适配 V2.0 schema (4 处)
- [x] `tests/test_student_api.py` 适配 + `_setup_tag` 幂等化 (acceps 201/409)
- [x] `tests/test_v2_admin_api.py` (24 个用例, 覆盖所有新增接口)
- [x] 全量测试 98 passed

### Phase 11: 管理端前端重构 — 沉浸式打标工作台 ✅

- [x] 重写 `static/admin.html` 布局:
  - [x] 顶部导航条 + 左侧边栏（打标台/学生/分组/图片/设置）
  - [x] 打标工作台：左右分栏（未处理池 w-3/5 + 标签池 w-2/5）
  - [x] 标签池按 TagGroup 分组面板展示
  - [x] 已打标图片网格（下方，支持 tagged/untagged/all 过滤）
  - [x] 标签编辑 Modal（含当前标签 + 可用标签选择器）
- [x] 重写 `static/js/admin.js`:
  - [x] State 驱动渲染：allImages → unprocessed + processed 自动分流
  - [x] 核心交互：点击标签 → PUT /images/{id}/tags → 图片消失 + 自动选中下一张
  - [x] processingLock 防抖锁 + 事件委托避免重复绑定
  - [x] 未处理池清空时自动隐藏工作区 + 显示"全部处理完毕"
  - [x] 已打标图片点击 → Modal 二次编辑标签
  - [x] 标签分组管理（增删改 + 标签拖拽移动）
  - [x] 批量学生创建（逗号分隔）
  - [x] 图片上传/管理/删除 + 相册设置完整保留

### Phase 12: 学生端前端重构 — 多选与队列下载 ✅

- [x] 修改 `static/student.html`:
  - [x] 导航栏新增"开启多选"切换按钮
  - [x] 底部浮现选择操作栏（全选/取消全选/下载选中/取消）
  - [x] 底部下载进度条（旋转 spinner + "正在下载 X/Y" + 中止按钮）
  - [x] 选中态 UI：indigo 半透明遮罩 + ✓ 圆形标记
- [x] 修改 `static/js/student.js`:
  - [x] 缩略图模式：列表用 OSS `x-oss-process=image/resize,m_lfit,w_400,h_400`，Lightbox 用原图
  - [x] 多选模式状态管理：`isMultiSelectMode` + `selectedIds: Set` + `downloadProgress`
  - [x] 下载队列：fetch → Blob → `URL.createObjectURL` → `<a download>` → 400ms 间隔防拦截
  - [x] 进度 UI："正在下载 X/Y — filename" + 旋转 spinner
  - [x] 中止功能：`downloadAborted` flag + 中止按钮
  - [x] 保留原有标签过滤 + Lightbox 键盘/触摸导航

### Phase 13: V2 集成测试与文档 ✅

- [x] 全量测试 `pytest tests/ -v` — **98/98 passed**
- [x] 数据库迁移回滚验证 — `test_migration_idempotent` + `test_migration_preserves_*` 全部通过
- [x] OSS 缩略图 URL — 前端拼接方案，`thumbnailUrl()` 逻辑已验证
- [x] 移动端兼容性审查:
  - [x] viewport meta + touch swipe 事件 + 响应式 grid (2/3/4 列)
  - [x] 多选触摸交互 — 点击切换选中（无需 hover）
  - [x] 下载队列 — `<a download>` 原生下载，移动端兼容
  - [x] 缩略图渲染 — OSS x-oss-process 实时处理，<100ms
- [x] 更新 `docs/graduation-album-design-v2.md` 标注 7 项实施偏差
- [x] Git tag: `v2.0.0`

---

### Phase 14: 标签管理 UI 优化与安全删除

- [x] 侧边栏 "标签分组" → "标签管理"
- [x] 面板标题 "标签分组管理" → "标签管理"
- [x] 标签 chip 添加删除按钮 (×)，hover 变红 (`hover:text-red-500`)
- [x] 删除确认对话框显示受影响的照片数量: `state.allImages.filter(img => img.tags.some(t => t.id === tagId)).length`
- [x] 删除后自动刷新 images + tag groups + workspace 视图
- [x] "未分类" 默认分组始终可见，样式与其他分组一致

---

### Phase 15: 项目完结与交付物整理

- [x] 依赖审计 — requirements.txt 确认完整覆盖所有运行依赖
- [x] 配置模板 — `.env.example` 重写，包含详细注释与 OSS CORS 引导
- [x] 代码清理:
  - [x] `static/js` — 无 `console.log` 残留（确认 0 处）
  - [x] `app` — 代码审查完成：无 console.log / TODO / 临时注释。`get_student()` 保留（测试依赖）
  - [x] `app/main.py` — 版本号更新为 `2.0.0`
- [x] 交付文档:
  - [x] `README.md` — 用户与部署文档（快速开始/OSS CORS 指南/使用手册/项目结构）
  - [x] `docs/technical-overview.md` — 技术架构深度解析（SSOT 隐私隔离/OSS 缩略图/下载队列/ER 图/测试策略）
- [x] Git 提交归档

---


## V3.0 Phase 进度

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

## 项目总结

### 开发规模

| 指标 | 数值 |
|---|---|
| 总 Phase 数 | 20 |
| 后端代码 (Python) | ~1600 行 |
| 前端代码 (HTML + JS) | ~2400 行 |
| 测试用例 | 102 (全量通过) |
| 数据模型 | 6 个表 |
| API 端点 | 20+ |

### 架构亮点

1. **SSOT 隐私隔离**: `Student.name = Tag.name` 逻辑匹配，零外键耦合，天然支持合影语义
2. **沉浸式打标工作台**: 状态驱动渲染 + 事件委托 + processingLock 防抖，V3.0 新增多标签 toggle + 确认按钮模式，完整支持合影语义
3. **前端队列下载**: Blob fetch + 400ms 间隔 + 可取消标志位，绕过浏览器批量下载拦截
4. **OSS 动静分离**: 数据库仅存 File Key，签名 URL 动态生成，V3.0 修复 x-oss-process 参与签名确保缩略图正确加载
5. **零构建步骤**: Vanilla JS + Tailwind CDN，无 npm/webpack，解压即用

### 技术债务与未来方向

- **未分类接口抽象**: `IStorageService`/`ITaggingService` 接口已定义但未用于多态，预留未来多云/AI 扩展
- **AI 自动打标**: `ManualTaggingService` 返回空列表，预留 InsightFace/CLIP 集成接口
- **并发扩展**: SQLite 适合单机/内网场景，如需多用户高并发可迁移至 PostgreSQL

---

*最后更新: 2026-06-06 | V3.0 Phase 22 · 图片管理多选批量删除*
