#!/usr/bin/env python3
"""
单词听写模块 - 针对已学单词的间隔重复练习

本模块专门用于中学生听写练习，适用场景：
1. 学生在学校已经学习过单词（非全新词汇）
2. 通过听写测试检验记忆效果
3. 根据听写结果安排后续复习

设计特点：
- 基于 FSRS (Free Spaced Repetition Scheduler) 算法
- 针对"已学单词"场景调整了初始稳定性参数
- 最短复习间隔为 1 天（适合中学生的实际学习节奏）
- 按记忆可提取性（Retrievability）排序，优先复习即将遗忘的单词

与 Anki 的区别：
- Anki 针对"学习全新内容"，有学习步骤（1分钟→10分钟→1天）
- 本模块针对"复习已学内容"，首次正确即可安排较长间隔

评分规则：
- 一次正确 (Easy): 掌握牢固，14天后复习
- 两次正确 (Good): 基本掌握，7天后复习
- 三次正确 (Hard): 有点生疏，3天后复习
- 错误 (Again): 薄弱词，1天后复习

Usage:
    python dictation.py              # 使用默认词书（北师大七上）
    python dictation.py --list       # 列出可用词书
    python dictation.py --book xxx   # 指定词书
"""

import json
import os
import sys
import argparse
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from pathlib import Path

from bookmanager import BookManager, Word

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv 可选

# 阿里云百炼 Qwen API
try:
    import httpx
    QWEN_AVAILABLE = True
except ImportError:
    QWEN_AVAILABLE = False

# 项目路径
PROJECT_ROOT = Path(__file__).parent
DEFAULT_BOOK = "bsd_grade7_up"

# TTS（使用统一 tts 模块）

# FSRS 参数
FSRS_W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]


@dataclass
class Card:
    """
    单词卡片数据类

    包含单词基本信息和 FSRS 学习状态。

    FSRS 核心参数说明：
    - difficulty (D): 单词难度，范围 1-10，根据每次复习结果动态调整
    - stability (S): 记忆稳定性，单位为天，表示记忆半衰期
    - state: 学习状态 (0=新卡, 1=学习中, 2=复习中)

    可提取性 (Retrievability) 由 stability 和距上次复习的时间计算得出：
    R = 0.9 ^ (elapsed_days / stability)
    """
    word: str
    phonetic: str
    translation: str
    unit: str

    # FSRS 状态
    difficulty: float = 0.0  # 难度 D
    stability: float = 0.0   # 稳定性 S
    state: int = 0           # 0=新卡, 1=学习中, 2=复习中

    # 学习记录
    reps: int = 0            # 复习次数
    lapses: int = 0          # 遗忘次数
    last_review: Optional[str] = None  # 上次复习时间
    due: Optional[str] = None          # 下次复习时间

    # 本次学习数据
    attempts: int = 0        # 本次尝试次数
    correct: bool = False    # 本次是否正确
    current_inputs: List[str] = field(default_factory=list)  # 本次输入记录

    # 历史学习记录（用于大模型分析错误模式）
    history: List[Dict] = field(default_factory=list)

    @classmethod
    def from_word(cls, word: Word) -> "Card":
        """从 Word 对象创建 Card"""
        return cls(
            word=word.word,
            phonetic=word.phonetic,
            translation=word.translation,
            unit=word.unit
        )


@dataclass
class LearningSession:
    """学习会话"""
    cards: List[Card] = field(default_factory=list)
    current_index: int = 0
    correct_count: int = 0
    wrong_count: int = 0
    start_time: Optional[datetime] = None


