"""
FastAPI 服务器入口

包含:
- 所有 API 路由
- 模板渲染
- 静态文件服务
- TTS 音频缓存
"""

import os

# 加载环境变量（必须在导入其他模块之前）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 清除代理环境变量，避免 httpx 使用 SOCKS 代理
for _proxy_key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(_proxy_key, None)

import json
import asyncio
import tempfile
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Request, Depends, HTTPException, status, Form, Response, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# 本地模块
from database import (
    init_db, get_db, Session,
    create_user, authenticate_user, get_user_by_id,
    create_token, verify_token,
    get_user_progress, update_progress, get_due_cards,
    add_history, get_user_stats
)
from bookmanager import BookManager, BOOK_NAMES, get_book_display_name

# FSRS 算法和辅助函数 (从 dictation.py 复用)
from dictation import (
    init_difficulty, init_stability,
    next_difficulty, next_recall_stability, next_forget_stability,
    retrievability, next_interval,
    grade_from_attempts,
    calculate_similarity, get_error_hint
)

# TTS
try:
    import edge_tts
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

# 阿里云百炼 (Qwen-Plus)
try:
    import httpx
    QWEN_AVAILABLE = True
except ImportError:
    QWEN_AVAILABLE = False

# 阿里云百炼 Qwen3-TTS（替代 edge-tts）
QWEN_TTS_AVAILABLE = bool(os.getenv("DASHSCOPE_API_KEY"))

# Conversation and Speech modules
from conversation import ConversationManager
from speech import (
    SpeechRecognizer, PronunciationAssessor,
    generate_feedback_text, generate_ai_feedback, ACCURACY_THRESHOLD,
    QwenChineseSpeechRecognizer, generate_translation_feedback, calculate_text_similarity,
    Qwen3TTS, synthesize_speech
)

# Database models for pronunciation
from database import (
    add_pronunciation_record, update_phoneme_errors,
    get_user_weak_phonemes, get_pronunciation_records,
    PronunciationRecord, PhonemeError
)

# Phoneme to letter mapping
from phoneme_mapper import merge_assessment_with_letters

# 全局实例
conv_manager = ConversationManager()
speech_recognizer = SpeechRecognizer()
pronunciation_assessor = PronunciationAssessor()
chinese_recognizer = QwenChineseSpeechRecognizer()  # 中文语音识别器（翻译练习用）

# 项目路径
PROJECT_ROOT = Path(__file__).parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
AUDIO_CACHE_DIR = STATIC_DIR / "audio"

# 确保目录存在
STATIC_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)
AUDIO_CACHE_DIR.mkdir(exist_ok=True)
RECORDINGS_DIR = STATIC_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)

# 创建应用
app = FastAPI(title="英语学习应用", version="1.0.0")

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 模板引擎
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# 词书管理器
book_manager = BookManager()

# 初始化数据库
init_db()


# ==================== Pydantic 模型 ====================

class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class SessionStart(BaseModel):
    book_id: str
    mode: str = "review"  # review / new / all
    unit: Optional[str] = None
    limit: int = 20


class AnswerSubmit(BaseModel):
    word: str
    input: str
    attempt: int


class ExampleRequest(BaseModel):
    word: str
    translation: str


class ConversationStartRequest(BaseModel):
    words: List[dict]  # [{"word": "...", "translation": "..."}]
    mode: str = "guided"
    rounds: Optional[int] = None  # 对话轮数（可选）


class ConversationReplyRequest(BaseModel):
    conversation_id: str
    user_input: str  # ASR 识别的文本
    target_words: List[str]


# ==================== 认证依赖 ====================

def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[dict]:
    """从 Cookie 或 Header 获取当前用户"""
    # 优先从 Cookie 获取
    token = request.cookies.get("token")

    # 如果没有 Cookie，尝试从 Header 获取
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        return None

    payload = verify_token(token)
    if not payload:
        return None

    user = get_user_by_id(db, payload["user_id"])
    if not user:
        return None

    return {"id": user.id, "username": user.username}


def require_auth(request: Request, db: Session = Depends(get_db)):
    """要求登录的依赖"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已过期"
        )
    return user


# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, db: Session = Depends(get_db)):
    """首页 - 词书列表"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    books = book_manager.list_books()
    # 构建词书列表，包含 ID 和中文名
    book_list = [{"id": b, "name": get_book_display_name(b)} for b in books]
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user,
        "books": book_list
    })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    """登录页面"""
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": None
    })


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: Session = Depends(get_db)):
    """注册页面"""
    user = get_current_user(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)

    return templates.TemplateResponse("login.html", {
        "request": request,
        "is_register": True,
        "error": None
    })


@app.get("/dictation/{book_id}", response_class=HTMLResponse)
async def dictation_page(request: Request, book_id: str, db: Session = Depends(get_db)):
    """听写练习页面"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # 加载词书
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    return templates.TemplateResponse("dictation.html", {
        "request": request,
        "user": user,
        "book_id": book_id,
        "total_words": len(words)
    })


@app.get("/conversation/{book_id}", response_class=HTMLResponse)
async def conversation_page(request: Request, book_id: str, db: Session = Depends(get_db)):
    """对话练习页面"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("conversation.html", {
        "request": request,
        "user": user,
        "book_id": book_id
    })


