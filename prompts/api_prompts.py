"""
高考英语阅读理解生成器 - API 提示词模板

使用方法：
1. 导入对应的提示词模板
2. 使用 format() 方法填充参数
3. 发送给 LLM API

示例：
    from api_prompts import READING_GENERATOR_SYSTEM, get_reading_prompt

    system_prompt = READING_GENERATOR_SYSTEM
    user_prompt = get_reading_prompt(
        passage_type="C",
        topic="人工智能对教育的影响",
        target_words=["artificial", "intelligence", "transform"]
    )
"""

# ==================== 系统提示词 ====================

READING_GENERATOR_SYSTEM = """你是中国高考英语命题专家，严格按照高考标准生成阅读理解题。

核心规则：
1. 正确答案必须同义替换原文，不能直接复制
2. 干扰项要有迷惑性，但不能使用绝对词(always/never/all/none)
3. 每道题只能有一个正确答案
4. 所有选项长度相近，语法正确

输出必须是有效的JSON格式。"""


# ==================== 用户提示词模板 ====================

READING_PROMPT_TEMPLATE = """请生成一道{passage_type}篇难度的高考英语阅读理解题。

【参数】
- 篇目类型：{passage_type}篇
- 主题：{topic}
- 核心词汇（必须在文章中使用）：{target_words}

【词汇要求】
文章必须包含上述核心词汇，这些是高考必背词汇。允许适当扩展使用其他词汇以丰富文章内容。

【{passage_type}篇规范】
{passage_spec}

【题目分布】
{question_spec}

【答案解析要求】
每道题必须包含详细的"teaching_explanation"字段，用老师给学生讲课的口吻，包含：
1. 本题考点（如"细节理解-信息定位"、"推理判断-作者态度"、"词义猜测-上下文推断"）
2. 正确答案为什么对：引用原文具体句子，说明同义替换关系
3. 每个错误选项为什么错：标注干扰手法（张冠李戴/曲解原意/无中生有/过度推理/以偏概全）并具体解释
4. 做题技巧提示（可选）

【输出JSON格式】
{{
  "passage": "文章正文（英文原文，分段用\\n\\n分隔）",
  "passage_translation": ["第一段中文翻译", "第二段中文翻译", "第三段中文翻译", "..."],
  "word_count": 词数,
  "questions": [
    {{
      "number": 1,
      "type": "题型",
      "question": "题目",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "answer": "正确答案字母",
      "teaching_explanation": "像老师讲课一样的详细解析，示例：\n\n这道题考查的是【细节理解】能力，需要在文中定位具体信息。\n\n正确答案是C。我们来看原文第二段：\"原文引用...\"。选项C说的\"选项内容...\"就是对这句话的同义替换。\n\n为什么其他选项错了呢？\n\nA选项说\"...\"，这属于【无中生有】。原文根本没提到这个信息。\n\nB选项说\"...\"，这是【曲解原意】。原文说的是X，不是Y。\n\nD选项说\"...\"，也是【过度推理】。原文只暗示了X，没有说Y。\n\n【做题技巧】细节题要注意同义替换，警惕看起来相关但实际偏离的干扰项。"
    }}
  ]
}}"""


# ==================== 主题池配置（按难度分类） ====================

TOPIC_POOLS = {
    "medium": [
        "科技发展与日常生活",
        "环境保护与可持续发展",
        "健康生活方式",
        "社会现象分析",
        "教育创新与变革",
        "心理健康与压力管理",
        "文化传承与交流",
        "城市发展与规划",
        "网络社交的利弊",
        "青少年成长问题",
        "职业规划与发展",
        "科学发现与应用"
    ],
    "hard": [
        "人工智能与未来社会",
        "心理学最新研究成果",
        "全球经济趋势分析",
        "医学与健康科学进展",
        "社会学研究发现",
        "前沿科技突破",
        "气候变化与应对策略",
        "基因技术与伦理",
        "认知科学新发现",
        "教育心理学研究",
        "跨文化交流研究",
        "神经科学与大脑研究"
    ]
}

# 难度对应的篇目类型
DIFFICULTY_TO_PASSAGE = {
    "medium": "C",  # 说明文
    "hard": "D"     # 学术说明文/议论文
}


