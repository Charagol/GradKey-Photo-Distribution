> **V4.0 设计蓝图 — 已封存** | 完成日期: 2026-06-10 | 测试: 113
> 此文件为版本启动时的设计文档。实际实施偏差见 task-tracker.md 各 Phase 记录。
>
# 毕业季专属相册 — 设计文档 V4.0

> **V4.0 设计蓝图** | 创建日期: 2026-06-09 | 状态: 已封存
> V4.0 定位为工程化与体验大版本，在 V3.0 稳定基座上引入前端持久化、批量打标、管理端运维、容错增强、性能调优和 Docker 部署。

---

## Context

V3.0 封存时全量测试 108/108 通过，核心架构趋于稳定：SSOT 隐私隔离、State-Driven Rendering、事件委托 + processingLock、后端 OSS 签名缩略图 URL。V4.0 不再引入新的架构范式，而是补齐工程化短板和体验打磨——让这个单机应用更接近「开箱即用」的产品状态。

---

## 版本目标

1. **登录持久化** — sessionStorage → localStorage，学生刷新页面不被迫重登
2. **Lightbox 体验收敛** — w_1200 缩略图承载，无「查看原图」按钮，引导用户使用多选下载
3. **~~CDN 加速~~（已搁置）** — OSS 私有 Bucket → CDN 回源鉴权，后端 URL 签名适配 CDN 域名
4. **批量打标** — 两方向全覆盖：多选未处理照片一键打标 + 点击分组一次打上全组标签
5. **管理端运维面板** — 存储概览 + 数据统计 + CSV 导出学生名单
6. **容错增强** — 上传重试、网络断开提示、OSS 不可达降级显示
7. **性能调优** — 浏览器缓存优化、SQLite WAL 模式、Tailwind 本地化、DB 连接池参数
8. **Docker 工程化** — Dockerfile + docker-compose.yml + 部署说明，零业务代码侵入

---

## Phase 清单

| Phase | 内容 | 规模 | 说明 |
|-------|------|:---:|------|
| P1 | 登录 localStorage 持久化 | 小 | sessionStorage → localStorage + JWT exp 校验。零风险改动，后端不改 |
| P2 | Lightbox w_1200 渐进式 | 小 | 无「查看原图」按钮。底部引导文案：「如需原图请使用多选下载」 |
| P3 | ~~CDN 配置适配~~ **已搁置** | — | 收益/成本比过低，详见决策 3。建议跳过 |
| P4 | 批量打标（选图 + 选分组） | 中 | 方向A：多选未处理照片 → 一次性打上相同标签；方向B：点击分组 → 一次打上该组全部标签。两个方向都执行。纯前端改动 |
| P5 | 管理端运维（存储概览 + CSV 导出） | 中 | Dashboard 显示 OSS 占用/照片数/学生数/标签数；`GET /api/admin/students/export` 返回 CSV（姓名,密钥） |
| P6 | 容错增强 | 中 | 上传重试、网络断开提示、OSS 不可达降级显示 |
| P7 | 性能调优（含 4 项子任务） | 中 | 见下方子任务详解 |
| P7-1 | 浏览器缓存优化 | 小 | 前端图片列表 TTL 缓存（30min 新鲜窗口），减少签名 URL 生成请求；`oss_signed_url_expires` 900→3600 |
| P7-2 | SQLite WAL 模式 | 小 | `PRAGMA journal_mode=WAL`，读不阻塞写，提升并发能力 |
| P7-3 | Tailwind 本地化 | 小 | Tailwind CSS 从 CDN 引用改为本地文件，消除外部网络依赖 |
| P7-4 | DB 连接池参数 | 小 | SQLAlchemy `pool_size=3, max_overflow=5, pool_pre_ping=True` |
| P8 | Docker 工程化 | 中 | Dockerfile + docker-compose.yml + 部署说明。不改变任何业务代码 |

---

## 关键技术决策及理由

### 1. 登录缓存：localStorage 替代 sessionStorage

**决策**：直接用 `localStorage` + JWT exp 校验，不加「记住我」开关。

**理由**：
- 毕业相册使用场景为个人设备或班级共用设备，无网吧/图书馆等公用电脑风险
- sessionStorage 在浏览器标签页关闭后清除，学生刷新页面即被迫重登，体验割裂
- JWT 本身携带 `exp` 过期时间，前端通过解析 `payload.exp` 与当前时间对比，过期即清空 localStorage 并重定向登录页
- 不加「记住我」开关：避免 UI 复杂度，且该场景下默认就应该记住

**影响范围**：前端改 4 个存储调用前缀（`sessionStorage` → `localStorage`），后端不改一行代码。

**风险**：极低。JWT exp 机制已存在，前端校验逻辑约 5 行。

---

### 2. Lightbox：w_1200 缩略图，无「查看原图」按钮

**决策**：Lightbox 组件使用 `w_1200` 缩略图（通过 `get_thumbnail_signed_url(key, width=1200)` 生成），不提供「查看原图」按钮。

