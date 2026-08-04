import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma  import Chroma
from langchain_core.prompts import ChatPromptTemplate
from database import add_message
from auth import get_current_user

load_dotenv()

router = APIRouter(prefix="/rag", tags=["RAG 知识库问答"])

# 向量库持久化目录（必须和上传接口保持一致）
VECTOR_DB_DIR = "./chroma_db"

# 初始化嵌入模型（必须和上传时用的模型完全一致）
embeddings = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    openai_api_base=os.getenv("OPENAI_API_BASE")
)

# 尝试加载已存在的向量库
try:
    vector_store = Chroma(
        persist_directory=VECTOR_DB_DIR,
        embedding_function=embeddings
    )
    # 创建检索器：每次检索最相似的 3 个文档块
    retriever = vector_store.as_retriever(search_kwargs={"k": 3})
    print(f"✅ 向量库加载成功，路径：{VECTOR_DB_DIR}")
except Exception as e:
    print(f"⚠️ 向量库加载失败（可能还没有上传过 PDF）：{e}")
    retriever = None


# 定义请求体格式
class RAGQuery(BaseModel):
    question: str
    conversation_id: int | None = None


@router.post("/")
async def rag_answer(query: RAGQuery, user: dict = Depends(get_current_user)):
    """
    RAG 问答流程：
    1. 在向量库中检索相关文档片段
    2. 将片段作为上下文，让 AI 基于这些内容回答
    """
    # 检查向量库是否可用
    if retriever is None:
        raise HTTPException(
            status_code=400,
            detail="向量数据库未初始化，请先通过 /upload/ 接口上传 PDF 文件。"
        )

    # 1. 检索相关文档
    docs = retriever.invoke(query.question)

    # 如果没找到相关内容
    if not docs:
        return {
            "answer": "抱歉，知识库中没有找到与您问题相关的内容。",
            "sources": [],
            "retrieved_count": 0
        }

    # 2. 拼接上下文（把检索到的多个文档块合并成一个长文本）
    context = "\n\n---\n\n".join([doc.page_content for doc in docs])

    # 提取来源信息（方便展示引用）
    sources = list(set([doc.metadata.get("source", "未知来源") for doc in docs]))

    # 3. 构造 Prompt 模板
    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "你是一个基于知识库的问答助手。请严格根据下面的【上下文】内容回答用户的问题。\n"
         "注意：\n"
         "1. 如果上下文中没有提到相关信息，请直接说'找不到相关信息'，不要编造。\n"
         "2. 回答要简洁、准确，用中文。\n\n"
         "【上下文】\n{context}"),
        ("human", "{question}")
    ])

    # 4. 初始化 LLM
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_api_base=os.getenv("OPENAI_API_BASE"),
        temperature=0.2
    )

    # 5. 调用 AI
    try:
        response = llm.invoke(
            prompt.format(context=context, question=query.question)
        )
        answer = response.content
        # 落库
        if query.conversation_id is not None:
            add_message(query.conversation_id, "user", query.question, user_id=user["user_id"])
            add_message(
                query.conversation_id, "assistant", answer, sources=sources, user_id=user["user_id"]
            )
        return {
            "answer": answer,
            "sources": sources,  # 引用了哪些文件（方便溯源）
            "retrieved_count": len(docs)  # 检索到了几个文档块
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 调用失败：{str(e)}")