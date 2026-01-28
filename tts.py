"""
统一 TTS（语音合成）模块

使用 Edge-TTS (Microsoft Neural Voices) 进行语音合成，提供统一缓存。

架构：
    EdgeTTSEngine  - Microsoft Edge TTS 引擎（支持多种英文音色）
    TTSCache       - 统一文件缓存
    TTSService     - 门面服务（缓存 + 合成）

Usage:
    from tts import tts_service

    # 合成英文单词（默认美式男声）
    path = await tts_service.synthesize("hello", language="en", speed="normal")

    # 指定英式女声
    path = await tts_service.synthesize("hello", language="en", voice_id="gb-female")

    # 合成中文句子
    path = await tts_service.synthesize("你好世界", language="zh")

    # 查询可用英文音色
    voices = tts_service.get_english_voices()

    # 查询引擎信息
    info = tts_service.get_engine_info()
"""

import os
import hashlib
import tempfile
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ==================== Edge-TTS 引擎 ====================

class EdgeTTSEngine:
    """
    Microsoft Edge TTS 引擎

    特点：免费、无需 API Key、支持多语言和语速调节

    英文音色（4种）：
        us-male:   en-US-AndrewNeural  美式男声（默认）
        us-female: en-US-JennyNeural   美式女声
        gb-male:   en-GB-RyanNeural    英式男声
        gb-female: en-GB-LibbyNeural   英式女声

    中文默认：zh-CN-XiaoxiaoNeural（女声）
    """

    # 英文音色映射（voice_id → Edge-TTS voice name）
    ENGLISH_VOICES = {
        "us-male": "en-US-AndrewNeural",
        "us-female": "en-US-JennyNeural",
        "gb-male": "en-GB-RyanNeural",
        "gb-female": "en-GB-LibbyNeural",
    }

    DEFAULT_ENGLISH_VOICE_ID = "us-male"

    # 语言默认音色（中文等非英文语言）
    VOICES = {
        "zh": "zh-CN-XiaoxiaoNeural",
    }

    RATE_MAP = {
        "normal": "+0%",       # 1x
        "moderate": "-10%",    # 句子朗读用
        "slow": "-30%",        # 旧版慢速（兼容）
        "0.75x": "-25%",       # 0.75 倍速
        "0.5x": "-50%",        # 0.5 倍速
    }

    def __init__(self):
        self._available = None

    @property
    def name(self) -> str:
        return "Edge-TTS"

    def is_available(self) -> bool:
        if self._available is None:
            try:
                import edge_tts  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def resolve_voice(self, language: str = "en", voice_id: Optional[str] = None) -> str:
        """
        解析最终使用的 Edge-TTS voice name

        Args:
            language: "en" | "zh"
            voice_id: 英文音色 ID（如 "us-male", "gb-female"），仅对英文有效

        Returns:
            Edge-TTS voice name（如 "en-US-AndrewNeural"）
        """
        if language == "en":
            vid = voice_id or self.DEFAULT_ENGLISH_VOICE_ID
            return self.ENGLISH_VOICES.get(vid, self.ENGLISH_VOICES[self.DEFAULT_ENGLISH_VOICE_ID])
        return self.VOICES.get(language, self.VOICES["zh"])

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        speed: str = "normal",
        voice_id: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        合成语音

        Args:
            text: 要合成的文本
            language: "en" | "zh"
            speed: "slow" | "normal" | "moderate"
            voice_id: 英文音色 ID（如 "us-male", "gb-female"），仅对英文有效

        Returns:
            MP3 音频字节数据，失败返回 None
        """
        if not self.is_available():
            return None

        if not text or not text.strip():
            return None

        import edge_tts

        voice = self.resolve_voice(language, voice_id)
        rate = self.RATE_MAP.get(speed, "+0%")

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            communicate = edge_tts.Communicate(text, voice, rate=rate)
            await communicate.save(tmp_path)

            audio_data = Path(tmp_path).read_bytes()
            os.unlink(tmp_path)
            return audio_data

        except Exception as e:
            logger.warning("[Edge-TTS] 合成异常: %s: %s", type(e).__name__, e)
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass
            return None


# ==================== 缓存管理器 ====================

class TTSCache:
    """统一 TTS 缓存管理器"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def make_key(self, text: str, language: str, speed: str, voice_id: str = "") -> str:
        """
        生成缓存 key

        短文本（≤30字符且纯字母/空格）使用原文作为 key，方便调试。
        长文本或含特殊字符的使用 MD5 哈希。
        voice_id 用于区分不同英文音色的缓存。
        """
        safe = text.strip().lower()
        # 音色前缀：英文带 voice_id，中文不需要
        voice_prefix = f"{voice_id}_" if voice_id else ""

        if len(safe) <= 30 and all(c.isalpha() or c.isspace() for c in safe):
            file_safe = safe.replace(" ", "_")
            return f"{language}_{voice_prefix}{speed}_{file_safe}"
        else:
            text_hash = hashlib.md5(safe.encode()).hexdigest()[:12]
            return f"{language}_{voice_prefix}{speed}_{text_hash}"

    def get(self, cache_key: str) -> Optional[Path]:
        """查找缓存文件，存在则返回路径"""
        cache_file = self.cache_dir / f"{cache_key}.mp3"
        if cache_file.exists() and cache_file.stat().st_size > 0:
            return cache_file
        return None

    async def put(self, cache_key: str, audio_data: bytes) -> Path:
        """写入缓存文件并返回路径"""
        cache_file = self.cache_dir / f"{cache_key}.mp3"
        cache_file.write_bytes(audio_data)
        return cache_file


