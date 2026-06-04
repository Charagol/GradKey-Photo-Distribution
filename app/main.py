"""FastAPI 应用入口 — 毕业季专属相册。

架构：
- 本地 SQLite 数据库
- 阿里云 OSS 存储图片
- JWT 管理员 + 学生双重认证
- 基于 Tag 名称匹配的隐私隔离
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routes import admin_router, auth_router, student_router

app = FastAPI(
    title="毕业季专属相册",
    version="0.1.0",
    description="本地 FastAPI + 阿里云 OSS，动静分离，隐私隔离。",
)

# CORS — 允许所有来源（内网使用场景）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(student_router)


@app.get("/admin", include_in_schema=False)
async def admin_page():
    """管理后台 SPA 页面。"""
    return FileResponse("static/admin.html")


@app.get("/")
async def health_check():
    """健康检查。"""
    return {"status": "ok", "app": "毕业季专属相册"}


# 挂载静态资源目录（JS / CSS / 图片等）
app.mount("/static", StaticFiles(directory="static"), name="static")
