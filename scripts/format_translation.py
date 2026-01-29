#!/usr/bin/env python3
"""
整理词书释义格式脚本

将词典风格的释义转换为词性分行式格式：
- 词性标注规范化：a. → adj.
- 按词性分行：每个词性独占一行
- 精简含义：每个词性保留 1-3 个核心含义
- 去除专业标注：[化]、[法]、[医]、[计] 等
"""

import os
import sys
import json
import time
import httpx
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("DASHSCOPE_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def format_translation_with_ai(word: str, translation: str) -> str:
    """使用 AI 整理单个单词的释义"""

    prompt = f"""请将以下英语单词的中文释义整理为词性分行式格式。

【整理规则】
1. 词性标注规范化：a. → adj.，其他保持（n. vt. vi. adv. prep. conj. pron.）
2. 按词性分行：每个词性独占一行，用换行符分隔
3. 精简含义：每个词性只保留 1-3 个最常用的核心含义
4. 去除专业标注：删除 [化]、[法]、[医]、[计]、[机]、[电]、[经]、[网络] 等专业领域标注
5. 如果释义明显错误，请修正为正确的释义

【输入】
单词：{word}
原释义：{translation}

【输出格式】
直接输出整理后的释义，每个词性一行，不要其他解释。
例如：
n. 年长者，毕业班学生
adj. 年长的，高级的"""

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "qwen-plus",
                    "messages": [
                        {"role": "system", "content": "你是一位英语词典编辑，负责整理单词释义格式。只输出整理后的释义，不要任何解释。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200
                }
            )

            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content
            else:
                print(f"  API 错误: {response.status_code}")
                return translation

    except Exception as e:
        print(f"  请求失败: {e}")
        return translation


def process_book(input_file: str, output_file: str = None):
    """处理单个词书文件"""

    # 禁用输出缓冲
    import functools
    print = functools.partial(__builtins__.print, flush=True)

    if not API_KEY:
        print("错误：未配置 DASHSCOPE_API_KEY")
        sys.exit(1)

    input_path = Path(input_file)
    if not input_path.exists():
        print(f"错误：文件不存在 {input_file}")
        sys.exit(1)

    # 输出文件默认覆盖原文件
    if output_file is None:
        output_file = input_file

    print(f"读取词书: {input_path.name}")
    with open(input_path, "r", encoding="utf-8") as f:
        words = json.load(f)

    print(f"共 {len(words)} 个单词\n")

    # 处理每个单词
    for i, word_data in enumerate(words):
        word = word_data["word"]
        old_translation = word_data["translation"]

        print(f"[{i+1}/{len(words)}] {word}")
        print(f"  原: {old_translation[:50]}{'...' if len(old_translation) > 50 else ''}")

        # 调用 AI 整理
        new_translation = format_translation_with_ai(word, old_translation)
        word_data["translation"] = new_translation

        print(f"  新: {new_translation[:50]}{'...' if len(new_translation) > 50 else ''}")
        print()

        # 避免 API 限流
        time.sleep(0.5)

    # 保存结果
    print(f"\n保存到: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)

    print("完成！")


# 需要批量处理的高中词书列表
SENIOR_BOOKS = [
    "bsd_senior_compulsory2.json",
    "bsd_senior_compulsory3.json",
    "bsd_senior_elective1.json",
    "bsd_senior_elective2.json",
    "bsd_senior_elective3.json",
    "bsd_senior_elective4.json",
]


def process_all_senior_books():
    """批量处理所有高中词书"""
    import functools
    print = functools.partial(__builtins__.print, flush=True)

    books_dir = PROJECT_ROOT / "data" / "books"

    print("=" * 50)
    print("批量处理高中词书释义")
    print("=" * 50)
    print()

    for book_name in SENIOR_BOOKS:
        book_path = books_dir / book_name
        if book_path.exists():
            print(f"\n{'='*50}")
            print(f"开始处理: {book_name}")
            print(f"{'='*50}\n")
            process_book(str(book_path))
        else:
            print(f"跳过: {book_name} (文件不存在)")

    print("\n" + "=" * 50)
    print("所有词书处理完成！")
    print("=" * 50)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法:")
        print("  python format_translation.py <词书文件>     # 处理单个词书")
        print("  python format_translation.py --all-senior  # 处理所有高中词书")
        print()
        print("示例:")
        print("  python format_translation.py data/books/bsd_senior_compulsory2.json")
        print("  python format_translation.py --all-senior")
        sys.exit(1)

    if sys.argv[1] == "--all-senior":
        process_all_senior_books()
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else None
        process_book(input_file, output_file)