def load_progress(progress_file: str) -> Dict[str, dict]:
    """加载学习进度"""
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_progress(progress_file: str, cards: List[Card]):
    """保存学习进度"""
    # 先加载现有进度（保留历史记录）
    existing = {}
    if os.path.exists(progress_file):
        with open(progress_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

    progress = {}
    for card in cards:
        if card.reps > 0:  # 只保存学习过的卡片
            # 获取已有的历史记录
            existing_history = existing.get(card.word, {}).get('history', [])

            # 合并新的历史记录
            all_history = existing_history + card.history

            progress[card.word] = {
                'difficulty': card.difficulty,
                'stability': card.stability,
                'state': card.state,
                'reps': card.reps,
                'lapses': card.lapses,
                'last_review': card.last_review,
                'due': card.due,
                'history': all_history
            }

    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def apply_progress(cards: List[Card], progress: Dict[str, dict]):
    """应用学习进度到卡片"""
    for card in cards:
        if card.word in progress:
            p = progress[card.word]
            card.difficulty = p.get('difficulty', 0.0)
            card.stability = p.get('stability', 0.0)
            card.state = p.get('state', 0)
            card.reps = p.get('reps', 0)
            card.lapses = p.get('lapses', 0)
            card.last_review = p.get('last_review')
            card.due = p.get('due')
            # 不加载历史到内存（历史记录在保存时直接从文件合并）


# ==================== FSRS 核心算法 ====================

def init_difficulty(grade: int) -> float:
    """初始化难度 (grade: 1-4, 对应 Again/Hard/Good/Easy)"""
    return max(1, min(10, FSRS_W[4] - (grade - 3) * FSRS_W[5]))


def init_stability(grade: int) -> float:
    """
    初始化稳定性
    针对"学校已学过"的场景调整：
    - 一次正确(Easy): 学生掌握牢固，14天后复习
    - 两次正确(Good): 基本掌握，7天后复习
    - 三次正确(Hard): 有点生疏，3天后复习
    - 错误(Again): 薄弱词，1天后复习
    """
    # 针对已学单词的初始稳定性（比标准 FSRS 更长）
    INIT_STABILITY_FOR_LEARNED = {
        1: 1.0,   # Again - 错误，1天后
        2: 3.0,   # Hard - 3次才对，3天后
        3: 7.0,   # Good - 2次才对，7天后
        4: 14.0,  # Easy - 1次就对，14天后
    }
    return INIT_STABILITY_FOR_LEARNED.get(grade, 1.0)


def next_difficulty(d: float, grade: int) -> float:
    """更新难度"""
    new_d = d - FSRS_W[6] * (grade - 3)
    return max(1, min(10, FSRS_W[7] * init_difficulty(3) + (1 - FSRS_W[7]) * new_d))


def next_recall_stability(d: float, s: float, r: float, grade: int) -> float:
    """计算复习后的新稳定性"""
    hard_penalty = FSRS_W[15] if grade == 2 else 1
    easy_bonus = FSRS_W[16] if grade == 4 else 1
    return s * (1 +
        pow(2.71828, FSRS_W[8]) *
        (11 - d) *
        pow(s, -FSRS_W[9]) *
        (pow(2.71828, FSRS_W[10] * (1 - r)) - 1) *
        hard_penalty * easy_bonus
    )


def next_forget_stability(d: float, s: float, r: float) -> float:
    """遗忘后的新稳定性"""
    return FSRS_W[11] * pow(d, -FSRS_W[12]) * (pow(s + 1, FSRS_W[13]) - 1) * pow(2.71828, FSRS_W[14] * (1 - r))


def retrievability(s: float, t: float) -> float:
    """计算可提取性 (记忆保持率)"""
    if s <= 0:
        return 0
    return pow(0.9, t / s)


def next_interval(s: float, desired_r: float = 0.9) -> int:
    """
    计算下次复习间隔

    Args:
        s: 稳定性 (天)
        desired_r: 期望记忆保持率，默认 0.9 (90%)

    Returns:
        复习间隔天数，最小 1 天，最大 365 天

    Note:
        最短间隔设为 1 天，适合中学生的实际学习节奏。
        不会出现几小时后复习的情况。
    """
    if s <= 0:
        return 1
    FACTOR = 19.0 / 81.0  # FSRS-4.5 标准常量
    DECAY = -0.5
    interval = (s / FACTOR) * (pow(desired_r, 1.0 / DECAY) - 1)
    return max(1, min(365, round(interval)))  # 最小间隔 1 天


def fsrs_schedule(card: Card, grade: int) -> Card:
    """
    FSRS 调度算法 - 根据听写结果更新卡片状态

    Args:
        card: 单词卡片
        grade: 评分
            - 1 (Again): 错误，最终未能正确拼写
            - 2 (Hard): 第3次尝试才正确
            - 3 (Good): 第2次尝试正确
            - 4 (Easy): 第1次尝试就正确

    Returns:
        更新后的卡片

    Note:
        对于新卡（首次听写），使用针对"已学单词"调整的初始稳定性：
        - Easy: 14天, Good: 7天, Hard: 3天, Again: 1天
        这比标准 FSRS 的初始值更长，因为学生已在学校学过这些单词。
    """
    now = datetime.now()
    card.last_review = now.isoformat()
    card.reps += 1

    if card.state == 0:  # 新卡
        card.difficulty = init_difficulty(grade)
        card.stability = init_stability(grade)
        card.state = 1 if grade < 3 else 2

    else:  # 复习卡
        # 计算当前可提取性
        if card.due:
            due_time = datetime.fromisoformat(card.due)
            elapsed = (now - due_time).days
        else:
            elapsed = 0

        r = retrievability(card.stability, max(0, elapsed))

        # 更新难度
        card.difficulty = next_difficulty(card.difficulty, grade)

        # 更新稳定性
        if grade == 1:  # 遗忘
            card.stability = next_forget_stability(card.difficulty, card.stability, r)
            card.lapses += 1
            card.state = 1  # 进入重新学习
        else:
            card.stability = next_recall_stability(card.difficulty, card.stability, r, grade)
            card.state = 2

    # 计算下次复习时间
    interval = next_interval(card.stability)
    card.due = (now + timedelta(days=interval)).isoformat()

    return card


# ==================== 用户界面 ====================

def clear_screen():
    """清屏"""
    os.system('cls' if os.name == 'nt' else 'clear')


def display_card(card: Card, index: int, total: int):
    """显示单词卡片"""
    print(f"\n{'='*50}")
    print(f"  进度: {index + 1}/{total}")
    print(f"{'='*50}")
    print()

    # 提取词性
    translation = card.translation
    pos = ""
    if translation.startswith("n."):
        pos = "n."
    elif translation.startswith("v."):
        pos = "v."
    elif translation.startswith("adj."):
        pos = "adj."
    elif translation.startswith("adv."):
        pos = "adv."
    elif translation.startswith("pron."):
        pos = "pron."
    elif translation.startswith("prep."):
        pos = "prep."
    elif translation.startswith("conj."):
        pos = "conj."
    elif translation.startswith("int."):
        pos = "int."

    # 显示词性和中文
    if pos:
        meaning = translation[len(pos):].strip()
        print(f"  【{pos}】{meaning}")
    else:
        print(f"  {translation}")

    print()


def check_answer(card: Card, user_input: str) -> bool:
    """检查答案"""
    return user_input.strip().lower() == card.word.lower()


# ==================== 相似度计算 ====================

def levenshtein_distance(s1: str, s2: str) -> int:
    """
    计算两个字符串的编辑距离（Levenshtein Distance）

    编辑距离是将一个字符串转换为另一个字符串所需的最少单字符编辑操作次数。
    操作包括：插入、删除、替换。

    Args:
        s1: 第一个字符串
        s2: 第二个字符串

    Returns:
        编辑距离
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 插入、删除、替换的代价
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def calculate_similarity(correct: str, user_input: str) -> float:
    """
    计算用户输入与正确答案的相似度

    Args:
        correct: 正确答案
        user_input: 用户输入

    Returns:
        相似度 (0-1)，1 表示完全相同
    """
    correct_lower = correct.lower().strip()
    input_lower = user_input.lower().strip()

    if not correct_lower or not input_lower:
        return 0.0

    distance = levenshtein_distance(correct_lower, input_lower)
    max_len = max(len(correct_lower), len(input_lower))

    return 1 - (distance / max_len)


def get_error_hint(correct: str, user_input: str) -> str:
    """
    根据相似度返回错误提示

    Args:
        correct: 正确答案
        user_input: 用户输入

    Returns:
        错误提示文本
    """
    similarity = calculate_similarity(correct, user_input)
    if similarity >= 0.7:  # 70% 以上相似，说明只是个别字母错误
        return "拼写错误"
    else:
        return "错误"


async def _tts_synthesize_and_play(text: str, speed: str = "normal"):
    """使用统一 TTS 模块合成并通过 afplay 播放（CLI 模式专用）"""
    from tts import TTSService
    cache_dir = PROJECT_ROOT / "static" / "audio"
    service = TTSService(cache_dir)
    result = await service.synthesize(text=text, language="en", speed=speed)
    if result:
        os.system(f'afplay "{result}" 2>/dev/null')


def play_word(word: str):
    """同步播放单词（CLI 模式）"""
    asyncio.run(_tts_synthesize_and_play(word, "normal"))


def play_word_slow(word: str):
    """同步慢速播放单词（CLI 模式）"""
    asyncio.run(_tts_synthesize_and_play(word, "slow"))


def play_sentence(sentence: str):
    """同步播放句子（CLI 模式）"""
    asyncio.run(_tts_synthesize_and_play(sentence, "moderate"))


# ==================== 阿里云百炼 Qwen API ====================

def generate_example_sentence(word: str, translation: str) -> Optional[Dict]:
    """
    调用阿里云百炼 Qwen-Plus API 生成包含目标单词的例句

    Args:
        word: 目标单词
        translation: 单词释义

    Returns:
        包含 sentence 和 chinese 的字典，失败返回 None
    """
    if not QWEN_AVAILABLE:
        return None

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return None

    prompt = f"""单词 {word}（{translation}），生成一个简单例句帮助学生记忆拼写。
要求：
- 句子简短（10词以内）
- 适合初中生理解
- 目标单词在句中清晰可辨

返回JSON：{{"sentence": "例句", "chinese": "中文翻译"}}"""

    try:
        response = httpx.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-plus",
                "messages": [
                    {"role": "system", "content": "你是一位英语教师助手，辅导中国初中生学习英语词汇。回复使用JSON格式。"},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 200
            },
            timeout=10.0
        )

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            # 解析 JSON（处理可能的 markdown 代码块）
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            return json.loads(content)
    except Exception as e:
        pass

    return None


def show_result(card: Card, correct: bool, attempts: int):
    """显示结果"""
    if correct:
        if attempts == 1:
            print(f"\n  ✓ 正确！")
        else:
            print(f"\n  ✓ 正确！（第 {attempts} 次尝试）")
        # 播放单词发音
        print(f"  🔊 {card.word}")
        play_word(card.word)
    else:
        print(f"\n  ✗ 正确答案: {card.word}")
        # 错误时也播放，帮助记忆
        print(f"  🔊 {card.word}")
        play_word(card.word)

    print(f"  音标: {card.phonetic}")

    # 显示记忆强度（仅对已学习过的单词）
    if card.state > 0 and card.last_review:
        r = get_card_retrievability(card)
        r_percent = int(r * 100)
        if r >= 0.9:
            strength = "强"
        elif r >= 0.7:
            strength = "中"
        else:
            strength = "弱"
        print(f"  记忆强度: {r_percent}% ({strength})")


def grade_from_attempts(attempts: int, correct: bool, skipped: bool = False) -> int:
    """
    根据听写尝试次数确定 FSRS 评分

    评分逻辑（针对已学单词场景）：
    - 第1次就正确 → Easy (4): 学生掌握牢固
    - 第2次才正确 → Good (3): 基本掌握，稍有遗忘
    - 第3次才正确 → Hard (2): 有点生疏，需要加强
    - 最终错误 → Again (1): 薄弱词，需要重点复习
    - 跳过 → Again (1): 完全没印象，需要重点复习

    Args:
        attempts: 尝试次数 (1-3)
        correct: 最终是否正确
        skipped: 是否跳过（完全没印象）

    Returns:
        FSRS 评分 (1-4)
    """
    if skipped or not correct:
        return 1  # Again
    if attempts == 1:
        return 4  # Easy
    elif attempts == 2:
        return 3  # Good
    else:
        return 2  # Hard


def get_card_retrievability(card: Card) -> float:
    """
    计算卡片当前的可提取性（记忆保持率）

    可提取性表示学生此刻能回忆起该单词的概率。
    公式: R = 0.9 ^ (elapsed_days / stability)

    Returns:
        0-1 之间的浮点数：
        - 接近 1.0: 记忆清晰，很可能记得
        - 低于 0.7: 记忆模糊，可能遗忘

    用途：
        用于确定复习优先级，可提取性越低的单词越需要优先复习
    """
    if card.state == 0 or not card.last_review or card.stability <= 0:
        return 1.0  # 新卡或未学习过，返回 1.0

    now = datetime.now()
    last_review_time = datetime.fromisoformat(card.last_review)
    elapsed_days = (now - last_review_time).total_seconds() / 86400  # 转换为天数

    return retrievability(card.stability, max(0, elapsed_days))


def get_due_cards(cards: List[Card], limit: int = 20) -> List[Card]:
    """
    获取今天需要复习的卡片

    排序逻辑：
    1. 到期的复习卡优先，按可提取性从低到高排序（最可能遗忘的优先）
    2. 然后是新卡

    Args:
        cards: 所有卡片列表
        limit: 返回的最大卡片数

    Returns:
        今日待学习的卡片列表
    """
    now = datetime.now()
    due_cards_with_r = []  # (card, retrievability)
    new_cards = []

    for card in cards:
        if card.state == 0:  # 新卡
            new_cards.append(card)
        elif card.due:
            due_time = datetime.fromisoformat(card.due)
            if due_time <= now:
                # 计算可提取性
                r = get_card_retrievability(card)
                due_cards_with_r.append((card, r))

    # 按可提取性从低到高排序（越低越紧急）
    due_cards_with_r.sort(key=lambda x: x[1])
    due_cards = [card for card, r in due_cards_with_r]

    # 优先复习到期卡片，然后是新卡
    result = due_cards[:limit]
    remaining = limit - len(result)
    if remaining > 0:
        result.extend(new_cards[:remaining])

    return result


def run_learning_session(cards: List[Card], progress_file: str):
    """运行学习会话"""
    if not cards:
        print("\n没有需要学习的单词！")
        return

    session = LearningSession(cards=cards, start_time=datetime.now())

    print(f"\n本次学习 {len(cards)} 个单词")
    print("输入单词后按 Enter 确认")
    print("输入 s 跳过（完全没印象），输入 q 退出")
    input("\n按 Enter 开始...")

    wrong_cards = []  # 记录错误的卡片，需要再练

    while session.current_index < len(session.cards):
        card = session.cards[session.current_index]
        card.attempts = 0
        card.correct = False
        card.current_inputs = []  # 重置本次输入记录

        clear_screen()
        display_card(card, session.current_index, len(session.cards))

        max_attempts = 3
        skipped = False
        can_replay = False  # 是否允许重听（第2次错误后开启）
        while card.attempts < max_attempts and not card.correct and not skipped:
            card.attempts += 1

            user_input = input("  请输入单词: ").strip()

            # 处理重听请求（不消耗尝试次数）
            while user_input.lower() == 'r' and can_replay:
                print(f"  🔊 (慢速)")
                play_word_slow(card.word)
                user_input = input("  请输入单词: ").strip()

            if user_input.lower() == 'q':
                print("\n已退出学习")
                save_progress(progress_file, session.cards)
                return

            if user_input.lower() == 's':
                skipped = True
                card.attempts = max_attempts  # 跳过视为用尽所有机会
                card.current_inputs.append("[skipped]")  # 记录跳过
                print(f"\n  ⏭ 跳过 - 正确答案: {card.word}")
                print(f"  🔊 {card.word}")
                play_word(card.word)
                print(f"  音标: {card.phonetic}")
            elif check_answer(card, user_input):
                card.correct = True
                card.current_inputs.append(user_input)  # 记录正确输入
                session.correct_count += 1
            else:
                card.current_inputs.append(user_input)  # 记录错误输入
                # 错误处理：分级提示逻辑
                remaining = max_attempts - card.attempts

                if card.attempts == 1:
                    # 第1次错误：根据相似度给出提示
                    hint = get_error_hint(card.word, user_input)
                    print(f"  ✗ {hint}，还有 {remaining} 次机会")

                elif card.attempts == 2:
                    # 第2次错误：慢速播放发音，允许重听
                    print(f"  ✗ 错误，听一下发音，还有 {remaining} 次机会")
                    print(f"  🔊 (慢速)")
                    play_word_slow(card.word)
                    print(f"  输入 r 可重听")
                    can_replay = True  # 开启重听功能

                # 第3次错误在循环结束后处理

        # 第3次错误：展示例句辅助记忆（不再有输入机会）
        if not card.correct and not skipped and card.attempts >= max_attempts:
            print(f"\n  ✗ 错误")
            example = generate_example_sentence(card.word, card.translation)
            if example and "sentence" in example:
                print(f"  💡 例句: {example['sentence']}")
                if "chinese" in example:
                    print(f"     {example['chinese']}")
                print(f"  🔊")
                play_sentence(example['sentence'])

        if not card.correct:
            session.wrong_count += 1
            wrong_cards.append(card)

        if not skipped:
            show_result(card, card.correct, card.attempts)

        # FSRS 更新
        grade = grade_from_attempts(card.attempts, card.correct, skipped)
        fsrs_schedule(card, grade)

        # 跳过的单词额外记录一次遗忘（因为完全没印象比普通错误更严重）
        if skipped:
            card.lapses += 1

        # 保存本次学习记录到历史
        card.history.append({
            "time": datetime.now().isoformat(),
            "inputs": card.current_inputs.copy(),
            "result": "skipped" if skipped else ("correct" if card.correct else "wrong"),
            "attempts": card.attempts,
            "grade": grade
        })

        # 显示下次复习时间
        if card.due:
            due_time = datetime.fromisoformat(card.due)
            days = (due_time.date() - datetime.now().date()).days
            if days == 0:
                print(f"  下次复习: 今天")
            elif days == 1:
                print(f"  下次复习: 明天")
            else:
                print(f"  下次复习: {days} 天后")

        input("\n  按 Enter 继续...")
        session.current_index += 1

    # 学习结束
    clear_screen()
    print("\n" + "="*50)
    print("  学习完成！")
    print("="*50)
    print(f"\n  正确: {session.correct_count}")
    print(f"  错误: {session.wrong_count}")

    if session.start_time:
        duration = datetime.now() - session.start_time
        minutes = int(duration.total_seconds() // 60)
        seconds = int(duration.total_seconds() % 60)
        print(f"  用时: {minutes}分{seconds}秒")

    # 保存进度
    save_progress(progress_file, session.cards)
    print(f"\n  进度已保存")

    # 如果有错误，询问是否再练
    if wrong_cards:
        print(f"\n  有 {len(wrong_cards)} 个单词需要加强")
        choice = input("  是否继续练习这些单词？(y/n): ").strip().lower()
        if choice == 'y':
            run_learning_session(wrong_cards, progress_file)


def show_statistics(cards: List[Card]):
    """显示统计信息"""
    total = len(cards)
    new_count = sum(1 for c in cards if c.state == 0)
    learning_count = sum(1 for c in cards if c.state == 1)
    review_count = sum(1 for c in cards if c.state == 2)

    now = datetime.now()
    due_today = 0
    urgent_count = 0  # 紧急复习（可提取性 < 70%）

    # 统计记忆强度分布
    r_high = 0    # >= 90%
    r_medium = 0  # 70-90%
    r_low = 0     # < 70%

    for card in cards:
        if card.state > 0 and card.last_review:
            r = get_card_retrievability(card)
            if r >= 0.9:
                r_high += 1
            elif r >= 0.7:
                r_medium += 1
            else:
                r_low += 1

            if card.due:
                due_time = datetime.fromisoformat(card.due)
                if due_time.date() <= now.date():
                    due_today += 1
                    if r < 0.7:
                        urgent_count += 1

    print(f"\n{'='*50}")
    print("  学习统计")
    print(f"{'='*50}")
    print(f"\n  总词汇量: {total}")
    print(f"  新单词: {new_count}")
    print(f"  学习中: {learning_count}")
    print(f"  已掌握: {review_count}")
    print(f"\n  今日待复习: {due_today}", end="")
    if urgent_count > 0:
        print(f" (紧急: {urgent_count})")
    else:
        print()

    # 显示记忆强度分布
    learned = r_high + r_medium + r_low
    if learned > 0:
        print(f"\n  记忆强度分布:")
        print(f"    强 (≥90%): {r_high} 词")
        print(f"    中 (70-90%): {r_medium} 词")
        print(f"    弱 (<70%): {r_low} 词")
    print()


def main_menu(cards: List[Card], progress_file: str):
    """主菜单"""
    while True:
        clear_screen()
        print("\n" + "="*50)
        print("  单词拼写练习 - 北师大版七年级上册")
        print("="*50)

        show_statistics(cards)

        print("  1. 开始今日学习")
        print("  2. 学习新单词 (20个)")
        print("  3. 复习所有单词")
        print("  4. 按单元学习")
        print("  0. 退出")

        choice = input("\n  请选择: ").strip()

        if choice == '1':
            due_cards = get_due_cards(cards, limit=20)
            if due_cards:
                run_learning_session(due_cards, progress_file)
            else:
                print("\n  今天没有需要学习的单词！")
                input("  按 Enter 返回...")

        elif choice == '2':
            new_cards = [c for c in cards if c.state == 0][:20]
            if new_cards:
                run_learning_session(new_cards, progress_file)
            else:
                print("\n  没有新单词了！")
                input("  按 Enter 返回...")

        elif choice == '3':
            run_learning_session(cards.copy(), progress_file)

        elif choice == '4':
            # 按单元显示
            units = {}
            for card in cards:
                unit = card.unit or "未分类"
                if unit not in units:
                    units[unit] = []
                units[unit].append(card)

            print("\n  可用单元:")
            unit_list = list(units.keys())
            for i, unit in enumerate(unit_list, 1):
                print(f"    {i}. {unit} ({len(units[unit])}词)")

            try:
                unit_choice = int(input("\n  选择单元 (输入序号): ")) - 1
                if 0 <= unit_choice < len(unit_list):
                    selected_unit = unit_list[unit_choice]
                    run_learning_session(units[selected_unit], progress_file)
            except ValueError:
                pass

        elif choice == '0':
            print("\n  再见！")
            break


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="单词听写练习")
    parser.add_argument("--book", default=DEFAULT_BOOK, help=f"词书名称 (默认: {DEFAULT_BOOK})")
    parser.add_argument("--list", action="store_true", help="列出可用词书")
    return parser.parse_args()


def main():
    """主程序"""
    args = parse_args()

    # 初始化词书管理器
    book_manager = BookManager()

    # 列出词书
    if args.list:
        print("可用词书:")
        for book_id in book_manager.list_books():
            info = book_manager.get_book_info(book_id)
            print(f"  {info['name']} ({book_id}): {info['total_words']} 词")
        return

    # 加载词书
    book_name = args.book
    book_info = book_manager.get_book_info(book_name) if book_name in book_manager.list_books() else None
    display_name = book_info['name'] if book_info else book_name
    print(f"加载词书: {display_name}")

    try:
        words = book_manager.load(book_name)
    except FileNotFoundError:
        print(f"错误: 词书 '{book_name}' 不存在")
        print("可用词书:", ", ".join(book_manager.list_books()))
        sys.exit(1)

    # 将 Word 转换为 Card
    cards = [Card.from_word(w) for w in words]
    print(f"已加载 {len(cards)} 个单词")

    # 获取进度文件路径
    progress_file = book_manager.get_progress_file(book_name)

    # 加载进度
    progress = load_progress(str(progress_file))
    apply_progress(cards, progress)
    if progress:
        print(f"已恢复 {len(progress)} 个单词的学习进度")

    # 进入主菜单
    main_menu(cards, str(progress_file))


if __name__ == "__main__":
    main()
