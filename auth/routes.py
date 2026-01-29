"""
认证模块 - API 路由

包含注册、登录、用户资料管理等接口
"""

import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from database import (
    get_db, create_user, authenticate_user, get_user_by_id,
    create_token
)
from .schemas import (
    UserCreate, UserLogin, UserProfile, UserProfileResponse,
    GRADE_OPTIONS
)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 静态数据目录
STATIC_DATA_DIR = Path(__file__).parent.parent / "static" / "data"


def require_auth(request):
    """
    从请求中获取并验证用户身份

    这是一个辅助函数，需要在 server.py 中实现依赖注入
    """
    pass  # 将在 server.py 中通过依赖注入实现


@router.post("/register")
async def api_register(data: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册

    接收完整的用户注册信息，创建新用户账号
    """
    # 创建用户
    user = create_user(
        db,
        username=data.username,
        password=data.password,
        email=data.email,
        grade=data.grade,
        school=data.school,
        age=data.age,
        province=data.province,
        city=data.city,
        phone=data.phone,
        parent_phone=data.parent_phone
    )

    if not user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 生成 JWT Token
    token = create_token(user.id, user.username)

    # 返回响应并设置 Cookie
    response = JSONResponse(content={
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "grade": user.grade
        }
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,  # 7天
        samesite="lax"
    )
    return response


@router.post("/login")
async def api_login(data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user.id, user.username)

    response = JSONResponse(content={
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "grade": user.grade
        }
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax"
    )
    return response


@router.get("/grades")
async def api_grades():
    """获取年级选项列表"""
    return {"grades": GRADE_OPTIONS}


@router.get("/regions")
async def api_regions():
    """获取省市数据"""
    regions_file = STATIC_DATA_DIR / "regions.json"
    if regions_file.exists():
        with open(regions_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"provinces": []}
