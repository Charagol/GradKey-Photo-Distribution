"""路由包 — 集中导出所有 Router 实例。"""

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router

__all__ = ["auth_router", "admin_router"]
