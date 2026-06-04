"""阿里云 OSS 存储服务实现 — 策略模式具体实现。

所有 OSS 网络 IO 操作通过 asyncio.to_thread() 异步化，
避免阻塞 FastAPI 事件循环。
"""

import asyncio
from pathlib import Path
from uuid import uuid4

import oss2
from oss2.exceptions import NoSuchKey, OssError

from app.config import settings
from app.services.interfaces.istorage_service import IStorageService


class AliyunOssStorageService(IStorageService):
    """阿里云 OSS 对象存储服务。

    通过 oss2 SDK 实现文件上传、临时签名 URL 生成、
    删除和存在性检查。所有 OSS 调用均包装为异步操作。

    文件命名策略: images/{uuid4().hex}{ext} — 防止覆盖且不可预测。
    """

    def __init__(self) -> None:
        """初始化 OSS 客户端，从全局 settings 读取凭证。"""
        self._endpoint: str = settings.oss_endpoint
        self._bucket_name: str = settings.oss_bucket
        self._url_expires: int = settings.oss_signed_url_expires

        self._auth: oss2.Auth = oss2.Auth(
            settings.oss_access_key,
            settings.oss_secret,
        )
        self._bucket: oss2.Bucket = oss2.Bucket(
            self._auth,
            self._endpoint,
            self._bucket_name,
        )

    @staticmethod
    def _generate_file_key(original_name: str) -> str:
        """生成基于 UUID 的唯一文件 Key。

        Args:
            original_name: 原始文件名，用于提取后缀。

        Returns:
            str: 格式为 images/{32位hex}{ext} 的唯一标识符。
        """
        ext: str = Path(original_name).suffix.lower()
        if not ext:
            ext = ".jpg"
        return f"images/{uuid4().hex}{ext}"

    async def upload(
        self, file_data: bytes, file_name: str, content_type: str
    ) -> str:
        """上传文件到 OSS 并返回生成的 File Key。

        Args:
            file_data: 文件二进制内容。
            file_name: 原始文件名。
            content_type: MIME 类型。

        Returns:
            str: UUID 命名的 OSS 对象 Key。
        """
        file_key: str = self._generate_file_key(file_name)
        headers: dict[str, str] = {"Content-Type": content_type}

        await asyncio.to_thread(
            self._bucket.put_object,
            file_key,
            file_data,
            headers=headers,
        )
        return file_key

    async def get_signed_url(
        self, file_key: str, expires_seconds: int | None = None
    ) -> str:
        """生成带签名的临时访问 URL。

        Args:
            file_key: OSS 对象 Key。
            expires_seconds: 有效期（秒），默认使用全局配置（900秒）。

        Returns:
            str: 带签名的 GET 请求 URL。
        """
        if expires_seconds is None:
            expires_seconds = self._url_expires

        url: str = await asyncio.to_thread(
            self._bucket.sign_url,
            "GET",
            file_key,
            expires_seconds,
        )
        return url

    async def delete(self, file_key: str) -> bool:
        """从 OSS 删除对象。

        Args:
            file_key: 要删除的对象 Key。

        Returns:
            bool: 删除成功 True，对象不存在 False。
        """
        try:
            await asyncio.to_thread(
                self._bucket.delete_object,
                file_key,
            )
            return True
        except (NoSuchKey, OssError):
            return False

    async def exists(self, file_key: str) -> bool:
        """检查 OSS 中是否存在指定对象。

        Args:
            file_key: 要检查的对象 Key。

        Returns:
            bool: 存在 True。
        """
        result: bool = await asyncio.to_thread(
            self._bucket.object_exists,
            file_key,
        )
        return result
