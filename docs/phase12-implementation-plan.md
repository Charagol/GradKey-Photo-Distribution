# Phase 12: 学生端 UI 重构（多选与队列下载）— 轻量实施方案

## 一、JS 状态管理

扩展现有 `state` 对象，新增以下字段：

```js
const state = {
    // ── 现有字段（不变） ──
    token: null,
    studentName: null,
    allImages: [],
    allTags: [],
    activeTag: '__all__',
    lightboxIndex: -1,

    // ── Phase 12 新增 ──
    isMultiSelectMode: false,          // 多选模式开关
    selectedIds: new Set(),            // 选中图片 ID 集合（Set 保证 O(1) 查重）
    downloadProgress: null,            // { current: number, total: number } | null
    downloadAborted: false,            // 用户是否点击了中止下载
};
```

**关键规则**：
- 切换 `isMultiSelectMode` 时，清空 `selectedIds`（避免残留状态）
- 退出多选模式时，清空 `selectedIds` 和 `downloadProgress`
- `selectedIds` 不受标签过滤影响 — 选中的 ID 即使切换 filter 也保持选中

## 二、OSS 缩略图处理逻辑

不修改后端，前端拼接 OSS `x-oss-process` 参数。

```js
/**
 * 生成缩略图 URL
 * OSS 签名 URL 已含 ? 参数，用 & 拼接处理参数
 * 格式: ...?Expires=...&Signature=...&x-oss-process=image/resize,m_lfit,w_400,h_400
 */
function thumbnailUrl(originalUrl) {
    if (!originalUrl) return '';
    const sep = originalUrl.includes('?') ? '&' : '?';
    return `${originalUrl}${sep}x-oss-process=image/resize,m_lfit,w_400,h_400`;
}
```

**使用场景**：
- 列表网格 `<img src="${thumbnailUrl(img.url)}">` → 大幅减少首屏流量（400px 缩略图）
- Lightbox 大图 `<img src="${img.url}">` → 使用原始高清 URL
- 下载时 `fetch(img.url)` → 使用原始 URL 获取原图

## 三、下载队列算法（伪代码）

```
async function startDownload() {
    1. 获取 selectedIds 对应的 image 对象列表 images[]
    2. 创建 state.downloadProgress = { current: 0, total: images.length }
    3. 显示下载进度条 UI ("正在下载 0/N...")
    4. state.downloadAborted = false

    5. for (const img of images) {
        6.  if (state.downloadAborted) break;

        7.  更新进度 UI: state.downloadProgress.current++
            显示 "正在下载 current/total..."

        8.  try {
                // fetch 原图 blob
                9.  const resp = await fetch(img.url);
               10.  const blob = await resp.blob();
                
                // 创建临时虚拟 <a> 标签触发浏览器下载
               11.  const blobUrl = URL.createObjectURL(blob);
               12.  const a = document.createElement('a');
               13.  a.href = blobUrl;
               14.  a.download = img.file_name || `photo_${img.id}.jpg`;
               15.  document.body.appendChild(a);
               16.  a.click();
               17.  document.body.removeChild(a);
                
                // 延迟后释放 Blob URL（不能立即释放，浏览器异步下载需要时间）
               18.  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
            } catch (err) {
               19. showToast(`${img.file_name} 下载失败: ${err.message}`, 'error');
            }

            // 300-500ms 间隔，防止浏览器拦截批量下载弹窗
           20. if (images.indexOf(img) < images.length - 1) {
               21. await sleep(400);  // 400ms 间隔
               }
        }

        22. 隐藏进度条
        23. showToast(`下载完成: ${successCount}/${images.length}`, 'success')
        24. 自动退出多选模式
    }
```

**核心防拦截策略**：
- 每张图片下载间 `sleep(400)` — 浏览器不会将间隔 400ms 的下载视为批量弹窗
- 使用 `fetch` → `blob` → `URL.createObjectURL` → `<a download>` 链路，而非直接打开 URL（避免某些浏览器直接预览而非下载）
- 提供"中止下载"按钮，设置 `state.downloadAborted = true`

## 四、HTML 变更清单

新增元素（在现有 `#navbar` 和 `#photo-grid-section` 之间）：

```html
<!-- Navbar 中新增多选按钮 -->
<button id="multi-select-toggle-btn">开启多选</button>

<!-- 底部下载操作栏（多选模式下显示） -->
<div id="selection-bar" class="hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t ...">
    <button id="select-all-btn">全选</button>
    <button id="deselect-all-btn">取消全选</button>
    <span id="selection-count">已选 0 张</span>
    <button id="download-selected-btn">下载选中 (0)</button>
    <button id="cancel-select-btn">取消</button>
</div>

<!-- 下载进度条（下载期间显示） -->
<div id="download-progress-bar" class="hidden fixed bottom-16 inset-x-0 z-50 ...">
    <div>正在下载 <span id="download-current">0</span>/<span id="download-total">0</span>...</div>
    <button id="abort-download-btn">中止</button>
</div>
```

图片卡片上新增选中态遮罩：
```html
<!-- 多选模式下可见 -->
<div class="multi-select-overlay">
    <div class="checkmark">✓</div>
</div>
```

## 五、交互流程变更

| 场景 | 多选模式 OFF（默认） | 多选模式 ON |
|---|---|---|
| 点击图片 | 打开 Lightbox 预览 | 切换选中/取消选中 |
| Lightbox 导航 | ← → 键盘 + 触摸滑动 | 禁用（不打开 Lightbox） |
| 底部操作栏 | 隐藏 | 显示（全选/下载/取消） |
| 标签筛选 | 正常 | 正常（已选中的不受筛选影响） |
| 下载按钮 | 不显示 | 显示（含选中数量） |

## 六、文件变更

| 文件 | 操作 | 行数估计 |
|---|---|---|
| `static/student.html` | 修改 | +40 行（navbar 按钮 + 操作栏 + 进度条 + 遮罩） |
| `static/js/student.js` | 重写 | ~520 行（新增 ~150 行，核心函数：`toggleMultiSelect`, `toggleSelectImage`, `selectAll`, `startDownload`, `thumbnailUrl`） |

## 关键决策确认

1. **缩略图在前端拼接**，不修改后端 API（后续可优化为后端返回 `thumbnail_url` 字段）
2. **下载时使用原始 `url`**（高清原图），缩略图仅用于列表展示
3. **多选模式下点击图片** = 切换选中，不打开 Lightbox（保持交互直觉）
4. **下载完成后自动退出多选模式**，清空选中状态
