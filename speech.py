"""
Azure Speech 语音识别模块

提供语音转文字功能，可复用于：
- 对话练习中的学生回复识别
- 未来的口语评测功能

Usage:
    from speech import SpeechRecognizer

    recognizer = SpeechRecognizer()
    result = await recognizer.recognize_from_bytes(audio_data)
"""

import os
import tempfile
import asyncio
import threading
from typing import Optional

# Azure Speech SDK
try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_SPEECH_AVAILABLE = True
except ImportError:
    AZURE_SPEECH_AVAILABLE = False
    speechsdk = None


class SpeechRecognizer:
    """Azure Speech 语音识别器"""

    def __init__(self):
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = os.getenv("AZURE_SPEECH_REGION", "eastasia")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return AZURE_SPEECH_AVAILABLE and bool(self.speech_key)

    def _recognize_sync(self, audio_path: str) -> dict:
        """
        同步识别音频文件（内部方法）
        使用连续识别模式，支持较长的语音输入

        Args:
            audio_path: 音频文件路径

        Returns:
            识别结果字典
        """
        if not self.is_available():
            return {"success": False, "text": "", "error": "Azure Speech 未配置"}

        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key,
                region=self.speech_region
            )
            speech_config.speech_recognition_language = "en-US"

            audio_config = speechsdk.AudioConfig(filename=audio_path)
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )

            # 使用连续识别收集完整音频中的所有语句
            all_texts = []
            done_event = threading.Event()
            error_info = {"error": None}

            def on_recognized(evt):
                if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
                    all_texts.append(evt.result.text)

            def on_canceled(evt):
                cancellation = evt.cancellation_details
                if cancellation.reason == speechsdk.CancellationReason.Error:
                    error_info["error"] = f"识别取消: {cancellation.reason}, {cancellation.error_details}"
                done_event.set()

            def on_session_stopped(evt):
                done_event.set()

            recognizer.recognized.connect(on_recognized)
            recognizer.canceled.connect(on_canceled)
            recognizer.session_stopped.connect(on_session_stopped)

            recognizer.start_continuous_recognition()
            done_event.wait(timeout=30)
            recognizer.stop_continuous_recognition()

            if error_info["error"]:
                return {"success": False, "text": "", "error": error_info["error"]}

            if all_texts:
                full_text = " ".join(all_texts)
                return {
                    "success": True,
                    "text": full_text,
                    "confidence": 0.9,
                    "error": None
                }
            else:
                return {"success": False, "text": "", "error": "未识别到语音"}

        except Exception as e:
            return {"success": False, "text": "", "error": str(e)}

    async def recognize_from_file(self, audio_path: str) -> dict:
        """
        从音频文件识别文字

        Args:
            audio_path: 音频文件路径（支持 wav, mp3, webm）

        Returns:
            {
                "success": True,
                "text": "识别的文本",
                "confidence": 0.9,
                "error": None
            }
        """
        # 在线程池中运行同步识别
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._recognize_sync, audio_path)

    async def recognize_from_bytes(self, audio_data: bytes, file_ext: str = ".wav") -> dict:
        """
        从音频字节流识别（用于前端上传）

        Args:
            audio_data: 音频数据字节
            file_ext: 文件扩展名（默认 .wav）

        Returns:
            识别结果字典
        """
        if not self.is_available():
            return {"success": False, "text": "", "error": "Azure Speech 服务未配置"}

        # 需要将 webm 转换为 wav 格式
        if file_ext in [".webm", ".ogg", ".mp4", ".m4a"]:
            converted_data = await self._convert_to_wav(audio_data, file_ext)
            if converted_data is None:
                return {"success": False, "text": "", "error": "音频格式转换失败"}
            audio_data = converted_data
            file_ext = ".wav"

        # 临时保存文件后识别
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            return await self.recognize_from_file(temp_path)
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass

    async def _convert_to_wav(self, audio_data: bytes, source_ext: str) -> Optional[bytes]:
        """
        将音频转换为 Azure Speech SDK 兼容的 WAV 格式

        Azure Speech 需要特定格式:
        - PCM 16-bit
        - 16kHz 采样率
        - 单声道
        - 标准 RIFF WAV 头
        """
        import subprocess

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as src_file:
            src_file.write(audio_data)
            src_path = src_file.name

        # 使用不同的文件名避免冲突
        dst_path = tempfile.mktemp(suffix=".wav")

        try:
            # 使用 ffmpeg 转换 - 添加 -f wav 确保输出格式正确
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",                    # 覆盖输出文件
                "-i", src_path,          # 输入文件
                "-acodec", "pcm_s16le",  # PCM 16-bit little-endian
                "-ar", "16000",          # 16kHz 采样率
                "-ac", "1",              # 单声道
                "-f", "wav",             # 强制 WAV 格式
                dst_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                print(f"[FFmpeg] 转换失败: {stderr.decode()}")
                return None

            if os.path.exists(dst_path):
                with open(dst_path, "rb") as f:
                    wav_data = f.read()
                print(f"[FFmpeg] 转换成功: {len(audio_data)} -> {len(wav_data)} bytes")
                return wav_data
            return None

        except Exception as e:
            print(f"[FFmpeg] 音频转换异常: {e}")
            return None

        finally:
            # 清理临时文件
            try:
                os.unlink(src_path)
            except:
                pass
            try:
                os.unlink(dst_path)
            except:
                pass


