#!/usr/bin/env python3
"""
一次性脚本：修复词书翻译字段的格式问题

修复内容：
1. 复合词性标记统一为 "n. & vi." 格式（每个词性带点号，用 " & " 连接）
2. 词性标记后加空格（如 "adj.发人深省的" → "adj. 发人深省的"）
3. 多余空格压缩为单个空格
4. 中文之间的英文逗号改为中文逗号（如 "温室,暖房" → "温室，暖房"）
5. 中文之间的英文分号改为中文分号

运行方式：
    python fix_translations.py          # 预览修改（不写入）
    python fix_translations.py --apply  # 实际写入文件

输出：
    修改前后对比，以及受影响的文件统计
"""

import json
import re
import sys
import glob
from pathlib import Path

# 合法的词性缩写
VALID_POS = {
    'n', 'v', 'vt', 'vi', 'adj', 'adv', 'prep', 'conj',
    'pron', 'det', 'art', 'num', 'int', 'interj', 'aux',
    'abbr', 'phr', 'pl', 'link', 'modal', 'a',
}


def normalize_pos_tag(match_text: str) -> str:
    """
    将复合词性标记规范化

    输入示例: "n&vi.", "adj&pron&adv.", "n & v", "vi.&vt."
    输出示例: "n. & vi.", "adj. & pron. & adv.", "n. & v.", "vi. & vt."
    """
    # 提取所有词性缩写
    parts = re.findall(r'[a-z]+', match_text)
    # 验证是否都是合法词性
    if all(p in VALID_POS for p in parts):
        return ' & '.join(f'{p}.' for p in parts)
    return match_text


def fix_translation(text: str) -> str:
    """修复单条翻译文本"""
    original = text

    # 0. 预处理："n um" → "num"（数词被错误空格拆分）
    text = re.sub(r'\bn\s+um\b', 'num', text)

    # 1. 规范化复合词性标记（& 连接）
    # 匹配: n&vi. / adj&pron&adv. / n & v / vi.&vt. / prep&conj&adv. 等
    text = re.sub(
        r'\b([a-z]+)\.?\s*&\s*([a-z]+(?:\s*&\s*[a-z]+)*)\.?(?=\s|[\u4e00-\u9fff(（*])',
        lambda m: normalize_pos_tag(m.group()),
        text
    )

    # 1b. 规范化斜杠连接的词性标记（如 "vi./vt."）
    text = re.sub(
        r'\b([a-z]+)\.\s*/\s*([a-z]+)\.(?=\s|[\u4e00-\u9fff(（])',
        lambda m: normalize_pos_tag(m.group()),
        text
    )

    # 2. 单个词性后无空格直接接中文/括号的情况
    # "adj.发人深省的" → "adj. 发人深省的"
    # 但不影响省略号 "..." 或 "……"
    text = re.sub(
        r'([a-z]+\.)(?=[^\s.\da-z&/])',
        r'\1 ',
        text
    )

    # 2b. 无点号的单个词性后直接接空格+中文（人教版格式）
    # "n 课" → "n. 课", "adj 快乐的" → "adj. 快乐的"
    # 仅处理行首或换行后的词性（避免误伤正文中的英文单词）
    text = re.sub(
        r'(^|\n)\s*([a-z]+)\s+(?=[\u4e00-\u9fff(（])',
        lambda m: f'{m.group(1)}{m.group(2)}. ',
        text
    )

    # 3. 多余空格压缩
    text = re.sub(r'  +', ' ', text)

    # 4. 中文之间的英文逗号 → 中文逗号
    # "温室,暖房" → "温室，暖房"
    text = re.sub(
        r'([\u4e00-\u9fff\u3000-\u303f）)])\s*,\s*([\u4e00-\u9fff(（])',
        r'\1，\2',
        text
    )

    # 5. 中文之间的英文分号 → 中文分号
    text = re.sub(
        r'([\u4e00-\u9fff\u3000-\u303f）)])\s*;\s*([\u4e00-\u9fff(（])',
        r'\1；\2',
        text
    )

    # 6. 中文逗号/分号后多余空格
    text = re.sub(r'([，；])\s+', r'\1', text)

    # 7. 首尾空格
    text = text.strip()

    return text


def main():
    apply = '--apply' in sys.argv
    books_dir = Path(__file__).parent / 'data' / 'books'

    total_changes = 0
    file_changes = {}

    for filepath in sorted(books_dir.glob('*.json')):
        with open(filepath, 'r', encoding='utf-8') as f:
            words = json.load(f)

        changes = []
        modified = False

        for w in words:
            old = w['translation']
            new = fix_translation(old)
            if old != new:
                changes.append((w['word'], old, new))
                w['translation'] = new
                modified = True

        if changes:
            file_changes[filepath.name] = changes
            total_changes += len(changes)

            if apply and modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(words, f, ensure_ascii=False, indent=2)

    # 输出报告
    print(f"{'=' * 60}")
    print(f"词书翻译格式修复报告")
    print(f"{'=' * 60}")
    print(f"扫描文件: {len(list(books_dir.glob('*.json')))} 本词书")
    print(f"需修改: {len(file_changes)} 本词书, {total_changes} 条翻译")
    print(f"模式: {'实际写入' if apply else '预览模式（加 --apply 执行写入）'}")
    print()

    for filename, changes in sorted(file_changes.items()):
        print(f"--- {filename} ({len(changes)} 条) ---")
        for word, old, new in changes[:10]:
            print(f"  {word}")
            print(f"    旧: {old[:80]}")
            print(f"    新: {new[:80]}")
        if len(changes) > 10:
            print(f"  ... 还有 {len(changes) - 10} 条")
        print()

    if not apply and total_changes > 0:
        print(f"确认无误后执行: python fix_translations.py --apply")


if __name__ == '__main__':
    main()
