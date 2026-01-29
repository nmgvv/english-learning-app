"""
认证模块

包含用户注册、登录、资料管理等功能
"""

from .routes import router as auth_router
from .schemas import UserCreate, UserProfile, UserLogin

__all__ = ["auth_router", "UserCreate", "UserProfile", "UserLogin"]
