"""存储服务抽象接口 — 策略模式核心。

所有存储实现（阿里云 OSS / MinIO / 本地磁盘）必须实现此接口，
使得上层业务代码不依赖具体存储实现（依赖反转 DIP）。
"""

from abc import ABC, abstractmethod


class IStorageService(ABC):
    """对象存储服务抽象基类。

    定义文件上传、签名 URL 生成、删除、存在性检查的标准契约。
    实现类负责具体的存储后端操作。
    """

    @abstractmethod
    async def upload(self, file_data: bytes, file_name: str, content_type: str) -> str:
        """上传文件到对象存储。

        Args:
            file_data: 文件二进制内容。
            file_name: 原始文件名（用于提取扩展名）。
            content_type: MIME 类型（如 image/jpeg）。

        Returns:
            str: 生成的文件 Key（UUID 命名，如 images/a1b2c3d4.jpg）。
        """
        ...

    @abstractmethod
    async def get_signed_url(self, file_key: str, expires_seconds: int = 900) -> str:
        """生成带签名的临时访问 URL。

        Args:
            file_key: 文件的 OSS Key。
            expires_seconds: URL 有效期（秒），默认 900（15 分钟）。

        Returns:
            str: 带签名的临时 URL，可供前端直接访问。
        """
        ...

    @abstractmethod
    async def delete(self, file_key: str) -> bool:
        """从对象存储中删除文件。

        Args:
            file_key: 要删除的文件 Key。

        Returns:
            bool: 删除成功返回 True，文件不存在返回 False。
        """
        ...

    @abstractmethod
    async def exists(self, file_key: str) -> bool:
        """检查文件是否存在于对象存储中。

        Args:
            file_key: 要检查的文件 Key。

        Returns:
            bool: 存在返回 True。
        """
        ...