class PronunciationAssessor:
    """Azure Speech 发音评估器"""

    def __init__(self):
        self.speech_key = os.getenv("AZURE_SPEECH_KEY")
        self.speech_region = os.getenv("AZURE_SPEECH_REGION", "eastasia")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return AZURE_SPEECH_AVAILABLE and bool(self.speech_key)

    def _assess_sync(self, audio_path: str, reference_text: str) -> dict:
        """
        同步发音评估（内部方法）

        Args:
            audio_path: 音频文件路径
            reference_text: 参考文本（单词）

        Returns:
            评估结果字典
        """
        if not self.is_available():
            return {"success": False, "error": "Azure Speech 未配置"}

        print(f"[Azure Speech] 开始评估, 音频: {audio_path}")
        print(f"[Azure Speech] 参考文本长度: {len(reference_text)} 字符")

        try:
            # 语音配置
            speech_config = speechsdk.SpeechConfig(
                subscription=self.speech_key,
                region=self.speech_region
            )
            speech_config.speech_recognition_language = "en-US"

            # 发音评估配置
            pronunciation_config = speechsdk.PronunciationAssessmentConfig(
                reference_text=reference_text,
                grading_system=speechsdk.PronunciationAssessmentGradingSystem.HundredMark,
                granularity=speechsdk.PronunciationAssessmentGranularity.Phoneme,
                enable_miscue=True
            )
            # 使用 IPA 音标
            pronunciation_config.phoneme_alphabet = "IPA"

            # 音频配置
            audio_config = speechsdk.AudioConfig(filename=audio_path)

            # 创建识别器并应用发音评估配置
            recognizer = speechsdk.SpeechRecognizer(
                speech_config=speech_config,
                audio_config=audio_config
            )
            pronunciation_config.apply_to(recognizer)

            # 执行识别
            result = recognizer.recognize_once()

            print(f"[Azure Speech] 识别结果原因: {result.reason}")

            if result.reason == speechsdk.ResultReason.RecognizedSpeech:
                # 获取发音评估结果
                pronunciation_result = speechsdk.PronunciationAssessmentResult(result)

                # 获取详细 JSON 结果
                json_result = result.properties.get(
                    speechsdk.PropertyId.SpeechServiceResponse_JsonResult
                )

                # 解析音素级别详情
                phoneme_details = self._extract_phoneme_details(json_result)

                # 解析单词级别得分（用于句子评估）
                word_scores = self._extract_word_scores(json_result)

                print(f"[Azure Speech] 识别文本: {result.text}")
                print(f"[Azure Speech] 准确度: {pronunciation_result.accuracy_score}, 流利度: {pronunciation_result.fluency_score}")
                print(f"[Azure Speech] 完整度: {pronunciation_result.completeness_score}, 发音分: {pronunciation_result.pronunciation_score}")
                print(f"[Azure Speech] 单词数: {len(word_scores)}")

                return {
                    "success": True,
                    "recognized_text": result.text,
                    "accuracy_score": pronunciation_result.accuracy_score,
                    "pronunciation_score": pronunciation_result.pronunciation_score,
                    "fluency_score": pronunciation_result.fluency_score,
                    "completeness_score": pronunciation_result.completeness_score,
                    "phoneme_details": phoneme_details,
                    "word_scores": word_scores,
                    "error": None
                }
            elif result.reason == speechsdk.ResultReason.NoMatch:
                return {"success": False, "error": "未识别到语音，请重试"}
            elif result.reason == speechsdk.ResultReason.Canceled:
                cancellation = result.cancellation_details
                return {
                    "success": False,
                    "error": f"评估取消: {cancellation.reason}"
                }
            else:
                return {"success": False, "error": f"评估失败: {result.reason}"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _extract_phoneme_details(self, json_result: str) -> list:
        """
        从 JSON 结果中提取音素级别详情

        Returns:
            [{"phoneme": "h", "accuracy": 95.0, "error_type": "None"}, ...]
        """
        if not json_result:
            return []

        try:
            import json
            data = json.loads(json_result)
            phonemes = []

            # 遍历 NBest 中的单词和音素
            for nbest in data.get("NBest", []):
                for word in nbest.get("Words", []):
                    word_error = word.get("PronunciationAssessment", {}).get("ErrorType", "None")

                    for phoneme in word.get("Phonemes", []):
                        pa = phoneme.get("PronunciationAssessment", {})
                        accuracy = pa.get("AccuracyScore", 0)

                        # 如果音素准确度低于60分，标记错误类型
                        error_type = "None"
                        if accuracy < 60:
                            error_type = word_error if word_error != "None" else "Mispronunciation"

                        phonemes.append({
                            "phoneme": phoneme.get("Phoneme", ""),
                            "accuracy": accuracy,
                            "error_type": error_type
                        })

            return phonemes
        except Exception as e:
            print(f"解析音素详情失败: {e}")
            return []

    def _extract_word_scores(self, json_result: str) -> list:
        """
        从 JSON 结果中提取单词级别得分

        用于句子/段落评估时获取每个单词的得分

        Returns:
            [{"word": "hello", "accuracy": 95.0, "error_type": "None"}, ...]
        """
        if not json_result:
            return []

        try:
            import json
            data = json.loads(json_result)
            word_scores = []

            # 遍历 NBest 中的单词
            for nbest in data.get("NBest", []):
                for word in nbest.get("Words", []):
                    word_text = word.get("Word", "")
                    pa = word.get("PronunciationAssessment", {})
                    accuracy = pa.get("AccuracyScore", 0)
                    error_type = pa.get("ErrorType", "None")

                    word_scores.append({
                        "word": word_text,
                        "accuracy": accuracy,
                        "error_type": error_type
                    })

            return word_scores
        except Exception as e:
            print(f"解析单词得分失败: {e}")
            return []

    async def assess_from_bytes(self, audio_data: bytes, reference_text: str,
                                 file_ext: str = ".wav") -> dict:
        """
        从音频字节流进行发音评估

        Args:
            audio_data: 音频数据字节
            reference_text: 参考文本（单词）
            file_ext: 文件扩展名

        Returns:
            评估结果字典
        """
        if not self.is_available():
            return {"success": False, "error": "Azure Speech 服务未配置"}

        # 转换音频格式（如需要）
        if file_ext in [".webm", ".ogg", ".mp4", ".m4a"]:
            converted_data = await self._convert_to_wav(audio_data, file_ext)
            if converted_data is None:
                return {"success": False, "error": "音频格式转换失败"}
            audio_data = converted_data
            file_ext = ".wav"

        # 临时保存文件后评估
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, self._assess_sync, temp_path, reference_text
            )
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass

    async def _convert_to_wav(self, audio_data: bytes, source_ext: str) -> Optional[bytes]:
        """
        将音频转换为 Azure Speech SDK 兼容的 WAV 格式

        Azure Speech 需要特定格式:
        - PCM 16-bit
        - 16kHz 采样率
        - 单声道
        - 标准 RIFF WAV 头
        """
        import subprocess

        # 检查音频数据大小
        if len(audio_data) < 1000:
            print(f"[FFmpeg] 音频数据太小: {len(audio_data)} bytes，可能录音时间太短")
            return None

        # 检查 webm 文件头
        if source_ext == ".webm":
            # WebM 文件应以 EBML 头开始 (0x1A 0x45 0xDF 0xA3)
            if len(audio_data) >= 4:
                header = audio_data[:4]
                if header != b'\x1a\x45\xdf\xa3':
                    print(f"[FFmpeg] WebM 文件头异常: {header.hex()}，预期: 1a45dfa3")

        print(f"[FFmpeg] 开始转换: {len(audio_data)} bytes, 格式: {source_ext}")

        # 创建临时文件
        with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as src_file:
            src_file.write(audio_data)
            src_path = src_file.name

        # 使用不同的文件名避免冲突
        dst_path = tempfile.mktemp(suffix=".wav")

        try:
            # 使用 ffmpeg 转换 - 添加 -f wav 确保输出格式正确
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",                    # 覆盖输出文件
                "-i", src_path,          # 输入文件
                "-acodec", "pcm_s16le",  # PCM 16-bit little-endian
                "-ar", "16000",          # 16kHz 采样率
                "-ac", "1",              # 单声道
                "-f", "wav",             # 强制 WAV 格式
                dst_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                stderr_text = stderr.decode() if stderr else "无错误信息"
                print(f"[FFmpeg] 转换失败 (returncode={process.returncode}):")
                print(f"[FFmpeg] stderr: {stderr_text}")
                return None

            if os.path.exists(dst_path):
                with open(dst_path, "rb") as f:
                    wav_data = f.read()
                print(f"[FFmpeg] 转换成功: {len(audio_data)} -> {len(wav_data)} bytes")
                return wav_data

            print(f"[FFmpeg] 输出文件不存在: {dst_path}")
            return None

        except FileNotFoundError:
            print("[FFmpeg] FFmpeg 未安装或不在 PATH 中")
            return None
        except Exception as e:
            print(f"[FFmpeg] 音频转换异常: {type(e).__name__}: {e}")
            return None

        finally:
            try:
                os.unlink(src_path)
            except:
                pass
            try:
                os.unlink(dst_path)
            except:
                pass


