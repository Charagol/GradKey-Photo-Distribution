"""打标服务抽象接口 — 策略模式核心。

支持未来从手动打标切换到 AI 自动识别（InsightFace / CLIP），
无需修改上层业务代码。
"""

from abc import ABC, abstractmethod


class ITaggingService(ABC):
    """图片智能打标服务抽象基类。

    当前 ManualTaggingService 返回空列表（标签完全由管理员手选）。
    未来可替换为基于 AI 模型的自动打标实现。
    """

    @abstractmethod
    async def extract_tags(self, image_data: bytes, file_name: str) -> list[str]:
        """分析图片并提取建议标签。

        Args:
            image_data: 图片二进制内容（供 AI 模型使用）。
            file_name: 原始文件名（供未来上下文分析）。

        Returns:
            list[str]: 建议的标签名列表。ManualTaggingService 返回空列表。
        """
        ...
