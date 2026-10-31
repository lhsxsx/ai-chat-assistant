import os

from dotenv import load_dotenv

load_dotenv()

# 本地模型默认从 HuggingFace 下载，国内直连不通，改用镜像站
# 必须在 transformers / sentence_transformers 导入之前设置
if os.getenv("HF_ENDPOINT") is None:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

LOCAL_MODEL = os.getenv("LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

_embeddings = None


def get_embeddings():
    """
    嵌入模型单例，避免每次请求重新加载模型权重。
    通过 EMBEDDING_BACKEND 切换：
      local —— 本地 bge-small-zh（默认，无需 API 额度）
      api   —— 智谱 embedding-3（需要资源包）
    """
    global _embeddings
    if _embeddings is None:
        if os.getenv("EMBEDDING_BACKEND", "local") == "api":
            from langchain_openai import OpenAIEmbeddings

            _embeddings = OpenAIEmbeddings(
                model=os.getenv("EMBEDDING_MODEL", "embedding-3"),
                openai_api_key=os.getenv("OPENAI_API_KEY"),
                openai_api_base=os.getenv("OPENAI_API_BASE"),
            )
        else:
            from langchain_huggingface import HuggingFaceEmbeddings

            _embeddings = HuggingFaceEmbeddings(
                model_name=LOCAL_MODEL,
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
    return _embeddings