def generate_feedback_text(assessment_result: dict, word: str) -> str:
    """
    根据评估结果生成中文反馈文本

    Args:
        assessment_result: 发音评估结果
        word: 目标单词

    Returns:
        中文反馈文本
    """
    if not assessment_result.get("success"):
        return "没有听清楚，请再试一次。"

    accuracy = assessment_result.get("accuracy_score", 0)
    phoneme_details = assessment_result.get("phoneme_details", [])

    # 找出发音有问题的音素
    problem_phonemes = [
        p for p in phoneme_details
        if p.get("accuracy", 100) < 60 or p.get("error_type") != "None"
    ]

    if accuracy >= 90:
        return "非常好！发音很标准。"
    elif accuracy >= 75:
        return "不错！发音基本正确。"
    elif accuracy >= 60:
        if problem_phonemes:
            phoneme_str = "、".join([p["phoneme"] for p in problem_phonemes[:3]])
            return f"还可以，注意 {phoneme_str} 的发音。"
        return "还可以，继续练习。"
    else:
        if problem_phonemes:
            # 分析错误类型
            omissions = [p for p in problem_phonemes if p.get("error_type") == "Omission"]
            if omissions:
                return "有些音漏掉了，再听一遍标准发音。"
            return "发音需要改进，请仔细听标准发音后再试。"
        return "发音需要改进，请再试一次。"


