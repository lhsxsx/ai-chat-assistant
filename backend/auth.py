"""认证模块：密码哈希 + JWT 签发/验证 + FastAPI 依赖项"""
import os
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_user_by_username

# JWT 密钥（从环境变量读取，默认值仅用于开发）
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production-please")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # token 有效期 7 天

# Bearer token 提取器
security = HTTPBearer(auto_error=False)


# ========== 密码哈希（pbkdf2_hmac + 随机盐） ==========
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """哈希密码，返回 (hash, salt)。若不提供 salt 则生成新的。"""
    if salt is None:
        salt = secrets.token_hex(16)
    # pbkdf2: 100000 轮，sha256，输出 32 字节
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000, dklen=32)
    return dk.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """验证密码是否匹配"""
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, password_hash)


# ========== JWT 签发/验证 ==========
def create_access_token(user_id: int, username: str) -> str:
    """签发 JWT token"""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解码 JWT，返回 payload 或 None"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ========== FastAPI 依赖项 ==========
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """要求请求携带有效 JWT，返回用户信息。
    用法：在路由参数中加 user: dict = Depends(get_current_user)
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息，请先登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证已过期或无效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
    }


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict | None:
    """可选认证：有 token 就解析，没有就返回 None（用于 chat 等公开接口）"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    return {
        "user_id": int(payload["sub"]),
        "username": payload["username"],
    }
