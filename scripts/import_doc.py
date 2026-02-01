#!/usr/bin/env python3
"""
从 DOC 文件中解析英语单词，输出为项目标准 JSON 格式。

用法:
    python scripts/import_doc.py 人教版初中英语单词附音标.doc

依赖: macOS textutil（系统自带，无需安装）
"""

import re
import json
import subprocess
import sys
from pathlib import Path


def doc_to_text(doc_path: str) -> str:
    """用 macOS textutil 将 doc 转为纯文本"""
    result = subprocess.run(
        ["textutil", "-convert", "txt", "-stdout", doc_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"textutil 转换失败: {result.stderr}")
    return result.stdout


def extract_phonetic_and_rest(text: str) -> tuple[str, str, str]:
    """
    从序号之后的文本中提取: 单词、音标、词性+释义

    处理多种格式:
      - 标准:    what [hwɔt] pron 什么
      - 无空格:  computer[kəm'pju:tə]n电脑
      - 词组:    in English [in'iŋgliʃ]  phr. 用英语
      - 无音标:  on time   phr. 准时
      - 词组音标: take turns [,teik 'tə:nz] phr. 轮流
    """
    # 找 [音标] 的位置
    m = re.search(r'\[([^\]]+)\]', text)
    if m:
        before = text[:m.start()].rstrip()
        phonetic = m.group(1)
        after = text[m.end():].strip()

        # before 是单词部分，after 是词性+释义
        # 但 after 可能以 ] 开头的残留，或者词性紧贴音标
        word = before

        # 如果 after 为空或只有词性释义粘连在音标后面
        # 如: computer[kəm'pju:tə]n电脑 → after = "n电脑"
        # 需要把粘连的词性分离
        if after and not after[0].isspace() and not after.startswith("phr"):
            # 在词性标记前插入空格: n电脑 → n 电脑
            after = re.sub(r'^(n|v|adj|adv|int|prep|conj|num|pron|v\.aux|art)(?=[^\s\.])', r'\1 ', after)

        return word, phonetic, after
    else:
        # 没有音标，按词性关键词分割
        # 找第一个词性标记的位置
        pos_match = re.search(
            r'(?:^|\s)((?:v\.aux|phr\.|adj|adv|prep|conj|num|pron|int|art|n|v)\b)',
            text
        )
        if pos_match:
            word = text[:pos_match.start()].strip()
            translation = text[pos_match.start():].strip()
            return word, "", translation

        return text.strip(), "", ""


def parse_words(text: str) -> dict[str, list[dict]]:
    """
    解析文本，返回 {册名: [词条列表]}

    每行格式: 序号  单词 [音标] 词性 中文释义
    册标记: 第一册 / 第二册 / 第三册
    """
    lines = text.strip().split("\n")

    books = {}
    current_book = "第一册"

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 册标记
        if re.match(r'^第[一二三四五六]册$', stripped):
            current_book = stripped
            if current_book not in books:
                books[current_book] = []
            continue

        # 跳过标题、备注、页脚
        if stripped.startswith(("初中英语", "备注", "adv ", "phr.", "PAGE", "教务处")):
            continue

        # 必须以序号开头
        m = re.match(r'^\s*(\d+)\s+(.+)$', stripped)
        if not m:
            continue

        seq, rest = m.groups()
        word, phonetic_raw, translation = extract_phonetic_and_rest(rest)

        # 清理
        word = word.strip()
        if not word:
            continue

        # 音标加 / / 包裹
        phonetic = ""
        if phonetic_raw:
            phonetic = "/" + phonetic_raw.strip().strip("/") + "/"

        translation = translation.strip()

        # 跳过 "xxx 的缩写形式" 且无音标的条目（如 I'm, it's）
        if "的缩写形式" in translation and not phonetic:
            continue

        entry = {
            "word": word,
            "phonetic": phonetic,
            "translation": translation,
            "unit": current_book
        }

        if current_book not in books:
            books[current_book] = []
        books[current_book].append(entry)

    return books


def main():
    if len(sys.argv) < 2:
        print("用法: python scripts/import_doc.py <doc文件路径> [输出目录]")
        print("示例: python scripts/import_doc.py 人教版初中英语单词附音标.doc data/books/")
        sys.exit(1)

    doc_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not Path(doc_path).exists():
        print(f"文件不存在: {doc_path}")
        sys.exit(1)

    print(f"解析文件: {doc_path}")
    text = doc_to_text(doc_path)
    books = parse_words(text)

    # 输出统计和预览
    total = 0
    for book_name, words in books.items():
        print(f"\n{book_name}: {len(words)} 个词")
        total += len(words)
        # 预览前3个
        for w in words[:3]:
            print(f"  {w['word']} {w['phonetic']} {w['translation']}")
        print(f"  ...")

    print(f"\n总计: {total} 个词")

    # 合并输出为单个 JSON
    all_words = []
    for book_name, words in books.items():
        all_words.extend(words)

    # 生成输出文件名
    stem = Path(doc_path).stem
    output_path = Path(output_dir) / f"{stem}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_words, f, ensure_ascii=False, indent=2)

    print(f"\n已保存到: {output_path}")

    # 也按册分别输出
    for book_name, words in books.items():
        book_filename = f"{stem}_{book_name}.json"
        book_path = Path(output_dir) / book_filename
        with open(book_path, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)
        print(f"  {book_name} -> {book_path}")


if __name__ == "__main__":
    main()
