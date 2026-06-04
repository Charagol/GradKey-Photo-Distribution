# Phase 11: 管理端 UI 重构（沉浸式打标工作流）— 实施草案

## 一、HTML 骨架草图

当前 `admin.html` 是旧的选项卡架构（学生/标签/图片/设置四个 Tab Panel）。Phase 11 将**完全重写** `#dashboard` 内部结构，保留登录遮罩、Toast 容器和 Tailwind CDN 不变。

### 新布局层级

```
#dashboard (初始 hidden)
├── #topbar (顶部导航条，h-16, flex, 白色背景, 阴影)
│   ├── 标题 "管理后台"
│   └── #logout-btn (退出登录)
│
└── .flex (主体区域)
    ├── #sidebar (w-56, 左侧导航, 固定高度)
    │   ├── 导航按钮组：
    │   │   ├── .nav-btn[data-tab="workspace"] → 🎯 打标工作台
    │   │   ├── .nav-btn[data-tab="students"]   → 👤 学生管理
    │   │   ├── .nav-btn[data-tab="tag-groups"]  → 📂 标签分组
    │   │   └── .nav-btn[data-tab="settings"]    → ⚙️ 设置
    │   └── 底部：版本信息
    │
    └── #main-content (flex-1, 溢出滚动)
        │
        ├── #tab-workspace (打标工作台面板)
        │   ├── #workspace-area (当有未处理图片时可见)
        │   │   ├── .flex.gap-6
        │   │   │   ├── #unprocessed-pool (左侧, w-3/5)
        │   │   │   │   ├── 标题："📸 待打标图片" + 计数 badge
        │   │   │   │   └── #unprocessed-grid (grid, 缩略图网格, 4列)
        │   │   │   │       ├── .thumb-item[data-image-id] × N
        │   │   │   │       │   ├── <img> 缩略图 (aspect-[4/3], object-cover)
        │   │   │   │       │   └── 高亮选中态：ring-2 ring-indigo-500
        │   │   │   │
        │   │   │   └── #tag-pool (右侧, w-2/5)
        │   │   │       ├── 标题："🏷️ 选择标签" + 说明文字
        │   │   │       └── #tag-group-panels
        │   │   │           └── .tag-group-panel × N (按 TagGroup 分组)
        │   │   │               ├── .group-header (分组名 + 标签计数)
        │   │   │               └── .tag-chips (flex-wrap)
        │   │   │                   └── .tag-chip[data-tag-id] × N
        │   │   │                       └── 标签名（可点击按钮）
        │   │
        │   └── #workspace-empty (当无未处理图片时可见)
        │       └── 🎉 "所有图片已处理完毕" 提示
        │
        ├── #tab-students (学生管理面板)
        │   ├── 批量创建卡片
        │   │   ├── <textarea> 姓名输入（逗号分隔, 支持多行）
        │   │   └── "添加" 按钮
        │   ├── 学生表格 (同旧版, #students-tbody)
        │   └── 空状态
        │
        ├── #tab-tag-groups (标签分组管理面板)
        │   ├── 新建分组卡片
        │   ├── 分组列表 #tag-group-list
        │   │   └── .group-card × N
        │   │       ├── 分组名 + 编辑/删除按钮
        │   │       └── 该分组下的 tag chips（用 PUT /tags/{id} 移动）
        │   └── 空状态
        │
        └── #tab-settings (设置面板, 同旧版)
```

### 图片编辑 Modal

```
#edit-modal (初始 hidden, 固定定位遮罩层)
├── .modal-backdrop (半透明背景, 点击关闭)
└── .modal-content (居中白色卡片, max-w-lg)
    ├── 大图预览 (含签名 URL)
    ├── 当前标签列表 (可删除)
    ├── 添加标签搜索/选择器
    ├── "保存" 按钮
    └── "关闭" 按钮
```

### 已处理图片区域

```
#processed-section (始终在打标台下方显示)
├── 标题 "📁 已处理图片" + 计数
├── 筛选按钮组：全部 | 已打标 | 未打标（对应 ?tagged 参数）
└── #processed-grid (grid, 同缩略图网格)
    └── .processed-item × N（点击打开 edit-modal）
```

---

## 二、JS 状态管理设计

```js
const state = {
    // ── 认证 ──
    token: null,                    // 从 sessionStorage 恢复

    // ── 导航 ──
    currentTab: 'workspace',        // workspace | students | tag-groups | settings

    // ── 图片数据（核心） ──
    allImages: [],                  // GET /api/admin/images 全量数据
    unprocessed: [],                // 内存分流：tags.length === 0 的图片
    processed: [],                  // 内存分流：tags.length > 0 的图片
    currentImageId: null,           // 当前高亮选中的未处理图片 ID

    // ── 标签数据 ──
    tagGroups: [],                  // GET /api/admin/tag-groups（含嵌套 tags）
    // 结构: [{ id, name, tags: [{id, name, group_id}] }]

    // ── 学生数据 ──
    students: [],                   // GET /api/admin/students

    // ── UI 状态 ──
    filteredProcessed: [],          // 已处理图片的过滤视图（全部/已打标/未打标）
    processingLock: false,          // 防止快速重复点击标签
    editingImageId: null,           // 当前 Modal 编辑的图片 ID
};
```