@app.get("/conversation-setup/{book_id}", response_class=HTMLResponse)
async def conversation_setup_page(request: Request, book_id: str, db: Session = Depends(get_db)):
    """对话练习 - 单元选择页面"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("conversation_setup.html", {
        "request": request,
        "user": user,
        "book_id": book_id
    })


@app.get("/reading/{book_id}", response_class=HTMLResponse)
async def reading_page(request: Request, book_id: str, unit: Optional[str] = None, db: Session = Depends(get_db)):
    """跟读练习页面"""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # 获取词书名称
    book_name = get_book_display_name(book_id)

    return templates.TemplateResponse("reading.html", {
        "request": request,
        "user": user,
        "book_id": book_id,
        "book_name": book_name,
        "unit": unit or ""
    })


# ==================== 认证 API ====================

@app.post("/api/auth/register")
async def api_register(data: UserCreate, db: Session = Depends(get_db)):
    """用户注册"""
    if len(data.username) < 2:
        raise HTTPException(status_code=400, detail="用户名至少2个字符")
    if len(data.password) < 4:
        raise HTTPException(status_code=400, detail="密码至少4个字符")

    user = create_user(db, data.username, data.password, data.email)
    if not user:
        raise HTTPException(status_code=400, detail="用户名已存在")

    token = create_token(user.id, user.username)
    response = JSONResponse(content={
        "success": True,
        "user": {"id": user.id, "username": user.username}
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,  # 7天
        samesite="lax"
    )
    return response


@app.post("/api/auth/login")
async def api_login(data: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    user = authenticate_user(db, data.username, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user.id, user.username)
    response = JSONResponse(content={
        "success": True,
        "user": {"id": user.id, "username": user.username}
    })
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        max_age=7 * 24 * 3600,
        samesite="lax"
    )
    return response


@app.post("/api/auth/logout")
async def api_logout():
    """用户登出"""
    response = JSONResponse(content={"success": True})
    response.delete_cookie("token")
    return response


@app.get("/api/auth/me")
async def api_me(user: dict = Depends(require_auth)):
    """获取当前用户信息"""
    return {"user": user}


# ==================== 词书 API ====================

@app.get("/api/books")
async def api_books():
    """获取词书列表"""
    books = book_manager.list_books()
    return {"books": books}


@app.get("/api/books/{book_id}")
async def api_book_detail(book_id: str):
    """获取词书详情"""
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 统计单元
    units = {}
    for word in words:
        unit = word.unit or "未分类"
        if unit not in units:
            units[unit] = 0
        units[unit] += 1

    return {
        "book_id": book_id,
        "total_words": len(words),
        "units": units
    }


@app.get("/api/book/{book_id}/units")
async def api_book_units(book_id: str):
    """获取词书的所有章节列表"""
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 提取唯一的章节名并排序
    units = sorted(set(w.unit for w in words if w.unit))
    return {"units": units}


@app.get("/api/book/{book_id}/units/stats")
async def api_book_units_stats(
    book_id: str,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """获取词书各单元的学习统计"""
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 获取用户进度
    progress_list = get_user_progress(db, user["id"], book_id)
    learned_words = {p.word for p in progress_list}

    # 按单元统计
    unit_stats = {}
    for word in words:
        unit = word.unit or "未分类"
        if unit not in unit_stats:
            unit_stats[unit] = {"name": unit, "total_count": 0, "learned_count": 0}
        unit_stats[unit]["total_count"] += 1
        if word.word in learned_words:
            unit_stats[unit]["learned_count"] += 1

    # 排序并返回
    units = sorted(unit_stats.values(), key=lambda x: x["name"])
    return {"units": units}


class LearnedWordsRequest(BaseModel):
    units: List[str]


@app.post("/api/book/{book_id}/learned-words")
async def api_book_learned_words(
    book_id: str,
    data: LearnedWordsRequest,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """获取指定单元中已学过的单词列表"""
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 过滤指定单元的单词
    if data.units:
        unit_words = [w for w in words if w.unit in data.units]
    else:
        unit_words = words

    # 获取用户进度
    progress_list = get_user_progress(db, user["id"], book_id)
    learned_set = {p.word for p in progress_list}

    # 筛选已学单词
    learned_words = [
        {"word": w.word, "translation": w.translation}
        for w in unit_words
        if w.word in learned_set
    ]

    return {"words": learned_words, "count": len(learned_words)}


@app.get("/api/books/{book_id}/words")
async def api_book_words(
    book_id: str,
    unit: Optional[str] = None,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """获取词书单词列表（带学习进度）"""
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 过滤单元
    if unit:
        words = [w for w in words if w.unit == unit]

    # 获取用户进度
    progress_list = get_user_progress(db, user["id"], book_id)
    progress_map = {p.word: p for p in progress_list}

    result = []
    for word in words:
        p = progress_map.get(word.word)
        result.append({
            "word": word.word,
            "phonetic": word.phonetic,
            "translation": word.translation,
            "unit": word.unit,
            "learned": p is not None,
            "due": p.due.isoformat() if p and p.due else None
        })

    return {"words": result}


# ==================== 学习会话 API ====================

@app.post("/api/session/start")
async def api_session_start(
    data: SessionStart,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """开始学习会话"""
    words = book_manager.load(data.book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 过滤单元
    if data.unit:
        words = [w for w in words if w.unit == data.unit]

    # 获取用户进度
    progress_list = get_user_progress(db, user["id"], data.book_id)
    progress_map = {p.word: p for p in progress_list}

    # 根据模式筛选单词
    now = datetime.utcnow()
    cards = []

    for word in words:
        p = progress_map.get(word.word)

        if data.mode == "new":
            # 只学新词
            if not p:
                cards.append({
                    "word": word.word,
                    "phonetic": word.phonetic,
                    "translation": word.translation,
                    "unit": word.unit,
                    "is_new": True
                })
        elif data.mode == "review":
            # 复习模式：按 FSRS 算法选择需要复习的单词
            # 1. 优先选择已到期的单词（due <= now）
            # 2. 在到期单词中，按可提取性从低到高排序（最容易遗忘的优先）
            if p:
                # 计算排序优先级
                # priority: 越小越优先复习
                # - 已到期：priority = retrievability (0-1)
                # - 未到期：priority = 2 + days_until_due (确保排在到期单词后面)
                priority = 2.0  # 默认：未设置 due 的排在中间

                if p.due:
                    days_until_due = (p.due - now).total_seconds() / 86400
                    if days_until_due <= 0:
                        # 已到期：按可提取性排序（越低越优先）
                        if p.stability and p.stability > 0 and p.last_review:
                            elapsed_days = (now - p.last_review).total_seconds() / 86400
                            priority = retrievability(p.stability, max(0, elapsed_days))
                        else:
                            priority = 0.5  # 没有 stability 数据，给中等优先级
                    else:
                        # 未到期：排在后面，按剩余天数排序
                        priority = 2.0 + days_until_due

                cards.append({
                    "word": word.word,
                    "phonetic": word.phonetic,
                    "translation": word.translation,
                    "unit": word.unit,
                    "is_new": False,
                    "_priority": priority  # 用于排序
                })
        else:
            # all: 所有词
            is_new = p is None
            cards.append({
                "word": word.word,
                "phonetic": word.phonetic,
                "translation": word.translation,
                "unit": word.unit,
                "is_new": is_new
            })

    # 复习模式：按 FSRS 优先级排序
    if data.mode == "review":
        cards.sort(key=lambda c: c.get("_priority", 2.0))
        # 移除内部排序字段（前端不需要）
        for card in cards:
            card.pop("_priority", None)

    # 限制数量
    cards = cards[:data.limit]

    return {
        "total": len(cards),
        "cards": cards
    }


@app.post("/api/session/submit")
async def api_session_submit(
    data: AnswerSubmit,
    book_id: str,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """提交答案"""
    # 获取单词信息
    word_obj = book_manager.get_word(book_id, data.word)
    if not word_obj:
        raise HTTPException(status_code=404, detail="单词不存在")

    correct = data.input.strip().lower() == data.word.lower()

    # 使用 dictation.py 的相似度计算和提示
    similarity = 0.0
    hint = "错误"
    if not correct and data.input.strip():
        similarity = calculate_similarity(data.word, data.input)
        hint = get_error_hint(data.word, data.input)

    return {
        "correct": correct,
        "similarity": similarity,
        "hint": hint,
        "remaining_attempts": 3 - data.attempt
    }


@app.post("/api/session/complete")
async def api_session_complete(
    book_id: str,
    word: str,
    correct: bool,
    attempts: int,
    inputs: List[str],
    skipped: bool = False,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """完成单词学习，使用 dictation.py 的 FSRS 算法更新状态"""
    from datetime import timedelta
    from database import get_word_progress

    # 使用 dictation.py 的评分函数
    grade = grade_from_attempts(attempts, correct, skipped)

    now = datetime.utcnow()

    # 获取现有进度
    progress = get_word_progress(db, user["id"], book_id, word)

    if progress:
        # 复习卡：更新现有进度
        reps = progress.reps + 1
        lapses = progress.lapses

        # 计算当前可提取性
        if progress.due:
            elapsed = (now - progress.due).days
        else:
            elapsed = 0
        r = retrievability(progress.stability, max(0, elapsed))

        # 更新难度
        difficulty = next_difficulty(progress.difficulty, grade)

        # 更新稳定性
        if grade == 1:  # 遗忘
            stability = next_forget_stability(difficulty, progress.stability, r)
            lapses += 1
            state = 1  # 重新学习
        else:
            stability = next_recall_stability(difficulty, progress.stability, r, grade)
            state = 2  # 复习中

        if skipped:
            lapses += 1

    else:
        # 新卡片：使用初始化函数
        reps = 1
        lapses = 1 if (not correct or skipped) else 0
        difficulty = init_difficulty(grade)
        stability = init_stability(grade)
        state = 1 if grade < 3 else 2

    # 计算下次复习间隔
    interval_days = next_interval(stability)
    due = now + timedelta(days=interval_days)

    # 更新数据库
    update_progress(
        db, user["id"], book_id, word,
        difficulty=difficulty,
        stability=stability,
        state=state,
        reps=reps,
        lapses=lapses,
        last_review=now,
        due=due
    )

    # 添加历史记录
    result = "skipped" if skipped else ("correct" if correct else "wrong")
    add_history(db, user["id"], book_id, word, inputs, result, attempts, grade)

    return {
        "success": True,
        "next_review": due.isoformat(),
        "interval_days": interval_days,
        "grade": grade
    }


# ==================== TTS API ====================

@app.get("/api/tts/{speed}/{word}")
async def api_tts(speed: str, word: str, user: dict = Depends(require_auth)):
    """获取单词发音（需要认证）- 使用 Qwen3-TTS"""
    # 清理单词（只保留字母和空格）
    safe_word = "".join(c for c in word if c.isalpha() or c.isspace())
    if not safe_word:
        raise HTTPException(status_code=400, detail="无效的单词")

    # 缓存文件路径（使用 .wav 格式）
    cache_file = AUDIO_CACHE_DIR / f"{safe_word}_{speed}.wav"

    # 检查缓存
    if not cache_file.exists():
        # 优先使用 Qwen3-TTS
        if QWEN_TTS_AVAILABLE:
            try:
                tts = Qwen3TTS()
                # slow 模式使用较慢语速
                rate = 0.75 if speed == "slow" else 1.0
                audio_data = await tts.synthesize(safe_word, language="English", rate=rate)
                if audio_data:
                    with open(cache_file, 'wb') as f:
                        f.write(audio_data)
                else:
                    raise Exception("音频生成失败")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")
        # 回退到 edge-tts
        elif TTS_AVAILABLE:
            cache_file = AUDIO_CACHE_DIR / f"{safe_word}_{speed}.mp3"
            rate = "-30%" if speed == "slow" else "+0%"
            try:
                communicate = edge_tts.Communicate(safe_word, "en-US-JennyNeural", rate=rate)
                await communicate.save(str(cache_file))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")
        else:
            raise HTTPException(status_code=503, detail="TTS 服务不可用")

    # 根据文件类型返回正确的 MIME 类型
    media_type = "audio/wav" if str(cache_file).endswith(".wav") else "audio/mpeg"
    return FileResponse(
        str(cache_file),
        media_type=media_type,
        filename=f"{safe_word}.wav" if str(cache_file).endswith(".wav") else f"{safe_word}.mp3"
    )


@app.get("/api/tts/sentence")
async def api_tts_sentence(
    sentence: str,
    user: dict = Depends(require_auth)
):
    """
    获取句子发音（需要认证）- 使用 Qwen3-TTS 智能语调

    Qwen3-TTS 会根据文本内容（疑问句、感叹句等）自动调整语调
    """
    # 优先使用 Qwen3-TTS（智能语调）
    if QWEN_TTS_AVAILABLE:
        try:
            tts = Qwen3TTS()
            audio_data = await tts.synthesize(sentence)

            if audio_data:
                return Response(
                    content=audio_data,
                    media_type="audio/wav",
                    headers={"Content-Disposition": "inline; filename=sentence.wav"}
                )
            else:
                raise Exception("音频生成失败")
        except Exception as e:
            # 如果 Qwen3-TTS 失败，尝试回退到 edge-tts
            if TTS_AVAILABLE:
                pass  # 继续使用 edge-tts
            else:
                raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

    # 回退到 edge-tts
    if TTS_AVAILABLE:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            communicate = edge_tts.Communicate(sentence, "en-US-JennyNeural", rate="-10%")
            await communicate.save(tmp_path)
            return FileResponse(tmp_path, media_type="audio/mpeg")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

    raise HTTPException(status_code=503, detail="TTS 服务不可用")


# ==================== 阿里云百炼 Qwen API ====================

@app.post("/api/example-sentence")
async def api_example_sentence(data: ExampleRequest, user: dict = Depends(require_auth)):
    """生成例句（使用阿里云百炼 Qwen-Plus）"""
    if not QWEN_AVAILABLE:
        return {"sentence": None, "chinese": None, "error": "Qwen 服务不可用"}

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return {"sentence": None, "chinese": None, "error": "未配置 DASHSCOPE_API_KEY"}

    prompt = f"""单词 {data.word}（{data.translation}），生成一个简单例句帮助学生记忆拼写。
