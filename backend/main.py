import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from routers import chat, upload, rag, agent, history, auth

load_dotenv()

app = FastAPI(
    title="我的 AI 后端",
    description="基于 FastAPI + 智谱 GLM，支持 RAG 知识库问答和 Agent 智能体",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有路由
app.include_router(chat.router)    # 纯聊天（含流式）
app.include_router(upload.router)  # 上传 + 向量化
app.include_router(rag.router)     # RAG 知识库问答
app.include_router(agent.router)   # Agent 智能体
app.include_router(history.router) # 对话历史
app.include_router(auth.router)    # 认证（注册/登录）

@app.get("/")
async def root():
    return {
        "message": "AI 后端服务运行正常",
        "docs": "/docs",
        "interfaces": {
            "纯聊天": "/chat/",
            "流式聊天": "/chat/stream",
            "上传PDF": "/upload/",
            "RAG问答": "/rag/",
            "Agent智能体": "/agent/",
            "对话历史": "/history/conversations"
        }
    }