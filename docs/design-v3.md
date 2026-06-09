# 毕业季专属相册 — 设计文档 V3.0

> **V3.0 设计蓝图 — 已封存** | 完成日期: 2026-06-06 | 测试: 108/108
> V3.0 为过渡版本，主要内容为致命缺陷修复和体验优化，为 V4.0 大版本做准备。

---

## Context

V2.0 构建了沉浸式打标工作台、标签分组体系、学生端多选下载三大核心功能，但存在两个致命缺陷和若干体验问题。V3.0 定位为 **V2.0 稳定版**：不引入新的大功能，专注缺陷修复和交互打磨。

---

## 版本目标

1. **修复合影语义破坏** — V2.0 打标工作台点击标签立即提交 + 自动推进，导致每张照片只能打一个标签，与 SSOT 隐私隔离（一张照片多人可见）根本矛盾
2. **修复缩略图全链路 403** — OSS SDK `sign_url` 参数传递错误 + 前端拼接方案签名失效，导致学生端和管理端缩略图均不可用
3. **体验优化** — 中文全角逗号批量输入、标签瀑布流布局、学生端 UI 收敛、批量删除

---

## 关键技术决策

### 1. 打标工作台多标签模式 (Phase 17)

**问题**：V2.0 标签点击 → 立即 `PUT /images/{id}/tags` + 自动推进，每张只能打一个标签。

**方案**：多标签 toggle + 确认按钮模式

```
用户操作流: 点击标签 → toggle 选中态(蓝底高亮) → 可多选 → 点击"确认标记" → 
           一次性 PUT 全部 tag_ids → 提交成功 → 自动推进下一张

State 新增字段: selectedTagIds: []  (工作台待确认标签列表)
关键函数: toggleTagSelection(tagId) / confirmTags() / renderConfirmButton()
```

**不变**：后端 `PUT /api/admin/images/{id}/tags` 接口语义不变（全量替换），前端一次性提交多个 tag_ids。

### 2. OSS 缩略图签名修复 (Phase 17 → 19)

**Problem Lifecycle**:

| 版本 | 方案 | 问题 |
|------|------|------|
| V1.0 | 无缩略图 | 网格加载原图 3-10MB |
| V2.0 | 前端 `url + '&x-oss-process=...'` 字符串拼接 | `x-oss-process` 不在签名中 → 403 |
| V3.0 P17 | 后端 `sign_url` 但第 4 个位置参数 | 参数识别为 `headers` 未追加到 URL → 403 |
| **V3.0 P19** | 后端 `params={"x-oss-process": ...}` 关键字参数 | 正确参与签名 + 追加到 URL → 200 |

**最终正确实现** (`app/services/aliyun_oss_storage.py`):
```python
url = await asyncio.to_thread(
    self._bucket.sign_url, "GET", file_key, expires_seconds,
    params={"x-oss-process": process_value},  # 关键字参数！第5个位置
)
```

### 3. 图片批量删除 (Phase 21 → 22)

**后端**：新增 `DELETE /api/admin/images/batch` 端点
- 请求体 `ImageBatchDeleteRequest(image_ids: list[int])`
- 事务包裹（DB all-or-nothing），OSS best-effort
- 路由顺序：`/images/batch` 必须在 `/images/{image_id}` 之前注册

**前端**：多选模式 + 事件委托框架
- `state.isMultiSelectMode` + `selectedImageIds: Set`
- 卡片叠加 indigo ring + 勾选徽章
- `#image-manage-grid` 事件委托（card 点击/删除按钮）
- `switchTab()` 切换 Tab 自动重置多选状态

---

## Phase 清单

| Phase | 内容 | 测试 |
|-------|------|------|
| 16 | 标签管理页初始加载 Bug 修复 | 98→98 |
| 17 | 打标工作台多标签模式 + 学生端缩略图初版 | 98→102 |
| 18 | 全角逗号批量/瀑布流/学生端 UI 收敛 | 102 |
| 19 | OSS 缩略图签名根因修复 (`params=` 关键字) | 102 |
| 20 | 管理端缩略图加载启用 | 102 |
| 21 | 编辑弹窗缩略图化/多选模式预留/移除遗留 UI | 102→102 |
| 22 | 图片管理多选批量删除 | 102→108 |

---

## V3.0 API 新增/变更

| 方法 | 路径 | Phase | 说明 |
|------|------|-------|------|
| PUT | `GET /api/student/my-images` | 17 | 响应新增 `thumbnail_url` 字段 |
| GET | `GET /api/admin/images` | 20 | 响应新增 `thumbnail_url` 字段 |
| PUT | `POST /api/admin/students` | 18 | `names` 字段改为中文全角逗号分隔 |
| DELETE | `DELETE /api/admin/images/batch` | 22 | 批量删除，Route 顺序在 `{image_id}` 前 |

---

## 前端架构变更

**admin.js state 新增字段** (V3.0 累积):

```javascript
const state = {
    // … V2.0 字段 …
    selectedTagIds: [],        // Phase 17: 多标签 toggle
    isMultiSelectMode: false,   // Phase 21: 图片管理多选模式
    selectedImageIds: new Set(), // Phase 22: 批量删除选中集
};
```

**关键模式变更**:
- 标签交互: `直接提交` → `toggle + 确认按钮`
- 删除交互: `renderAllImages() 内 bind` → `#image-manage-grid 事件委托`
- OSS URL: `前端拼接` → `后端签名 thumbnail_url`

---

## V2.0 遗留问题解决

| V2.0 遗留 | V3.0 解决 |
|-----------|-----------|
| 缩略图前端拼接 403 | P17+P19: 后端 `params=` 签名 |
| 合影无法多标签 | P17: toggle+confirm 模式 |
| 管理端无缩略图 | P20: 填充 thumbnail_url |
| 批量添加需半角逗号 | P18: 中文全角逗号支持 |
| 标签面板垂直堆叠 | P18: 双列瀑布流 |
| 学生端多选按钮分散 | P18: UI 收敛至统一操作栏 |
| 编辑弹窗预览原图 | P21: 缩略图化 |
| 无批量删除 | P22: 多选批量删除 |
| 上传区遗留关联标签 | P21: 移除 |