要求：
- 句子简短（10词以内）
- 适合初中生理解
- 目标单词在句中清晰可辨

返回JSON：{{"sentence": "例句", "chinese": "中文翻译"}}"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是一位英语教师助手，辅导中国初中生学习英语词汇。回复使用JSON格式。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 200
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                # 解析 JSON（处理可能的 markdown 代码块）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                return json.loads(content)
            else:
                return {"sentence": None, "chinese": None, "error": f"API 返回 {response.status_code}"}
    except Exception as e:
        return {"sentence": None, "chinese": None, "error": str(e)}


# ==================== 统计 API ====================

@app.get("/api/stats/{book_id}")
async def api_stats(book_id: str, user: dict = Depends(require_auth), db: Session = Depends(get_db)):
    """获取学习统计"""
    stats = get_user_stats(db, user["id"], book_id)

    # 获取词书总词数
    words = book_manager.load(book_id)
    stats["total_words"] = len(words) if words else 0

    # 获取今日待复习数
    due_cards = get_due_cards(db, user["id"], book_id)
    stats["due_today"] = len(due_cards)

    return stats


# ==================== 语音识别 API ====================

@app.post("/api/speech/recognize")
async def api_speech_recognize(
    audio: UploadFile = File(...),
    user: dict = Depends(require_auth)
):
    """
    语音识别 API

    接收音频文件，返回识别的文本
    """
    if not speech_recognizer.is_available():
        return {"success": False, "text": "", "error": "Azure Speech 服务未配置"}

    # 读取音频数据
    audio_data = await audio.read()

    # 获取文件扩展名
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    # 调用识别
    result = await speech_recognizer.recognize_from_bytes(audio_data, ext)
    return result


