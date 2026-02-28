"""
数据库模型和用户认证模块

包含:
- SQLAlchemy 模型定义 (User, Progress, History)
- 数据库连接和初始化
- JWT Token 生成和验证
- 密码哈希工具
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime, ForeignKey, UniqueConstraint, func, case
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# JWT 相关
import hashlib
import hmac
import base64

# 项目路径
PROJECT_ROOT = Path(__file__).parent
DATABASE_PATH = PROJECT_ROOT / "data" / "app.db"

# 创建数据库引擎
engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# JWT 密钥（生产环境应从环境变量读取）
JWT_SECRET = os.getenv("JWT_SECRET", "english-learning-app-secret-key-2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24 * 7  # 7天过期


# ==================== 数据库模型 ====================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # ========== 扩展字段（注册信息） ==========
    # 学习信息
    grade = Column(String(20), nullable=True)  # 年级: grade7/grade8/grade9/senior1/senior2/senior3
    school = Column(String(100), nullable=True)  # 学校名称

    # 个人信息
    age = Column(Integer, nullable=True)  # 年龄
    province = Column(String(50), nullable=True)  # 省份
    city = Column(String(50), nullable=True)  # 城市
    phone = Column(String(20), nullable=True)  # 手机号
    parent_phone = Column(String(20), nullable=True)  # 家长联系方式
    weak_areas = Column(String(100), nullable=True)  # 薄弱项 JSON: ["listening","speaking","reading","writing"]

    # 关系
    progress = relationship("Progress", back_populates="user")
    history = relationship("History", back_populates="user")


class Progress(Base):
    """学习进度表 - FSRS 状态"""
    __tablename__ = "progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    book_id = Column(String(50), nullable=False)
    word = Column(String(100), nullable=False)

    # FSRS 状态
    difficulty = Column(Float, default=0.0)
    stability = Column(Float, default=0.0)
    state = Column(Integer, default=0)  # 0=新卡, 1=学习中, 2=复习中
    reps = Column(Integer, default=0)
    lapses = Column(Integer, default=0)
    last_review = Column(DateTime, nullable=True)
    due = Column(DateTime, nullable=True)

    # 唯一约束
    __table_args__ = (
        UniqueConstraint('user_id', 'book_id', 'word', name='uix_user_book_word'),
    )

    # 关系
    user = relationship("User", back_populates="progress")


class History(Base):
    """学习历史表"""
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    book_id = Column(String(50), nullable=False)
    word = Column(String(100), nullable=False)

    time = Column(DateTime, nullable=False, default=datetime.utcnow)
    inputs = Column(Text, nullable=True)  # JSON 数组
    result = Column(String(20), nullable=True)  # correct/wrong/skipped
    attempts = Column(Integer, default=0)
    grade = Column(Integer, default=0)  # FSRS 评分 1-4

    # 关系
    user = relationship("User", back_populates="history")


class StudySession(Base):
    """学习会话表 - 记录每次学习的会话级别数据"""
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, default=0)
    mode = Column(String(20), nullable=True)
    book_id = Column(String(50), nullable=True)
    total_words = Column(Integer, default=0)
    first_correct = Column(Integer, default=0)
    second_correct = Column(Integer, default=0)
    third_correct = Column(Integer, default=0)
    wrong_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    best_streak = Column(Integer, default=0)

    user = relationship("User")


class PronunciationRecord(Base):
    """发音评估记录表"""
    __tablename__ = "pronunciation_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    book_id = Column(String(50), nullable=False)
    word = Column(String(100), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 音频存储路径（相对于 static/recordings/）
    audio_path = Column(String(255), nullable=True)

    # 评分 (0-100)
    accuracy_score = Column(Float, nullable=True)
    pronunciation_score = Column(Float, nullable=True)
    fluency_score = Column(Float, nullable=True)
    completeness_score = Column(Float, nullable=True)

    # 识别出的文本
    recognized_text = Column(String(255), nullable=True)

    # 音素详情 (JSON)
    # 格式: [{"phoneme": "h", "accuracy": 95, "error_type": "None"}, ...]
    phoneme_details = Column(Text, nullable=True)

    # 关系
    user = relationship("User")


class PhonemeError(Base):
    """音素错误汇总表 - 用于分析薄弱发音"""
    __tablename__ = "phoneme_errors"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 音素（IPA 格式）
    phoneme = Column(String(10), nullable=False, index=True)

    # 统计数据
    total_attempts = Column(Integer, default=0)      # 总尝试次数
    error_count = Column(Integer, default=0)         # 错误次数
    avg_accuracy = Column(Float, default=0.0)        # 平均准确度

    # 错误类型统计 (JSON)
    # 格式: {"Mispronunciation": 5, "Omission": 2, "Insertion": 1}
    error_types = Column(Text, default="{}")

    # 最后更新时间
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 唯一约束
    __table_args__ = (
        UniqueConstraint('user_id', 'phoneme', name='uix_user_phoneme'),
    )

    # 关系
    user = relationship("User")


class ConfusingWords(Base):
    """混淆词对缓存表 - 存储大模型生成的混淆词"""
    __tablename__ = "confusing_words"

    id = Column(Integer, primary_key=True, index=True)
    word = Column(String(100), unique=True, nullable=False, index=True)
    confusing = Column(Text, nullable=False)  # JSON: ["effect", "efficient", "afford"]
    created_at = Column(DateTime, default=datetime.utcnow)


class ConfusionRecord(Base):
    """学生混淆记录表 - 记录容易选错的单词"""
    __tablename__ = "confusion_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    correct_word = Column(String(100), nullable=False)  # 正确答案
    selected_word = Column(String(100), nullable=False)  # 学生选择的错误答案
    count = Column(Integer, default=1)  # 混淆次数
    last_confused = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'correct_word', 'selected_word', name='uix_confusion'),
    )

    # 关系
    user = relationship("User")


# ==================== 数据库初始化 ====================

def init_db():
    """初始化数据库，创建所有表"""
    # 确保 data 目录存在
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    # 执行迁移，添加新字段
    migrate_user_table()
    # 创建 study_sessions 表（如不存在）
    Base.metadata.create_all(bind=engine, tables=[StudySession.__table__])
    # 创建快速摸底相关表（如不存在）
    Base.metadata.create_all(bind=engine, tables=[ConfusingWords.__table__, ConfusionRecord.__table__])
    # 一次性修正 FSRS due 日期
    migrate_fix_fsrs_due()


def migrate_user_table():
    """
    迁移 users 表，添加新字段（如果不存在）

    用于兼容已有用户数据，新字段全部为 nullable
    """
    from sqlalchemy import text

    new_columns = [
        ("grade", "VARCHAR(20)"),
        ("school", "VARCHAR(100)"),
        ("age", "INTEGER"),
        ("province", "VARCHAR(50)"),
        ("city", "VARCHAR(50)"),
        ("phone", "VARCHAR(20)"),
        ("parent_phone", "VARCHAR(20)"),
        ("weak_areas", "VARCHAR(100)"),
    ]

    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                conn.commit()
            except Exception:
                # 列已存在，忽略错误
                pass


def migrate_fix_fsrs_due():
    """一次性修正：用正确的 FSRS 公式重算所有 due 日期"""
    from dictation import next_interval

    db = SessionLocal()
    try:
        records = db.query(Progress).filter(
            Progress.last_review.isnot(None),
            Progress.stability > 0
        ).all()

        updated = 0
        for p in records:
            new_interval = next_interval(p.stability)
            new_due = p.last_review + timedelta(days=new_interval)
            if p.due != new_due:
                p.due = new_due
                updated += 1

        if updated > 0:
            db.commit()
            print(f"[迁移] 已修正 {updated}/{len(records)} 条记录的 due 日期")
    finally:
        db.close()


def get_db():
    """获取数据库会话（用于依赖注入）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== 密码哈希 ====================

