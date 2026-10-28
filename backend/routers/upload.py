import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from dotenv import load_dotenv

# LangChain 相关导入
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from auth import get_current_user

load_dotenv()

router = APIRouter(prefix="/upload", tags=["文件上传"])

TEMP_DIR = "./temp"
VECTOR_DB_DIR = "./chroma_db"  # 向量库持久化目录

# 确保目录存在
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

# 初始化嵌入模型（智谱的 embedding-3）
embeddings = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
    openai_api_key=os.getenv("OPENAI_API_KEY"),
    openai_api_base=os.getenv("OPENAI_API_BASE")
)


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

        # 给每个切片打上 user_id 标记，检索时按此过滤，避免跨用户读取私有文档
        for chunk in chunks:
            chunk.metadata["user_id"] = user["user_id"]

        # 4. 向量化并存入 Chroma（持久化，新版自动落盘无需 persist()）
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

    # 5. 清理临时文件
    if os.path.exists(file_path):
        os.remove(file_path)

    # 6. 返回成功信息
    return {
        "message": f"文件 {file.filename} 上传并向量化成功",
        "chunks_count": len(chunks),  # 共切成了多少块
        "vector_db_path": VECTOR_DB_DIR
    }


@router.get("/knowledge")
async def get_knowledge_list(user: dict = Depends(get_current_user)):
    """
    获取知识库（Chroma 向量库）中所有文档的列表
    返回每个文档的来源、切片数量等信息
    """
    try:
        # 加载向量库
        vector_store = Chroma(
            persist_directory=VECTOR_DB_DIR,
            embedding_function=embeddings
        )
        
        # 获取所有文档的元数据（只统计当前用户自己的文档）
        collection = vector_store.get(where={"user_id": user["user_id"]})
        
        if not collection or not collection['ids']:
            return {
                "documents": [],
                "total_chunks": 0,
                "total_sources": 0
            }
        
        # 按 source 分组统计
        source_stats = {}
        for i, metadata in enumerate(collection['metadatas']):
            source = metadata.get('source', '未知来源') if metadata else '未知来源'
            page = metadata.get('page', 0) if metadata else 0
            
            if source not in source_stats:
                source_stats[source] = {
                    'source': source,
                    'chunks': 0,
                    'pages': set()
                }
            source_stats[source]['chunks'] += 1
            source_stats[source]['pages'].add(page)
        
        # 转换为列表并排序
        documents = []
        for source, stats in sorted(source_stats.items()):
            # 从文件名提取显示名称（去除路径）
            display_name = os.path.basename(source) if source != '未知来源' else source
            documents.append({
                'name': display_name,
                'source': source,
                'chunks': stats['chunks'],
                'pages': len(stats['pages'])
            })
        
        total_chunks = sum(d['chunks'] for d in documents)
        
        return {
            "documents": documents,
            "total_chunks": total_chunks,
            "total_sources": len(documents)
        }
        
    except Exception as e:
        # 如果向量库不存在或为空，返回空列表
        if 'does not exist' in str(e).lower() or 'not found' in str(e).lower():
            return {
                "documents": [],
                "total_chunks": 0,
                "total_sources": 0
            }
        raise HTTPException(status_code=500, detail=f"获取知识库列表失败：{str(e)}")