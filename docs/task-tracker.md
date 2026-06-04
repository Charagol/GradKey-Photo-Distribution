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

- [ ] 创建 `app/models/tag_group.py` (TagGroup 模型)
- [ ] Tag 模型新增 `group_id` 外键
- [ ] 更新 `app/models/__init__.py` 注册 TagGroup
- [ ] 编写迁移脚本 `app/migrations/v2_migrate.py`
  - [ ] 创建 tag_group 表
  - [ ] 插入默认"未分类"分组
  - [ ] ALTER tag 表添加 group_id 列
  - [ ] 现有 Tag 默认归入"未分类"
- [ ] 编写 `tests/test_tag_group.py` (模型 + 迁移验证)

### Phase 10: 管理端 API 升级

- [ ] `app/services/tag_group_service.py` (TagGroup CRUD)
- [ ] `aliyun_oss_storage.py` 新增 `get_thumbnail_url()` 方法
- [ ] `app/schemas/admin.py` 新增:
  - [ ] `TagGroupCreate` / `TagGroupUpdate` / `TagGroupResponse`
  - [ ] `BatchStudentCreate`
  - [ ] `ImageTagUpdate`
- [ ] 管理员路由新增:
  - [ ] `POST /api/admin/students/batch` (批量添加 + 自动建 Tag)
  - [ ] **修改** `POST /api/admin/students` (单条创建时自动建 Tag)
  - [ ] `GET/POST /api/admin/tag-groups`
  - [ ] `PUT/DELETE /api/admin/tag-groups/{id}`
  - [ ] `PUT /api/admin/tags/{id}` (修改标签所属分组)
  - [ ] `PUT /api/admin/images/{id}/tags` (编辑图片标签)
  - [ ] **修改** `GET /api/admin/images` (新增 `?tagged=false` 查询参数)
- [ ] 学生路由修改:
  - [ ] `GET /api/student/my-images` 返回 `thumbnail_url` 字段
- [ ] 编写 `tests/test_v2_admin_api.py` (覆盖所有新增/修改接口)

### Phase 11: 管理端前端重构 — 沉浸式打标工作台

- [ ] 重写 `static/admin.html` 布局:
  - [ ] 左侧边栏新增"打标台"Tab
  - [ ] 打标工作台：左右分栏容器
  - [ ] 标签池按分组折叠面板
  - [ ] 已打标图片网格（下方）
  - [ ] 标签编辑弹窗组件
- [ ] 重写 `static/js/admin.js`:
  - [ ] 未处理池数据加载与自动选中第一张
  - [ ] 点击标签 → PUT 打标 → 图片消失 + 自动下一张
  - [ ] 池清空时 UI 自动隐藏
  - [ ] 已打标图片点击 → 标签编辑弹窗
  - [ ] 标签分组管理页面（增删改）
  - [ ] 批量添加学生（逗号分隔解析）
  - [ ] 原学生/标签/设置/上传功能保留并适配新布局

### Phase 12: 学生端前端重构 — 多选与队列下载

- [ ] 修改 `static/student.html`:
  - [ ] 导航栏新增"多选"切换按钮
  - [ ] 底部浮现下载栏（选中 N 张时出现）
  - [ ] 选中态 UI：边框高亮 + 遮罩 + ✓ 图标
- [ ] 修改 `static/js/student.js`:
  - [ ] 缩略图加载模式（使用 `thumbnail_url` 作为 img src）
  - [ ] 多选模式状态管理 + toggle
  - [ ] `DownloadQueue` 类实现:
    - [ ] fetch → Blob → `URL.createObjectURL` → `<a download>` 触发
    - [ ] 300ms 间隔序列化下载
    - [ ] 进度 UI 更新 "正在下载 X/Y"
    - [ ] 总大小估算
    - [ ] 中止功能
  - [ ] 保留原有标签过滤 + Lightbox + 键盘导航功能

### Phase 13: V2 集成测试与文档

- [ ] 全量测试 `pytest tests/ -v` (V1.0 61 + V2.0 新增)
- [ ] 数据库迁移回滚验证
- [ ] OSS 缩略图 URL 端到端测试（需真实 OSS 环境）
- [ ] 移动端 Safari / Chrome 兼容性测试:
  - [ ] 多选触摸交互
  - [ ] 队列下载体验
  - [ ] 缩略图渲染
- [ ] 更新 `docs/graduation-album-design-v2.md` 标注实际实现偏差
- [ ] Git 提交并打 tag: `v2.0.0`

---

## 核心接口签名 (V2.0 新增)

### IStorageService

```python
class IStorageService(ABC):
    async def upload(self, file_data: bytes, file_name: str, content_type: str) -> str
    async def get_signed_url(self, file_key: str, expires_seconds: int = 900) -> str
    async def get_thumbnail_url(self, file_key: str, width: int = 400) -> str  # V2.0 NEW
    async def delete(self, file_key: str) -> bool
    async def exists(self, file_key: str) -> bool
```

### ITaggingService

```python
class ITaggingService(ABC):
    async def extract_tags(self, image_data: bytes, file_name: str) -> list[str]
```

---

*最后更新: 2026-06-04 | V1.0 完结 · V2.0 规划完成，待实施*
