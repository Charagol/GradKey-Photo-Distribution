"""FastAPI 应用入口 — 毕业季专属相册。

架构：
- 本地 SQLite 数据库
- 阿里云 OSS 存储图片
- JWT 管理员 + 学生双重认证
- 基于 Tag 名称匹配的隐私隔离
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import admin_router, auth_router

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

# 注册路由
app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/")
async def health_check():
    """健康检查。"""
    return {"status": "ok", "app": "毕业季专属相册"}
