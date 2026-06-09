# V4.0 P8: Docker 工程化
# 基于 python:3.11-slim 构建，镜像精简，无需编译依赖

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 先安装依赖（利用 Docker layer cache，代码变更不触发重装）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码（.dockerignore 已排除 .env / *.db / 缓存文件）
COPY . .

# 暴露端口
EXPOSE 8000

# 启动 FastAPI 应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