# ==================== 各篇目规范 ====================

PASSAGE_SPECS = {
    "A": """- 体裁：应用文（广告/通知/指南/活动介绍）
- 词数：250-300词
- 难度：简单
- 特点：信息点明确，含时间/地点/价格等具体信息""",

    "B": """- 体裁：记叙文（人物故事/哲理故事/个人经历）
- 词数：300-350词
- 难度：中等偏易
- 特点：时间顺序叙述，有情感变化或启示""",

    "C": """- 体裁：说明文（科普/社会现象/环保/健康）
- 词数：350-400词
- 难度：中等
- 特点：现象→原因→影响/解决方案的结构""",

    "D": """- 体裁：学术说明文/议论文（前沿科技/研究发现）
- 词数：380-450词
- 难度：较难
- 特点：含学术术语、长难句、研究数据"""
}

QUESTION_SPECS = {
    "A": "4道细节理解题（考查时间/地点/价格/要求等具体信息）",
    "B": "2道细节理解题 + 1道推理判断题 + 1道主旨大意题",
    "C": "2道细节理解题 + 1道推理判断题 + 1道词义猜测题",
    "D": "1道细节理解题 + 1道推理判断题 + 1道主旨大意题 + 1道词义猜测题"
}


def get_reading_prompt(passage_type: str, topic: str, target_words: list = None) -> str:
    """
    生成阅读理解题的用户提示词

    Args:
        passage_type: 篇目类型 (A/B/C/D)
        topic: 文章主题
        target_words: 需要包含的目标词汇列表

    Returns:
        格式化后的提示词字符串
    """
    passage_type = passage_type.upper()
    if passage_type not in PASSAGE_SPECS:
        raise ValueError(f"passage_type 必须是 A/B/C/D，收到: {passage_type}")

    words_str = ", ".join(target_words) if target_words else "无特定要求"

    return READING_PROMPT_TEMPLATE.format(
        passage_type=passage_type,
        topic=topic,
        target_words=words_str,
        passage_spec=PASSAGE_SPECS[passage_type],
        question_spec=QUESTION_SPECS[passage_type]
    )


# ==================== 单独题型生成提示词 ====================

DETAIL_QUESTION_PROMPT = """根据以下文章生成{count}道细节理解题。

【文章】
{passage}

【要求】
1. 设问方式随机使用：
   - According to the passage, which of the following is TRUE/NOT TRUE about...?
   - What can we learn from the passage about...?
   - Which of the following is NOT mentioned?

2. 正确答案：同义替换原文，有明确依据

3. 干扰项设置（每题3个）：
   - 张冠李戴：混淆不同对象信息
   - 曲解原意：改变程度/范围
   - 无中生有：添加原文未提及的信息

【输出JSON】
{{"questions": [...]}}"""


INFERENCE_QUESTION_PROMPT = """根据以下文章生成{count}道推理判断题。

【文章】
{passage}

【考查方向】
- 逻辑推理：根据文中信息合理推断
- 作者态度：positive/negative/neutral/objective
- 写作目的：to inform/persuade/entertain/warn

【设问方式】
- What can be inferred from the passage?
- It can be concluded that...
- The author's attitude towards... is...
- What is the author's purpose in writing this passage?

【正确答案要求】
- 推理有文中依据但非直接陈述
- 使用委婉词：may/might/probably/likely

【干扰项】
- 过度推理：超出原文范围
- 曲解态度：误判作者立场
- 以偏概全：部分代替整体

【输出JSON】
{{"questions": [...]}}"""


VOCABULARY_QUESTION_PROMPT = """根据以下文章生成{count}道词义猜测题。

【文章】
{passage}

【选词标准】
- 有上下文线索可推断的词/短语
- 多义词在特定语境中的含义
- 代词指代内容
- 短语的深层含义

【设问方式】
- The underlined word "..." probably means...
- What does "..." in Paragraph X refer to?
- The word "..." is closest in meaning to...

【干扰项设置】
- 该词的其他常见含义（不符合语境）
- 与上下文部分相关但不准确
- 字面意思（如果考查引申义）

【输出JSON】
{{"questions": [...]}}"""


