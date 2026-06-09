# 毕业季专属相册 — 设计文档 V1.0

> **V1.0 设计蓝图 — 已封存** | 完成日期: 2026-06-04 | 测试: 61/61
> 此文件为版本启动时的原始设计。实际实施偏差见 task-tracker.md 各 Phase 记录。

---

## Context

V1.0 实现了一个高隐私、高性能的图片分发 Web 应用。核心场景：摄影师上传打标照片 → 系统生成个人密钥 → 学生凭「相册密码 + 个人密钥」双重验证获取专属照片流。

核心架构决策：
- **动静分离**：图片直接存储于阿里云 OSS，应用服务器仅存 File Key
- **隐私隔离 (SSOT)**：`Student.name = Tag.name` 逻辑匹配，零外键耦合
- **零构建前端**：Vanilla JS + Tailwind CDN，无 npm/webpack

---

## 项目目录树

```
private album/
├── app/
│   ├── main.py                   # FastAPI 入口、路由挂载
│   ├── config.py                 # Pydantic Settings
│   ├── database.py               # SQLAlchemy 引擎与会话
│   ├── dependencies.py           # 依赖注入
│   ├── models/
│   │   ├── student.py            # Student (id, name, secret_key)
│   │   ├── image.py              # Image (id, file_key, file_name, …)
│   │   ├── tag.py                # Tag (id, name)
│   │   ├── image_tag.py          # 多对多关联表
│   │   └── album_config.py       # 相册密码（单行表）
│   ├── routes/
│   │   ├── admin.py              # 管理端 API
│   │   ├── auth.py               # 认证 API
│   │   └── student.py            # 学生端 API
│   ├── services/
│   │   ├── aliyun_oss_storage.py  # OSS 存储 (upload/sign/delete/exists)
│   │   ├── auth_service.py        # JWT + bcrypt 密码
│   │   └── student_service.py     # Student CRUD + 密钥生成
│   ├── schemas/                  # Pydantic 请求/响应模型
│   └── middleware/                # JWT 认证中间件
├── static/
│   ├── admin.html                # 管理后台 (Tab: 学生/标签/图片/设置)
│   ├── student.html              # 学生门户 (登录/照片流/Lightbox)
│   └── js/
│       ├── admin.js
│       └── student.js
├── tests/                        # pytest (61 用例)
└── requirements.txt
```

---

## 数据模型

```
album_config (单行)       student
├─ password_hash           ├─ name
└─ …                       └─ secret_key (6位)

    image ←── image_tags ──→ tag
    ├─ file_key (UNIQUE)     └─ name (UNIQUE)
    ├─ file_name
    ├─ content_type
    ├─ file_size
    └─ uploaded_at
```

---

## API 端点

### 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/auth` | 管理员登录（相册密码）→ JWT |
| POST | `/api/student/auth` | 学生登录（相册密码 + 姓名 + 密钥）→ JWT |

### 管理员
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/admin/students` | 学生列表 / 单个创建 |
| PUT/DELETE | `/api/admin/students/{id}` | 重命名 / 删除学生 |
| POST | `/api/admin/students/{id}/reset-key` | 重置个人密钥 |
| GET | `/api/admin/images` | 全量图片列表 |
| POST | `/api/admin/images` | 多图上传（可选初始标签） |
| DELETE | `/api/admin/images/{id}` | 删除图片 |
| GET/POST/DELETE | `/api/admin/tags` | 标签 CRUD |
| PUT | `/api/admin/album-password` | 修改相册密码 |

### 学生端
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/student/my-images` | 按姓名匹配 Tag 返回图片 |
| GET | `/api/student/my-tags` | 该学生的标签列表 |

---

## 技术栈

| 层次 | 技术 |
|------|------|
| 后端 | FastAPI + SQLAlchemy 2.0 + SQLite |
| 对象存储 | 阿里云 OSS (oss2 SDK) |
| 认证 | JWT (python-jose) + bcrypt |
| 前端 | Vanilla JS + Tailwind CSS CDN |
| 测试 | pytest + httpx (SQLite :memory:) |

---

## 已知局限

- **标签无分组** — 平面列表，无组织层级（V2.0 TagGroup 解决）
- **打标无工作台** — 需手动在上传区填写标签（V2.0 沉浸式打标台解决）
- **学生端无多选** — 单张预览下载（V2.0 队列下载解决）
- **缩略图前端拼接** — 签名不覆盖 `x-oss-process` 参数，实际不可用（V3.0 修复）
- **AI 打标预留** — `ManualTaggingService` 返回空列表，预留 AI 扩展接口
