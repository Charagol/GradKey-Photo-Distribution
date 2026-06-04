"""FastAPI 应用入口 — 毕业季专属相册。

架构：
- 本地 SQLite 数据库
- 阿里云 OSS 存储图片
- JWT 管理员 + 学生双重认证
- 基于 Tag 名称匹配的隐私隔离
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes import admin_router, auth_router, student_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title="毕业季专属相册",
    version="2.0.0",
    description="本地 FastAPI + 阿里云 OSS，动静分离，隐私隔离。",
)

# ── 中间件 ────────────────────────────────────────────────────────────────

# CORS — 允许所有来源（内网使用场景）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip 压缩 — 对 >1KB 的响应体启用压缩，减少带宽占用
app.add_middleware(GZipMiddleware, minimum_size=1000)

# ── 全局异常处理 ──────────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception):
    """捕获所有未处理的异常，记录日志并返回通用 500 错误。

    避免将内部堆栈信息泄露给客户端，
    同时保留完整的 traceback 供运维排查。
    """
    logger.exception("未处理的服务器内部错误: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请联系管理员"},
    )


# ── API 路由 ──────────────────────────────────────────────────────────────

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(student_router)


# ── 前端页面 ──────────────────────────────────────────────────────────────


@app.get("/admin", include_in_schema=False)
async def admin_page():
    """管理后台 SPA 页面。"""
    return FileResponse("static/admin.html")


@app.get("/student", include_in_schema=False)
async def student_page():
    """学生门户 SPA 页面。"""
    return FileResponse("static/student.html")


@app.get("/")
async def root():
    """根路径 → 重定向到学生门户。"""
    return RedirectResponse(url="/student")


# ── 静态资源 ──────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory="static"), name="static")
