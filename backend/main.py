import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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

# ===== 托管前端静态文件 =====
# 前端打包后的 dist 目录路径
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    # 挂载静态资源（CSS/JS/图片等）
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    # 所有非 API 路由都返回前端 index.html（支持前端路由）
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # 如果是 API 路径，返回 404
        if full_path.startswith(("chat", "upload", "rag", "agent", "history", "auth", "docs")):
            return {"detail": "Not Found"}
        index_path = os.path.join(FRONTEND_DIST, "index.html")
        return FileResponse(index_path)