**理由**：
- `w_1200` 在手机屏幕上已不可分辨与原图的差异（2K 手机屏物理宽度 1440px 时，1200px 图片经 CSS 适配后像素密度完全覆盖）
- 原图（3-10MB）在 Lightbox 中加载无实际收益，反造成带宽浪费和加载延迟
- 学生需要原图的唯一场景是保存到本地 → 这正是「多选队列下载」功能的设计目的
- 产品引导路径：Lightbox 底部固定文案——「如需要高清原图，请使用多选下载功能」——将用户自然导向下载流程

**影响范围**：前端 Lightbox 组件新增一个签名请求（w_1200 缩略图），底部新增引导行；后端无改动（`get_thumbnail_signed_url` 接口已支持任意宽高）。

**风险**：极低。现有 `get_thumbnail_signed_url` 接口已支持动态 width 参数，无需新增端点。

---

### 3. CDN：OSS 私有 Bucket → CDN 回源鉴权（*已搁置*）

**决策**：CDN 域名指向 OSS 私有 Bucket，使用 CDN 回源鉴权代替 OSS 签名 URL 直连。

**理由**：
- 当前架构中，每次学生/管理员打开页面，后端需为每张图片生成带 OSS 签名的临时 URL（900s 过期），并发请求量大时成为瓶颈
- CDN 回源鉴权模式下：CDN 节点缓存图片（含缩略图），命中时直接返回，无需回源；首次回源时 CDN 携带鉴权头向私有 Bucket 拉取
- 签名策略简化：后端 `get_signed_url` / `get_thumbnail_signed_url` 仍然返回签名 URL，但域名从 OSS 直连域名切换为 CDN 域名
- 适配 OSS Bucket 私有策略 + CDN 私有 Bucket 回源鉴权（TypeA），不改变 Bucket ACL 设置

**实现要点**：
- 新增配置项 `CDN_DOMAIN`（如 `cdn.example.com`），替代原有 `OSS_ENDPOINT` 用于 URL 生成
- `AliyunOssStorageService` 签名逻辑不变（仍由 OSS SDK 生成），仅将返回 URL 中的 host 替换为 CDN 域名
- CDN 侧配置：添加加速域名 → 源站选择 OSS 私有 Bucket → 开启回源鉴权 → 配置缓存规则（图片 30 天、缩略图 30 天）

**影响范围**：后端 `AliyunOssStorageService` URL 组装逻辑；新增 `CDN_DOMAIN` 配置项；CDN 控制台配置（不在代码仓库内）。

**风险**：中等。CDN 配置失误可能导致图片全量不可访问。需在 CDN 配置确认后再切换后端域名。

> **2026-06-09 搁置**：经成本收益分析，P3 不值得实施。
> - **成本**：CDN 与 OSS 直连年费均在 3-5 元量级，绝对差额可忽略
> - **提速无效**：缩略图 50KB，50ms vs 200ms 延迟差无法感知；下载原图 5MB×30 张=150MB，受带宽瓶颈主导，CDN 无能为力
> - **风险不对等**：为了一年省一块钱，不值得踩 CDN 配置失误导致全站 403 的风险，也不值得为此新增代码中域名替换逻辑和签名有效期调整
> - **结论**：跳过 P3，保留此决策记录供未来参考

---

### 4. 管理端不需要下载功能

**决策**：管理员的多选模式只承载批量删除，不添加下载功能。

**理由**：
- 管理员是生产者（上传照片），不是消费者。管理端的职责是上传、打标、管理——而非浏览下载
- 管理员本地持有原片，下载功能为冗余操作
- OSS 控制台已提供完整的文件管理能力（预览、下载、删除），无需在应用内重复
- 保持管理端多选模式的语义单一性：选中 = 要删除，避免混淆

---

### 5. 人脸识别预准备：推迟至 V5.0

**决策**：V4.0 不建 `FaceEmbedding` 表，不修改 `ITaggingService` 接口。

**理由**：
- 当前没有代码向 `FaceEmbedding` 表写数据，提前建表无意义——空表只增加迁移文件复杂度
- `ITaggingService` 接口定义已完成，`ManualTaggingService` 返回空列表的契约明确，V4.0 无需触碰此接口
- V5.0 一次性完成模型建立 + 方案选型 + `extract_tags` 实现 + 打标工作台 AI 集成，效率更高

---

### 6. 浏览器缓存：前端图片列表 TTL 缓存 + 签名 URL 有效期延长

**决策**：管理端前端维护 `_imagesLoadedAt` 时间戳，在 30 分钟内复用已加载的图片列表数据，不发起新的 API 请求；同时将 OSS 签名 URL 有效期从 900s 延长至 3600s。

**理由**：
- 管理端工作流（上传 → 打标 → 管理）中，用户在多个 Tab 间频繁切换，每次切回图片管理 Tab 都会重新调用 `GET /api/admin/images`，后端为每张照片生成 OSS 签名 URL
- 30 分钟内图片数据几乎不会变化（管理员本人是唯一写入者），重复请求完全是浪费
- 签名 URL 有效期 900s（15min）短于缓存窗口 30min，导致缓存命中时 URL 可能已过期。延长至 3600s（1h）覆盖 2 个缓存窗口
- 实现极简：前端一个时间戳 + 一个 if 判断，后端一个配置值修改