def hash_password(password: str) -> str:
    """
    使用 SHA256 + salt 哈希密码

    生产环境建议使用 bcrypt 或 argon2
    """
    salt = "english-learning-salt"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码"""
    return hash_password(password) == password_hash


# ==================== JWT Token ====================

def base64url_encode(data: bytes) -> str:
    """Base64 URL 安全编码"""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')


def base64url_decode(data: str) -> bytes:
    """Base64 URL 安全解码"""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += '=' * padding
    return base64.urlsafe_b64decode(data)


def create_token(user_id: int, username: str) -> str:
    """
    创建 JWT Token

    Args:
        user_id: 用户 ID
        username: 用户名

    Returns:
        JWT Token 字符串
    """
    # Header
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_b64 = base64url_encode(json.dumps(header).encode())

    # Payload
    now = datetime.utcnow()
    payload = {
        "user_id": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp())
    }
    payload_b64 = base64url_encode(json.dumps(payload).encode())

    # Signature
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        JWT_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    signature_b64 = base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def verify_token(token: str) -> Optional[dict]:
    """
    验证 JWT Token

    Args:
        token: JWT Token 字符串

    Returns:
        解码后的 payload，验证失败返回 None
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts

        # 验证签名
        message = f"{header_b64}.{payload_b64}"
        expected_signature = hmac.new(
            JWT_SECRET.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        actual_signature = base64url_decode(signature_b64)
        if not hmac.compare_digest(expected_signature, actual_signature):
            return None

        # 解码 payload
        payload = json.loads(base64url_decode(payload_b64))

        # 检查过期
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            return None

        return payload

    except Exception:
        return None


# ==================== 用户操作 ====================

def create_user(
    db: Session,
    username: str,
    password: str,
    email: str = None,
    grade: str = None,
    school: str = None,
    age: int = None,
    province: str = None,
    city: str = None,
    phone: str = None,
    parent_phone: str = None
) -> Optional[User]:
    """
    创建新用户

    Args:
        db: 数据库会话
        username: 用户名
        password: 明文密码
        email: 邮箱（必填）
        grade: 年级（必填）
        school: 学校名称（必填）
        age: 年龄（可选）
        province: 省份（可选）
        city: 城市（可选）
        phone: 手机号（可选）
        parent_phone: 家长联系方式（可选）

    Returns:
        创建的用户对象，失败返回 None
    """
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return None

    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email,
        grade=grade,
        school=school,
        age=age,
        province=province,
        city=city,
        phone=phone,
        parent_phone=parent_phone
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """
    验证用户登录

    Args:
        db: 数据库会话
        username: 用户名
        password: 明文密码

    Returns:
        验证成功返回用户对象，失败返回 None
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    db.commit()

    return user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """根据 ID 获取用户"""
    return db.query(User).filter(User.id == user_id).first()


# ==================== 进度操作 ====================

def get_user_progress(db: Session, user_id: int, book_id: str) -> List[Progress]:
    """获取用户在某本词书的学习进度"""
    return db.query(Progress).filter(
        Progress.user_id == user_id,
        Progress.book_id == book_id
    ).all()


def get_word_progress(db: Session, user_id: int, book_id: str, word: str) -> Optional[Progress]:
    """获取用户对某个单词的学习进度"""
    return db.query(Progress).filter(
        Progress.user_id == user_id,
        Progress.book_id == book_id,
        Progress.word == word
    ).first()


def update_progress(db: Session, user_id: int, book_id: str, word: str,
                   difficulty: float, stability: float, state: int,
                   reps: int, lapses: int, last_review: datetime, due: datetime) -> Progress:
    """更新或创建学习进度"""
    progress = get_word_progress(db, user_id, book_id, word)

    if progress:
        progress.difficulty = difficulty
        progress.stability = stability
        progress.state = state
        progress.reps = reps
        progress.lapses = lapses
        progress.last_review = last_review
        progress.due = due
    else:
        progress = Progress(
            user_id=user_id,
            book_id=book_id,
            word=word,
            difficulty=difficulty,
            stability=stability,
            state=state,
            reps=reps,
            lapses=lapses,
            last_review=last_review,
            due=due
        )
        db.add(progress)

    db.commit()
    db.refresh(progress)
    return progress


MAX_DAILY_REVIEWS = 100  # 每日最大复习量


def get_due_cards(db: Session, user_id: int, book_id: str = None) -> List[Progress]:
    """获取今日待复习的单词（全局或指定词书）

    分档 + 随机目标 + 逐档拉取：
    1. 每日随机一个复习目标数量（40-70），避免学生产生惰性
    2. 所有已学单词按 due 日期升序排列（最紧急在前）
    3. 从最紧急的开始拉取，直到达到目标数量
    4. 超过上限时截断
    """
    import random
    now = datetime.utcnow()

    # 随机每日目标（40-70），避免每天复习量一致
    daily_target = random.randint(40, 70)

    # 获取所有已学单词，按 due 升序（最紧急→最不紧急）
    query = db.query(Progress).filter(
        Progress.user_id == user_id,
        Progress.state >= 1  # 排除新卡（state=0）
    )

    if book_id:
        query = query.filter(Progress.book_id == book_id)

    all_cards = query.order_by(Progress.due.asc()).all()

    # 从最紧急的开始取，直到达到目标或上限
    target = min(daily_target, MAX_DAILY_REVIEWS, len(all_cards))
    result = all_cards[:target]

    # 打乱顺序（防止学生从顺序猜到难度档位）
    random.shuffle(result)
    return result


# ==================== 历史记录操作 ====================

def add_history(db: Session, user_id: int, book_id: str, word: str,
               inputs: List[str], result: str, attempts: int, grade: int) -> History:
    """添加学习历史记录"""
    history = History(
        user_id=user_id,
        book_id=book_id,
        word=word,
        time=datetime.utcnow(),
        inputs=json.dumps(inputs, ensure_ascii=False),
        result=result,
        attempts=attempts,
        grade=grade
    )
    db.add(history)
    db.commit()
    db.refresh(history)
    return history


def get_word_history(db: Session, user_id: int, book_id: str, word: str) -> List[History]:
    """获取某个单词的学习历史"""
    return db.query(History).filter(
        History.user_id == user_id,
        History.book_id == book_id,
        History.word == word
    ).order_by(History.time.desc()).all()


def get_difficulty_coefficient(db: Session, user_id: int, book_id: str, word: str) -> float:
    """根据近期复习历史的错误率计算难度系数，用于调整复习间隔

    系数范围 0.5-1.0：
    - 错误率 0% → 1.0（无调整）
    - 错误率 30% → 0.85（间隔缩短15%）
    - 错误率 50% → 0.75（间隔缩短25%）
    - 错误率 100% → 0.5（间隔缩短50%）
    """
    history = get_word_history(db, user_id, book_id, word)
    recent = history[:10]  # 最近10次复习记录

    if len(recent) < 3:
        return 1.0  # 数据不足，不调整

    error_count = sum(1 for h in recent if h.result != "correct")
    error_rate = error_count / len(recent)

    return max(0.5, 1.0 - error_rate * 0.5)


def get_words_history_stats(db: Session, user_id: int, words_with_books: List[tuple]) -> dict:
    """批量获取多个单词的学习历史统计

    Args:
        db: 数据库会话
        user_id: 用户ID
        words_with_books: [(book_id, word), ...] 单词和词书ID对的列表

    Returns:
        {(book_id, word): {"total": N, "correct": M, "wrong": Y}, ...}
    """
    if not words_with_books:
        return {}

    # 使用 SQL 聚合一次性查询所有单词的统计
    query = db.query(
        History.book_id,
        History.word,
        func.count(History.id).label("total"),
        func.sum(case((History.result == "correct", 1), else_=0)).label("correct"),
        func.sum(case((History.result == "wrong", 1), else_=0)).label("wrong"),
        func.sum(case((History.result == "skipped", 1), else_=0)).label("skipped")
    ).filter(
        History.user_id == user_id
    ).group_by(History.book_id, History.word)

    # 构建结果字典
    result = {}
    words_set = set(words_with_books)
    for row in query.all():
        key = (row.book_id, row.word)
        if key in words_set:
            result[key] = {
                "total": row.total or 0,
                "correct": int(row.correct or 0),
                "wrong": int(row.wrong or 0),
                "skipped": int(row.skipped or 0)
            }

    return result


def get_user_stats(db: Session, user_id: int, book_id: str = None) -> dict:
    """获取用户学习统计（使用 SQL 聚合优化）"""
    # 使用 SQL COUNT 和 CASE 进行单次查询统计
    query = db.query(
        func.count(History.id).label("total"),
        func.sum(case((History.result == "correct", 1), else_=0)).label("correct"),
        func.sum(case((History.result == "wrong", 1), else_=0)).label("wrong"),
        func.sum(case((History.result == "skipped", 1), else_=0)).label("skipped")
    ).filter(History.user_id == user_id)

    if book_id:
        query = query.filter(History.book_id == book_id)

    result = query.first()
    total = result.total or 0
    correct = result.correct or 0
    wrong = result.wrong or 0
    skipped = result.skipped or 0

    # 获取学习过的单词数
    progress_query = db.query(func.count(Progress.id)).filter(Progress.user_id == user_id)
    if book_id:
        progress_query = progress_query.filter(Progress.book_id == book_id)
    words_learned = progress_query.scalar() or 0

    return {
        "total_reviews": total,
        "correct": correct,
        "wrong": wrong,
        "skipped": skipped,
        "accuracy": round(correct / total * 100, 1) if total > 0 else 0,
        "words_learned": words_learned
    }


def get_global_mastered_curve(db: Session, user_id: int, days: int = 7) -> dict:
    """获取全局掌握单词数曲线（跨所有词书），按尝试次数分三条线

    分类逻辑（互斥，按最近一次正确的尝试次数归类）：
    - 一次正确(attempts=1) → set_1st，从 set_2nd/set_3rd 移除
    - 二次正确(attempts=2) → set_2nd，从 set_1st/set_3rd 移除
    - 三次正确(attempts=3) → set_3rd，从 set_1st/set_2nd 移除
    - 答错 → 从所有集合移除

    Returns:
        {"dates": [...], "counts_1st": [...], "counts_2nd": [...], "counts_3rd": [...], "total": N}
    """
    from datetime import timedelta
    from collections import defaultdict

    records = db.query(History).filter(
        History.user_id == user_id
    ).order_by(History.time.asc()).all()

    if not records:
        return {"dates": [], "counts_1st": [], "counts_2nd": [], "counts_3rd": [], "total": 0}

    def _update_sets(set_1st, set_2nd, set_3rd, word, result, attempts):
        if result == "correct" and attempts == 1:
            set_1st.add(word)
            set_2nd.discard(word)
            set_3rd.discard(word)
        elif result == "correct" and attempts == 2:
            set_2nd.add(word)
            set_1st.discard(word)
            set_3rd.discard(word)
        elif result == "correct" and attempts == 3:
            set_3rd.add(word)
            set_1st.discard(word)
            set_2nd.discard(word)
        elif result == "wrong":
            set_1st.discard(word)
            set_2nd.discard(word)
            set_3rd.discard(word)

    set_1st, set_2nd, set_3rd = set(), set(), set()
    daily_1st = defaultdict(int)
    daily_2nd = defaultdict(int)
    daily_3rd = defaultdict(int)

    for r in records:
        _update_sets(set_1st, set_2nd, set_3rd, r.word, r.result, r.attempts)
        ds = r.time.strftime("%m-%d")
        daily_1st[ds] = len(set_1st)
        daily_2nd[ds] = len(set_2nd)
        daily_3rd[ds] = len(set_3rd)

    if days > 0:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)

        # 重算：先算 start_date 之前的基准
        set_1st, set_2nd, set_3rd = set(), set(), set()
        for r in records:
            if r.time.date() < start_date:
                _update_sets(set_1st, set_2nd, set_3rd, r.word, r.result, r.attempts)
        last_1st, last_2nd, last_3rd = len(set_1st), len(set_2nd), len(set_3rd)

        # 再算范围内的数据
        s1, s2, s3 = set_1st.copy(), set_2nd.copy(), set_3rd.copy()
        daily_1st, daily_2nd, daily_3rd = defaultdict(int), defaultdict(int), defaultdict(int)
        for r in records:
            if r.time.date() >= start_date:
                _update_sets(s1, s2, s3, r.word, r.result, r.attempts)
                ds = r.time.strftime("%m-%d")
                daily_1st[ds] = len(s1)
                daily_2nd[ds] = len(s2)
                daily_3rd[ds] = len(s3)

        dates, c1, c2, c3 = [], [], [], []
        current_date = start_date
        while current_date <= end_date:
            ds = current_date.strftime("%m-%d")
            if ds in daily_1st:
                last_1st, last_2nd, last_3rd = daily_1st[ds], daily_2nd[ds], daily_3rd[ds]
            dates.append(ds)
            c1.append(last_1st)
            c2.append(last_2nd)
            c3.append(last_3rd)
            current_date += timedelta(days=1)

        return {
            "dates": dates, "counts_1st": c1, "counts_2nd": c2, "counts_3rd": c3,
            "total": len(s1) + len(s2) + len(s3)
        }

    dates = list(daily_1st.keys())
    return {
        "dates": dates,
        "counts_1st": list(daily_1st.values()),
        "counts_2nd": list(daily_2nd.values()),
        "counts_3rd": list(daily_3rd.values()),
        "total": len(set_1st) + len(set_2nd) + len(set_3rd)
    }


# ==================== 学习会话操作 ====================

def add_study_session(db: Session, user_id: int, started_at: datetime,
                      ended_at: datetime, duration_ms: int, mode: str,
                      book_id: str, total_words: int, first_correct: int,
                      second_correct: int, third_correct: int,
                      wrong_count: int, skipped_count: int,
                      best_streak: int) -> StudySession:
    """保存学习会话记录"""
    record = StudySession(
        user_id=user_id,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        mode=mode,
        book_id=book_id,
        total_words=total_words,
        first_correct=first_correct,
        second_correct=second_correct,
        third_correct=third_correct,
        wrong_count=wrong_count,
        skipped_count=skipped_count,
        best_streak=best_streak
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_learning_stats(db: Session, user_id: int, period: str = "day") -> dict:
    """获取学习统计（按时段聚合）

    Args:
        period: "day" / "week" / "month" / "year"

    Returns:
        包含学习时长、单词数、正确率分布、词书分布、每日明细的字典
    """
    from sqlalchemy import text
    from bookmanager import get_book_display_name

    now = datetime.utcnow() + timedelta(hours=8)  # 转为北京时间
    today = now.date()

    if period == "day":
        start_date = today
    elif period == "week":
        start_date = today - timedelta(days=today.weekday())  # 本周一
    elif period == "month":
        start_date = today.replace(day=1)
    elif period == "year":
        start_date = today.replace(month=1, day=1)
    else:
        start_date = today

    # 转为 UTC 时间范围（北京时间 00:00 = UTC 前一天 16:00）
    start_utc = datetime(start_date.year, start_date.month, start_date.day) - timedelta(hours=8)
    end_utc = datetime(today.year, today.month, today.day, 23, 59, 59) - timedelta(hours=8)

    # 1. 从 history 表聚合
    hist_query = db.query(
        func.count(History.id).label("total"),
        func.sum(case((History.result == "correct", 1), else_=0)).label("correct"),
        func.sum(case(((History.result == "correct") & (History.attempts == 1), 1), else_=0)).label("first"),
        func.sum(case(((History.result == "correct") & (History.attempts == 2), 1), else_=0)).label("second"),
        func.sum(case(((History.result == "correct") & (History.attempts == 3), 1), else_=0)).label("third"),
        func.sum(case((History.result == "wrong", 1), else_=0)).label("wrong"),
        func.sum(case((History.result == "skipped", 1), else_=0)).label("skipped"),
    ).filter(
        History.user_id == user_id,
        History.time >= start_utc,
        History.time <= end_utc
    )
    hr = hist_query.first()

    total_words = hr.total or 0
    correct = int(hr.correct or 0)
    first_correct = int(hr.first or 0)
    second_correct = int(hr.second or 0)
    third_correct = int(hr.third or 0)
    wrong_count = int(hr.wrong or 0)
    skipped_count = int(hr.skipped or 0)
    accuracy = round(correct / total_words * 100, 1) if total_words > 0 else 0

    # 2. 从 study_sessions 表聚合
    sess_query = db.query(
        func.sum(StudySession.duration_ms).label("total_ms"),
        func.count(StudySession.id).label("count"),
        func.max(StudySession.best_streak).label("best_streak")
    ).filter(
        StudySession.user_id == user_id,
        StudySession.started_at >= start_utc,
        StudySession.started_at <= end_utc
    )
    sr = sess_query.first()
    study_time_ms = int(sr.total_ms or 0)
    sessions_count = sr.count or 0
    best_streak = sr.best_streak or 0

    # 3. 词书分布
    book_rows = db.query(
        History.book_id,
        func.count(History.id).label("total"),
        func.sum(case((History.result == "correct", 1), else_=0)).label("correct")
    ).filter(
        History.user_id == user_id,
        History.time >= start_utc,
        History.time <= end_utc
    ).group_by(History.book_id).all()

    book_breakdown = []
    for row in book_rows:
        bt = row.total or 0
        bc = int(row.correct or 0)
        book_breakdown.append({
            "book_id": row.book_id,
            "book_name": get_book_display_name(row.book_id),
            "words": bt,
            "accuracy": round(bc / bt * 100, 1) if bt > 0 else 0
        })

    # 4. 每日明细（周/月/年时提供）
    daily_breakdown = []
    if period != "day":
        # 用原生 SQL 按北京时间日期分组
        daily_hist = db.execute(text("""
            SELECT DATE(time, '+8 hours') as day,
                   COUNT(*) as total,
                   SUM(CASE WHEN result='correct' THEN 1 ELSE 0 END) as correct
            FROM history
            WHERE user_id = :uid AND time >= :start AND time <= :end
            GROUP BY day ORDER BY day
        """), {"uid": user_id, "start": start_utc, "end": end_utc}).fetchall()

        daily_sess = {}
        for row in db.execute(text("""
            SELECT DATE(started_at, '+8 hours') as day,
                   SUM(duration_ms) as ms
            FROM study_sessions
            WHERE user_id = :uid AND started_at >= :start AND started_at <= :end
            GROUP BY day
        """), {"uid": user_id, "start": start_utc, "end": end_utc}).fetchall():
            daily_sess[row[0]] = int(row[1] or 0)

        for row in daily_hist:
            day_str = row[0]
            dt = row[1] or 0
            dc = int(row[2] or 0)
            daily_breakdown.append({
                "date": day_str[5:] if len(day_str) > 5 else day_str,  # MM-DD
                "words": dt,
                "accuracy": round(dc / dt * 100, 1) if dt > 0 else 0,
                "study_time_ms": daily_sess.get(day_str, 0)
            })

    return {
        "study_time_ms": study_time_ms,
        "sessions_count": sessions_count,
        "total_words": total_words,
        "first_correct": first_correct,
        "second_correct": second_correct,
        "third_correct": third_correct,
        "wrong_count": wrong_count,
        "skipped_count": skipped_count,
        "accuracy": accuracy,
        "best_streak": best_streak,
        "book_breakdown": book_breakdown,
        "daily_breakdown": daily_breakdown
    }


def get_weak_words(db: Session, user_id: int, limit: int = 20) -> list:
    """获取薄弱单词列表（基于 FSRS 评估：遗忘过的单词按难度排序）"""
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT book_id, word, difficulty, stability, lapses, state, reps
        FROM progress
        WHERE user_id = :uid
          AND lapses > 0
        ORDER BY difficulty DESC, lapses DESC, stability ASC
        LIMIT :lim
    """), {"uid": user_id, "lim": limit}).fetchall()

    return [
        {
            "word": row[1],
            "book_id": row[0],
            "difficulty": round(row[2], 1),
            "stability": round(row[3], 1),
            "lapses": row[4],
            "state": row[5],
            "reps": row[6]
        }
        for row in rows
    ]