# ==================== 大模型智能点评 ====================

# 准确度阈值：低于此值触发大模型点评和练习推荐
ACCURACY_THRESHOLD = 75


async def generate_ai_feedback(
    word: str,
    accuracy_score: float,
    phoneme_details: list,
    letter_mapping: list = None
) -> dict:
    """
    使用阿里云百炼 Qwen-Plus 生成智能发音点评

    Args:
        word: 目标单词
        accuracy_score: 总体准确度分数
        phoneme_details: 音素级别评估详情
        letter_mapping: 字母-音素映射（可选）

    Returns:
        {
            "feedback": "点评文本",
            "practice_words": ["word1", "word2", "word3"],
            "problem_phonemes": [{"phoneme": "θ", "accuracy": 45}],
            "tips": "发音技巧提示"
        }
    """
    import os
    import httpx

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        # 没有配置 API，返回基础反馈
        return _generate_basic_feedback(word, accuracy_score, phoneme_details)

    # 找出问题音素（阈值75分，低于此分数需要练习）
    problem_phonemes = [
        {"phoneme": p["phoneme"], "accuracy": p.get("accuracy", 0)}
        for p in phoneme_details
        if p.get("accuracy", 100) < 75 or p.get("error_type", "None") != "None"
    ]

    # 构建提示词
    phoneme_info = "\n".join([
        f"- /{p['phoneme']}/: {p['accuracy']:.0f}分"
        for p in phoneme_details
    ])

    problem_info = ""
    if problem_phonemes:
        problem_info = "问题音素：" + ", ".join([
            f"/{p['phoneme']}/ ({p['accuracy']:.0f}分)"
            for p in problem_phonemes
        ])

    prompt = f"""你是一个专业的英语发音教练。请根据评估结果直接指出问题，不要使用空洞的表扬。

单词: {word}
总体准确度: {accuracy_score:.0f}分

各音素得分:
{phoneme_info}

{problem_info}

请用中文回复，格式如下（JSON）:
{{
    "feedback": "直接指出问题（15字以内，不要表扬）",
    "tips": "具体的改进方法（30字以内）",
    "focus_phoneme": "最需要注意的一个音素（IPA格式，如 θ）",
    "practice_words": [
        {{"word": "football", "pos": "n.", "meaning": "足球"}},
        {{"word": "basketball", "pos": "n.", "meaning": "篮球"}},
        {{"word": "baseball", "pos": "n.", "meaning": "棒球"}}
    ]
}}

要求：
1. 禁止使用"不错""很好""继续加油"等空洞表扬
2. 只要有任何音素<75分，必须指出具体问题音素
3. 所有音素>=75分时，feedback 写"发音正确"即可
4. tips 必须包含具体的发音技巧（舌位、口型、气流等）
5. practice_words（重要）：只要有任何音素<75分，就必须推荐3个包含该问题音素的练习单词
   - 每个包含 word（英文）、pos（词性）、meaning（中文释义，5字以内）
   - 必须选择包含 focus_phoneme 这个音素的单词
   - 单词要简单常用（适合初中生）
   - 只有所有音素>=75分时才可以为空数组"""

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
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 200
                }
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # 解析 JSON 响应
                import json
                import re

                # 提取 JSON 部分（支持嵌套）
                # 找到第一个 { 和最后一个 } 之间的内容
                start_idx = content.find('{')
                end_idx = content.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx + 1]
                    ai_result = json.loads(json_str)

                    # 获取大模型推荐的练习单词（现在是对象数组）
                    practice_words = ai_result.get("practice_words", [])
                    # 确保是对象格式，并过滤掉当前单词
                    filtered_words = []
                    for pw in practice_words:
                        if isinstance(pw, dict):
                            pw_word = pw.get("word", "")
                            if pw_word.lower() != word.lower():
                                filtered_words.append({
                                    "word": pw_word,
                                    "pos": pw.get("pos", ""),
                                    "meaning": pw.get("meaning", "")
                                })
                        elif isinstance(pw, str) and pw.lower() != word.lower():
                            # 兼容旧格式（纯字符串）
                            filtered_words.append({"word": pw, "pos": "", "meaning": ""})
                    practice_words = filtered_words[:3]

                    return {
                        "feedback": ai_result.get("feedback", "继续练习！"),
                        "tips": ai_result.get("tips", ""),
                        "practice_words": practice_words,
                        "problem_phonemes": problem_phonemes,
                        "focus_phoneme": ai_result.get("focus_phoneme", "")
                    }

    except Exception as e:
        print(f"AI 点评生成失败: {e}")

    # 失败时返回基础反馈
    return _generate_basic_feedback(word, accuracy_score, phoneme_details)