---

## 三、核心 JS 函数签名与逻辑

### 3.1 初始化 & 认证（复用现有模式）

| 函数 | 说明 |
|---|---|
| `init()` | DOMContentLoaded 入口：恢复 token → showDashboard() 或 showLogin() → bindEvents() → switchTab('workspace') |
| `showLogin()` / `showDashboard()` | 同旧版，切换 #login-overlay / #dashboard 可见性 |
| `handleLogin()` / `logout()` | 同旧版，POST /api/admin/auth |
| `bindEvents()` | 绑定所有事件监听器（导航、打标、学生、分组、设置、Modal） |

### 3.2 数据加载

| 函数 | 逻辑 |
|---|---|
| `async loadAllData()` | 首次进入 dashboard 时并行调用：`Promise.all([loadImages(), loadTagGroups(), loadStudents()])` |
| `async loadImages()` | `GET /api/admin/images` → 存入 `state.allImages` → 调用 `splitImages()` |
| `async loadTagGroups()` | `GET /api/admin/tag-groups` → 存入 `state.tagGroups` |
| `async loadStudents()` | `GET /api/admin/students` → 存入 `state.students` |

### 3.3 图片分流与筛选

| 函数 | 逻辑 |
|---|---|
| `splitImages()` | 遍历 `state.allImages`：`tags.length === 0` → `unprocessed[]`，否则 → `processed[]`。`processed[]` 按 `uploaded_at` 倒序排列。 |
| `filterProcessed(filter)` | 筛选 `state.processed`：`'all'` → 全部，`'tagged'` → `tags.length > 0`，`'untagged'` → `tags.length === 0`。结果存入 `state.filteredProcessed`，调用 `renderProcessedGrid()` |

### 3.4 渲染函数

| 函数 | DOM 操作 |
|---|---|
| `renderWorkspace()` | **关键函数**。根据 `state.unprocessed.length > 0` 决定显示 `#workspace-area` 还是 `#workspace-empty`。有未处理图片时：调用 `renderUnprocessedGrid()` + `renderTagPool()`；无未处理图片时隐藏工作区、显示完成提示。 |
| `renderUnprocessedGrid()` | 遍历 `state.unprocessed`，为每张图片创建 `.thumb-item` 元素（`<img>` + 文件名），插入 `#unprocessed-grid`。给当前 `state.currentImageId` 对应的元素添加高亮类（`ring-2 ring-indigo-500`）。 |
| `selectImage(id)` | 设置 `state.currentImageId = id`。更新 `#unprocessed-grid` 中所有 `.thumb-item` 的高亮状态（只高亮当前）。不发起 API 调用。 |
| `renderTagPool()` | 遍历 `state.tagGroups`，为每个分组创建 `.tag-group-panel`（分组名标题 + `.tag-chips` 容器）。每个 tag 渲染为 `.tag-chip` 按钮，绑定事件委托。 |
| `renderProcessedGrid()` | 遍历 `state.filteredProcessed`，渲染缩略图网格到 `#processed-grid`。每张图点击 → `openEditModal(imageId)` |
| `renderStudents()` | 渲染学生表格（复用旧版逻辑，适配 JSON 响应 `[0].id`） |
| `renderTagGroups()` | 渲染分组管理列表（每个分组的名称 + 标签 + 编辑/删除按钮） |

### 3.5 打标交互（核心）

| 函数 | 逻辑 |
|---|---|
| `async applyTag(tagId)` | **整个工作流的核心**。1) 获取当前 `state.currentImageId` 和对应 image 对象。2) 从 image.tags 提取已有 tag IDs，追加 `tagId` 组成新的 tag_ids 数组。3) 设置 `state.processingLock = true`（防抖）。4) `PUT /api/admin/images/{imageId}/tags {tag_ids: [...]}`。5) 成功：将该图片从 `state.unprocessed` 移除并追加到 `state.processed` 开头。重新渲染（`renderWorkspace()` + `renderProcessedGrid()`）。如果 `unprocessed` 仍有数据，`currentImageId` 自动设为第一张。`processingLock = false`。6) 失败：`showToast(error, 'error')`，`processingLock = false`。 |
| `onUnprocessedClick(imageId)` | 如果 `processingLock` 为 true 则忽略。调用 `selectImage(imageId)` |

### 3.6 Modal 相关

