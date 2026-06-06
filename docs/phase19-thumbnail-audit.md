# Phase 19 三端缩略图实现方案对比报告

> 诊断日期: 2026-06-06 | 类型: 只读诊断，不含代码修改

---

## 1. 对比总表

| 页面 | API 端点 | 后端填充 `thumbnail_url` | 前端使用 `thumbnail_url` | 实际加载缩略图？ |
|------|----------|--------------------------|--------------------------|------------------|
| **学生端** | `GET /api/student/my-images` | ✅ 第 94 行调用 `get_thumbnail_signed_url` | ✅ 第 272 行 `img.thumbnail_url \|\| thumbnailUrl(img.url)` | ✅ **是** |
| **打标工作台** | `GET /api/admin/images` | ❌ 未调用 `get_thumbnail_signed_url` | ❌ 全部使用 `img.url` | ❌ **否 (原图)** |
| **图片管理** | `GET /api/admin/images` | ❌ 同上，共用端点 | ❌ 全部使用 `img.url` | ❌ **否 (原图)** |

---

## 2. 逐页详细分析

### 2.1 学生端 (student.html)

#### A. 数据来源

- **API 端点**: `GET /api/student/my-images`
- **后端实现** ([student.py:90-107](app/routes/student.py:90)):
  ```python
  for img in images:
      url = await storage.get_signed_url(img.file_key)
      thumbnail_url = await storage.get_thumbnail_signed_url(img.file_key)
      result.append(ImageResponse(
          ...
          url=url,
          thumbnail_url=thumbnail_url,  # ← 已填充
      ))
  ```
- **`thumbnail_url` 是否填充**: ✅ 是。后端为每张图片并行调用 `get_signed_url` 和 `get_thumbnail_signed_url`，二者均基于 Phase 18 修复后的正确签名方案（`params=` 关键字参数）。

#### B. 前端渲染

- **渲染函数**: `renderPhotoGrid()` ([student.js:247](static/js/student.js:247))
- **`<img>` src 来源** ([student.js:272](static/js/student.js:272)):
  ```javascript
  const gridSrc = img.thumbnail_url || thumbnailUrl(img.url);
  ```
  优先使用后端生成的 `thumbnail_url`，若为空则降级到客户端拼接 `thumbnailUrl()`。
- **客户端拼接代码** ([student.js:237](static/js/student.js:237)):
  ```javascript
  function thumbnailUrl(originalUrl) {
      return `${originalUrl}${sep}x-oss-process=image/resize,m_lfit,w_400,h_400`;
  }
  ```
  该降级逻辑在 Phase 18 修复后理论上**不再触发**（因为 `thumbnail_url` 已正确填充）。即使触发，客户端拼接也会因签名不包含处理参数导致 403，但由于降级链的短路特性，这已是"死代码"路径。

#### C. 实际效果

- 网格中加载的是 **缩略图**（OSS 实时缩放至 `m_lfit,w_400,h_400`）
- 用户点击卡片进入 Lightbox 时，加载 **原图**（`data-img-url` 属性绑定 `img.url`）— 行为正确
- 多选下载使用 **原图**（`startDownload()` 用 `img.url` 发起 fetch）— 行为正确

#### D. 结论

✅ **学生端已完整实现缩略图加载**。后端填充 `thumbnail_url` → 前端优先使用 → OSS 实时缩放返回小图。

---

### 2.2 管理后台 — 打标工作台 (admin.html 打标台 Tab)

#### A. 数据来源

- **API 端点**: `GET /api/admin/images`（与图片管理共用）
- **后端实现** ([admin.py:284-321](app/routes/admin.py:284)):
  ```python
  for img in images:
      url = await storage.get_signed_url(img.file_key)
      result.append(ImageResponse(
          ...
          url=url,
          # thumbnail_url 未赋值 → Pydantic 默认 None
      ))
  ```
- **`thumbnail_url` 是否填充**: ❌ **未填充**。后端只调用 `get_signed_url`，不调用 `get_thumbnail_signed_url`。`ImageResponse.thumbnail_url` 取默认值 `None`，在 JSON 序列化时该字段不会出现在响应中。

#### B. 前端渲染

`admin.js` 中有 **三个** 渲染位置，全部使用 `img.url`（原图）：

| 渲染函数 | 行号 | `src` 值 | 场景 |
|----------|------|----------|------|
| `renderUnprocessedGrid()` | [admin.js:469](static/js/admin.js:469) | `escapeHtml(img.url)` | 待打标缩略图条 |
| `renderProcessedGrid()` | [admin.js:721](static/js/admin.js:721) | `escapeHtml(img.url)` | 已打标图片网格 |
| `openEditModal()` | [admin.js:750](static/js/admin.js:750) | `image.url` | 编辑弹窗预览 |

管理员端**没有任何**客户端 OSS URL 拼接逻辑（无 `thumbnailUrl()` 函数、无正则替换、无参数追加）。