def _generate_basic_feedback(word: str, accuracy_score: float, phoneme_details: list) -> dict:
    """生成基础反馈（无 AI 时使用）"""
    # 阈值75分，低于此分数的音素需要练习
    problem_phonemes = [
        {"phoneme": p["phoneme"], "accuracy": p.get("accuracy", 0)}
        for p in phoneme_details
        if p.get("accuracy", 100) < 75 or p.get("error_type", "None") != "None"
    ]

    # 优先根据问题音素给出反馈，而非总分
    if not problem_phonemes:
        # 所有音素都>=75分
        feedback = "发音正确"
        tips = ""
        focus_phoneme = ""
    else:
        # 有问题音素，按最低分排序
        problem_phonemes.sort(key=lambda x: x["accuracy"])
        focus_phoneme = problem_phonemes[0]["phoneme"]
        worst_score = problem_phonemes[0]["accuracy"]

        if worst_score < 40:
            phoneme_str = "、".join([f"/{p['phoneme']}/" for p in problem_phonemes[:3]])
            feedback = f"{phoneme_str} 需要重点练习"
            tips = "放慢语速，一个音一个音地跟读"
        elif worst_score < 60:
            phoneme_str = "、".join([f"/{p['phoneme']}/" for p in problem_phonemes[:2]])
            feedback = f"{phoneme_str} 发音错误"
            tips = "先听标准发音，再模仿口型和舌位"
        else:
            feedback = f"/{focus_phoneme}/ 发音不准（{worst_score:.0f}分）"
            tips = "对照音标，注意舌位和口型"

    return {
        "feedback": feedback,
        "tips": tips,
        "practice_words": [],  # 基础模式不推荐单词（需要 AI）
        "problem_phonemes": problem_phonemes,
        "focus_phoneme": focus_phoneme
    }


# 便捷函数
async def recognize_speech(audio_data: bytes, file_ext: str = ".wav") -> dict:
    """识别语音的便捷函数"""
    recognizer = SpeechRecognizer()
    return await recognizer.recognize_from_bytes(audio_data, file_ext)


async def assess_pronunciation(audio_data: bytes, reference_text: str, file_ext: str = ".wav") -> dict:
    """发音评估的便捷函数"""
    assessor = PronunciationAssessor()
    return await assessor.assess_from_bytes(audio_data, reference_text, file_ext)


# ==================== 阿里云百炼 Qwen3-ASR 中文语音识别 ====================

class QwenChineseSpeechRecognizer:
    """
    阿里云百炼 Qwen3-ASR-Flash 中文语音识别器

    用于中文翻译练习中识别学生说的中文翻译

    使用方法：
        recognizer = QwenChineseSpeechRecognizer()
        result = await recognizer.recognize_from_bytes(audio_data, ".webm")
        print(result["text"])  # 识别的中文文本
    """

    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)

    async def recognize_from_bytes(
        self,
        audio_data: bytes,
        file_ext: str = ".wav",
        context_words: list = None
    ) -> dict:
        """
        从音频字节流识别中文

        Args:
            audio_data: 音频数据字节
            file_ext: 文件扩展名（.wav, .webm, .ogg, .mp3）
            context_words: 上下文单词列表，用于提高识别准确率（可选）

        Returns:
            {
                "success": True,
                "text": "识别的中文文本",
                "error": None
            }
        """
        if not self.is_available():
            return {"success": False, "text": "", "error": "阿里云百炼 API 未配置"}

        try:
            import dashscope
            from dashscope import MultiModalConversation

            # 设置 API 配置
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

            # 需要将音频转换为 WAV 格式
            if file_ext in [".webm", ".ogg", ".mp4", ".m4a"]:
                converted_data = await self._convert_to_wav(audio_data, file_ext)
                if converted_data is None:
                    return {"success": False, "text": "", "error": "音频格式转换失败"}
                audio_data = converted_data
                file_ext = ".wav"

            # 保存到临时文件（SDK 需要文件路径）
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            try:
                # 构建消息
                messages = []

                # 上下文增强（可选）- 传入相关单词可提高识别准确率
                if context_words:
                    context = "，".join(context_words[:10])  # 最多10个
                    messages.append({
                        "role": "system",
                        "content": [{"text": f"当前学习的单词释义包括：{context}"}]
                    })
                else:
                    messages.append({
                        "role": "system",
                        "content": [{"text": ""}]
                    })

                # 添加音频
                messages.append({
                    "role": "user",
                    "content": [{"audio": f"file://{temp_path}"}]
                })

                # 在线程池中运行同步调用
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: MultiModalConversation.call(
                        model="qwen3-asr-flash",
                        messages=messages,
                        result_format="message",
                        asr_options={
                            "language": "zh",  # 指定中文
                            "enable_itn": True  # 启用逆文本正则化
                        }
                    )
                )

                if response.status_code == 200:
                    # 提取识别结果
                    output = response.output
                    choices = output.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", [])
                        if content and len(content) > 0:
                            recognized_text = content[0].get("text", "")
                            return {
                                "success": True,
                                "text": recognized_text,
                                "error": None
                            }

                    return {"success": False, "text": "", "error": "响应中无识别内容"}
                else:
                    return {
                        "success": False,
                        "text": "",
                        "error": f"API 错误: {response.code} - {response.message}"
                    }

            finally:
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except ImportError:
            return {"success": False, "text": "", "error": "dashscope SDK 未安装"}
        except Exception as e:
            return {"success": False, "text": "", "error": str(e)}

    async def _convert_to_wav(self, audio_data: bytes, source_ext: str) -> Optional[bytes]:
        """将音频转换为 WAV 格式"""
        if len(audio_data) < 1000:
            print(f"[Qwen-ASR] 音频数据太小: {len(audio_data)} bytes")
            return None

        with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as src_file:
            src_file.write(audio_data)
            src_path = src_file.name

        dst_path = tempfile.mktemp(suffix=".wav")

        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i", src_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                dst_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                print(f"[Qwen-ASR] FFmpeg 转换失败: {stderr.decode()}")
                return None

            if os.path.exists(dst_path):
                with open(dst_path, "rb") as f:
                    return f.read()
            return None

        except Exception as e:
            print(f"[Qwen-ASR] 音频转换异常: {e}")
            return None

        finally:
            try:
                os.unlink(src_path)
            except:
                pass
            try:
                os.unlink(dst_path)
            except:
                pass