**实现要点**：
- `admin.js` 新增全局变量 `window._imagesLoadedAt = null`，`loadImages()` 开头检查距今是否 < 30min
- 超时后正常请求并更新时间戳；上传/删除操作后重置时间戳为 null 强制刷新
- `app/config.py` 中 `oss_signed_url_expires` 从 900 改为 3600

**影响范围**：前端 `admin.js` 图片加载逻辑；后端 `config.py` 一个配置值。
**风险**：极低。缓存失效路径（上传/删除后重置）保证数据一致性。签名有效期延长不引入安全风险——URL 通过 HTTPS 传输，且该应用运行在受控环境。

---

## 预期 API 变更

| 方法 | 路径 | Phase | 说明 |
|------|------|-------|------|
| — | `get_signed_url` / `get_thumbnail_signed_url` | ~~3~~ 已搁置 | 原计划：返回值域名从 OSS 直连切换为 CDN 域名，签名逻辑不变 |
| GET | `GET /api/admin/dashboard/stats` | 5 | 新增：返回 OSS 存储占用、照片数、学生数、分组数、标签数 |
| GET | `GET /api/admin/students/export` | 5 | 新增：返回 CSV 文件（姓名,密钥），`Content-Type: text/csv` |
| — | — | 4 | 纯前端改动，无 API 变更 |
| — | — | 6 | 无新增端点，现有 API 增加前端重试/降级逻辑 |
| — | — | 7-1 | `GET /api/admin/images` 前端缓存层，无后端变更；`oss_signed_url_expires` 900→3600 |
| — | — | 7-2/7-3/7-4 | 纯基础设施，无 API 变更 |
| — | — | 8 | 纯工程化，无 API 变更 |

---

## 前端架构变更

**State 对象扩展**（V4.0 累积）：

```javascript
const state = {
    // … V3.0 字段（selectedTagIds, isMultiSelectMode, selectedImageIds）…
    // V4.0 新增：
    // P1: auth 从 sessionStorage 迁移到 localStorage，无 state 变更
    // P2: Lightbox 组件内部 currentImageUrl / isLoading
    // P4: batchTagTargetImageIds: Set, batchTagSourceGroupId: int|null
    // P5: dashboardData: {storage_bytes, photo_count, student_count, tag_count}
    // P6: networkStatus: 'online'|'offline', uploadRetryQueue: []
};
```

**关键模式变更**：

| 模块 | V3.0 | V4.0 |
|------|------|------|
| 登录态存储 | `sessionStorage` | `localStorage` + JWT exp 校验 |
| Lightbox | 不独立（内联于 photo grid click） | 独立组件，w_1200 缩略图 + 引导文案 |
| 打标工作台 | 逐张 toggle + 确认 | 新增批量模式：多选照片 → 一键打标；点击分组 → 全组标签 |
| 管理端首页 | 上传 + 打标 + 图片管理三 Tab | 新增 Dashboard Tab（存储概览） |
| 网络容错 | 无 | 上传重试（3 次指数退避）、断网提示 banner、OSS 不可达占位图 |
| Tailwind CSS | CDN 引用 | 本地化（构建产物置于 `static/`） |
| 浏览器缓存 | 无 | 图片列表 TTL 缓存（30min），上传/删除后强制刷新 |

---

## V5.0 预览

V5.0 将引入人脸识别自动打标，是一次 AI 能力集成版本。

| Phase | 内容 |
|-------|------|
| P1 | FaceEmbedding 模型建立（新增模型 + 迁移） |
| P2 | 方案选型：DeepFace + ArcFace 优先（一行代码切换模型），备选 InsightFace / face_recognition |
| P3 | `ITaggingService.extract_tags()` 实现，替代 `ManualTaggingService` 空返回 |
| P4 | 打标工作台集成 AI 建议标签区 |
| P5 | V5.0 测试、文档、收尾 |

**人脸识别方案决策（预研结论）**：

- **首选**：DeepFace + ArcFace 后端——一行代码切换模型，适合练手和快速验证
- **备选**：InsightFace——工业级精度，但模型需手动下载（~300MB）
- **不走**：云端 API（阿里云/AWS）——照片外传违背项目隐私定位
- **推理方式**：同步检测（50 张 × 100ms ≈ 5 秒），不需要异步任务队列
- **不需要 GPU**：CPU 推理完全够这个量级

### 产品方向

- 本项目定位：练手项目，目标是跑通人脸识别技术栈，非商用
- 到 V5.0 人脸识别完成后暂停开发
- 不做：微信小程序、服务器上线的代码适配
- 核心价值：「你的照片，只给对的人看」——打标即分发，让每张照片自动找到该看见它的人

---

*创建日期: 2026-06-09 | 基于 V4-planning-notes.md 起草*
