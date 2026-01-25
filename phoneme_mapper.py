"""
音素到字母映射模块

使用 g2p (Gi2Pi) 库将单词转换为音素序列，并提供字母到音素的对齐映射。
无需手动维护映射规则，库内置支持复杂单词的自动对齐。

Usage:
    from phoneme_mapper import get_letter_phoneme_mapping, merge_assessment_with_letters

    # 获取字母-音素映射
    mapping = get_letter_phoneme_mapping("pretty")
    # [{"letter": "p", "phoneme": "p"}, {"letter": "r", "phoneme": "ɹ"}, ...]

    # 合并 Azure 评估结果
    result = merge_assessment_with_letters("pretty", azure_phoneme_details)
"""

from typing import List, Dict, Optional


class PhonemeMapper:
    """音素映射器 - 使用 Gi2Pi 提供字母到音素的对齐"""

    def __init__(self):
        self.transducer = None
        self._init_transducer()

    def _init_transducer(self):
        """初始化 g2p 转换器"""
        try:
            from g2p import make_g2p
            # 英语到 IPA 的转换
            self.transducer = make_g2p('eng', 'eng-ipa')
        except ImportError:
            print("警告: g2p 未安装，音素映射功能不可用")
            self.transducer = None
        except Exception as e:
            print(f"警告: g2p 初始化失败: {e}")
            self.transducer = None

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return self.transducer is not None

    def get_phonemes(self, word: str) -> str:
        """
        获取单词的 IPA 音素字符串

        Args:
            word: 英文单词

        Returns:
            IPA 音素字符串
        """
        if not self.is_available():
            return ""

        result = self.transducer(word.lower())
        return result.output_string

    def get_letter_mapping(self, word: str) -> List[Dict]:
        """
        获取字母到音素的映射

        使用 g2p 的 substring_alignments 功能，自动处理复杂单词。

        Args:
            word: 英文单词

        Returns:
            映射列表，每项包含 letter 和 phoneme
            例如: [{"letter": "p", "phoneme": "p"}, {"letter": "r", "phoneme": "ɹ"}, ...]
        """
        if not self.is_available():
            return []

        word_lower = word.lower()
        result = self.transducer(word_lower)

        # 使用 substring_alignments 获取对齐
        alignments = result.substring_alignments()

        mapping = []
        char_pos = 0

        for letter_group, phoneme in alignments:
            mapping.append({
                'letter': letter_group,
                'phoneme': phoneme,
                'char_start': char_pos,
                'char_end': char_pos + len(letter_group)
            })
            char_pos += len(letter_group)

        return mapping

    def merge_with_assessment(self, word: str, phoneme_details: List[Dict]) -> List[Dict]:
        """
        将字母映射与 Azure 的音素评估结果合并

        Azure 返回的音素和 g2p 生成的音素可能略有差异，
        使用顺序对齐的方式合并评估分数。

        Args:
            word: 单词
            phoneme_details: Azure 返回的音素详情
                [{"phoneme": "p", "accuracy": 95, "error_type": "None"}, ...]

        Returns:
            合并后的映射，每项包含 letter, phoneme, accuracy, error_type
        """
        letter_mapping = self.get_letter_mapping(word)

        if not letter_mapping:
            return []

        if not phoneme_details:
            # 没有评估数据，只返回字母映射
            for item in letter_mapping:
                item['accuracy'] = None
                item['error_type'] = None
            return letter_mapping

        # 按顺序对齐 Azure 音素和 g2p 音素
        # 由于音素数量可能不完全匹配，使用顺序对齐
        assessment_idx = 0

        for item in letter_mapping:
            g2p_phoneme = item['phoneme']

            if not g2p_phoneme:
                # 静音字母
                item['accuracy'] = 100
                item['error_type'] = 'None'
                continue

            if assessment_idx < len(phoneme_details):
                azure_data = phoneme_details[assessment_idx]
                item['accuracy'] = azure_data.get('accuracy', 0)
                item['error_type'] = azure_data.get('error_type', 'None')
                assessment_idx += 1
            else:
                # 没有更多评估数据
                item['accuracy'] = None
                item['error_type'] = None

        return letter_mapping


# 单例实例
_mapper_instance = None


def get_mapper() -> PhonemeMapper:
    """获取单例映射器"""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = PhonemeMapper()
    return _mapper_instance


def get_letter_phoneme_mapping(word: str) -> List[Dict]:
    """便捷函数：获取字母音素映射"""
    return get_mapper().get_letter_mapping(word)


def merge_assessment_with_letters(word: str, phoneme_details: List[Dict]) -> List[Dict]:
    """便捷函数：合并评估结果和字母映射"""
    return get_mapper().merge_with_assessment(word, phoneme_details)


# 测试
if __name__ == "__main__":
    mapper = PhonemeMapper()

    print("音素映射测试 (使用 Gi2Pi)")
    print("=" * 60)

    test_words = ['pretty', 'hello', 'beautiful', 'through', 'knight', 'phone']

    for word in test_words:
        print(f"\n单词: {word}")
        phonemes = mapper.get_phonemes(word)
        print(f"IPA: {phonemes}")

        mapping = mapper.get_letter_mapping(word)
        print("对齐映射:")
        for m in mapping:
            print(f"  {m['letter']:6} -> {m['phoneme'] or '(静音)'}")

    # 测试与评估结果合并
    print("\n" + "=" * 60)
    print("测试与 Azure 评估结果合并")

    mock_assessment = [
        {"phoneme": "p", "accuracy": 95, "error_type": "None"},
        {"phoneme": "ɹ", "accuracy": 45, "error_type": "Mispronunciation"},
        {"phoneme": "ɪ", "accuracy": 80, "error_type": "None"},
        {"phoneme": "t", "accuracy": 50, "error_type": "Mispronunciation"},
        {"phoneme": "i", "accuracy": 55, "error_type": "Mispronunciation"},
    ]

    merged = mapper.merge_with_assessment("pretty", mock_assessment)
    print("\npretty 合并结果:")
    for m in merged:
        acc = m.get('accuracy')
        acc_str = f"{acc:.0f}%" if acc is not None else "N/A"
        status = "✓" if acc and acc >= 60 else "✗" if acc else "?"
        print(f"  {m['letter']:6} -> {m['phoneme']:4} | {acc_str:>5} {status}")