# ==================== 阿里云百炼 Qwen3-ASR 英文语音识别 ====================

class QwenEnglishSpeechRecognizer:
    """
    阿里云百炼 Qwen3-ASR-Flash 英文语音识别器

    用于跟读练习中识别学生说的英文单词

    使用方法：
        recognizer = QwenEnglishSpeechRecognizer()
        result = await recognizer.recognize_from_bytes(audio_data, ".webm")
        print(result["text"])  # 识别的英文文本
    """

    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)

    async def recognize_from_bytes(
        self,
        audio_data: bytes,
        file_ext: str = ".wav",
        target_word: str = None
    ) -> dict:
        """
        从音频字节流识别英文

        Args:
            audio_data: 音频数据字节
            file_ext: 文件扩展名（.wav, .webm, .ogg, .mp3）
            target_word: 目标单词，用于提高识别准确率（可选）

        Returns:
            {
                "success": True,
                "text": "recognized english text",
                "is_correct": True/False,  # 是否与目标单词匹配
                "error": None
            }
        """
        if not self.is_available():
            return {"success": False, "text": "", "is_correct": False, "error": "阿里云百炼 API 未配置"}

        try:
            import dashscope
            from dashscope import MultiModalConversation

            # 设置 API 配置
            dashscope.api_key = self.api_key
            dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

            # 需要将音频转换为 WAV 格式
            if file_ext in [".webm", ".ogg", ".mp4", ".m4a"]:
                converted_data = await self._convert_to_wav(audio_data, file_ext)
                if converted_data is None:
                    return {"success": False, "text": "", "is_correct": False, "error": "音频格式转换失败"}
                audio_data = converted_data
                file_ext = ".wav"

            # 保存到临时文件（SDK 需要文件路径）
            with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            try:
                # 构建消息
                messages = []

                # 上下文增强（可选）
                if target_word:
                    messages.append({
                        "role": "system",
                        "content": [{"text": f"The expected word is: {target_word}"}]
                    })
                else:
                    messages.append({
                        "role": "system",
                        "content": [{"text": ""}]
                    })

                # 添加音频
                messages.append({
                    "role": "user",
                    "content": [{"audio": f"file://{temp_path}"}]
                })

                # 在线程池中运行同步调用
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: MultiModalConversation.call(
                        model="qwen3-asr-flash",
                        messages=messages,
                        result_format="message",
                        asr_options={
                            "language": "en",  # 指定英文
                            "enable_itn": True
                        }
                    )
                )

                if response.status_code == 200:
                    # 提取识别结果
                    output = response.output
                    choices = output.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", [])
                        if content and len(content) > 0:
                            recognized_text = content[0].get("text", "").strip()

                            # 判断是否与目标单词匹配
                            is_correct = False
                            if target_word and recognized_text:
                                # 忽略大小写比较
                                is_correct = recognized_text.lower() == target_word.lower()

                            return {
                                "success": True,
                                "text": recognized_text,
                                "is_correct": is_correct,
                                "error": None
                            }

                    return {"success": False, "text": "", "is_correct": False, "error": "响应中无识别内容"}
                else:
                    return {
                        "success": False,
                        "text": "",
                        "is_correct": False,
                        "error": f"API 错误: {response.code} - {response.message}"
                    }

            finally:
                try:
                    os.unlink(temp_path)
                except:
                    pass

        except ImportError:
            return {"success": False, "text": "", "is_correct": False, "error": "dashscope SDK 未安装"}
        except Exception as e:
            return {"success": False, "text": "", "is_correct": False, "error": str(e)}

    async def _convert_to_wav(self, audio_data: bytes, source_ext: str) -> Optional[bytes]:
        """将音频转换为 WAV 格式"""
        if len(audio_data) < 1000:
            print(f"[Qwen-ASR-EN] 音频数据太小: {len(audio_data)} bytes")
            return None

        with tempfile.NamedTemporaryFile(suffix=source_ext, delete=False) as src_file:
            src_file.write(audio_data)
            src_path = src_file.name

        dst_path = tempfile.mktemp(suffix=".wav")

        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i", src_path,
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                "-f", "wav",
                dst_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                print(f"[Qwen-ASR-EN] FFmpeg 转换失败: {stderr.decode()}")
                return None

            if os.path.exists(dst_path):
                with open(dst_path, "rb") as f:
                    return f.read()
            return None

        except Exception as e:
            print(f"[Qwen-ASR-EN] 音频转换异常: {e}")
            return None

        finally:
            try:
                os.unlink(src_path)
            except:
                pass
            try:
                os.unlink(dst_path)
            except:
                pass


