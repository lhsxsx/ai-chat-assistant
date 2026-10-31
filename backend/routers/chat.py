import os
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from database import add_message
from auth import get_current_user_optional

# 加载环境变量
load_dotenv()

# 创建一个路由实例，前缀为 /chat，标签用于文档分组
router = APIRouter(prefix="/chat", tags=["聊天"])

# 统一输出格式：纯文本，避免前端把 ** / ## / emoji 原样显示成杂乱字符
SYSTEM_PROMPT = (
    "你是一个中文助手。回答简洁准确。"
    "输出纯文本：不要使用 Markdown 标记（如 **、##、>、反引号）、不要使用 emoji 或装饰性符号，"
    "不要用加粗强调，直接用自然段落和普通短横线列表。"
)


# 定义请求体的数据格式（前端发送 JSON 必须符合这个格式）
class ChatRequest(BaseModel):
    question: str  # 用户的问题
    conversation_id: int | None = None  # 可选：关联的会话 ID


# 定义响应体的数据格式
class ChatResponse(BaseModel):
    answer: str  # AI 的回答
    model: str  # 用的什么模型


# 定义 POST 接口：http://localhost:8000/chat/
@router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, user: dict | None = Depends(get_current_user_optional)):
    try:
        # 1. 初始化 LLM
        llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME"),
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_API_BASE"),
            temperature=0.2
        )

        # 2. 调用智谱
        response = llm.invoke([("system", SYSTEM_PROMPT), ("human", request.question)])

        # 3. 落库（若提供 conversation_id）
        if request.conversation_id is not None:
            uid = user["user_id"] if user else None
            add_message(request.conversation_id, "user", request.question, user_id=uid)
            add_message(request.conversation_id, "assistant", response.content, user_id=uid)

        # 4. 返回结果
        return ChatResponse(
            answer=response.content,
            model=os.getenv("MODEL_NAME")
        )
    except Exception as e:
        # 如果出错，返回 500 错误
        raise HTTPException(status_code=500, detail=f"AI 服务调用失败：{str(e)}")


# ========== 流式输出接口：SSE ==========
# 前端通过 fetch + ReadableStream 读取，实现打字机效果
@router.post("/stream")
async def chat_stream(request: ChatRequest, user: dict | None = Depends(get_current_user_optional)):
    """SSE 流式聊天接口：逐 token 返回 AI 回答。
    响应格式：text/event-stream，每行 `data: {json}\n\n`"""

    def event_stream():
        full_answer = []
        try:
            llm = ChatOpenAI(
                model=os.getenv("MODEL_NAME"),
                api_key=os.getenv("OPENAI_API_KEY"),
                base_url=os.getenv("OPENAI_API_BASE"),
                temperature=0.2,
                streaming=True,
            )
            for chunk in llm.stream([("system", SYSTEM_PROMPT), ("human", request.question)]):
                token = chunk.content if hasattr(chunk, "content") else ""
                if not token:
                    continue
                full_answer.append(token)
                # SSE 协议：data: <payload>\n\n
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            # 结束标记
            yield "data: [DONE]\n\n"
        except Exception as e:
            # 流中出错，推送错误事件
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 落库（无论成功或失败，已生成的部分都存）
            if request.conversation_id is not None and full_answer:
                try:
                    uid = user["user_id"] if user else None
                    add_message(request.conversation_id, "user", request.question, user_id=uid)
                    add_message(
                        request.conversation_id,
                        "assistant",
                        "".join(full_answer),
                        user_id=uid,
                    )
                except Exception:
                    # 落库失败不影响主流程
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
