#!/usr/bin/env python3
"""
同义词索引模块

基于词书内部的中文含义匹配，构建同义词映射关系。
当学生在听写时输入了一个同义词（而非目标单词），能够识别并给出友好提示。

分级策略：
- 初中生（grade7/grade8/grade9）：同义词范围 = 所有初中词书（跨年级互通）
- 高中生（senior1/senior2/senior3）：同义词范围 = 高考3500 + 所有北师大高中词书（并集4364词）
- 不计尝试：同义词输入不消耗尝试次数，给予鼓励性提示后让学生重新输入

Usage:
    from synonym import SynonymIndex
    from bookmanager import BookManager

    book_manager = BookManager()
    synonym_index = SynonymIndex(book_manager)

    # 按学段过滤检查同义词
    result = synonym_index.check_synonym("abandon", "give up", grade="grade9")
    if result:
        print(result)
        # {"is_synonym": True, "input_word": "give up", "target_word": "abandon",
        #  "shared_meanings": ["放弃"], "hint": "give up 也表示「放弃」..."}
"""

import re
import logging
from typing import Dict, Set, List, Optional
from collections import defaultdict
from bookmanager import JUNIOR_BOOKS, SENIOR_BOOKS

logger = logging.getLogger(__name__)


class SynonymIndex:
    """
    同义词索引

    基于词书中文含义的交集构建同义词关系。
    例如 abandon 和 give up 都含有"放弃"这个中文含义，则互为同义词。
    """

    def __init__(self, book_manager):
        """
        初始化同义词索引

        Args:
            book_manager: BookManager 实例，用于加载所有词书数据
        """
        # 中文含义 → 英文单词集合
        self._meaning_to_words: Dict[str, Set[str]] = defaultdict(set)
        # 英文单词 → 同义词集合（不含自身）
        self._word_synonyms: Dict[str, Set[str]] = defaultdict(set)
        # 英文单词 → 该词的所有中文含义
        self._word_meanings: Dict[str, Set[str]] = defaultdict(set)
        # 英文单词 → 所属词书集合
        self._word_books: Dict[str, Set[str]] = defaultdict(set)

        self._build(book_manager)

    def _extract_meanings(self, translation: str) -> Set[str]:
        """
        从中文翻译中提取含义关键词

        去除词性标记(n./v./adj.等)、人名信息、领域标记等噪音。

        Args:
            translation: 中文翻译文本，如 "v. 放弃；抛弃 n. 遗弃"

        Returns:
            含义关键词集合，如 {"放弃", "抛弃", "遗弃"}
        """
        # 截断人名部分（"人名；" 之后的内容通常是国家+音译，无实际含义）
        if '人名' in translation:
            translation = translation[:translation.index('人名')]
        # 去掉词性标记
        text = re.sub(r'[a-z]+\.\s*', '', translation)
        # 去掉方括号和圆括号内容（如 [计]、(英) 等）
        text = re.sub(r'\[.*?\]', '', text)
        text = re.sub(r'\(.*?\)', '', text)
        # 按分隔符切分
        parts = re.split(r'[；;，,、/]', text)
        meanings = set()
        for p in parts:
            p = p.strip()
            # 至少2个中文字符，排除纯数字、纯标点和含残余括号的片段
            if (p and len(p) >= 2 and not p.isdigit()
                    and '(' not in p and ')' not in p
                    and not re.match(r'^[a-zA-Z\s]+$', p)):  # 排除纯英文残留
                meanings.add(p)
        return meanings

    def _build(self, book_manager):
        """从所有词书构建同义词索引"""
        word_count = 0
        seen_words = set()

        for book_id in book_manager.list_books():
            try:
                words = book_manager.load(book_id)
            except Exception as e:
                logger.warning(f"加载词书 {book_id} 失败: {e}")
                continue

            for word_obj in words:
                word_lower = word_obj.word.strip().lower()
                self._word_books[word_lower].add(book_id)

                if word_lower in seen_words:
                    continue
                seen_words.add(word_lower)
                word_count += 1

                meanings = self._extract_meanings(word_obj.translation)
                self._word_meanings[word_lower] = meanings
                for m in meanings:
                    self._meaning_to_words[m].add(word_lower)

        # 构建反向索引：每个单词的同义词
        for meaning, words in self._meaning_to_words.items():
            if len(words) >= 2:
                for w in words:
                    self._word_synonyms[w].update(words - {w})

        synonym_count = sum(1 for w in self._word_synonyms if self._word_synonyms[w])
        logger.info(f"同义词索引构建完成: {word_count} 个单词, {synonym_count} 个有同义词")

    def _get_level_books(self, grade: Optional[str]) -> Optional[List[str]]:
        """
        根据学生年级获取对应学段的词书列表

        分级策略：
        - 初中生 → 所有初中词书（跨年级，7/8/9年级互通）
        - 高中生 → 高考3500 + 所有北师大高中词书（并集覆盖4364词）

        Args:
            grade: 学生年级，如 "grade7" / "senior1"，None 表示不限制

        Returns:
            词书ID列表，None 表示不限制
        """
        if not grade:
            return None

        if grade.startswith("grade"):
            return JUNIOR_BOOKS
        elif grade.startswith("senior"):
            return SENIOR_BOOKS
        return None

    def get_synonyms(self, word: str, grade: Optional[str] = None) -> Set[str]:
        """
        获取单词的同义词集合

        Args:
            word: 目标单词
            grade: 学生年级，用于按学段过滤同义词范围

        Returns:
            同义词集合
        """
        word_lower = word.strip().lower()
        synonyms = self._word_synonyms.get(word_lower, set())

        book_ids = self._get_level_books(grade)
        if book_ids:
            book_set = set(book_ids)
            synonyms = {s for s in synonyms
                        if self._word_books.get(s, set()) & book_set}

        return synonyms

    def get_shared_meanings(self, word1: str, word2: str) -> Set[str]:
        """
        获取两个单词共享的中文含义

        Args:
            word1: 第一个单词
            word2: 第二个单词

        Returns:
            共享的中文含义集合
        """
        m1 = self._word_meanings.get(word1.strip().lower(), set())
        m2 = self._word_meanings.get(word2.strip().lower(), set())
        return m1 & m2

    def check_synonym(self, target_word: str, user_input: str,
                      grade: Optional[str] = None) -> Optional[dict]:
        """
        检查用户输入是否为目标单词的同义词

        Args:
            target_word: 目标单词（期望的正确答案）
            user_input: 用户实际输入
            grade: 学生年级，用于按学段过滤同义词范围

        Returns:
            如果是同义词，返回提示信息字典；否则返回 None
            {
                "is_synonym": True,
                "input_word": "give up",
                "target_word": "abandon",
                "shared_meanings": ["放弃"],
                "hint": "give up 也表示「放弃」，但这里要复习的是 abandon 哦"
            }
        """
        input_lower = user_input.strip().strip('.,!?;:').lower()
        target_lower = target_word.strip().strip('.,!?;:').lower()

        if input_lower == target_lower:
            return None  # 完全匹配，不是同义词场景

        synonyms = self.get_synonyms(target_lower, grade)

        if input_lower in synonyms:
            shared = self.get_shared_meanings(target_lower, input_lower)
            meanings_text = "、".join(sorted(shared)[:3])  # 最多显示3个共享含义

            return {
                "is_synonym": True,
                "input_word": user_input.strip(),
                "target_word": target_word,
                "shared_meanings": sorted(shared),
                "hint": f"{user_input.strip()} 也表示「{meanings_text}」，但这里要复习的是 {target_word} 哦"
            }

        return None

    def get_stats(self) -> dict:
        """获取索引统计信息"""
        total_words = len(self._word_meanings)
        words_with_synonyms = sum(1 for w in self._word_synonyms if self._word_synonyms[w])
        total_meanings = len(self._meaning_to_words)
        conflict_meanings = sum(1 for m, ws in self._meaning_to_words.items() if len(ws) >= 2)

        return {
            "total_words": total_words,
            "words_with_synonyms": words_with_synonyms,
            "synonym_ratio": f"{words_with_synonyms / total_words * 100:.1f}%" if total_words else "0%",
            "total_meanings": total_meanings,
            "conflict_meanings": conflict_meanings,
        }