# ==================== 阿里云百炼 Qwen-Plus 翻译评价 ====================

async def generate_translation_feedback(
    english: str,
    reference: str,
    user_text: str,
    similarity: float = 0.0
) -> dict:
    """
    使用阿里云百炼 Qwen-Plus 评价翻译结果

    Args:
        english: 英文原文
        reference: 标准中文翻译
        user_text: 用户说的中文
        similarity: 文本相似度（0-1）

    Returns:
        {
            "correct": True/False,
            "feedback": "简短评价",
            "issues": ["问题1", "问题2"],
            "suggestion": "改进建议"
        }
    """
    import httpx
    import json

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        # 无 API Key，使用简单判断
        return _simple_translation_feedback(reference, user_text, similarity)

    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    prompt = f"""学生正在练习英文到中文的翻译。

英文原文: {english}
标准翻译: {reference}
学生翻译: {user_text}

请评价学生的翻译:
1. 是否正确传达了原文含义
2. 用词是否准确
3. 如有问题，指出具体错误

返回 JSON（不要加任何解释）:
{{
    "correct": true或false,
    "feedback": "10字以内的简短评价",
    "issues": ["问题1", "问题2"],
    "suggestion": "15字以内的改进建议，如无问题则为空字符串"
}}

注意：
- 如果意思相近、表达自然，应判定为正确
- 同义词替换（如"管理"和"掌管"）应视为正确
- 只有明显错误才判定为不正确"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是翻译评估助手，客观简洁地评价翻译结果。只回复JSON，不要任何解释。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 150
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 解析 JSON
                try:
                    # 提取 JSON 部分
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0].strip()
                    else:
                        json_str = content.strip()

                    parsed = json.loads(json_str)
                    return {
                        "correct": parsed.get("correct", False),
                        "feedback": parsed.get("feedback", ""),
                        "issues": parsed.get("issues", []),
                        "suggestion": parsed.get("suggestion", "")
                    }
                except json.JSONDecodeError:
                    # JSON 解析失败，尝试从文本判断
                    is_correct = "正确" in content or "correct" in content.lower()
                    return {
                        "correct": is_correct,
                        "feedback": content[:20] if content else "评价生成失败",
                        "issues": [],
                        "suggestion": ""
                    }
            else:
                print(f"[Qwen-Plus] API 错误: {response.status_code}")
                return _simple_translation_feedback(reference, user_text, similarity)

    except Exception as e:
        print(f"[Qwen-Plus] 翻译评价异常: {e}")
        return _simple_translation_feedback(reference, user_text, similarity)


def _simple_translation_feedback(reference: str, user_text: str, similarity: float) -> dict:
    """简单的翻译评价（无 AI 时使用）"""
    # 简单的文本相似度判断
    if not user_text:
        return {
            "correct": False,
            "feedback": "未识别到语音",
            "issues": ["语音识别失败"],
            "suggestion": "请重新录音"
        }

    # 计算简单相似度
    if similarity == 0:
        # 简单的字符重叠率
        ref_chars = set(reference)
        user_chars = set(user_text)
        if ref_chars:
            similarity = len(ref_chars & user_chars) / len(ref_chars)

    if similarity >= 0.7 or reference in user_text or user_text in reference:
        return {
            "correct": True,
            "feedback": "翻译正确",
            "issues": [],
            "suggestion": ""
        }
    elif similarity >= 0.4:
        return {
            "correct": False,
            "feedback": "翻译部分正确",
            "issues": ["含义不完整"],
            "suggestion": f"正确答案是：{reference}"
        }
    else:
        return {
            "correct": False,
            "feedback": "翻译错误",
            "issues": ["含义不符"],
            "suggestion": f"正确答案是：{reference}"
        }


async def evaluate_passage_translation(
    english_passage: str,
    user_translation: str
) -> dict:
    """
    使用阿里云百炼 Qwen-Plus 评估短文翻译

    Args:
        english_passage: 英文短文原文
        user_translation: 用户的中文翻译

    Returns:
        {
            "reference_translation": "AI参考翻译",
            "score": 85,
            "feedback": "整体评价",
            "strengths": ["优点1", "优点2"],
            "issues": ["问题1", "问题2"],
            "suggestion": "改进建议"
        }
    """
    import httpx
    import json

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        # 无 API Key，返回简单评估
        return _simple_passage_evaluation(english_passage, user_translation)

    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

    prompt = f"""你是英语教学专家。学生正在练习将英文短文翻译成中文。

【英文原文】
{english_passage}

【学生翻译】
{user_translation}

