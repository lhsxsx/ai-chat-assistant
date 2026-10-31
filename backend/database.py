"""PostgreSQL 数据库模块：存储对话会话与消息。

表结构：
- users: 用户（id, username, password_hash, salt, created_at）
- conversations: 会话（id, user_id, title, mode, created_at, updated_at）
- messages: 消息（id, conversation_id, role, content, sources_json, created_at）
- documents: 知识库文档（id, user_id, filename, chunks_count, pages, created_at）
"""
import os
import json
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# PostgreSQL 数据库连接配置
# 格式: postgresql://用户名:密码@主机:端口/数据库名
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ai_chat"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 自动检测连接是否有效
    pool_size=5,         # 连接池大小
    max_overflow=10,     # 最大溢出连接数
    echo=False,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)  # pbkdf2 哈希
    salt = Column(String(64), nullable=False)  # 盐
    created_at = Column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(200), nullable=False, default="新对话")
    mode = Column(String(20), nullable=False, default="chat")  # chat / rag / agent
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.id"
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)  # user / assistant
    content = Column(Text, nullable=False, default="")
    sources_json = Column(Text, nullable=True)  # RAG 来源信息的 JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "sources": json.loads(self.sources_json) if self.sources_json else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Document(Base):
    """知识库文档：记录用户上传过哪些 PDF，用于列表展示与按用户删除。

    向量切片存在 Chroma 中，metadata 里带上 document_id，删除时按此清理。
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)  # 原始文件名（不含路径）
    chunks_count = Column(Integer, nullable=False, default=0)  # 切片数量
    pages = Column(Integer, nullable=False, default=0)  # 页数
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.filename,
            "chunks": self.chunks_count,
            "pages": self.pages,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# 首次导入时自动建表
Base.metadata.create_all(engine)


@contextmanager
def get_db():
    """获取数据库会话的上下文管理器"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ========== User CRUD ==========
def get_user_by_username(username: str) -> dict | None:
    """根据用户名查询用户"""
    with get_db() as db:
        u = db.query(User).filter(User.username == username).first()
        if u is None:
            return None
        return {
            "id": u.id,
            "username": u.username,
            "password_hash": u.password_hash,
            "salt": u.salt,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }


def create_user(username: str, password_hash: str, salt: str) -> dict:
    """创建用户"""
    with get_db() as db:
        u = User(username=username, password_hash=password_hash, salt=salt)
        db.add(u)
        db.flush()
        return {
            "id": u.id,
            "username": u.username,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }


# ========== Conversation CRUD（均带 user_id 隔离） ==========
def create_conversation_dict(user_id: int, mode: str = "chat", title: str | None = None) -> dict:
    """创建新会话，返回 dict。会话绑定到指定 user_id。"""
    with get_db() as db:
        conv = Conversation(user_id=user_id, mode=mode, title=title or "新对话")
        db.add(conv)
        db.flush()
        result = {
            "id": conv.id,
            "title": conv.title,
            "mode": conv.mode,
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
        }
        return result


def list_conversations(user_id: int, limit: int = 100) -> list[dict]:
    """列出某用户的会话（按更新时间倒序）。只返回该 user_id 的会话。"""
    with get_db() as db:
        convs = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": c.id,
                "title": c.title,
                "mode": c.mode,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            }
            for c in convs
        ]


def get_conversation_messages(conversation_id: int, user_id: int) -> list[dict] | None:
    """获取某会话的所有消息。若会话不属于该 user_id 则返回 None。"""
    with get_db() as db:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if conv is None:
            return None
        return [m.to_dict() for m in conv.messages]


def add_message(
    conversation_id: int,
    role: str,
    content: str,
    sources: list[str] | None = None,
    user_id: int | None = None,
) -> dict | None:
    """向会话追加一条消息。若提供 user_id，会校验该会话是否属于此用户。"""
    with get_db() as db:
        query = db.query(Conversation).filter(Conversation.id == conversation_id)
        if user_id is not None:
            query = query.filter(Conversation.user_id == user_id)
        conv = query.first()
        if conv is None:
            return None
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources_json=json.dumps(sources, ensure_ascii=False) if sources else None,
        )
        db.add(msg)
        conv.updated_at = datetime.utcnow()
        # 第一条用户消息作为会话标题
        if role == "user" and conv.title == "新对话":
            conv.title = content[:30] + ("…" if len(content) > 30 else "")
        db.flush()
        return msg.to_dict()


def delete_conversation(conversation_id: int, user_id: int) -> bool:
    """删除会话。若会话不属于该 user_id 则返回 False。"""
    with get_db() as db:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if conv is None:
            return False
        db.delete(conv)
        return True


def rename_conversation(conversation_id: int, user_id: int, title: str) -> dict | None:
    """重命名会话。若会话不属于该 user_id 则返回 None。"""
    with get_db() as db:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if conv is None:
            return None
        conv.title = title
        db.flush()
        return {
            "id": conv.id,
            "title": conv.title,
            "mode": conv.mode,
        }


def get_recent_messages(conversation_id: int, user_id: int, limit: int = 6) -> list[dict]:
    """取某会话最近 limit 条消息（按时间正序返回），用于给 RAG 提供多轮上下文。

    会话不属于该 user_id 时返回空列表。
    """
    with get_db() as db:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
            .first()
        )
        if conv is None:
            return []
        recent = (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
            .all()
        )
        return [{"role": m.role, "content": m.content} for m in reversed(recent)]


# ========== Document CRUD（均带 user_id 隔离） ==========
def create_document(user_id: int, filename: str, chunks_count: int, pages: int) -> dict:
    """登记一份上传的文档，返回包含 id 的 dict（向量切片需带上该 id）。"""
    with get_db() as db:
        doc = Document(
            user_id=user_id,
            filename=filename,
            chunks_count=chunks_count,
            pages=pages,
        )
        db.add(doc)
        db.flush()
        return doc.to_dict()


def list_documents(user_id: int) -> list[dict]:
    """列出某用户上传的文档（按上传时间倒序）。"""
    with get_db() as db:
        docs = (
            db.query(Document)
            .filter(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .all()
        )
        return [d.to_dict() for d in docs]


def delete_document(document_id: int, user_id: int) -> dict | None:
    """删除文档记录。不属于该用户时返回 None，成功则返回被删文档信息。"""
    with get_db() as db:
        doc = (
            db.query(Document)
            .filter(Document.id == document_id, Document.user_id == user_id)
            .first()
        )
        if doc is None:
            return None
        result = doc.to_dict()
        db.delete(doc)
        return result
