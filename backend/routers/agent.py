import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.agent_service import ask_agent, stream_ask_agent
from database import add_message
from auth import get_current_user

router = APIRouter(prefix="/agent", tags=["Agent 智能体"])

class Question(BaseModel):
    question: str
    conversation_id: int | None = None

@router.post("/")
async def agent_endpoint(q: Question, user: dict = Depends(get_current_user)):
    """
    Agent 智能体接口（非流式）：
    - 自动判断使用知识库检索还是搜索引擎
    - 也可以直接回答简单问题
    """
    try:
        answer = ask_agent(q.question, user["user_id"])
        # 落库
        if q.conversation_id is not None:
            add_message(q.conversation_id, "user", q.question, user_id=user["user_id"])
            add_message(q.conversation_id, "assistant", answer, user_id=user["user_id"])
        return {
            "answer": answer,
            "mode": "agent"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 处理失败：{str(e)}")


# ========== 流式接口：推送 Agent 思考过程 ==========
@router.post("/stream")
async def agent_stream(q: Question, user: dict = Depends(get_current_user)):
    """SSE 流式 Agent 接口：逐步推送思考/工具调用/观察/最终答案。
    响应格式：text/event-stream，每行 `data: {json}\n\n`

    事件类型：
      thought     - LLM 的思考文本
      action      - 工具调用（tool + input）
      observation - 工具返回结果
      answer      - 最终答案（可能多次推送，最后一次为准）
      done        - 结束
      error       - 错误
    """
    def event_stream():
        final_answer = ""
        try:
            for event in stream_ask_agent(q.question, user["user_id"]):
                ev_type = event.get("type", "")
                content = event.get("content", "")
                if ev_type == "answer":
                    final_answer = content
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 落库
            if q.conversation_id is not None and final_answer:
                try:
                    add_message(q.conversation_id, "user", q.question, user_id=user["user_id"])
                    add_message(q.conversation_id, "assistant", final_answer, user_id=user["user_id"])
                except Exception:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