MAIN_IDEA_QUESTION_PROMPT = """根据以下文章生成{count}道主旨大意题。

【文章】
{passage}

【设问方式】
- What is the main idea of the passage?
- Which of the following would be the best title?
- The passage is mainly about...
- What does the passage mainly discuss?

【正确答案特征】
- 高度概括，覆盖全文
- 不能太宽泛也不能太具体
- 抓住文章核心观点

【干扰项设置】
- 以偏概全：只涉及部分内容
- 过于宽泛：范围超出文章
- 偏离主题：与主旨无关

【输出JSON】
{{"questions": [...]}}"""


def get_question_prompt(question_type: str, passage: str, count: int = 1) -> str:
    """
    生成单独题型的提示词

    Args:
        question_type: 题型 (detail/inference/vocabulary/main_idea)
        passage: 原文内容
        count: 题目数量

    Returns:
        格式化后的提示词
    """
    prompts = {
        "detail": DETAIL_QUESTION_PROMPT,
        "inference": INFERENCE_QUESTION_PROMPT,
        "vocabulary": VOCABULARY_QUESTION_PROMPT,
        "main_idea": MAIN_IDEA_QUESTION_PROMPT
    }

    if question_type not in prompts:
        raise ValueError(f"question_type 必须是 {list(prompts.keys())}")

    return prompts[question_type].format(count=count, passage=passage)


# ==================== 阅读理解生成函数 ====================

import random
import json
import os

# 词书文件列表（优先使用高考3500词库）
VOCABULARY_BOOKS = [
    "gaokao_3500.json",  # 高考必背词汇（约6000词，覆盖3500核心词）
]

# 缓存词汇列表
_vocabulary_cache = None

def load_vocabulary_from_books() -> list[str]:
    """
    从7本词书中加载所有单词

    Returns:
        list: 所有单词列表
    """
    global _vocabulary_cache
    if _vocabulary_cache is not None:
        return _vocabulary_cache

    words = []
    # 获取词书目录路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    books_dir = os.path.join(current_dir, "..", "data", "books")

    for book_file in VOCABULARY_BOOKS:
        book_path = os.path.join(books_dir, book_file)
        try:
            with open(book_path, "r", encoding="utf-8") as f:
                book_data = json.load(f)
                for item in book_data:
                    if "word" in item:
                        words.append(item["word"])
        except Exception as e:
            print(f"加载词书 {book_file} 失败: {e}")

    _vocabulary_cache = words
    return words


def get_random_target_words(count: int = 8) -> list[str]:
    """
    随机选取目标词汇

    Args:
        count: 选取数量

    Returns:
        list: 随机选取的单词列表
    """
    all_words = load_vocabulary_from_books()
    if not all_words:
        return []
    return random.sample(all_words, min(count, len(all_words)))


def get_random_reading_prompt(difficulty: str = "medium") -> tuple[str, str, str]:
    """
    根据难度随机生成阅读理解提示词

    Args:
        difficulty: 难度等级 (medium/hard)

    Returns:
        tuple: (system_prompt, user_prompt, topic)
    """
    if difficulty not in TOPIC_POOLS:
        difficulty = "medium"

    # 随机选择主题
    topic = random.choice(TOPIC_POOLS[difficulty])

    # 获取对应的篇目类型
    passage_type = DIFFICULTY_TO_PASSAGE[difficulty]

    # 根据难度选取不同数量的目标词汇
    word_count = 10 if difficulty == "hard" else 8
    target_words = get_random_target_words(word_count)

    # 生成提示词
    user_prompt = get_reading_prompt(
        passage_type=passage_type,
        topic=topic,
        target_words=target_words
    )

    return READING_GENERATOR_SYSTEM, user_prompt, topic


# ==================== 批量生成示例 ====================

if __name__ == "__main__":
    # 示例：生成一道 C 篇阅读理解
    prompt = get_reading_prompt(
        passage_type="C",
        topic="社交媒体对青少年心理健康的影响",
        target_words=["social media", "mental health", "anxiety", "depression"]
    )

    print("=== 系统提示词 ===")
    print(READING_GENERATOR_SYSTEM)
    print("\n=== 用户提示词 ===")
    print(prompt)
