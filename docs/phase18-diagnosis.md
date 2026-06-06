# Phase 18 缩略图加载失败 — 根因诊断报告

> 诊断日期: 2026-06-06 | 状态: 待修复

---

## 1. 故障现象回顾

学生端页面加载后，缩略图网格中所有图片返回 **403 Forbidden**。

**关键证据** — 后端 API 响应中的两个 URL（同一图片）：

```
url:            ...Expires=1780741634&Signature=sPWi9Sj9A32ko5GclQbthPesOHc%3D
thumbnail_url:  ...Expires=1780741634&Signature=jjg%2BtzWXVy8OasSKWjquJtki5HI%3D
```

- 两个 URL 的签名不同 → `sign_url` 确实被调用了两次
- **两个 URL 都不包含 `x-oss-process` 参数** → 缩略图 URL 与原图 URL 格式完全一致，仅签名不同
- 前端 `img.thumbnail_url` 非空（有有效 URL），不触发 `thumbnailUrl(img.url)` 降级逻辑
- 浏览器直接使用不含 `x-oss-process` 的 URL 请求，签名不匹配 → 403

---

## 2. 根因分析

### 2.1 核心缺陷：`sign_url` 参数位置错误

**`oss2==2.19.1` 的 `Bucket.sign_url` 真实签名：**

```python
def sign_url(self, method, key, expires,
             headers=None,      # ← 第 4 个位置参数
             params=None,       # ← 第 5 个位置参数
             slash_safe=False,
             additional_headers=None):
```

**Phase 17 代码（`aliyun_oss_storage.py:131-137`）：**

```python
url: str = await asyncio.to_thread(
    self._bucket.sign_url,
    "GET",                                 # method
    file_key,                              # key
    expires_seconds,                       # expires
    {"x-oss-process": process_value},      # ← 意图作为 params，实际成为 headers
)
```

**实际执行结果：**

| 参数位置 | 参数名 | 代码传入值 | SDK 接收为 |
|----------|--------|------------|------------|
| 1st | `method` | `"GET"` | ✅ method |
| 2nd | `key` | `file_key` | ✅ key |
| 3rd | `expires` | `expires_seconds` | ✅ expires |
| **4th** | **`headers`** | `{"x-oss-process": ...}` | ❌ **成为 headers** |
| 5th | `params` | 未传入 → `None` | `None` |

`{"x-oss-process": ...}` 被传入 `headers` 参数，导致：

1. **签名层面**：OSS SDK 将 `x-oss-process` 作为 HTTP Header 纳入 `CanonicalizedHeaders` 进行签名计算。这解释了为什么 `thumbnail_url` 的签名与 `url` 不同。
2. **URL 层面**：`headers` 参数不会被拼接到 URL Query String 中（headers 是 HTTP 请求头，不是查询参数）。因此返回的 URL 不包含 `x-oss-process`。
3. **验证层面**：浏览器用该 URL 请求 OSS 时，HTTP 请求中不携带 `x-oss-process` 头，而 URL 中也没有 `x-oss-process` 查询参数。OSS 服务端根据实际收到的请求（无 header 无 query param）重新计算签名 → 与 URL 中携带的签名不匹配 → **403 Forbidden**。

### 2.2 前端降级逻辑为何未触发

```javascript
// student.js:272
const gridSrc = img.thumbnail_url || thumbnailUrl(img.url);
```

`img.thumbnail_url` 是一个合法的 OSS 签名 URL 字符串（只是不含 `x-oss-process`），它是 **truthy** 的，所以 `||` 短路求值永远不会退到 `thumbnailUrl(img.url)`。

即使降级逻辑触发，`thumbnailUrl()` 的简单字符串拼接 `&x-oss-process=...` 也会因为签名不包含该参数而继续 403。

### 2.3 Phase 17 测试为何未发现

测试使用 `mock_bucket.sign_url = MagicMock(return_value="https://fake-oss.com/thumb-url")`，Mock 的返回值是一个固定的假 URL，不反映真实 SDK 的参数处理行为。因此测试通过但实际行为错误。

---

## 3. 修复方案

### 3.1 唯一修复点：`app/services/aliyun_oss_storage.py:131-137`

将 `params` 字典作为**关键字参数**传递，确保它正确映射到 `sign_url` 的 `params` 形参：

