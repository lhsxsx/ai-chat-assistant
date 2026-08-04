from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from database import (
    list_conversations,
    get_conversation_messages,
    create_conversation_dict,
    delete_conversation,
    rename_conversation,
)
from auth import get_current_user

router = APIRouter(prefix="/history", tags=["对话历史"])


class CreateConvRequest(BaseModel):
    mode: str = "chat"
    title: str | None = None


class RenameRequest(BaseModel):
    title: str


@router.get("/conversations")
async def get_conversations(user: dict = Depends(get_current_user)):
    """列出当前用户的所有会话（仅返回该用户的）"""
    return {"conversations": list_conversations(user["user_id"])}


@router.post("/conversations")
async def create_conversation_api(req: CreateConvRequest, user: dict = Depends(get_current_user)):
    """创建新会话，自动绑定到当前用户"""
    if req.mode not in ("chat", "rag", "agent"):
        raise HTTPException(400, detail="mode 必须是 chat/rag/agent")
    return create_conversation_dict(user_id=user["user_id"], mode=req.mode, title=req.title)


@router.get("/conversations/{conversation_id}")
async def get_conversation_api(conversation_id: int, user: dict = Depends(get_current_user)):
    """获取某会话的所有消息。若会话不属于当前用户则返回 404。"""
    msgs = get_conversation_messages(conversation_id, user["user_id"])
    if msgs is None:
        raise HTTPException(404, detail="会话不存在或无权访问")
    return {"messages": msgs}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation_api(conversation_id: int, user: dict = Depends(get_current_user)):
    """删除会话。若会话不属于当前用户则返回 404。"""
    ok = delete_conversation(conversation_id, user["user_id"])
    if not ok:
        raise HTTPException(404, detail="会话不存在或无权访问")
    return {"message": "已删除"}


@router.patch("/conversations/{conversation_id}")
async def rename_conversation_api(
    conversation_id: int, req: RenameRequest, user: dict = Depends(get_current_user)
):
    """重命名会话。若会话不属于当前用户则返回 404。"""
    result = rename_conversation(conversation_id, user["user_id"], req.title)
    if result is None:
        raise HTTPException(404, detail="会话不存在或无权访问")
    return result