| 函数 | 逻辑 |
|---|---|
| `openEditModal(imageId)` | 从 `state.allImages` 找到图片。显示 `#edit-modal`。渲染：大图预览 + 当前标签列表（每个带 × 删除按钮）+ 添加标签选择器（展示所有可用标签）。设置 `state.editingImageId = imageId` |
| `closeEditModal()` | 隐藏 `#edit-modal`，重置 `state.editingImageId = null` |
| `async saveImageTags()` | 收集 Modal 内当前 tags 的 ID 集合 → `PUT /api/admin/images/{state.editingImageId}/tags` 全量替换 → 成功后 `loadAllData()`，关闭 Modal |
| `addTagToEdit(tagId)` | 在 Modal 内将 tag 添加到临时 tagIds 列表，更新 Modal 内的标签 UI |
| `removeTagFromEdit(tagId)` | 从临时 tagIds 列表中移除，更新 Modal UI |

### 3.7 学生管理

| 函数 | 逻辑 |
|---|---|
| `async addStudents()` | 读取 textarea 内容，`POST /api/admin/students {names: "张三,李四"}` → `loadAllData()` |
| `async resetKey(id)` / `async deleteStudent(id)` | 与旧版相同逻辑 |

### 3.8 标签分组管理

| 函数 | 逻辑 |
|---|---|
| `async addTagGroup()` | `POST /api/admin/tag-groups {name}` → `loadTagGroups()` → 重新渲染 |
| `async renameTagGroup(id)` | `PUT /api/admin/tag-groups/{id} {name}` → `loadTagGroups()` |
| `async deleteTagGroup(id)` | 确认对话框 → `DELETE /api/admin/tag-groups/{id}` → `loadTagGroups()` + `loadImages()` |
| `async moveTagToGroup(tagId, groupId)` | `PUT /api/admin/tags/{tagId} {group_id: groupId}` → `loadTagGroups()` |

### 3.9 设置

| 函数 | 说明 |
|---|---|
| `async updatePassword()` | 同旧版，`PUT /api/admin/album-password` |

---

## 四、设计决策与关键实现细节

### 4.1 事件委托策略
不采用 `querySelectorAll` + `forEach` 绑定事件的旧模式。改为在容器元素上使用事件委托，通过 `event.target.closest('[data-xxx]')` 定位目标：
- `#unprocessed-grid` 上的 click → `.thumb-item[data-image-id]`
- `#tag-pool` 上的 click → `.tag-chip[data-tag-id]`
- `#processed-grid` 上的 click → `.processed-item[data-image-id]`
这避免了重新渲染后必须重新绑定事件的问题。

### 4.2 防抖锁 `processingLock`
打标操作期间防止快速重复点击导致并发 API 调用混乱。在 `applyTag()` 开始时检查锁，操作完成后释放。

### 4.3 高亮自动切换
- 进入工作台时，若有未处理图片，默认选中第一张 (`currentImageId = unprocessed[0].id`)
- 打标成功后图片移出 `unprocessed`，当前索引自动变为下一张（即原第二张变为第一张）
- `renderUnprocessedGrid()` 始终用 `state.currentImageId` 判断高亮

### 4.4 标签池按分组展示
直接使用 `GET /api/admin/tag-groups` 返回的嵌套结构（`TagGroupResponse` 包含 `tags: list[TagResponse]`），无需二次查询。分组按 `id` 排序，保留"未分类"分组在最前。

### 4.5 Modal 内的标签编辑
- 当前标签：以 chips 形式展示，每个带有 × 删除按钮
- 添加标签：在 Modal 右侧/下方展示可用标签列表（从 `state.tagGroups` 构建），点击即可添加
- 保存：收集 Modal 内当前的 tag ID 集合 → `PUT /images/{id}/tags` 全量替换
- 取消：直接关闭 Modal，不保存

### 4.6 空状态隐藏逻辑
`renderWorkspace()` 中判断：
```js
if (state.unprocessed.length === 0) {
    workspaceArea.classList.add('hidden');
    workspaceEmpty.classList.remove('hidden');
} else {
    workspaceArea.classList.remove('hidden');
    workspaceEmpty.classList.add('hidden');
}
```
注意：**已处理图片区域**（`#processed-section`）始终可见，不受未处理池影响。

### 4.7 `img` 标签的 `onerror` 回退
图片加载失败时显示占位 SVG（灰色背景 + 图片裂开 icon），复用旧版的 `onerror` 回退模式。

---

## 五、文件变更清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `static/admin.html` | **重写** | 完全替换 `#dashboard` 内的 HTML 结构 |
| `static/js/admin.js` | **重写** | 新状态管理 + 新渲染函数 + 新事件委托模式 |
| `docs/task-tracker.md` | 更新 | Phase 11 标记为完成 |
| `tests/test_v2_admin_api.py` | 不变 | 后端 API 测试无需变更 |
