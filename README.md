# 毕业季专属相册 V4.0

> 为班级/年级毕业季打造的私有相册平台 —— 管理员沉浸式打标，学生按姓名隔离查看与下载。

## 项目简介

毕业季合影管理面临三大痛点:
1. **照片分散**：班级群、网盘、手机相册散落各处，难以统一管理
2. **隐私泄露**：大合影与个人照混在一起，难以按人分发
3. **下载困难**：浏览器默认在新窗口打开图片，无法批量下载

本项目的解决思路：将照片统一上传至阿里云 OSS，管理员通过**沉浸式打标工作台**为学生照片打上姓名标签，学生通过「相册密码 + 个人密钥」双重验证登录后，仅能看到自己名下的照片，并支持**多选队列下载**。

---

## 核心特性

### 沉浸式打标工作台
- 左侧待打标图片池 + 右侧标签分组面板，点击即打，自动推进下一张
- **V3.0 多标签模式**: 支持同时选中多个标签 + 一次性确认打标，完整支持合影语义
- 已处理图片支持标签编辑（Modal 内增删标签）
- 标签分组管理：支持创建/重命名/删除分组，标签可在分组间移动
- **V3.0 标签池瀑布流布局**: 标签分组面板双列瀑布流展示，空间利用更高效

### 多选模式与队列下载（学生端）
- 一键切换多选模式，支持全选/逐个选择/跨分组长按选择
- 浏览器原生队列下载，400ms 间隔防拦截，进度条实时反馈
- 可随时中止下载队列
- **V3.0 多选 UI 收敛**: 操作栏统一至筛选栏下方，交互更连贯

### 缩略图全链路（V3.0 重点修复）
- **Phase 17/19 根因修复**: 修正 OSS SDK `sign_url` 传参方式，`x-oss-process` 参数正确参与签名计算
- **管理端缩略图**: 打标工作台、图片管理均加载 400px 缩略图，带宽节省 95%+
- **编辑弹窗缩略图化**: 标签编辑预览使用缩略图，与原图加载形成分级策略

### 图片管理批量操作（V3.0 新增）
- 多选批量删除: 开启多选 → 全选/逐个勾选 → 一键批量删除
- 卡片叠加 indigo 选中态（ring + 勾选徽章），交互与删除模式完整隔离

### 隐私隔离
- 基于 `Student.name = Tag.name` 匹配，学生只能看到自己姓名标签下的照片
- 无额外外键耦合，架构简洁可靠

### 动静分离
- 阿里云 OSS 存储原图，SQLite 仅存 File Key
- 签名 URL 动态生成（15 分钟有效期），禁止公开访问
- 缩略图通过 OSS `x-oss-process=image/resize` 实时处理，签名内建

### 其他 V3.0 改进
- 批量添加学生支持中文全角逗号分隔（`张三，李四`）
- 标签删除显示受影响照片数确认对话框
- 移除遗留上传区关联标签功能（打标工作台已完全替代）

### V4.0 新增亮点
- **登录持久化**: localStorage + JWT exp 校验，学生刷新不重登
- **Lightbox 缩略图**: w_1200 缩略图承载，告别 3-10MB 原图加载
- **批量打标**: 多选照片一键批量打标 + 点击分组全选组内标签
- **仪表盘**: 管理端默认首页，存储概览 + 数据统计 + CSV 导出
- **Docker 一键部署**: `docker-compose up -d`，启动自动建表
- **性能调优**: 前端 TTL 缓存、SQLite WAL、Tailwind 本地化、DB 连接池
- **容错增强**: 上传重试（指数退避）、断网提示 banner、图片加载降级

---

## Docker 部署（V4.0 新增）

一行启动：

```bash
docker-compose up -d
```

首次部署步骤：

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env：填写 OSS 配置 + 修改 DATABASE_URL=sqlite:///data/album.db

# 2. 启动服务
docker-compose up -d