def get_learning_streak(db: Session, user_id: int) -> dict:
    """获取连续学习天数"""
    from sqlalchemy import text

    rows = db.execute(text("""
        SELECT DISTINCT DATE(time, '+8 hours') as day
        FROM history
        WHERE user_id = :uid
        ORDER BY day DESC
    """), {"uid": user_id}).fetchall()

    if not rows:
        return {"current_streak": 0, "longest_streak": 0}

    days = [row[0] for row in rows]
    today = (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d")

    # 当前连续天数
    current_streak = 0
    check_date = today
    for d in days:
        if d == check_date:
            current_streak += 1
            check_date = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            break

    # 最长连续天数
    longest = 1
    streak = 1
    for i in range(1, len(days)):
        prev = datetime.strptime(days[i - 1], "%Y-%m-%d")
        curr = datetime.strptime(days[i], "%Y-%m-%d")
        if (prev - curr).days == 1:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 1

    return {"current_streak": current_streak, "longest_streak": max(longest, current_streak)}


def get_review_completion(db: Session, user_id: int) -> dict:
    """获取今日复习完成率"""
    now = datetime.utcnow()
    # 今日应复习：due <= 当前时间
    due_total = db.query(func.count(Progress.id)).filter(
        Progress.user_id == user_id,
        Progress.due <= now,
        Progress.state >= 1  # 非新卡
    ).scalar() or 0

    # 今日已复习：今天的 history 记录数（去重单词）
    today_start_utc = datetime(now.year, now.month, now.day) - timedelta(hours=8)
    reviewed_today = db.query(func.count(func.distinct(
        History.book_id + '|' + History.word
    ))).filter(
        History.user_id == user_id,
        History.time >= today_start_utc
    ).scalar() or 0

    completion = round(reviewed_today / due_total * 100, 1) if due_total > 0 else 100.0

    return {
        "due_total": due_total,
        "reviewed_today": reviewed_today,
        "completion_rate": min(completion, 100.0)
    }


def get_pronunciation_history(db: Session, user_id: int, limit: int = 20) -> list:
    """获取发音评估历史"""
    records = db.query(PronunciationRecord).filter(
        PronunciationRecord.user_id == user_id
    ).order_by(PronunciationRecord.created_at.desc()).limit(limit).all()

    return [
        {
            "word": r.word,
            "accuracy_score": r.accuracy_score,
            "pronunciation_score": r.pronunciation_score,
            "fluency_score": r.fluency_score,
            "completeness_score": r.completeness_score,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in records
    ]


def get_phoneme_errors(db: Session, user_id: int, limit: int = 20) -> list:
    """获取薄弱音素列表"""
    records = db.query(PhonemeError).filter(
        PhonemeError.user_id == user_id,
        PhonemeError.error_count > 0
    ).order_by(PhonemeError.avg_accuracy.asc()).limit(limit).all()

    return [
        {
            "phoneme": r.phoneme,
            "total_attempts": r.total_attempts,
            "error_count": r.error_count,
            "avg_accuracy": round(r.avg_accuracy, 1),
            "error_types": json.loads(r.error_types) if r.error_types else {}
        }
        for r in records
    ]


# ==================== 发音评估操作 ====================

def add_pronunciation_record(db: Session, user_id: int, book_id: str, word: str,
                              audio_path: str, accuracy_score: float,
                              pronunciation_score: float, fluency_score: float,
                              completeness_score: float, recognized_text: str,
                              phoneme_details: str) -> PronunciationRecord:
    """添加发音评估记录"""
    record = PronunciationRecord(
        user_id=user_id,
        book_id=book_id,
        word=word,
        audio_path=audio_path,
        accuracy_score=accuracy_score,
        pronunciation_score=pronunciation_score,
        fluency_score=fluency_score,
        completeness_score=completeness_score,
        recognized_text=recognized_text,
        phoneme_details=phoneme_details
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_phoneme_errors(db: Session, user_id: int, phoneme_details: List[dict]):
    """
    更新用户的音素错误统计

    Args:
        db: 数据库会话
        user_id: 用户ID
        phoneme_details: 音素详情列表 [{"phoneme": "h", "accuracy": 95, "error_type": "None"}, ...]
    """
    # 先按音素聚合，避免同一音素多次处理导致冲突
    phoneme_stats = {}
    for phoneme_data in phoneme_details:
        phoneme = phoneme_data.get("phoneme", "")
        if not phoneme:
            continue

        accuracy = phoneme_data.get("accuracy", 100)
        error_type = phoneme_data.get("error_type", "None")

        if phoneme not in phoneme_stats:
            phoneme_stats[phoneme] = {
                "attempts": 0,
                "total_accuracy": 0,
                "errors": 0,
                "error_types": {}
            }

        stats = phoneme_stats[phoneme]
        stats["attempts"] += 1
        stats["total_accuracy"] += accuracy

        is_error = accuracy < 60 or error_type != "None"
        if is_error:
            stats["errors"] += 1
            stats["error_types"][error_type] = stats["error_types"].get(error_type, 0) + 1

    # 批量获取所有现有记录（一次查询代替 N 次查询）
    phonemes_to_update = list(phoneme_stats.keys())
    existing_records = db.query(PhonemeError).filter(
        PhonemeError.user_id == user_id,
        PhonemeError.phoneme.in_(phonemes_to_update)
    ).all()
    existing_map = {r.phoneme: r for r in existing_records}

    # 批量处理
    new_records = []
    for phoneme, stats in phoneme_stats.items():
        error_record = existing_map.get(phoneme)

        if error_record:
            # 更新统计
            old_total = error_record.total_attempts
            new_total = old_total + stats["attempts"]
            error_record.total_attempts = new_total
            error_record.error_count += stats["errors"]

            # 更新错误类型统计
            if stats["errors"] > 0:
                error_types = json.loads(error_record.error_types or "{}")
                for et, count in stats["error_types"].items():
                    error_types[et] = error_types.get(et, 0) + count
                error_record.error_types = json.dumps(error_types)

            # 更新平均准确度（加权平均）
            error_record.avg_accuracy = (
                error_record.avg_accuracy * old_total + stats["total_accuracy"]
            ) / new_total
        else:
            # 创建新记录
            avg_accuracy = stats["total_accuracy"] / stats["attempts"]
            new_records.append(PhonemeError(
                user_id=user_id,
                phoneme=phoneme,
                total_attempts=stats["attempts"],
                error_count=stats["errors"],
                avg_accuracy=avg_accuracy,
                error_types=json.dumps(stats["error_types"])
            ))

    # 批量添加新记录
    if new_records:
        db.add_all(new_records)

    # 一次提交
    db.commit()


def get_user_weak_phonemes(db: Session, user_id: int, top_n: int = 10) -> List[PhonemeError]:
    """获取用户发音薄弱的音素（按平均准确度升序）"""
    return db.query(PhonemeError).filter(
        PhonemeError.user_id == user_id,
        PhonemeError.total_attempts >= 3  # 至少3次尝试才有统计意义
    ).order_by(
        PhonemeError.avg_accuracy.asc()
    ).limit(top_n).all()


def get_pronunciation_records(db: Session, user_id: int, book_id: str = None,
                               word: str = None, limit: int = 50) -> List[PronunciationRecord]:
    """获取发音评估记录"""
    query = db.query(PronunciationRecord).filter(
        PronunciationRecord.user_id == user_id
    )
    if book_id:
        query = query.filter(PronunciationRecord.book_id == book_id)
    if word:
        query = query.filter(PronunciationRecord.word == word)

    return query.order_by(PronunciationRecord.created_at.desc()).limit(limit).all()


# 初始化数据库
if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化: {DATABASE_PATH}")
