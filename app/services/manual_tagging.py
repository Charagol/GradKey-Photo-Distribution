"""手动打标服务实现 — 策略模式当前实现。

标签完全由管理员手动分配，此服务作为占位，
为未来 AI 自动打标（InsightFace / CLIP）预留接口。
"""

from app.services.interfaces.itagging_service import ITaggingService


class ManualTaggingService(ITaggingService):
    """手动打标服务。

    当前实现永远返回空列表 — 标签由管理员手动创建和分配。
    extract_tags 方法保留为未来 AI 实现的扩展点。
    """

    async def extract_tags(self, image_data: bytes, file_name: str) -> list[str]:
        """返回空列表作为占位。

        Args:
            image_data: 图片二进制内容（当前未使用）。
            file_name: 原始文件名（当前未使用）。

        Returns:
            list[str]: 始终为空列表。
        """
        return []