# 3. 验证
curl http://localhost:8000/
```

说明：
- 数据库文件自动创建于 `./data/album.db`，容器销毁后数据不丢失
- 无需手动 `pip install` 或运行迁移脚本
- 管理后台：http://localhost:8000/admin | 学生门户：http://localhost:8000/student

手动部署请参考下方「快速开始」。

---

## 快速开始

### 环境要求

- Python 3.10+
- 阿里云 OSS Bucket（需自行创建）

### 1. 克隆与安装

```bash
# 克隆项目
git clone <repo-url> && cd private-album

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，至少填写以下 4 项:
#   OSS_ENDPOINT   — 如 https://oss-cn-hangzhou.aliyuncs.com
#   OSS_ACCESS_KEY — 阿里云 AccessKey ID
#   OSS_SECRET     — 阿里云 AccessKey Secret
#   OSS_BUCKET     — OSS Bucket 名称
```

### 3. 数据库迁移

首次运行前，若从 V1 升级，需要执行迁移脚本:

```bash
python -m app.migrations.v2_migrate
```

迁移脚本具有幂等性，重复执行不会出错。

### 4. 启动服务

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后访问:
- **管理后台**: http://localhost:8000/admin
- **学生门户**: http://localhost:8000/student

首次登录管理后台时，相册密码会被自动初始化（使用你输入的密码）。

---

## OSS 配置指南 (重要)

为实现前端队列下载功能，必须在阿里云 OSS 控制台配置 CORS（跨域资源共享）规则。

### 配置步骤

1. 登录 [阿里云 OSS 控制台](https://oss.console.aliyun.com/)
2. 进入目标 Bucket → 数据安全 → 跨域设置
3. 点击「创建规则」，填写以下内容:

| 配置项 | 值 |
|---|---|
| 来源 | `*` （或你的域名） |
| 允许 Methods | `GET, HEAD` |
| 允许 Headers | `*` |
| 暴露 Headers | `Content-Disposition` |
| 缓存时间 (Max-Age) | `3600` |

> **为什么需要 CORS？** 学生端队列下载使用 `fetch` 跨域获取 OSS 图片 Blob，再通过 `<a download>` 触发保存。缺少 CORS 配置会导致浏览器拦截跨域请求，下载功能失效。

---

## 使用手册

### 管理员操作

#### 1. 添加学生（批量）
1. 登录管理后台 → 点击「学生管理」标签
2. 在输入框中填写学生姓名，逗号分隔: `张三,李四,王五`
3. 点击「添加」，系统自动生成 6 位个人密钥

#### 2. 上传照片
1. 点击「图片管理」标签
2. 选择图片文件（支持多选）
3. 可选填写关联标签（逗号分隔）
4. 点击「上传」

#### 3. 沉浸式打标
1. 点击「打标工作台」标签
2. **左侧**：浏览待打标图片，点击选中
3. **右侧**：点击对应学生的标签按钮，自动打标并跳到下一张
4. 可点击标签旁的 × 按钮删除标签（会显示受影响照片数确认对话框）

#### 4. 标签分组管理
1. 点击「标签管理」标签
2. 创建分组（如「寝室」、「专业」）
3. 可通过下拉菜单将标签移动到不同分组

### 学生操作

#### 登录
1. 打开学生门户 → 输入相册密码 → 点击「验证相册密码」
2. 输入姓名和个人密钥（管理员提供）→ 登录

#### 浏览与下载
1. 普通模式：点击照片可全屏预览（支持左右滑动）
2. **多选模式**：点击右上角「多选」按钮
   - 勾选要下载的照片
   - 点击「下载」按钮开始队列下载
   - 进度条实时反馈，可随时取消

---

## 技术栈

| 层次 | 技术 |
|---|---|
| 后端框架 | FastAPI (Python) |
| 数据库 | SQLite + SQLAlchemy 2.0 ORM |
| 对象存储 | 阿里云 OSS (oss2 SDK) |
| 认证 | JWT (python-jose) + bcrypt |
| 前端 | Vanilla JS + Tailwind CSS（本地化） |
| 测试 | pytest + httpx |

详细技术架构说明见 [docs/technical-overview.md](docs/technical-overview.md)。

---

## 项目结构

```
private-album/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 环境配置 (pydantic-settings)
│   ├── database.py          # SQLAlchemy 引擎与会话
│   ├── dependencies.py      # 依赖注入
│   ├── models/              # ORM 数据模型
│   │   ├── image.py         # 图片 (OSS File Key)
│   │   ├── tag.py           # 标签 (V2: 带分组外键)
│   │   ├── tag_group.py     # 标签分组 (V2 新增)
│   │   ├── student.py       # 学生
│   │   ├── album_config.py  # 相册密码
│   │   └── image_tag.py     # 多对多关联表
│   ├── routes/              # API 路由
│   │   ├── admin.py         # 管理端 API
│   │   ├── auth.py          # 认证 API
│   │   └── student.py       # 学生端 API
│   ├── services/            # 业务服务
│   │   ├── aliyun_oss_storage.py  # OSS 存储
│   │   ├── auth_service.py        # JWT + 密码
│   │   └── student_service.py     # 学生 CRUD
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── middleware/           # JWT 认证中间件
│   └── migrations/           # 数据库迁移脚本
├── static/
│   ├── admin.html           # 管理后台 SPA
│   ├── student.html         # 学生门户 SPA
│   └── js/
│       ├── admin.js         # 管理端逻辑 (~1300 行)
│       └── student.js       # 学生端逻辑 (~700 行)
├── tests/                   # pytest 测试 (108 用例)
├── docs/                    # 文档
├── requirements.txt
├── Dockerfile                # V4.0 Docker 镜像
├── docker-compose.yml        # V4.0 容器编排
├── .dockerignore
├── .env.example
└── README.md
```

---

## License

MIT License
