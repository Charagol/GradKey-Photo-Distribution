"""学生端 Pydantic V2 Request/Response 模型。

学生认证需要三重信息：相册密码 + 姓名 + 个人密钥。
响应模型复用 admin 模块中的 ImageResponse 和 TagResponse。
"""

from pydantic import BaseModel


class StudentAuthRequest(BaseModel):
    """学生双重验证登录请求。

    相册密码（第一重） + 姓名与个人密钥（第二重）。
    """

    album_password: str
    name: str
    secret_key: str
