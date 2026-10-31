import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from dotenv import load_dotenv

# LangChain 相关导入
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from embeddings import get_embeddings
from auth import get_current_user
from database import create_document, delete_document, list_documents

load_dotenv()

router = APIRouter(prefix="/upload", tags=["文件上传"])

TEMP_DIR = "./temp"
VECTOR_DB_DIR = "./chroma_db"  # 向量库持久化目录

# 确保目录存在
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

# 初始化嵌入模型（本地 bge-small-zh，与检索端保持一致）
embeddings = get_embeddings()


@router.post("/")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """
    上传 PDF，自动切片并存入向量数据库
    """
    # 1. 检查文件类型
    if not file.filename.endswith('.pdf'):
        raise HTTPException(400, detail="目前仅支持 PDF 文件")

    # 2. 保存到临时目录
    file_path = os.path.join(TEMP_DIR, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(500, detail=f"文件保存失败：{str(e)}")

    # 3. 加载 PDF 并切片
    try:
        loader = PyPDFLoader(file_path)
        documents = loader.load()  # 读取所有页面

        # 切片：每块 500 字符，重叠 50 字符
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )
        chunks = splitter.split_documents(documents)

        if not chunks:
            raise Exception("PDF 内容为空，无法处理")

        # 4. 先在 PostgreSQL 登记文档，拿到 document_id 后再写向量
        doc = create_document(
            user_id=user["user_id"],
            filename=file.filename,
            chunks_count=len(chunks),
            pages=len(documents),
        )

        # 给每个切片打上 user_id 与 document_id 标记：
        # user_id 用于检索时按用户过滤，document_id 用于删除时批量清理向量
        for chunk in chunks:
            chunk.metadata["user_id"] = user["user_id"]
            chunk.metadata["document_id"] = doc["id"]

        # 5. 向量化并存入 Chroma（持久化，新版自动落盘无需 persist()）
        vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=VECTOR_DB_DIR  # 存到本地文件夹
        )

    except Exception as e:
        # 如果处理失败，清理临时文件并报错
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(500, detail=f"PDF 处理失败：{str(e)}")

    # 6. 清理临时文件
    if os.path.exists(file_path):
        os.remove(file_path)

    # 7. 返回成功信息
    return {
        "message": f"文件 {file.filename} 上传并向量化成功",
        "document_id": doc["id"],
        "chunks_count": len(chunks),  # 共切成了多少块
        "pages": len(documents),
    }


@router.get("/knowledge")
async def get_knowledge_list(user: dict = Depends(get_current_user)):
    """
    获取当前用户的知识库文档列表（数据来自 PostgreSQL 的 documents 表）
    """
    documents = list_documents(user["user_id"])
    return {
        "documents": documents,
        "total_chunks": sum(d["chunks"] for d in documents),
        "total_sources": len(documents),
    }


@router.delete("/knowledge/{document_id}")
async def delete_knowledge(document_id: int, user: dict = Depends(get_current_user)):
    """
    删除当前用户自己上传的文档：同时清理 PostgreSQL 记录与 Chroma 向量切片
    """
    # 1. 校验归属并删除数据库记录
    doc = delete_document(document_id, user["user_id"])
    if doc is None:
        raise HTTPException(404, detail="文档不存在或无权删除")

    # 2. 清理该文档对应的向量切片
    try:
        vector_store = Chroma(
            persist_directory=VECTOR_DB_DIR,
            embedding_function=embeddings
        )
        vector_store.delete(where={"document_id": document_id})
    except Exception as e:
        # 向量库为空或不存在时忽略，数据库记录已删除
        if 'does not exist' not in str(e).lower() and 'not found' not in str(e).lower():
            raise HTTPException(500, detail=f"向量清理失败：{str(e)}")

    return {"message": f"文档 {doc['name']} 已删除", "document_id": document_id}