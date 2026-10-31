import os
import json
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from database import add_message, get_recent_messages
from auth import get_current_user

load_dotenv()

router = APIRouter(prefix="/rag", tags=["RAG 知识库问答"])

# 向量库持久化目录（必须和上传接口保持一致）
VECTOR_DB_DIR = "./chroma_db"

# 携带的最近对话轮数（1 轮 = 1 问 + 1 答，即 2 条消息）
HISTORY_MESSAGES = 6

# 初始化嵌入模型（必须和上传时用的模型完全一致）
embeddings = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    openai_api_base=os.getenv("OPENAI_API_BASE")
)


def get_user_retriever(user_id: int):
    """按 user_id 构建检索器，只检索该用户自己上传的文档，避免跨租户数据泄漏。"""
    vector_store = Chroma(
        persist_directory=VECTOR_DB_DIR,
        embedding_function=embeddings
    )
    return vector_store.as_retriever(
        search_kwargs={"k": 3, "filter": {"user_id": user_id}}
    )


def _build_history_messages(conversation_id: int | None, user_id: int) -> list:
    """把最近几轮对话转成 LangChain 消息，供模型理解指代（如“它”“这个方案”）。"""
    if conversation_id is None:
        return []
    history = get_recent_messages(conversation_id, user_id, limit=HISTORY_MESSAGES)
    messages = []
    for item in history:
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        else:
            messages.append(AIMessage(content=item["content"]))
    return messages


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system",
         "你是一个基于知识库的问答助手。请严格根据下面的【上下文】内容回答用户的问题。\n"
         "注意：\n"
         "1. 如果上下文中没有提到相关信息，请直接说'找不到相关信息'，不要编造。\n"
         "2. 结合【对话历史】理解用户问题中的指代和省略（如“它”“这个”“上面提到的”）。\n"
         "3. 回答要简洁、准确，用中文。\n\n"
         "【上下文】\n{context}"),
        MessagesPlaceholder("history", optional=True),
        ("human", "{question}")
    ])


# 定义请求体格式
class RAGQuery(BaseModel):
    question: str
    conversation_id: int | None = None


@router.post("/stream")
async def rag_stream(query: RAGQuery, user: dict = Depends(get_current_user)):
    """RAG 流式问答接口（与 /chat/stream 一致的逐 token 输出）。

    响应格式：text/event-stream
      1. data: {"type": "sources", "sources": [...], "retrieved_count": n}
      2. data: {"token": "..."}   （多次）
      3. data: [DONE]
    """

    # 1. 先做检索（放在生成器外，检索失败可以直接返回 HTTP 错误）
    try:
        retriever = get_user_retriever(user["user_id"])
        docs = retriever.invoke(query.question)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"向量数据库不可用，请先通过 /upload/ 接口上传 PDF 文件：{e}"
        )

    # 来源文件名（去重且保持顺序，用于前端溯源展示）
    sources: list[str] = []
    for doc in docs:
        name = os.path.basename(doc.metadata.get("source", "未知来源"))
        if name not in sources:
            sources.append(name)

    def event_stream():
        full_answer: list[str] = []
        try:
            # 2. 先推送来源信息，前端可以边看答案边展示引用
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources, 'retrieved_count': len(docs)}, ensure_ascii=False)}\n\n"

            # 没有检索到内容，直接给出兜底回答
            if not docs:
                fallback = "抱歉，知识库中没有找到与您问题相关的内容。"
                full_answer.append(fallback)
                yield f"data: {json.dumps({'token': fallback}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            # 3. 拼接上下文 + 最近几轮对话
            context = "\n\n---\n\n".join([doc.page_content for doc in docs])

            llm = ChatOpenAI(
                model=os.getenv("MODEL_NAME"),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_api_base=os.getenv("OPENAI_API_BASE"),
                temperature=0.2,
                streaming=True
            )

            chain = _build_prompt() | llm
            for chunk in chain.stream({
                "context": context,
                "history": _build_history_messages(query.conversation_id, user["user_id"]),
                "question": query.question,
            }):
                token = chunk.content if hasattr(chunk, "content") else ""
                if not token:
                    continue
                full_answer.append(token)
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            # 结束标记
            yield "data: [DONE]\n\n"
        except Exception as e:
            # 流中出错，推送错误事件
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            # 4. 落库（用户问题 + 已生成的部分回答 + 来源）
            if query.conversation_id is not None and full_answer:
                try:
                    add_message(query.conversation_id, "user", query.question, user_id=user["user_id"])
                    add_message(
                        query.conversation_id,
                        "assistant",
                        "".join(full_answer),
                        sources=sources,
                        user_id=user["user_id"],
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
