"""路由包 — 集中导出所有 Router 实例。"""

from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.student import router as student_router

__all__ = ["admin_router", "auth_router", "student_router"]
