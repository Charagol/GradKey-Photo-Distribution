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

*最后更新: 2026-06-04*
