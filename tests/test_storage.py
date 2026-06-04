"""AliyunOssStorageService 单元测试。

使用 unittest.mock 对 oss2 SDK 进行全面 Mock，
确保不发起任何真实网络请求。
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from app.services.aliyun_oss_storage import AliyunOssStorageService


@pytest.fixture
def mock_oss():
    """构建 Mock OSS 环境，返回 (service, mock_bucket) 元组。"""
    with (
        patch("app.services.aliyun_oss_storage.oss2.Auth") as mock_auth_cls,
        patch("app.services.aliyun_oss_storage.oss2.Bucket") as mock_bucket_cls,
    ):
        mock_auth_cls.return_value = MagicMock()
        mock_bucket = MagicMock()
        mock_bucket_cls.return_value = mock_bucket

        service = AliyunOssStorageService()
        yield service, mock_bucket


class TestUpload:
    """upload 方法测试套件。"""

    def test_upload_generates_uuid_file_key(self, mock_oss):
        """验证 file_key 符合 images/{32位hex}.{ext} 格式。"""
        service, mock_bucket = mock_oss

        file_key = service._generate_file_key("photo.jpg")

        assert re.match(r"^images/[a-f0-9]{32}\.jpg$", file_key)

    def test_upload_returns_string_key(self, mock_oss):
        """验证 upload 返回字符串 key。"""
        service, mock_bucket = mock_oss
        mock_bucket.put_object = MagicMock()

        import asyncio
        file_key = asyncio.run(
            service.upload(b"fake-data", "test.png", "image/png")
        )

        assert isinstance(file_key, str)
        assert file_key.startswith("images/")

    def test_upload_passes_content_type_header(self, mock_oss):
        """验证 upload 将 content_type 写入 headers。"""
        service, mock_bucket = mock_oss
        mock_bucket.put_object = MagicMock()

        import asyncio
        asyncio.run(
            service.upload(b"fake-data", "test.png", "image/png")
        )

        call_args = mock_bucket.put_object.call_args
        headers = call_args[1]["headers"]
        assert headers["Content-Type"] == "image/png"


class TestGetSignedUrl:
    """get_signed_url 方法测试套件。"""

    def test_get_signed_url_returns_string(self, mock_oss):
        """验证返回值为非空字符串。"""
        service, mock_bucket = mock_oss
        mock_bucket.sign_url = MagicMock(return_value="https://fake-oss.com/signed-url")

        import asyncio
        url = asyncio.run(
            service.get_signed_url("images/test.jpg")
        )

        assert isinstance(url, str)
        assert len(url) > 0

    def test_get_signed_url_uses_default_expiry(self, mock_oss):
        """验证默认有效期参数为 900 秒。"""
        service, mock_bucket = mock_oss
        mock_bucket.sign_url = MagicMock(return_value="https://fake-oss.com/signed-url")

        import asyncio
        asyncio.run(service.get_signed_url("images/test.jpg"))

        call_args = mock_bucket.sign_url.call_args
        assert call_args[0][0] == "GET"
        assert call_args[0][1] == "images/test.jpg"
        assert call_args[0][2] == 900

    def test_get_signed_url_uses_custom_expiry(self, mock_oss):
        """验证自定义有效期被正确传递。"""
        service, mock_bucket = mock_oss
        mock_bucket.sign_url = MagicMock(return_value="https://fake-oss.com/signed-url")

        import asyncio
        asyncio.run(service.get_signed_url("images/test.jpg", 300))

        call_args = mock_bucket.sign_url.call_args
        assert call_args[0][2] == 300


class TestDelete:
    """delete 方法测试套件。"""

    def test_delete_returns_true_on_success(self, mock_oss):
        """验证正常删除返回 True。"""
        service, mock_bucket = mock_oss
        mock_bucket.delete_object = MagicMock(return_value=None)

        import asyncio
        result = asyncio.run(
            service.delete("images/test.jpg")
        )

        assert result is True

    def test_delete_returns_false_on_oss_error(self, mock_oss):
        """验证 OSS 异常时返回 False。"""
        service, mock_bucket = mock_oss
        from oss2.exceptions import NoSuchKey
        mock_bucket.delete_object = MagicMock(
            side_effect=NoSuchKey(404, {}, "body", {"Code": "NoSuchKey"})
        )

        import asyncio
        result = asyncio.run(
            service.delete("images/nonexistent.jpg")
        )

        assert result is False


class TestExists:
    """exists 方法测试套件。"""

    def test_exists_returns_true_when_object_present(self, mock_oss):
        """验证对象存在时返回 True。"""
        service, mock_bucket = mock_oss
        mock_bucket.object_exists = MagicMock(return_value=True)

        import asyncio
        result = asyncio.run(
            service.exists("images/test.jpg")
        )

        assert result is True

    def test_exists_returns_false_when_object_absent(self, mock_oss):
        """验证对象不存在时返回 False。"""
        service, mock_bucket = mock_oss
        mock_bucket.object_exists = MagicMock(return_value=False)

        import asyncio
        result = asyncio.run(
            service.exists("images/missing.jpg")
        )

        assert result is False
