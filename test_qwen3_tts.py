"""
Qwen3-TTS-Flash 语音合成测试脚本

测试阿里云百炼 Qwen3-TTS-Flash 的语音合成功能
"""

import os
import asyncio
import base64
import httpx

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def download_audio(url: str) -> bytes:
    """从 URL 下载音频数据"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        if response.status_code == 200:
            return response.content
        else:
            raise Exception(f"下载失败: {response.status_code}")


async def test_qwen3_tts_non_streaming():
    """测试非流式语音合成"""
    import dashscope

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        print("错误: DASHSCOPE_API_KEY 未设置")
        return False

    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

    # 测试英文合成
    test_texts = [
        ("Hello, how are you today?", "English", "question"),
        ("I love learning English!", "English", "exclamation"),
        ("The weather is beautiful.", "English", "statement"),
        ("你好，欢迎来到英语学习应用！", "Chinese", "chinese"),
    ]

    print("=" * 60)
    print("Qwen3-TTS-Flash 非流式语音合成测试")
    print("=" * 60)

    for text, lang, desc in test_texts:
        print(f"\n测试 [{desc}]: {text}")

        try:
            response = dashscope.MultiModalConversation.call(
                model="qwen3-tts-flash",
                api_key=api_key,
                text=text,
                voice="Cherry",  # 活泼年轻女性
                language_type=lang,
                stream=False
            )

            print(f"  状态码: {response.status_code}")

            if response.status_code == 200:
                output = response.output

                # 检查 audio 字段（URL 方式返回）
                if hasattr(output, 'audio') and output.audio:
                    audio_info = output.audio
                    audio_url = audio_info.get('url', '')
                    audio_data = audio_info.get('data', '')

                    if audio_url:
                        print(f"  音频 URL: {audio_url[:80]}...")
                        # 下载音频
                        try:
                            audio_bytes = await download_audio(audio_url)
                            filename = f"test_{desc}.wav"
                            with open(filename, 'wb') as f:
                                f.write(audio_bytes)
                            print(f"  ✓ 音频保存: {filename} ({len(audio_bytes)} bytes)")
                        except Exception as e:
                            print(f"  下载失败: {e}")

                    elif audio_data:
                        # base64 数据方式
                        audio_bytes = base64.b64decode(audio_data)
                        filename = f"test_{desc}.wav"
                        with open(filename, 'wb') as f:
                            f.write(audio_bytes)
                        print(f"  ✓ 音频保存: {filename} ({len(audio_bytes)} bytes)")
                    else:
                        print(f"  音频信息: {audio_info}")
                else:
                    print(f"  输出结构: {output}")

            else:
                print(f"  错误: {response.code} - {response.message}")

        except Exception as e:
            print(f"  异常: {type(e).__name__}: {e}")

    return True


async def test_voices():
    """测试不同音色"""
    import dashscope

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return False

    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

    text = "Hello, I am your English teacher. Nice to meet you!"

    print("\n" + "=" * 60)
    print("测试不同音色")
    print("=" * 60)

    # 文档中提到的一些音色
    voices = ["Cherry", "Serena", "Ethan", "Chelsie"]

    for voice in voices:
        print(f"\n音色 {voice}:")

        try:
            response = dashscope.MultiModalConversation.call(
                model="qwen3-tts-flash",
                api_key=api_key,
                text=text,
                voice=voice,
                language_type="English",
                stream=False
            )

            if response.status_code == 200:
                output = response.output

                if hasattr(output, 'audio') and output.audio:
                    audio_url = output.audio.get('url', '')
                    if audio_url:
                        try:
                            audio_bytes = await download_audio(audio_url)
                            filename = f"test_voice_{voice}.wav"
                            with open(filename, 'wb') as f:
                                f.write(audio_bytes)
                            print(f"  ✓ 保存: {filename} ({len(audio_bytes)} bytes)")
                        except Exception as e:
                            print(f"  下载失败: {e}")
                    else:
                        print(f"  无 URL: {output.audio}")
                else:
                    print(f"  无 audio: {output}")

            else:
                print(f"  错误: {response.code} - {response.message}")

        except Exception as e:
            print(f"  异常: {e}")

    return True


async def test_sentence_types():
    """测试智能语调 - 不同句式"""
    import dashscope

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return False

    dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

    print("\n" + "=" * 60)
    print("测试智能语调（不同句式）")
    print("=" * 60)

    # 测试 Qwen3-TTS 的智能语调功能
    sentences = [
        ("What is your favorite color?", "疑问句-应该升调"),
        ("I am so happy today!", "感叹句-应该兴奋"),
        ("Please open your books.", "祈使句-应该平稳"),
        ("The cat is sleeping on the sofa.", "陈述句-应该平调"),
        ("Wow, that's amazing!", "惊叹-应该激动"),
    ]

    for text, desc in sentences:
        print(f"\n[{desc}]: {text}")

        try:
            response = dashscope.MultiModalConversation.call(
                model="qwen3-tts-flash",
                api_key=api_key,
                text=text,
                voice="Cherry",
                language_type="English",
                stream=False
            )

            if response.status_code == 200 and hasattr(response.output, 'audio'):
                audio_url = response.output.audio.get('url', '')
                if audio_url:
                    audio_bytes = await download_audio(audio_url)
                    # 使用简单文件名
                    safe_name = text[:20].replace(" ", "_").replace("?", "").replace("!", "")
                    filename = f"test_tone_{safe_name}.wav"
                    with open(filename, 'wb') as f:
                        f.write(audio_bytes)
                    print(f"  ✓ 保存: {filename}")
            else:
                print(f"  失败: {response.status_code}")

        except Exception as e:
            print(f"  异常: {e}")

    return True


def cleanup_test_files():
    """清理测试生成的音频文件"""
    import glob
    for f in glob.glob("test_*.wav"):
        try:
            os.remove(f)
            print(f"已删除: {f}")
        except:
            pass


def play_wav(filename: str):
    """播放 WAV 文件（macOS）"""
    import subprocess
    subprocess.run(["afplay", filename])


async def main():
    print("Qwen3-TTS-Flash API 测试")
    print("=" * 60)

    # 检查 dashscope SDK
    try:
        import dashscope
        print(f"dashscope 版本: {getattr(dashscope, '__version__', '未知')}")
    except ImportError:
        print("错误: dashscope 未安装")
        print("请运行: pip install dashscope")
        return

    # 运行测试
    await test_qwen3_tts_non_streaming()
    await test_voices()
    await test_sentence_types()

    print("\n" + "=" * 60)
    print("测试完成！生成的音频文件：")
    import glob
    for f in sorted(glob.glob("test_*.wav")):
        size = os.path.getsize(f)
        print(f"  - {f} ({size:,} bytes)")

    print("\n使用 play_wav('filename.wav') 播放音频")
    print("使用 cleanup_test_files() 清理测试文件")


if __name__ == "__main__":
    asyncio.run(main())
