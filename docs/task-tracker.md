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

- [x] 创建 `app/models/tag_group.py` (TagGroup 模型)
- [x] Tag 模型新增 `group_id` 外键
- [x] 更新 `app/models/__init__.py` 注册 TagGroup
- [x] 编写迁移脚本 `app/migrations/v2_migrate.py`
  - [x] 创建 tag_group 表
  - [x] 插入默认"未分类"分组
  - [x] SQLite 三表重建添加 group_id 列
  - [x] 现有 Tag 默认归入"未分类"
- [x] 编写 `tests/test_tag_group.py` (13 个用例，模型 + 迁移验证)
- [x] 测试夹具注入默认 TagGroup（test_admin_api.py / test_student_api.py）
- [x] Tag.before_insert 事件确保向后兼容
- [x] 生产数据库迁移验证通过（album.db: 5 tags → 未分类）

### Phase 10: 管理端 API 升级

- [x] `app/schemas/admin.py` 新增:
  - [x] `StudentCreate.names: str` (V2.0 逗号分隔批量)
  - [x] `TagGroupCreate` / `TagGroupUpdate` / `TagGroupResponse` (含嵌套 tags)
  - [x] `TagUpdate(group_id)` / `ImageTagUpdate(tag_ids: list[int])`
- [x] `app/services/student_service.py` 新增 `auto_commit` 参数支持批量事务
- [x] 管理员路由新增/修改:
  - [x] **POST /api/admin/students** (统一端点: `{"names": "张三,李四"}` 逗号分隔批量 + 自动建 Tag)
  - [x] `GET/POST /api/admin/tag-groups` (分组 CRUD)
  - [x] `PUT/DELETE /api/admin/tag-groups/{id}` (重命名/删除, 删除时 Tag 迁移至"未分类")
  - [x] `PUT /api/admin/tags/{id}` (移动标签至其他分组)
  - [x] `PUT /api/admin/images/{id}/tags` (全量替换图片标签)
  - [x] **GET /api/admin/images** (新增 `?tagged=true|false` 过滤参数)
- [x] `tests/test_admin_api.py` 适配 V2.0 schema (4 处)
- [x] `tests/test_student_api.py` 适配 + `_setup_tag` 幂等化 (acceps 201/409)
- [x] `tests/test_v2_admin_api.py` (24 个用例, 覆盖所有新增接口)
- [x] 全量测试 98 passed

### Phase 11: 管理端前端重构 — 沉浸式打标工作台 ✅

- [x] 重写 `static/admin.html` 布局:
  - [x] 顶部导航条 + 左侧边栏（打标台/学生/分组/图片/设置）
  - [x] 打标工作台：左右分栏（未处理池 w-3/5 + 标签池 w-2/5）
  - [x] 标签池按 TagGroup 分组面板展示
  - [x] 已打标图片网格（下方，支持 tagged/untagged/all 过滤）
  - [x] 标签编辑 Modal（含当前标签 + 可用标签选择器）
- [x] 重写 `static/js/admin.js`:
  - [x] State 驱动渲染：allImages → unprocessed + processed 自动分流
  - [x] 核心交互：点击标签 → PUT /images/{id}/tags → 图片消失 + 自动选中下一张
  - [x] processingLock 防抖锁 + 事件委托避免重复绑定
  - [x] 未处理池清空时自动隐藏工作区 + 显示"全部处理完毕"
  - [x] 已打标图片点击 → Modal 二次编辑标签
  - [x] 标签分组管理（增删改 + 标签拖拽移动）
  - [x] 批量学生创建（逗号分隔）
  - [x] 图片上传/管理/删除 + 相册设置完整保留

### Phase 12: 学生端前端重构 — 多选与队列下载 ✅

- [x] 修改 `static/student.html`:
  - [x] 导航栏新增"开启多选"切换按钮
  - [x] 底部浮现选择操作栏（全选/取消全选/下载选中/取消）
  - [x] 底部下载进度条（旋转 spinner + "正在下载 X/Y" + 中止按钮）
  - [x] 选中态 UI：indigo 半透明遮罩 + ✓ 圆形标记
- [x] 修改 `static/js/student.js`:
  - [x] 缩略图模式：列表用 OSS `x-oss-process=image/resize,m_lfit,w_400,h_400`，Lightbox 用原图
  - [x] 多选模式状态管理：`isMultiSelectMode` + `selectedIds: Set` + `downloadProgress`
  - [x] 下载队列：fetch → Blob → `URL.createObjectURL` → `<a download>` → 400ms 间隔防拦截
  - [x] 进度 UI："正在下载 X/Y — filename" + 旋转 spinner
  - [x] 中止功能：`downloadAborted` flag + 中止按钮
  - [x] 保留原有标签过滤 + Lightbox 键盘/触摸导航

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

*最后更新: 2026-06-04 | V1.0 完结 · Phase 9-12 完成 (98 tests) · 待 Phase 13*