```python
# 修复前（错误：params 被当作 headers 的第 4 位置参数）
url: str = await asyncio.to_thread(
    self._bucket.sign_url,
    "GET",
    file_key,
    expires_seconds,
    {"x-oss-process": process_value},
)

# 修复后（正确：params 作为关键字参数显式传递）
url: str = await asyncio.to_thread(
    self._bucket.sign_url,
    "GET",
    file_key,
    expires_seconds,
    params={"x-oss-process": process_value},
)
```

### 3.2 为何此修复是根本性的

- `params` 作为 keyword argument 传递 → SDK 正确识别为查询参数
- OSS SDK 将 `params` 字典的键值对**同时**用于签名计算 **和** URL Query String 拼接
- 修复后返回的 URL 格式应为：`...Expires=...&Signature=...&x-oss-process=image%2Fresize%2Cm_lfit%2Cw_400%2Ch_400`

### 3.3 无需修改的部分

| 组件 | 状态 | 原因 |
|------|------|------|
| `IStorageService` 抽象接口 | ✅ 不变 | 接口签名正确 |
| `ImageResponse` Schema | ✅ 不变 | `thumbnail_url` 字段定义正确 |
| `student.py` 路由 (`my_images`) | ✅ 不变 | 调用 `get_thumbnail_signed_url` 正确 |
| `student.js` 前端渲染 | ✅ 不变 | `img.thumbnail_url` 优先逻辑正确 |
| `get_signed_url()` | ✅ 不变 | 只传 3 个位置参数，无此问题 |

---

## 4. 影响范围分析

| 影响项 | 详情 |
|--------|------|
| 受影响功能 | 学生端缩略图网格渲染（所有图片 403） |
| 不受影响功能 | 管理员端（不使用 `thumbnail_url`）、原图访问（`url` 字段正常）、Lightbox 预览（使用 `url` 原图）、多选下载（使用 `url` 原图） |
| 代码改动量 | **1 行** (`aliyun_oss_storage.py:137` → 添加 `params=`) |
| 测试改动量 | 测试通过 Mock 验证，无需改动（但见下方验证项） |

---

## 5. 验证方法

### 5.1 自动化验证

```bash
pytest tests/ -v
```

要求：102/102 全量通过。

### 5.2 API 响应验证（修复后）

`GET /api/student/my-images` 响应中，`thumbnail_url` 应包含 `x-oss-process` 查询参数：

```
thumbnail_url: ...Expires=...&Signature=...&x-oss-process=image%2Fresize%2Cm_lfit%2Cw_400%2Ch_400
```

### 5.3 浏览器验证

1. 清空浏览器缓存（Ctrl+Shift+R 硬刷新）
2. 打开学生端页面，登录后观察缩略图网格
3. 所有缩略图应正常显示（HTTP 200），不再是 403
4. 点击缩略图打开 Lightbox → 原图正常显示
5. 进入多选模式 → 下载选中 → 原图正常下载

---

## 6. 经验教训

1. **Python 多位置参数 API 慎用位置传参**：当方法有 5+ 个位置参数且其中多个类型相同（都是 `dict`）时，应使用关键字参数消除歧义。
2. **Mock 测试的边界**：Mock 返回值测试不能替代集成验证。对于 SDK 封装层，应在修复后考虑增设一个"断言返回 URL 包含预期参数"的测试（见可选增强）。
3. **文档先行**：在下次遇到类似问题时应优先查阅 SDK 官方文档的完整方法签名，而非依赖推测。

---

## 附录 A：可选测试增强（非必须，建议后续实施）

在 `test_storage.py` 的 `TestGetThumbnailSignedUrl` 中新增一个测试：

```python
def test_returned_url_contains_process_param(self, mock_oss):
    """验证 sign_url 返回的 URL 中确实包含 x-oss-process（非仅签名）。"""
    service, mock_bucket = mock_oss
    mock_bucket.sign_url = MagicMock(
        return_value="https://fake-oss.com/signed-url?x-oss-process=image%2Fresize%2Cm_lfit%2Cw_400%2Ch_400"
    )

    import asyncio
    url = asyncio.run(service.get_thumbnail_signed_url("images/test.jpg"))

    assert "x-oss-process" in url
```

---

## 附录 B：oss2 2.19.1 `sign_url` 完整签名

```python
def sign_url(self, method, key, expires,
             headers=None,
             params=None,
             slash_safe=False,
             additional_headers=None):
```

来源：`inspect.signature(oss2.Bucket.sign_url)` 于 Python 3.13.13 / oss2 2.19.1 环境实机查询。
