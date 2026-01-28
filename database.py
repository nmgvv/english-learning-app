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


# ==================== 数据库初始化 ====================

def init_db():
    """初始化数据库，创建所有表"""
    # 确保 data 目录存在
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


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

def create_user(db: Session, username: str, password: str, email: str = None) -> Optional[User]:
    """
    创建新用户

    Args:
        db: 数据库会话
        username: 用户名
        password: 明文密码
        email: 邮箱（可选）

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
        email=email
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


def get_due_cards(db: Session, user_id: int, book_id: str = None) -> List[Progress]:
    """获取今日待复习的单词（全局或指定词书）

    Args:
        user_id: 用户ID
        book_id: 词书ID，如果为 None 则获取所有词书的待复习单词

    Returns:
        随机顺序的待复习单词列表（防止顺序记忆）
    """
    import random
    now = datetime.utcnow()
    # 计算今日结束时间（23:59:59），避免复习过程中数量增加
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    query = db.query(Progress).filter(
        Progress.user_id == user_id,
        Progress.due <= end_of_today
    )

    # 如果指定了词书，则过滤
    if book_id:
        query = query.filter(Progress.book_id == book_id)

    cards = query.all()

    # 随机打乱顺序，防止顺序记忆
    random.shuffle(cards)
    return cards


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
    """获取全局掌握单词数曲线（跨所有词书）

    掌握定义：
    - 一次答对(attempts=1, result=correct) → 计入掌握
    - 答错(result=wrong) → 从掌握中移除

    Args:
        user_id: 用户ID
        days: 统计天数，0 表示全部

    Returns:
        {"dates": ["01-20", ...], "counts": [10, ...], "total": 当前总掌握数}
    """
    from datetime import timedelta
    from collections import defaultdict

    # 查询用户所有历史记录，按时间排序
    query = db.query(History).filter(
        History.user_id == user_id
    ).order_by(History.time.asc())

    records = query.all()

    if not records:
        return {"dates": [], "counts": [], "total": 0}

    # 使用集合跟踪当前掌握的单词
    mastered_words = set()
    # 每日掌握数记录
    daily_counts = defaultdict(int)

    for record in records:
        word = record.word
        result = record.result
        attempts = record.attempts
        date_str = record.time.strftime("%m-%d")

        # 一次答对 → 加入掌握
        if result == "correct" and attempts == 1:
            mastered_words.add(word)
        # 答错 → 移出掌握
        elif result == "wrong":
            mastered_words.discard(word)

        # 记录当天结束时的掌握数
        daily_counts[date_str] = len(mastered_words)

    # 过滤时间范围
    if days > 0:
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days - 1)

        filtered_dates = []
        filtered_counts = []

        # 生成连续日期
        current_date = start_date
        last_count = 0

        # 找到 start_date 之前的最后一个掌握数作为基准
        for record in records:
            if record.time.date() < start_date:
                word = record.word
                result = record.result
                attempts = record.attempts
                if result == "correct" and attempts == 1:
                    mastered_words.add(word)
                elif result == "wrong":
                    mastered_words.discard(word)
        last_count = len(mastered_words)

        # 重新计算指定日期范围内的数据
        mastered_in_range = mastered_words.copy()
        for record in records:
            if record.time.date() >= start_date:
                word = record.word
                result = record.result
                attempts = record.attempts
                if result == "correct" and attempts == 1:
                    mastered_in_range.add(word)
                elif result == "wrong":
                    mastered_in_range.discard(word)
                daily_counts[record.time.strftime("%m-%d")] = len(mastered_in_range)

        while current_date <= end_date:
            date_str = current_date.strftime("%m-%d")
            if date_str in daily_counts:
                last_count = daily_counts[date_str]
            filtered_dates.append(date_str)
            filtered_counts.append(last_count)
            current_date += timedelta(days=1)

        return {
            "dates": filtered_dates,
            "counts": filtered_counts,
            "total": len(mastered_words)
        }

    # 全部数据
    dates = list(daily_counts.keys())
    counts = list(daily_counts.values())

    return {
        "dates": dates,
        "counts": counts,
        "total": len(mastered_words)
    }


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
