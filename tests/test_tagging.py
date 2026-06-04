"""ManualTaggingService 单元测试。"""

import asyncio

import pytest

from app.services.manual_tagging import ManualTaggingService


class TestManualTagging:
    """ManualTaggingService 测试套件。"""

    def test_extract_tags_returns_empty_list(self):
        """验证 extract_tags 始终返回空列表。"""
        service = ManualTaggingService()

        result = asyncio.run(
            service.extract_tags(b"fake-image-data", "photo.jpg")
        )

        assert result == []
        assert isinstance(result, list)

    def test_extract_tags_accepts_various_input_types(self):
        """验证方法接受任意输入并始终返回空列表。"""
        service = ManualTaggingService()

        cases = [
            (b"png-data", "image.png"),
            (b"", "empty.jpg"),
            (b"\x00\x01\x02", "binary.raw"),
            (b"jpeg-data", ""),
        ]

        for data, name in cases:
            result = asyncio.run(service.extract_tags(data, name))
            assert result == [], f"Failed for input ({name})"