#### C. 实际效果

- 打标工作台加载的是 **原图**（完整分辨率）
- 管理员每次刷新或切换图片时，浏览器需下载完整大图再缩放显示为缩略图
- 对于高分辨率照片（如 4000×3000 像素的相机原片），每个缩略图条需加载数 MB 数据
- 若未处理池有 50+ 张照片，带宽消耗极大，加载速度慢

#### D. 结论

❌ **打标工作台未实现缩略图加载**。缺失点：
1. **后端**: `list_images_view` 未调用 `get_thumbnail_signed_url`
2. **前端**: 未使用 `thumbnail_url` 字段（即使后端提供了也会被忽略）

---

### 2.3 管理后台 — 图片管理 (admin.html 图片管理 Tab)

#### A. 数据来源

- **API 端点**: `GET /api/admin/images`（与打标工作台**共用同一端点**）
- **后端行为**: 同 2.2.A — `thumbnail_url` 未填充
- **`thumbnail_url` 是否填充**: ❌ **未填充**（同上）

#### B. 前端渲染

- **渲染函数**: `renderAllImages()` ([admin.js:1111](static/js/admin.js:1111))
- **`<img>` src 来源** ([admin.js:1125](static/js/admin.js:1125)):
  ```javascript
  <img src="${escapeHtml(img.url)}" ... />
  ```
  直接使用 `img.url`（原图）。

#### C. 实际效果

- 图片管理网格中加载的是 **原图**
- 与打标工作台面临相同的问题 — 大图加载慢、带宽消耗高

#### D. 结论

❌ **图片管理未实现缩略图加载**。缺失点与打标工作台完全一致（同一端点，同一根因）。

---

## 3. 差异总结

### 3.1 已实现缩略图的页面

| 页面 | 实现方式 |
|------|----------|
| 学生端 | 后端 `student.py` 调用 `get_thumbnail_signed_url` → `thumbnail_url` 字段 → 前端 `img.thumbnail_url \|\| thumbnailUrl(img.url)` 优先使用 |

学生端覆盖了完整的"后端签名 → 字段传输 → 前端消费"链路。

### 3.2 未实现缩略图的页面

| 页面 | 根因位置 | 缺失环节 |
|------|----------|----------|
| 打标工作台 | `app/routes/admin.py:306-318` | 后端未调用 `get_thumbnail_signed_url` |
| 图片管理 | `app/routes/admin.py:306-318` | 同上（共用 `list_images_view`） |

两个管理端页面依赖同一端点 `GET /api/admin/images`，该端点在构建 `ImageResponse` 时仅填充 `url` 字段，不填充 `thumbnail_url`。前端也从未尝试使用 `thumbnail_url`。

### 3.3 修复路径

若要为管理端启用缩略图，需修改 **两个位置**：

| 序号 | 文件 | 变更 |
|------|------|------|
| 1 | `app/routes/admin.py:305-318` | `list_images_view` 中为每张图片调用 `storage.get_thumbnail_signed_url(img.file_key)` 并填入 `ImageResponse(thumbnail_url=...)` |
| 2 | `static/js/admin.js` | 三处渲染函数（`renderUnprocessedGrid`、`renderProcessedGrid`、`renderAllImages`）将 `img.url` 替换为 `img.thumbnail_url \|\| img.url` |

注意：`openEditModal()` 的预览需要大图，应保持 `image.url` 不变。

### 3.4 性能影响估算

假设管理员上传了 50 张 4000×3000 的 JPEG 照片（每张约 5MB），当前行为：

| 场景 | 当前（原图） | 修复后（缩略图） |
|------|-------------|-----------------|
| 打标工作台首屏（50 张待打标） | ~250 MB | ~5-10 MB（OSS 缩放至 400px） |
| 图片管理网格（全部图片） | ~250 MB+ | ~5-10 MB+ |

缩略图方案可节省 **95%+** 的管理端带宽，显著提升加载速度。

---

## 附录：涉及文件清单

| 文件 | 审查重点 |
|------|----------|
| `app/routes/student.py:90-107` | 学生端 `thumbnail_url` 填充逻辑 ✅ |
| `app/routes/admin.py:284-321` | 管理端 `list_images_view` — `thumbnail_url` 缺失 ❌ |
| `app/schemas/admin.py:107-120` | `ImageResponse.thumbnail_url` 字段定义 |
| `static/js/student.js:237-241` | `thumbnailUrl()` 客户端拼接降级函数 |
| `static/js/student.js:272` | `renderPhotoGrid()` 优先使用 `thumbnail_url` |
| `static/js/admin.js:469` | `renderUnprocessedGrid()` 使用 `img.url` |
| `static/js/admin.js:721` | `renderProcessedGrid()` 使用 `img.url` |
| `static/js/admin.js:750` | `openEditModal()` 使用 `image.url`（预览，应保持原图）|
| `static/js/admin.js:1125` | `renderAllImages()` 使用 `img.url` |
