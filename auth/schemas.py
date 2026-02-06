"""
认证模块 - Pydantic 数据模型

定义请求和响应的数据结构
"""

from typing import Optional, List
from pydantic import BaseModel, validator
import re


class UserCreate(BaseModel):
    """用户注册请求模型"""
    # 必填字段
    username: str
    password: str
    age: int
    grade: str  # grade7/grade8/grade9/senior1/senior2/senior3
    school: str

    # 必填字段（省市）
    province: str
    city: str

    # 可选字段
    email: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None

    @validator("username")
    def username_valid(cls, v):
        if len(v) < 2:
            raise ValueError("用户名至少2个字符")
        if len(v) > 50:
            raise ValueError("用户名不能超过50个字符")
        return v

    @validator("password")
    def password_valid(cls, v):
        if len(v) < 4:
            raise ValueError("密码至少4个字符")
        return v

    @validator("age")
    def age_valid(cls, v):
        if v < 6 or v > 25:
            raise ValueError("年龄范围 6-25 岁")
        return v

    @validator("grade")
    def grade_valid(cls, v):
        valid_grades = ["grade7", "grade8", "grade9", "senior1", "senior2", "senior3"]
        if v not in valid_grades:
            raise ValueError("无效的年级")
        return v

    @validator("school")
    def school_valid(cls, v):
        if not v or len(v) < 2:
            raise ValueError("学校名称至少2个字符")
        return v

    @validator("province")
    def province_valid(cls, v):
        if not v or len(v) < 2:
            raise ValueError("请选择省份")
        return v

    @validator("city")
    def city_valid(cls, v):
        if not v or len(v) < 2:
            raise ValueError("请选择城市")
        return v



class UserLogin(BaseModel):
    """用户登录请求模型"""
    username: str
    password: str


class UserProfile(BaseModel):
    """用户资料模型（用于查看和更新）"""
    username: Optional[str] = None
    email: Optional[str] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    age: Optional[int] = None
    province: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None


class UserProfileResponse(BaseModel):
    """用户资料响应模型"""
    id: int
    username: str
    email: Optional[str] = None
    grade: Optional[str] = None
    school: Optional[str] = None
    age: Optional[int] = None
    province: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    parent_phone: Optional[str] = None
    created_at: Optional[str] = None


# 年级选项
GRADE_OPTIONS = [
    {"id": "grade7", "name": "七年级（初一）"},
    {"id": "grade8", "name": "八年级（初二）"},
    {"id": "grade9", "name": "九年级（初三）"},
    {"id": "senior1", "name": "高一"},
    {"id": "senior2", "name": "高二"},
    {"id": "senior3", "name": "高三"},
]

