#!/usr/bin/env python3
"""
词书管理模块

提供词书文件的加载、解析和查询功能。

词书数据存放在 data/books/ 目录，支持 JSON 格式。
每本词书对应一个 JSON 文件，如 bsd_grade7_up.json（北师大七上）。

Usage:
    from book import BookManager, Word

    manager = BookManager()

    # 列出所有词书
    books = manager.list_books()

    # 加载词书
    words = manager.load("bsd_grade7_up")

    # 获取单个单词
    word = manager.get_word("bsd_grade7_up", "daughter")
"""

import json
from dataclasses import dataclass
from typing import List, Optional, Dict
from pathlib import Path


# 词书中文名映射
BOOK_NAMES = {
    # 初中词书
    "bsd_grade7_up": "北师大七年级上册",
    "bsd_grade7_down": "北师大七年级下册",
    "bsd_grade8_up": "北师大八年级上册",
    "bsd_grade8_down": "北师大八年级下册",
    "bsd_grade9_up": "北师大九年级上册",
    "bsd_grade9_down": "北师大九年级下册",
    "pep_grade7": "人教版七年级",
    "pep_grade8": "人教版八年级",
    "pep_grade9": "人教版九年级",
    "zhongkao": "中考词汇",
    # 高中词书
    "bsd_senior_compulsory1": "北师大高中必修一",
    "bsd_senior_compulsory2": "北师大高中必修二",
    "bsd_senior_compulsory3": "北师大高中必修三",
    "bsd_senior_elective1": "北师大高中选择性必修一",
    "bsd_senior_elective2": "北师大高中选择性必修二",
    "bsd_senior_elective3": "北师大高中选择性必修三",
    "bsd_senior_elective4": "北师大高中选择性必修四",
    # 高考词汇
    "gaokao_3500": "高考3500词",
}


def get_book_display_name(book_id: str) -> str:
    """获取词书的中文显示名称"""
    return BOOK_NAMES.get(book_id, book_id)


@dataclass
class Word:
    """
    单词数据结构

    Attributes:
        word: 单词拼写
        phonetic: 音标
        translation: 中文释义（包含词性）
        unit: 所属单元
    """
    word: str
    phonetic: str
    translation: str
    unit: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "Word":
        """从字典创建 Word 对象"""
        return cls(
            word=data.get("word", ""),
            phonetic=data.get("phonetic", ""),
            translation=data.get("translation", ""),
            unit=data.get("unit", "")
        )


class BookManager:
    """
    词书管理器

    管理词书文件的加载和查询。

    目录结构:
        data/
        ├── books/           # 词书数据（只读）
        │   ├── bsd_grade7_up.json
        │   └── bsd_grade7_down.json
        └── progress/        # 学习进度（读写）
    """

    def __init__(self, data_dir: Path = None):
        """
        初始化词书管理器

        Args:
            data_dir: 数据目录路径，默认为脚本同级的 data/ 目录
        """
        if data_dir is None:
            data_dir = Path(__file__).parent / "data"

        self.data_dir = Path(data_dir)
        self.books_dir = self.data_dir / "books"
        self.progress_dir = self.data_dir / "progress"

        # 缓存已加载的词书
        self._cache: Dict[str, List[Word]] = {}

    def list_books(self) -> List[str]:
        """
        列出所有可用词书

        Returns:
            词书名称列表（不含扩展名）
        """
        if not self.books_dir.exists():
            return []
        return sorted([f.stem for f in self.books_dir.glob("*.json")])

    def load(self, book_name: str, use_cache: bool = True) -> List[Word]:
        """
        加载词书

        Args:
            book_name: 词书名称（不含扩展名）
            use_cache: 是否使用缓存，默认 True

        Returns:
            单词列表

        Raises:
            FileNotFoundError: 词书文件不存在
        """
        if use_cache and book_name in self._cache:
            return self._cache[book_name]

        book_file = self.books_dir / f"{book_name}.json"
        if not book_file.exists():
            raise FileNotFoundError(f"词书不存在: {book_file}")

        with open(book_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        words = [Word.from_dict(item) for item in data]

        if use_cache:
            self._cache[book_name] = words

        return words

    def get_word(self, book_name: str, word: str) -> Optional[Word]:
        """
        获取单个单词信息

        Args:
            book_name: 词书名称
            word: 单词拼写

        Returns:
            Word 对象，如果未找到返回 None
        """
        words = self.load(book_name)
        word_lower = word.lower()
        for w in words:
            if w.word.lower() == word_lower:
                return w
        return None

    def get_words_by_unit(self, book_name: str, unit: str) -> List[Word]:
        """
        获取指定单元的单词

        Args:
            book_name: 词书名称
            unit: 单元名称

        Returns:
            该单元的单词列表
        """
        words = self.load(book_name)
        return [w for w in words if w.unit == unit]

    def get_units(self, book_name: str) -> List[str]:
        """
        获取词书中的所有单元

        Args:
            book_name: 词书名称

        Returns:
            单元名称列表（按出现顺序）
        """
        words = self.load(book_name)
        seen = set()
        units = []
        for w in words:
            if w.unit and w.unit not in seen:
                seen.add(w.unit)
                units.append(w.unit)
        return units

    def get_progress_file(self, book_name: str) -> Path:
        """
        获取词书对应的学习进度文件路径

        Args:
            book_name: 词书名称

        Returns:
            进度文件路径（可能不存在）
        """
        self.progress_dir.mkdir(parents=True, exist_ok=True)
        return self.progress_dir / f"{book_name}.json"

    def get_book_info(self, book_name: str) -> dict:
        """
        获取词书信息摘要

        Args:
            book_name: 词书名称

        Returns:
            包含词书统计信息的字典
        """
        words = self.load(book_name)
        units = self.get_units(book_name)

        return {
            "id": book_name,
            "name": get_book_display_name(book_name),
            "total_words": len(words),
            "units": len(units),
            "unit_names": units
        }


# 便捷函数
def list_books(data_dir: Path = None) -> List[str]:
    """列出所有可用词书"""
    return BookManager(data_dir).list_books()


def load_book(book_name: str, data_dir: Path = None) -> List[Word]:
    """加载词书"""
    return BookManager(data_dir).load(book_name)


# 命令行入口
if __name__ == "__main__":
    import sys

    manager = BookManager()

    if len(sys.argv) < 2:
        # 列出所有词书
        print("可用词书:")
        for book_id in manager.list_books():
            info = manager.get_book_info(book_id)
            print(f"  {info['name']} ({book_id}): {info['total_words']} 词")
    else:
        # 显示指定词书信息
        book_id = sys.argv[1]
        try:
            info = manager.get_book_info(book_id)
            print(f"词书: {info['name']}")
            print(f"ID: {info['id']}")
            print(f"单词数: {info['total_words']}")
            print(f"单元数: {info['units']}")
            print("\n单元列表:")
            for unit in info['unit_names']:
                words = manager.get_words_by_unit(book_id, unit)
                print(f"  {unit}: {len(words)} 词")
        except FileNotFoundError as e:
            print(f"错误: {e}")
            sys.exit(1)
