#!/usr/bin/env python3
"""
阿里云百炼 API 测试脚本

测试内容：
1. Qwen-Plus 文本生成（AI 评价翻译）
2. Qwen3-ASR-Flash 语音识别（中文）- 使用 DashScope SDK
3. CosyVoice TTS 语音合成 - 使用 DashScope SDK

使用方法：
    cd english-learning-app
    python3 tests/test_dashscope_api.py

参考文档：
- Qwen3-ASR: https://help.aliyun.com/zh/model-studio/qwen-speech-recognition
- CosyVoice: https://help.aliyun.com/zh/model-studio/text-to-speech
"""

import os
import sys
import json
import asyncio
import base64
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

# 从 .env 加载环境变量
from dotenv import load_dotenv
load_dotenv()

import httpx

# 配置
API_KEY = os.getenv("DASHSCOPE_API_KEY")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# 测试结果
test_results = []


def print_separator(title: str):
    """打印分隔线"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def record_result(name: str, success: bool, message: str, data: dict = None):
    """记录测试结果"""
    result = {
        "name": name,
        "success": success,
        "message": message,
        "data": data
    }
    test_results.append(result)
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"\n{status}: {name}")
    print(f"   {message}")
    if data:
        print(f"   数据: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")


async def test_qwen_plus():
    """测试 1: Qwen-Plus 文本生成（用于 AI 评价翻译）"""
    print_separator("测试 Qwen-Plus 文本生成")

    if not API_KEY:
        record_result("Qwen-Plus", False, "未配置 DASHSCOPE_API_KEY")
        return

    prompt = """
    学生正在练习英文到中文的翻译。

    英文原文: manage
    标准翻译: 管理；经营；设法做到
    学生翻译: 管理
    相似度: 85%

    请评价学生的翻译:
    1. 是否正确传达了原文含义
    2. 用词是否准确
    3. 表达是否自然
    4. 如有问题，指出具体错误

    返回 JSON:
    {
        "correct": true/false,
        "feedback": "简短评价",
        "issues": ["问题1", "问题2"],
        "suggestion": "改进建议"
    }
    """

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是翻译评估助手，客观简洁地评价翻译结果。回复JSON格式。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3
                }
            )

            print(f"状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                print(f"\n响应内容:\n{content}")

                # 尝试解析 JSON
                try:
                    # 提取 JSON 部分（如果有 markdown 代码块）
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0].strip()
                    else:
                        json_str = content

                    parsed = json.loads(json_str)
                    record_result(
                        "Qwen-Plus",
                        True,
                        "文本生成成功，JSON 解析正常",
                        {"feedback": parsed.get("feedback", ""), "correct": parsed.get("correct")}
                    )
                except json.JSONDecodeError as e:
                    record_result(
                        "Qwen-Plus",
                        True,
                        f"文本生成成功，但 JSON 解析失败: {e}",
                        {"raw_content": content[:200]}
                    )

                # 打印 token 使用情况
                usage = result.get("usage", {})
                print(f"\nToken 使用: 输入 {usage.get('prompt_tokens', 0)}, 输出 {usage.get('completion_tokens', 0)}")

            else:
                error_text = response.text
                record_result("Qwen-Plus", False, f"API 错误: {response.status_code}", {"error": error_text})

    except Exception as e:
        record_result("Qwen-Plus", False, f"请求异常: {str(e)}")


def test_qwen3_asr_sdk():
    """测试 2: Qwen3-ASR-Flash 语音识别（使用 DashScope SDK）"""
    print_separator("测试 Qwen3-ASR-Flash 语音识别 (SDK)")

    if not API_KEY:
        record_result("Qwen3-ASR", False, "未配置 DASHSCOPE_API_KEY")
        return

    try:
        import dashscope
        from dashscope import MultiModalConversation

        # 设置 API 配置
        dashscope.api_key = API_KEY
        dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

        # 使用阿里云官方示例音频 URL
        audio_url = "https://dashscope.oss-cn-beijing.aliyuncs.com/audios/welcome.mp3"

        print(f"使用在线音频: {audio_url}")

        messages = [
            {"role": "system", "content": [{"text": ""}]},  # Context 可用于传入热词
            {"role": "user", "content": [{"audio": audio_url}]}
        ]

        response = MultiModalConversation.call(
            model="qwen3-asr-flash",
            messages=messages,
            result_format="message",
            asr_options={
                "enable_itn": True  # 启用逆文本正则化
            }
        )

        print(f"\n响应状态: {response.status_code}")
        print(f"请求ID: {response.request_id}")

        if response.status_code == 200:
            # 提取识别结果
            output = response.output
            choices = output.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", [])
                if content and len(content) > 0:
                    recognized_text = content[0].get("text", "")
                    print(f"\n识别结果: {recognized_text}")

                    record_result(
                        "Qwen3-ASR",
                        True,
                        "语音识别成功",
                        {"recognized_text": recognized_text}
                    )
                else:
                    record_result("Qwen3-ASR", False, "响应中无识别内容", {"output": output})
            else:
                record_result("Qwen3-ASR", False, "响应中无 choices", {"output": output})

            # 打印 token 使用情况
            usage = response.usage
            if usage:
                print(f"\nToken 使用: 输入 {usage.get('input_tokens', 0)}, 输出 {usage.get('output_tokens', 0)}")

        else:
            record_result(
                "Qwen3-ASR",
                False,
                f"API 错误: {response.status_code}",
                {"code": response.code, "message": response.message}
            )

    except ImportError:
        record_result("Qwen3-ASR", False, "dashscope SDK 未安装，请运行: pip install dashscope")
    except Exception as e:
        import traceback
        traceback.print_exc()
        record_result("Qwen3-ASR", False, f"请求异常: {str(e)}")


def test_cosyvoice_tts_sdk():
    """测试 3: CosyVoice TTS 语音合成（使用 DashScope SDK）"""
    print_separator("测试 CosyVoice TTS 语音合成 (SDK)")

    if not API_KEY:
        record_result("CosyVoice", False, "未配置 DASHSCOPE_API_KEY")
        return

    try:
        import dashscope
        from dashscope.audio.tts_v2 import SpeechSynthesizer

        # 设置 API Key
        dashscope.api_key = API_KEY

        test_text = "Hello, welcome to the English learning application. Let's practice together."
        output_file = Path(__file__).parent / "test_output_cosyvoice.mp3"

        print(f"测试文本: {test_text}")
        print(f"输出文件: {output_file}")

        # 创建语音合成器
        # 可用音色: longxiaochun, longxiaoxia, longxiaobai, longlaotie 等
        synthesizer = SpeechSynthesizer(
            model="cosyvoice-v1",
            voice="longxiaochun"  # 龙小淳音色
        )

        # 同步合成
        audio_data = synthesizer.call(test_text)

        if audio_data:
            # 保存音频
            with open(output_file, "wb") as f:
                f.write(audio_data)

            file_size = output_file.stat().st_size
            print(f"\n音频已保存: {output_file}")
            print(f"文件大小: {file_size} bytes")

            record_result(
                "CosyVoice",
                True,
                "TTS 合成成功",
                {
                    "text": test_text,
                    "output_file": str(output_file),
                    "file_size": file_size
                }
            )
        else:
            record_result("CosyVoice", False, "未返回音频数据")

    except ImportError:
        record_result("CosyVoice", False, "dashscope SDK 未安装，请运行: pip install dashscope")
    except AttributeError as e:
        # 可能是旧版 SDK，尝试使用其他方式
        print(f"SDK 版本问题: {e}")
        test_cosyvoice_tts_websocket()
    except Exception as e:
        import traceback
        traceback.print_exc()
        record_result("CosyVoice", False, f"请求异常: {str(e)}")


def test_cosyvoice_tts_websocket():
    """使用 WebSocket API 测试 CosyVoice TTS"""
    print("\n尝试使用 WebSocket API...")

    try:
        import dashscope
        from dashscope.audio.tts import SpeechSynthesizer

        dashscope.api_key = API_KEY

        test_text = "Hello, welcome to the English learning application."
        output_file = Path(__file__).parent / "test_output_cosyvoice.mp3"

        # 使用同步方式调用
        result = SpeechSynthesizer.call(
            model='cosyvoice-v1',
            text=test_text,
            sample_rate=22050,
            format='mp3',
            voice='longxiaochun'
        )

        if result.get_audio_data():
            with open(output_file, "wb") as f:
                f.write(result.get_audio_data())

            file_size = output_file.stat().st_size
            print(f"音频已保存: {output_file}")
            print(f"文件大小: {file_size} bytes")

            record_result(
                "CosyVoice",
                True,
                "TTS 合成成功 (WebSocket)",
                {"text": test_text, "file_size": file_size}
            )
        else:
            record_result("CosyVoice", False, "未返回音频数据")

    except Exception as e:
        import traceback
        traceback.print_exc()
        record_result("CosyVoice", False, f"WebSocket 调用异常: {str(e)}")


async def test_models_list():
    """测试: 列出可用模型"""
    print_separator("列出可用模型")

    if not API_KEY:
        record_result("模型列表", False, "未配置 DASHSCOPE_API_KEY")
        return

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{BASE_URL}/models",
                headers={
                    "Authorization": f"Bearer {API_KEY}"
                }
            )

            print(f"状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                models = result.get("data", [])

                print(f"\n可用模型数量: {len(models)}")

                # 筛选语音相关模型
                audio_models = [m for m in models if "audio" in m.get("id", "").lower() or
                               "asr" in m.get("id", "").lower() or
                               "tts" in m.get("id", "").lower() or
                               "cosy" in m.get("id", "").lower()]

                if audio_models:
                    print("\n语音相关模型:")
                    for m in audio_models:
                        print(f"  - {m.get('id')}")

                # 筛选 Qwen 模型
                qwen_models = [m for m in models if "qwen" in m.get("id", "").lower()]
                if qwen_models:
                    print("\nQwen 模型（前10个）:")
                    for m in qwen_models[:10]:
                        print(f"  - {m.get('id')}")
                    if len(qwen_models) > 10:
                        print(f"  ... 还有 {len(qwen_models) - 10} 个")

                record_result("模型列表", True, f"获取成功，共 {len(models)} 个模型")

            else:
                error_text = response.text
                record_result("模型列表", False, f"API 错误: {response.status_code}", {"error": error_text[:500]})

    except Exception as e:
        record_result("模型列表", False, f"请求异常: {str(e)}")


def print_summary():
    """打印测试总结"""
    print_separator("测试总结")

    passed = sum(1 for r in test_results if r["success"])
    failed = len(test_results) - passed

    print(f"\n总计: {len(test_results)} 项测试")
    print(f"  ✅ 通过: {passed}")
    print(f"  ❌ 失败: {failed}")

    if failed > 0:
        print("\n失败项目:")
        for r in test_results:
            if not r["success"]:
                print(f"  - {r['name']}: {r['message']}")

    # 保存结果到文件
    result_file = Path(__file__).parent / "test_results.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到: {result_file}")


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  阿里云百炼 API 测试")
    print("=" * 60)

    if not API_KEY:
        print("\n❌ 错误: 未配置 DASHSCOPE_API_KEY 环境变量")
        print("请在 .env 文件中添加: DASHSCOPE_API_KEY=your_api_key")
        return

    print(f"\nAPI Key: {API_KEY[:10]}...{API_KEY[-4:]}")

    # 运行测试
    await test_models_list()
    await test_qwen_plus()

    # SDK 测试（同步调用）
    test_qwen3_asr_sdk()
    test_cosyvoice_tts_sdk()

    # 打印总结
    print_summary()


if __name__ == "__main__":
    asyncio.run(main())