# ==================== 对话练习 API ====================

@app.post("/api/conversation/start")
async def api_conversation_start(
    data: ConversationStartRequest,
    user: dict = Depends(require_auth)
):
    """开始对话练习"""
    if not conv_manager.is_available():
        return {"error": "DeepSeek API 未配置，无法开始对话"}

    try:
        return await conv_manager.start_conversation(data.words, data.mode, data.rounds)
    except Exception as e:
        return {"error": f"开始对话失败: {str(e)}"}


@app.post("/api/conversation/reply")
async def api_conversation_reply(
    data: ConversationReplyRequest,
    user: dict = Depends(require_auth)
):
    """提交对话回复（文本，来自 ASR）"""
    try:
        return await conv_manager.evaluate_response(
            data.conversation_id,
            data.user_input,
            data.target_words
        )
    except Exception as e:
        return {"error": f"处理回复失败: {str(e)}"}


@app.get("/api/conversation/summary/{conversation_id}")
async def api_conversation_summary(
    conversation_id: str,
    user: dict = Depends(require_auth)
):
    """获取对话总结"""
    return await conv_manager.get_summary(conversation_id)


# ==================== 发音评估 API ====================

async def save_pronunciation_audio(user_id: int, book_id: str, word: str,
                                    audio_data: bytes, ext: str) -> Optional[str]:
    """
    保存用户跟读音频

    存储策略：
    - 路径格式: /static/recordings/{user_id}/{book_id}/{word}_{timestamp}{ext}
    - 只保留最近3次录音（自动清理旧文件）
    """
    # 创建目录
    user_dir = RECORDINGS_DIR / str(user_id) / book_id
    user_dir.mkdir(parents=True, exist_ok=True)

    # 清理文件名中的特殊字符
    safe_word = "".join(c for c in word if c.isalnum() or c in " -_")

    # 清理旧文件（保留最近2个）
    existing = sorted(user_dir.glob(f"{safe_word}_*"), key=lambda x: x.stat().st_mtime)
    for old_file in existing[:-2]:  # 保留最近2个，新的是第3个
        try:
            old_file.unlink()
        except:
            pass

    # 保存新文件
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_word}_{timestamp}{ext}"
    filepath = user_dir / filename

    with open(filepath, "wb") as f:
        f.write(audio_data)

    # 返回相对路径
    return f"recordings/{user_id}/{book_id}/{filename}"


