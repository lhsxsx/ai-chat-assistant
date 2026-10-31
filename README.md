# AI 对话助手

**中文** | [English](README_EN.md)

[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![LangChain](https://img.shields.io/badge/LangChain-1.x-1C3C3C?logo=langchain&logoColor=white)](https://python.langchain.com/)

基于 FastAPI + React 的全栈 AI 对话应用，支持三种交互模式：纯对话、RAG 知识库问答、Agent 智能体。

## 为什么做这个

主流 AI 应用教程大多停在前端调接口、把模型回复拼成字符串。我想搞清楚三件更实际的事：

- **流式响应在真实链路上怎么落地**：SSE 分块到达时如何解析、跨 chunk 粘包怎么处理、用户中途想停下怎么办
- **RAG 的每一步到底在做什么**：切片粒度对召回的影响、检索结果怎么回填给模型、引用来源怎么让用户信任
- **Agent 的"思考"能不能被看见**：工具调用的中间过程如果只给最终答案，用户无法判断结论是否可信

所以这个项目把三种模式做成了同一套前后端架构下的三条独立链路，重点在流式通信、检索和工具编排的工程实现，而不是堆功能。

## 功能

- **Chat 流式对话**：基于 SSE 逐 token 推送，前端打字机效果，支持中断生成
- **RAG 知识库问答**：上传 PDF → 切片 → 向量化 → 相似度检索 → 上下文拼装，同样走 SSE 逐 token 输出，携带最近几轮对话，回答带来源溯源
- **知识库文档管理**：文档记录存入 PostgreSQL，列表与删除均按 `user_id` 隔离，删除时同步清理向量切片
- **Agent 智能体**：基于 LangChain 工具调用（知识库检索 / 搜索引擎 / 当前时间），前端可视化思考过程
- **多用户体系**：JWT 鉴权，会话与消息按 `user_id` 隔离，对话历史持久化到 PostgreSQL

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI、SQLAlchemy、PostgreSQL、PyJWT、LangChain、Chroma |
| 前端 | React 19、TypeScript、Vite |
| 模型 | 智谱 GLM（兼容 OpenAI 协议） |

## 架构

```
浏览器 ──> Vite 开发服务器（/chat /rag /agent /upload /history /auth 代理）
              │
              └──> FastAPI ──> PostgreSQL（用户 / 会话 / 消息）
                        ├──> Chroma（向量库，按 user_id 隔离）
                        └──> 智谱 GLM API（对话 + Embedding）
```

生产环境可将前端打包产物 `frontend/dist` 交由 FastAPI `StaticFiles` 托管，实现单端口部署。

## 目录结构

```
backend/
  main.py              应用入口、CORS、路由注册、前端静态托管
  auth.py              密码哈希（pbkdf2）与 JWT 签发/校验、鉴权依赖
  database.py          ORM 模型（users / conversations / messages / documents）与 CRUD
  routers/             chat、rag、agent、upload、history、auth 各业务路由
  services/            agent_service.py（Agent 构建与流式事件）
  eval/                RAG 检索评测（questions.json + retrieval_eval.py）
frontend/
  src/App.tsx          主界面（三种模式切换、会话列表、知识库）
  src/useChatStream.ts 流式通信、会话管理、SSE 解析
  src/useAuth.ts       登录态与鉴权头注入
```

## 快速开始

### 1. 启动 PostgreSQL

```bash
docker run -d --name ai-chat-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ai_chat \
  -p 5432:5432 postgres:15
```

表结构会在后端首次启动时自动创建。

### 2. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
```

在 `backend/.env` 中配置：

```env
OPENAI_API_KEY=<你的智谱 API Key>
OPENAI_API_BASE=https://open.bigmodel.cn/api/paas/v4/
MODEL_NAME=glm-4-flash
EMBEDDING_MODEL=embedding-3
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_chat
JWT_SECRET=<一段随机字符串>
```

启动：

```bash
uvicorn main:app --reload --port 8000
```

接口文档：http://localhost:8000/docs

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

## 检索评测

`backend/eval/questions.json` 里是针对所选 PDF 可回答的 32 道题，`retrieval_eval.py` 按当前切片与检索配置（500/50、k=3）测量 top-k 命中率：

```bash
cd backend
.venv\Scripts\python.exe eval\retrieval_eval.py --pdf "temp/你要评测的文件.pdf"
```

题目按关键词判定命中，结果写入 `eval/last_report.json`（该文件不入库）。

## 说明

- 知识库按 `user_id` 做租户隔离：上传时给切片打 `user_id` 与 `document_id` 标记，检索时按 `user_id` 过滤，删除时按 `document_id` 清理向量，用户之间无法互相检索或删除文档
- `.env` 已在 `.gitignore` 中忽略，请勿提交密钥
