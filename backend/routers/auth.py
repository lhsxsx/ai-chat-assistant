from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from database import get_user_by_username, create_user
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("用户名至少 2 个字符")
        if len(v) > 20:
            raise ValueError("用户名最多 20 个字符")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码至少 6 个字符")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest):
    """注册新用户"""
    # 检查用户名是否已存在
    existing = get_user_by_username(req.username)
    if existing is not None:
        raise HTTPException(400, detail="用户名已被占用")

    # 哈希密码
    password_hash, salt = hash_password(req.password)

    # 创建用户
    user = create_user(req.username, password_hash, salt)

    # 签发 token
    token = create_access_token(user["id"], user["username"])
    return {
        "message": "注册成功",
        "token": token,
        "user": user,
    }


@router.post("/login")
async def login(req: LoginRequest):
    """登录"""
    user = get_user_by_username(req.username)
    if user is None:
        raise HTTPException(401, detail="用户名或密码错误")

    if not verify_password(req.password, user["password_hash"], user["salt"]):
        raise HTTPException(401, detail="用户名或密码错误")

    token = create_access_token(user["id"], user["username"])
    return {
        "message": "登录成功",
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
        },
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息（需要 token）"""
    return {"user": user}