# ==================== 翻译练习 API ====================

@app.post("/api/translation/assess")
async def api_translation_assess(
    audio: UploadFile = File(...),
    word: str = Form(...),           # 英文单词
    chinese: str = Form(...),        # 标准中文翻译
    book_id: str = Form(...),
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    中文翻译练习评估 API

    1. 使用 Qwen3-ASR 识别用户说的中文
    2. 计算与标准翻译的相似度
    3. 使用 Qwen-Plus AI 评价翻译结果

    请求参数:
        audio: 音频文件（录音）
        word: 英文单词
        chinese: 标准中文翻译
        book_id: 词书 ID

    返回:
        {
            "success": True,
            "recognized_text": "用户说的中文",
            "reference_text": "标准翻译",
            "correct": True/False,
            "similarity": 0.85,
            "feedback": "评价",
            "issues": [],
            "suggestion": ""
        }
    """
    if not chinese_recognizer.is_available():
        return {
            "success": False,
            "error": "中文语音识别服务未配置，请检查 DASHSCOPE_API_KEY"
        }

    # 读取音频数据
    audio_data = await audio.read()

    # 获取文件扩展名
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    print(f"[翻译评估] 单词: {word}, 标准翻译: {chinese}, 音频大小: {len(audio_data)} bytes")

    # 1. 中文语音识别
    asr_result = await chinese_recognizer.recognize_from_bytes(audio_data, ext)
    print(f"[翻译评估] ASR 结果: {asr_result}")

    if not asr_result.get("success"):
        return {
            "success": False,
            "recognized_text": "",
            "reference_text": chinese,
            "correct": False,
            "error": asr_result.get("error", "语音识别失败"),
            "feedback": "语音识别失败，请重试",
            "issues": ["语音识别失败"],
            "suggestion": "请确保录音清晰，再试一次"
        }

    user_chinese = asr_result["text"]
    print(f"[翻译评估] 识别结果: {user_chinese}")

    # 2. 计算文本相似度
    similarity = calculate_text_similarity(chinese, user_chinese)
    print(f"[翻译评估] 相似度: {similarity:.2f}")

    # 3. AI 评价翻译
    feedback_result = await generate_translation_feedback(
        english=word,
        reference=chinese,
        user_text=user_chinese,
        similarity=similarity
    )

    # 4. 保存翻译记录（可选，如果有数据库表）
    # TODO: 添加 TranslationRecord 表后取消注释
    # record = add_translation_record(
    #     db, user["id"], book_id, word, chinese, user_chinese,
    #     similarity, feedback_result.get("correct", False),
    #     json.dumps(feedback_result, ensure_ascii=False)
    # )

    return {
        "success": True,
        "recognized_text": user_chinese,
        "reference_text": chinese,
        "correct": feedback_result.get("correct", False),
        "similarity": round(similarity, 2),
        "feedback": feedback_result.get("feedback", ""),
        "issues": feedback_result.get("issues", []),
        "suggestion": feedback_result.get("suggestion", "")
    }


@app.post("/api/translation/passage")
async def api_translation_passage(
    audio: UploadFile = File(...),
    passage: str = Form(...),        # 英文短文
    book_id: str = Form(...),
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    短文翻译评估 API

    1. 使用 Qwen3-ASR 识别用户说的中文翻译
    2. 使用 Qwen-Plus AI 生成参考翻译并评价用户翻译

    请求参数:
        audio: 音频文件（录音）
        passage: 英文短文
        book_id: 词书 ID

    返回:
        {
            "success": True,
            "recognized_text": "用户说的中文翻译",
            "reference_text": "AI参考翻译",
            "score": 85,
            "feedback": "整体评价",
            "strengths": ["优点1", "优点2"],
            "issues": ["问题1", "问题2"],
            "suggestion": "改进建议"
        }
    """
    if not chinese_recognizer.is_available():
        return {
            "success": False,
            "error": "中文语音识别服务未配置，请检查 DASHSCOPE_API_KEY"
        }

    # 读取音频数据
    audio_data = await audio.read()

    # 获取文件扩展名
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    print(f"[短文翻译] 短文长度: {len(passage)} 字符, 音频大小: {len(audio_data)} bytes")

    # 1. 中文语音识别
    asr_result = await chinese_recognizer.recognize_from_bytes(audio_data, ext)
    print(f"[短文翻译] ASR 结果: {asr_result}")

    if not asr_result.get("success"):
        return {
            "success": False,
            "recognized_text": "",
            "reference_text": "",
            "score": 0,
            "error": asr_result.get("error", "语音识别失败"),
            "feedback": "语音识别失败，请重试",
            "strengths": [],
            "issues": ["语音识别失败"],
            "suggestion": "请确保录音清晰，再试一次"
        }

    user_chinese = asr_result["text"]
    print(f"[短文翻译] 识别结果: {user_chinese}")

    # 2. AI 评估短文翻译
    from speech import evaluate_passage_translation
    eval_result = await evaluate_passage_translation(
        english_passage=passage,
        user_translation=user_chinese
    )

    return {
        "success": True,
        "recognized_text": user_chinese,
        "reference_text": eval_result.get("reference_translation", ""),
        "score": eval_result.get("score", 0),
        "feedback": eval_result.get("feedback", ""),
        "strengths": eval_result.get("strengths", []),
        "issues": eval_result.get("issues", []),
        "suggestion": eval_result.get("suggestion", "")
    }


@app.post("/api/pronunciation/assess")
async def api_pronunciation_assess(
    audio: UploadFile = File(...),
    word: str = Form(...),
    book_id: str = Form(...),
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    发音评估 API

    接收音频文件和参考单词，返回发音评估结果和反馈
    """
    if not pronunciation_assessor.is_available():
        return {"success": False, "error": "Azure Speech 服务未配置"}

    # 读取音频数据
    audio_data = await audio.read()

    # 获取文件扩展名
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    # 执行发音评估
    result = await pronunciation_assessor.assess_from_bytes(audio_data, word, ext)

    if result.get("success"):
        # 保存音频文件
        audio_path = await save_pronunciation_audio(
            user["id"], book_id, word, audio_data, ext
        )

        # 保存评估记录到数据库
        phoneme_details_json = json.dumps(result.get("phoneme_details", []), ensure_ascii=False)
        record = add_pronunciation_record(
            db, user["id"], book_id, word,
            audio_path,
            result.get("accuracy_score"),
            result.get("pronunciation_score"),
            result.get("fluency_score"),
            result.get("completeness_score"),
            result.get("recognized_text"),
            phoneme_details_json
        )

        # 更新音素错误统计
        update_phoneme_errors(db, user["id"], result.get("phoneme_details", []))

        # 生成字母到音素的映射（带准确度）
        letter_mapping = merge_assessment_with_letters(word, result.get("phoneme_details", []))
        result["letter_mapping"] = letter_mapping

        # 生成反馈：低于阈值时使用 AI 点评，否则使用简单反馈
        accuracy_score = result.get("accuracy_score", 0)

        if accuracy_score < ACCURACY_THRESHOLD:
            # 使用 AI 生成智能点评和练习推荐
            ai_feedback = await generate_ai_feedback(
                word,
                accuracy_score,
                result.get("phoneme_details", []),
                letter_mapping
            )
            result["feedback_text"] = ai_feedback["feedback"]
            result["tips"] = ai_feedback.get("tips", "")
            result["practice_words"] = ai_feedback.get("practice_words", [])
            result["focus_phoneme"] = ai_feedback.get("focus_phoneme", "")
        else:
            # 使用简单反馈
            feedback_text = generate_feedback_text(result, word)
            result["feedback_text"] = feedback_text
            result["tips"] = ""
            result["practice_words"] = []
            result["focus_phoneme"] = ""

        result["record_id"] = record.id

    return result


@app.get("/api/pronunciation/feedback-audio")
async def api_pronunciation_feedback_audio(text: str):
    """
    生成中文反馈语音 - 使用 Qwen3-TTS
    """
    import hashlib

    # 缓存策略：根据文本内容生成缓存 key
    cache_key = hashlib.md5(text.encode()).hexdigest()[:10]

    # 优先使用 Qwen3-TTS
    if QWEN_TTS_AVAILABLE:
        cache_file = AUDIO_CACHE_DIR / f"feedback_zh_{cache_key}.wav"

        if not cache_file.exists():
            try:
                tts = Qwen3TTS()
                audio_data = await tts.synthesize(text, language="Chinese")
                if audio_data:
                    with open(cache_file, 'wb') as f:
                        f.write(audio_data)
                else:
                    raise Exception("音频生成失败")
            except Exception as e:
                # 回退到 edge-tts
                if TTS_AVAILABLE:
                    cache_file = AUDIO_CACHE_DIR / f"feedback_zh_{cache_key}.mp3"
                    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                    await communicate.save(str(cache_file))
                else:
                    raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

        media_type = "audio/wav" if str(cache_file).endswith(".wav") else "audio/mpeg"
        return FileResponse(str(cache_file), media_type=media_type)

    # 回退到 edge-tts
    if TTS_AVAILABLE:
        cache_file = AUDIO_CACHE_DIR / f"feedback_zh_{cache_key}.mp3"

        if not cache_file.exists():
            try:
                communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                await communicate.save(str(cache_file))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

        return FileResponse(str(cache_file), media_type="audio/mpeg")

    raise HTTPException(status_code=503, detail="TTS 服务不可用")


@app.get("/api/pronunciation/stats")
async def api_pronunciation_stats(
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    获取用户发音薄弱点统计
    """
    # 查询错误率最高的音素
    weak_phonemes = get_user_weak_phonemes(db, user["id"], top_n=10)

    return {
        "weak_phonemes": [
            {
                "phoneme": p.phoneme,
                "error_rate": round(p.error_count / p.total_attempts * 100, 1) if p.total_attempts > 0 else 0,
                "avg_accuracy": round(p.avg_accuracy, 1),
                "total_attempts": p.total_attempts,
                "error_types": json.loads(p.error_types or "{}")
            }
            for p in weak_phonemes
        ]
    }


@app.get("/api/pronunciation/records")
async def api_pronunciation_records(
    book_id: Optional[str] = None,
    word: Optional[str] = None,
    limit: int = 20,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    获取发音评估历史记录
    """
    records = get_pronunciation_records(db, user["id"], book_id, word, limit)

    return {
        "records": [
            {
                "id": r.id,
                "word": r.word,
                "book_id": r.book_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "accuracy_score": r.accuracy_score,
                "pronunciation_score": r.pronunciation_score,
                "fluency_score": r.fluency_score,
                "recognized_text": r.recognized_text,
                "audio_path": r.audio_path
            }
            for r in records
        ]
    }


# ==================== 跟读练习 API ====================

@app.post("/api/reading/generate")
async def api_reading_generate(
    book_id: str,
    unit: Optional[str] = None,
    word_count: int = 5,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    生成跟读短文

    使用词书中的单词，由 LLM 生成一段简短的英语短文
    """
    if not QWEN_AVAILABLE:
        raise HTTPException(status_code=503, detail="Qwen 服务不可用")

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="未配置 DASHSCOPE_API_KEY")

    # 加载词书
    words = book_manager.load(book_id)
    if not words:
        raise HTTPException(status_code=404, detail="词书不存在")

    # 过滤单元
    if unit:
        words = [w for w in words if w.unit == unit]

    if not words:
        raise HTTPException(status_code=404, detail="该单元没有单词")

    # 获取用户已学单词
    progress_list = get_user_progress(db, user["id"], book_id)
    learned_words = {p.word for p in progress_list}

    # 优先选择已学单词
    available_words = [w for w in words if w.word in learned_words]
    if len(available_words) < word_count:
        # 补充未学单词
        remaining = [w for w in words if w.word not in learned_words]
        available_words.extend(remaining[:word_count - len(available_words)])

    # 随机选择
    import random
    selected = random.sample(available_words, min(word_count, len(available_words)))
    word_list = [w.word for w in selected]

    # 调用阿里云百炼 Qwen-Plus 生成短文

    # 获取单词的中文释义，帮助 LLM 理解语境
    word_meanings = []
    for w in selected:
        word_meanings.append(f"{w.word}（{w.translation}）")

    prompt = f"""你是一位资深英语教师和故事创作者。请根据以下单词，创作一个有趣的英语小故事（3-5句话）。

【必须使用的单词】
{chr(10).join(word_meanings)}

【创作原则】
1. **先构思故事，再融入单词**：先想一个有趣的小场景（比如：周末郊游、课堂趣事、生日派对、宠物日常），然后把单词自然地编织进去
2. **因果关系**：句子之间要有"因为...所以..."、"首先...然后...最后..."这样的逻辑链条
3. **具体细节**：加入人名、地点、时间等具体细节，让故事更生动
4. **情感起伏**：故事最好有一点小转折或情感变化（惊喜、感动、好笑等）

【禁止事项】
❌ 禁止写成"定义句"：如 "A wife is a married woman." "Theirs means belonging to them."
❌ 禁止写成"孤立句"：如 "I have a son. The book is hers. We are the only students."（句子之间毫无关联）
❌ 禁止生硬过渡：如 "Speaking of...", "By the way...", "Also..."

【优秀示例】
单词：son, wife, only, theirs, hers
✅ 好："Last Sunday, my son lost his favorite toy car at the park. My wife helped him look everywhere, but we only found a pink doll. 'That's not ours—it must be hers!' my son said, pointing at a little girl nearby. We returned the doll, and the girl's parents gave us a big smile. The toy car? It was in my son's pocket the whole time!"

❌ 差："My son is young. My wife is kind. This is the only book. The car is theirs. The bag is hers."

返回 JSON（只返回JSON，不要解释）：
{{"passage": "完整短文", "sentences": ["句子1", "句子2", ...], "words_used": ["已使用的单词列表"]}}"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是一位英语教师助手。回复使用JSON格式。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 500
                }
            )

            if response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"API 返回 {response.status_code}")

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # 解析 JSON（处理可能的 markdown 代码块）
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            data = json.loads(content)

            return {
                "passage": data.get("passage", ""),
                "sentences": data.get("sentences", []),
                "words_used": data.get("words_used", word_list)
            }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="LLM 返回格式错误")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成短文失败: {str(e)}")


@app.post("/api/reading/assess-sentence")
async def api_reading_assess_sentence(
    audio: UploadFile = File(...),
    sentence: str = Form(...),
    book_id: str = Form(...),
    user: dict = Depends(require_auth)
):
    """
    评估句子/段落发音

    使用 Azure Speech 评估整句或整段的发音
    """
    if not pronunciation_assessor.is_available():
        raise HTTPException(status_code=503, detail="Azure Speech 服务未配置")

    # 读取音频数据
    audio_data = await audio.read()
    print(f"[DEBUG] 收到音频数据: {len(audio_data)} bytes")
    print(f"[DEBUG] 参考文本: {sentence[:100]}...")

    # 获取文件扩展名
    filename = audio.filename or "recording.webm"
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    # 执行发音评估（使用句子作为参考文本）
    result = await pronunciation_assessor.assess_from_bytes(audio_data, sentence, ext)

    # 打印 Azure 返回的原始结果
    print(f"[DEBUG] Azure 评估结果: success={result.get('success')}")
    print(f"[DEBUG] accuracy_score={result.get('accuracy_score')}, fluency_score={result.get('fluency_score')}")
    print(f"[DEBUG] recognized_text={result.get('recognized_text', '')[:100]}")
    print(f"[DEBUG] word_scores count={len(result.get('word_scores', []))}")
    if result.get('error'):
        print(f"[DEBUG] error={result.get('error')}")

    if result.get("success"):
        # 从 word_scores 提取问题单词
        word_scores = result.get("word_scores", [])
        problem_words = []
        omitted_words = []  # 漏读的单词
        mispronounced_words = []  # 读错的单词

        for ws in word_scores:
            word = ws.get("word", "")
            accuracy = ws.get("accuracy", 0)
            error_type = ws.get("error_type", "None")

            # 漏读 (Omission) 或插入 (Insertion)
            if error_type == "Omission":
                omitted_words.append(word)
            elif error_type == "Mispronunciation" or accuracy < 60:
                mispronounced_words.append({"word": word, "accuracy": int(accuracy)})
            elif accuracy < 80:
                problem_words.append({"word": word, "accuracy": int(accuracy)})

        return {
            "success": True,
            "accuracy_score": result.get("accuracy_score", 0),
            "fluency_score": result.get("fluency_score", 0),
            "completeness_score": result.get("completeness_score", 0),
            "pronunciation_score": result.get("pronunciation_score", 0),
            "recognized_text": result.get("recognized_text", ""),
            "problem_words": problem_words,
            "omitted_words": omitted_words,
            "mispronounced_words": mispronounced_words,
            "word_scores": word_scores
        }
    else:
        return {
            "success": False,
            "error": result.get("error", "评估失败")
        }


class ReadingFeedbackRequest(BaseModel):
    passage: str
    sentences: List[str]
    sentence_results: List[dict]
    overall_score: int
    omitted_words: Optional[List[str]] = []
    mispronounced_words: Optional[List[dict]] = []


@app.post("/api/reading/feedback")
async def api_reading_feedback(
    data: ReadingFeedbackRequest,
    user: dict = Depends(require_auth)
):
    """
    生成跟读练习的总体评价

    使用 LLM 分析发音问题并给出改进建议
    """
    if not QWEN_AVAILABLE:
        # 返回默认评价
        return {
            "overall_score": data.overall_score,
            "feedback": f"准确度 {data.overall_score}%",
            "problems": [],
            "suggestions": []
        }

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return {
            "overall_score": data.overall_score,
            "feedback": f"你的发音得分是{data.overall_score}分。",
            "problems": [],
            "suggestions": []
        }

    # 整理各句评分
    sentence_scores = []
    problem_phonemes = []
    for i, result in enumerate(data.sentence_results):
        if result:
            score = result.get("accuracy", 0)
            sentence_scores.append(f"句{i+1}: {score}%")
            # 收集问题单词/音素
            for pw in result.get("problemWords", []):
                problem_phonemes.append(f"{pw.get('word', '')}({pw.get('accuracy', 0)}%)")

    # 整理漏读和读错单词
    omitted_str = ', '.join(data.omitted_words) if data.omitted_words else '无'
    mispronounced_str = ', '.join([f"{pw.get('word', '')}({pw.get('accuracy', 0)}%)" for pw in (data.mispronounced_words or [])]) if data.mispronounced_words else '无'

    prompt = f"""根据发音评估结果，简洁客观地总结。

短文：{data.passage}
各句评分：{', '.join(sentence_scores)}
总体得分：{data.overall_score}%
漏读单词：{omitted_str}
读错单词：{mispronounced_str}
其他问题单词：{', '.join(problem_phonemes) if problem_phonemes else '无'}

要求：
1. problems: 列出具体问题（漏读哪些词、读错哪些词）
2. suggestions: 针对漏读和读错的单词，给出1-2条具体练习建议

不要鼓励性语言，直接陈述事实。如果没有漏读或读错，可以不列出。

返回 JSON：
{{"overall_score": {data.overall_score}, "problems": ["具体问题"], "suggestions": ["具体建议"]}}"""

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是发音评估助手，客观简洁地总结评估结果，不要鼓励性语言。回复JSON格式。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 300
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                # 解析 JSON（处理可能的 markdown 代码块）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return json.loads(content)
            else:
                return {
                    "overall_score": data.overall_score,
                    "feedback": f"准确度 {data.overall_score}%",
                    "problems": [],
                    "suggestions": []
                }

    except Exception as e:
        return {
            "overall_score": data.overall_score,
            "feedback": f"准确度 {data.overall_score}%",
            "problems": [],
            "suggestions": []
        }


@app.get("/api/tts/chinese")
async def api_tts_chinese(text: str, user: dict = Depends(require_auth)):
    """
    生成中文语音（需要认证）- 使用 Qwen3-TTS

    用于播放中文评价反馈
    """
    import hashlib

    # 缓存策略
    cache_key = hashlib.md5(text.encode()).hexdigest()[:12]

    # 优先使用 Qwen3-TTS
    if QWEN_TTS_AVAILABLE:
        cache_file = AUDIO_CACHE_DIR / f"zh_{cache_key}.wav"

        if not cache_file.exists():
            try:
                tts = Qwen3TTS()
                audio_data = await tts.synthesize(text, language="Chinese")
                if audio_data:
                    with open(cache_file, 'wb') as f:
                        f.write(audio_data)
                else:
                    raise Exception("音频生成失败")
            except Exception as e:
                # 回退到 edge-tts
                if TTS_AVAILABLE:
                    cache_file = AUDIO_CACHE_DIR / f"zh_{cache_key}.mp3"
                    communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                    await communicate.save(str(cache_file))
                else:
                    raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

        media_type = "audio/wav" if str(cache_file).endswith(".wav") else "audio/mpeg"
        return FileResponse(str(cache_file), media_type=media_type)

    # 回退到 edge-tts
    if TTS_AVAILABLE:
        cache_file = AUDIO_CACHE_DIR / f"zh_{cache_key}.mp3"

        if not cache_file.exists():
            try:
                communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
                await communicate.save(str(cache_file))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"TTS 生成失败: {e}")

        return FileResponse(str(cache_file), media_type="audio/mpeg")

    raise HTTPException(status_code=503, detail="TTS 服务不可用")


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
