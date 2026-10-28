# AI Chat Assistant

[中文](README.md) | **English**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![LangChain](https://img.shields.io/badge/LangChain-1.x-1C3C3C?logo=langchain&logoColor=white)](https://python.langchain.com/)

A full-stack AI chat application built with FastAPI and React, offering three interaction modes: plain chat, RAG-based knowledge Q&A, and an Agent with tool calling.

## Why this project

Most AI app tutorials stop at calling an API from the frontend and concatenating the model's reply into a string. I wanted to dig into three things that matter in practice:

- **How streaming actually works end to end**: parsing SSE chunks as they arrive, handling events split across chunk boundaries, and letting users abort mid-generation
- **What each step of RAG is really doing**: how chunk size affects recall, how retrieved context is assembled into the prompt, and how cited sources make answers trustworthy
- **Whether an Agent's reasoning can be made visible**: if only the final answer is shown, users have no way to judge whether the conclusion is sound

So the three modes are implemented as independent pipelines on a shared frontend/backend architecture, with the focus on streaming communication, retrieval, and tool orchestration rather than on piling up features.

## Features

- **Streaming chat**: token-by-token push over SSE with a typewriter effect on the frontend and support for aborting generation
- **RAG knowledge Q&A**: upload PDF → split → embed → similarity search → context assembly, with sources cited in the answer
- **Agent**: LangChain tool calling (knowledge base retrieval / web search / current time) with the reasoning trace visualized in the UI
- **Multi-user support**: JWT authentication, conversations and messages scoped by `user_id`, chat history persisted in PostgreSQL

## Tech stack

| Layer | Technologies |
|---|---|
| Backend | FastAPI, SQLAlchemy, PostgreSQL, PyJWT, LangChain, Chroma |
| Frontend | React 19, TypeScript, Vite |
| Model | Zhipu GLM (OpenAI-compatible API) |

## Architecture

```
Browser ──> Vite dev server (/chat /rag /agent /upload /history /auth proxy)
              │
              └──> FastAPI ──> PostgreSQL (users / conversations / messages)
                        ├──> Chroma (vector store, isolated by user_id)
                        └──> Zhipu GLM API (chat + embeddings)
```

For production, the frontend build output in `frontend/dist` can be served by FastAPI's `StaticFiles`, giving a single-port deployment.

## Project layout

```
backend/
  main.py              app entry, CORS, route registration, static hosting
  auth.py              password hashing (pbkdf2), JWT issuing/verification
  database.py          ORM models (users / conversations / messages) and CRUD
  routers/             chat, rag, agent, upload, history, auth routes
  services/            agent_service.py (agent construction and streaming events)
frontend/
  src/App.tsx          main UI (mode switching, conversation list, knowledge base)
  src/useChatStream.ts streaming, conversation management, SSE parsing
  src/useAuth.ts       auth state and Authorization header injection
```

## Getting started

### 1. Start PostgreSQL

```bash
docker run -d --name ai-chat-pg \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ai_chat \
  -p 5432:5432 postgres:15
```

Tables are created automatically on the backend's first start.

### 2. Start the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

Create `backend/.env`:

```env
OPENAI_API_KEY=<your Zhipu API key>
OPENAI_API_BASE=https://open.bigmodel.cn/api/paas/v4/
MODEL_NAME=glm-4-flash
EMBEDDING_MODEL=embedding-3
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_chat
JWT_SECRET=<a random string>
```

Run:

```bash
uvicorn main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Notes

- The knowledge base is isolated per user: each chunk is tagged with `user_id` on upload and retrieval filters on that field, so users cannot search each other's private documents
- `.env` is listed in `.gitignore` — never commit your keys
