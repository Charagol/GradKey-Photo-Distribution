"""依赖注入 — 为 FastAPI 路由提供可替换的服务实例。

存储服务可被 app.dependency_overrides 替换，用于测试。
"""

from app.services.aliyun_oss_storage import AliyunOssStorageService


def get_storage_service() -> AliyunOssStorageService:
    """实例化并返回阿里云 OSS 存储服务。

    Returns:
        AliyunOssStorageService: 已就绪的 OSS 存储服务。
    """
    return AliyunOssStorageService()