# ==================== TTS 服务（门面） ====================

class TTSService:
    """
    TTS 门面服务

    统一入口，管理缓存，调用 Edge-TTS 引擎。
    """

    def __init__(self, cache_dir: Path):
        self.engine = EdgeTTSEngine()
        self.cache = TTSCache(cache_dir)

    async def synthesize(
        self,
        text: str,
        language: str = "en",
        speed: str = "normal",
        voice_id: Optional[str] = None,
    ) -> Optional[Path]:
        """
        合成语音并返回缓存文件路径

        自动查缓存 → 合成 → 写入缓存

        Args:
            text: 要合成的文本
            language: "en" | "zh"
            speed: "slow" | "normal" | "moderate"
            voice_id: 英文音色 ID（如 "us-male", "gb-female"），仅对英文有效

        Returns:
            音频文件 Path，失败时返回 None
        """
        if not text or not text.strip():
            return None

        # 确定实际 voice_id（英文默认 us-male，中文忽略）
        effective_voice_id = ""
        if language == "en":
            effective_voice_id = voice_id or self.engine.DEFAULT_ENGLISH_VOICE_ID

        # 1. 查缓存
        cache_key = self.cache.make_key(text, language, speed, effective_voice_id)
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # 2. 合成
        if not self.engine.is_available():
            logger.error("[TTS] Edge-TTS 不可用")
            return None

        try:
            audio_data = await self.engine.synthesize(
                text=text,
                language=language,
                speed=speed,
                voice_id=voice_id,
            )
            if audio_data:
                path = await self.cache.put(cache_key, audio_data)
                logger.info("[TTS] 合成成功: %s...", text[:30])
                return path
        except Exception as e:
            logger.warning("[TTS] 合成失败: %s", e)

        return None

    def get_english_voices(self) -> list[dict]:
        """返回可用的英文音色列表"""
        return [
            {"id": vid, "name": vname, "default": vid == self.engine.DEFAULT_ENGLISH_VOICE_ID}
            for vid, vname in self.engine.ENGLISH_VOICES.items()
        ]

    def get_active_engine_name(self) -> Optional[str]:
        """返回引擎名称（如果可用）"""
        return self.engine.name if self.engine.is_available() else None

    def get_engine_info(self) -> list[dict]:
        """返回引擎状态信息"""
        return [
            {"name": self.engine.name, "available": self.engine.is_available()}
        ]


# ==================== 全局单例 ====================

_tts_service: Optional[TTSService] = None


def init_tts_service(cache_dir: Path) -> TTSService:
    """初始化全局 TTS 服务（在 server.py 启动时调用）"""
    global _tts_service
    _tts_service = TTSService(cache_dir)
    logger.info(
        "[TTS] 服务初始化完成，引擎: %s",
        _tts_service.get_active_engine_name() or "不可用",
    )
    return _tts_service


def get_tts_service() -> TTSService:
    """获取全局 TTS 服务实例"""
    if _tts_service is None:
        raise RuntimeError("TTS 服务尚未初始化，请先调用 init_tts_service()")
    return _tts_service
