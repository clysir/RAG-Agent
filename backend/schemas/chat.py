"""聊天接口的请求/响应 schema —— 流式接口的 envelope 是 SSE 帧,见 schemas/agent。"""

from pydantic import Field

from schemas.common import APIModel


class ChatRequest(APIModel):
    """聊天接口入参 —— 通过 multipart/form-data 提交以支持图片。

    Form 字段:
        session_id: 会话 ID,前端首次自行生成 UUID
        query: 用户输入文本
        user_id: 可选用户 ID
        image: 可选 UploadFile(multipart)

    这里给的是结构化记录,实际接口因 multipart 不直接用此 Pydantic 类做 body。
    """

    session_id: str = Field(..., min_length=1, max_length=64, description="会话 ID")
    query: str = Field(..., min_length=1, max_length=2000, description="用户输入文本")
    user_id: str | None = Field(None, max_length=64)
    image_url: str | None = Field(None, description="若图片已上传到对象存储,可直接传 URL")


class CreateSessionRequest(APIModel):
    """创建会话接口入参 —— 可选,目前会话由前端 UUID 直接生成,留作扩展。"""

    user_id: str | None = None
    title: str | None = Field(None, max_length=256)


class SessionInfo(APIModel):
    """会话信息 —— GET /sessions/{id} 返回。"""

    id: str
    user_id: str | None = None
    title: str | None = None
    message_count: int = 0


class MessageRecord(APIModel):
    """单条历史消息 —— 列表接口返回。"""

    id: int
    role: str
    content: str
    image_url: str | None = None