请完成以下任务：
1. 提供一个准确、自然的中文参考翻译
2. 评估学生翻译的质量（0-100分）
3. 分析学生翻译的优点和不足
4. 给出改进建议

评分标准：
- 90-100分：翻译准确流畅，表达自然
- 80-89分：基本准确，个别地方可以改进
- 60-79分：大意正确，但有明显翻译问题
- 0-59分：存在严重理解错误或漏译

返回 JSON 格式（不要加任何解释）：
{{
    "reference_translation": "你的参考翻译",
    "score": 85,
    "feedback": "20字以内的整体评价",
    "strengths": ["优点1", "优点2"],
    "issues": ["问题1", "问题2"],
    "suggestion": "30字以内的改进建议"
}}

注意：
- 评分要客观公正，鼓励学生
- 如果学生翻译的主要意思正确，分数应在60分以上
- 优点和问题各列出1-3条，没有则为空数组
- 建议要具体可操作"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                base_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是翻译评估专家。只回复JSON，不要任何解释。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                }
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # 解析 JSON
                try:
                    # 提取 JSON 部分
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0].strip()
                    else:
                        json_str = content.strip()

                    parsed = json.loads(json_str)
                    return {
                        "reference_translation": parsed.get("reference_translation", ""),
                        "score": int(parsed.get("score", 0)),
                        "feedback": parsed.get("feedback", ""),
                        "strengths": parsed.get("strengths", []),
                        "issues": parsed.get("issues", []),
                        "suggestion": parsed.get("suggestion", "")
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[短文翻译] JSON 解析失败: {e}, 原始内容: {content[:200]}")
                    return _simple_passage_evaluation(english_passage, user_translation)
            else:
                print(f"[短文翻译] API 错误: {response.status_code}")
                return _simple_passage_evaluation(english_passage, user_translation)

    except Exception as e:
        print(f"[短文翻译] 评估异常: {e}")
        return _simple_passage_evaluation(english_passage, user_translation)


def _simple_passage_evaluation(english_passage: str, user_translation: str) -> dict:
    """简单的短文翻译评估（无 AI 时使用）"""
    if not user_translation or len(user_translation.strip()) < 5:
        return {
            "reference_translation": "(无法生成参考翻译)",
            "score": 0,
            "feedback": "未识别到有效翻译",
            "strengths": [],
            "issues": ["翻译内容过短或未识别"],
            "suggestion": "请清晰地说出完整的中文翻译"
        }

    # 简单根据翻译长度给分
    passage_words = len(english_passage.split())
    translation_chars = len(user_translation)

    # 假设每个英文单词对应约2个中文字符
    expected_chars = passage_words * 2
    ratio = translation_chars / expected_chars if expected_chars > 0 else 0

    if ratio >= 0.8:
        score = 75
        feedback = "翻译较为完整"
    elif ratio >= 0.5:
        score = 60
        feedback = "翻译基本完成"
    elif ratio >= 0.3:
        score = 45
        feedback = "翻译不够完整"
    else:
        score = 30
        feedback = "翻译内容过少"

    return {
        "reference_translation": "(AI 服务不可用，无法生成参考翻译)",
        "score": score,
        "feedback": feedback,
        "strengths": ["已完成翻译尝试"] if translation_chars > 10 else [],
        "issues": ["无法进行详细评估"] if not os.getenv("DASHSCOPE_API_KEY") else [],
        "suggestion": "请确保翻译完整，包含所有句子的含义"
    }


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    计算两个中文文本的相似度

    Args:
        text1: 文本1
        text2: 文本2

    Returns:
        相似度 (0-1)
    """
    if not text1 or not text2:
        return 0.0

    # 简单的字符级别相似度
    chars1 = set(text1.replace(" ", "").replace("，", "").replace("。", ""))
    chars2 = set(text2.replace(" ", "").replace("，", "").replace("。", ""))

    if not chars1 or not chars2:
        return 0.0

    intersection = len(chars1 & chars2)
    union = len(chars1 | chars2)

    return intersection / union if union > 0 else 0.0


# 便捷函数
async def recognize_chinese_speech(audio_data: bytes, file_ext: str = ".wav") -> dict:
    """识别中文语音的便捷函数"""
    recognizer = QwenChineseSpeechRecognizer()
    return await recognizer.recognize_from_bytes(audio_data, file_ext)


# 命令行测试
if __name__ == "__main__":
    import sys

    # 加载环境变量
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    recognizer = SpeechRecognizer()

    print("Azure Speech 语音识别测试")
    print("=" * 50)
    print(f"服务可用: {recognizer.is_available()}")
    print(f"区域: {recognizer.speech_region}")
    print(f"API Key: {recognizer.speech_key[:10]}...{recognizer.speech_key[-4:]}" if recognizer.speech_key else "未配置")

    # 测试 Qwen 中文识别
    qwen_recognizer = QwenChineseSpeechRecognizer()
    print(f"\nQwen3-ASR 中文识别可用: {qwen_recognizer.is_available()}")

    if len(sys.argv) > 1:
        audio_file = sys.argv[1]
        print(f"\n识别文件: {audio_file}")

        async def test():
            result = await recognizer.recognize_from_file(audio_file)
            print(f"结果: {result}")

        asyncio.run(test())
