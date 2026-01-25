# DeepSeek Prompt 模板设计

本文档定义英语学习应用中各步骤调用 DeepSeek API 的 Prompt 模板。

---

## 通用设定

### System Prompt

```
你是一位英语教师助手，辅导中国初中生学习英语词汇。回复使用中文，简洁直接。
```

### 输出格式

所有 Prompt 都要求返回 JSON 格式，便于程序解析。

---

## Step 1: 听 - 发音反馈

### 场景
学生跟读单词后，Azure Speech API 返回评分，DeepSeek 给出简洁诊断。

### Prompt

```
单词 {word} {phonetic}，学生发音评分 {score}/100。
问题音素：{problem_phoneme} {phoneme_score}分（可能发成了 {mistake}）

用JSON简洁反馈：
{
  "problem": "问题音素及发音要点（一句话）",
  "tip": "纠正方法（一句话）",
  "practice_words": ["练习词1", "练习词2"]
}

要求：practice_words 列出2-3个含相同音素的简单词，用于跟读练习。
```

### 示例

**输入：**
```
单词 daughter /ˈdɔːtə(r)/，学生发音评分 55/100。
问题音素：/ɔː/ 45分（可能发成了 /o/）
```

**输出：**
```json
{
  "problem": "/ɔː/ 发音不到位，可能发成了短音 /o/，元音长度不足",
  "tip": "发 /ɔː/ 时嘴型张大，舌位放低后缩，保持长音",
  "practice_words": ["thought", "water", "law"]
}
```

---

## Step 2: 看 - 记忆辅助

### 场景
展示单词时，通过相似发音的已知词帮助记忆新词。

### Prompt

```
单词 {word} {phonetic}，释义：{translation}

用JSON生成记忆辅助：
{
  "similar_sounds": [{"word": "相似词", "phonetic": "音标", "meaning": "含义"}],
  "word_family": [{"word": "同根词", "meaning": "含义"}],
  "spelling_tip": "拼写技巧（一句话）"
}

要求：
- similar_sounds: 2-3个发音相似的初中常见词
- word_family: 1-2个同根词或派生词（如有）
- spelling_tip: 简短拼写记忆技巧
```

### 示例

**输入：**
```
单词 daughter /ˈdɔːtə(r)/，释义：n. 女儿
```

**输出：**
```json
{
  "similar_sounds": [
    {"word": "doctor", "phonetic": "/ˈdɒktə(r)/", "meaning": "n. 医生"},
    {"word": "water", "phonetic": "/ˈwɔːtə(r)/", "meaning": "n. 水"}
  ],
  "word_family": [
    {"word": "granddaughter", "meaning": "n. 孙女"}
  ],
  "spelling_tip": "daughter 中 'gh' 不发音，记住 dau + gh + ter"
}
```

### 使用流程
1. 播放目标单词 TTS
2. 依次播放相似词 TTS
3. 学生跟读（不需要 Azure 评估）
4. 再次播放目标单词

---

## Step 3: 用 - 语境例句

### 场景
生成贴近学生生活的例句和练习题。

### Prompt

```
单词 {word}（{pos}），释义：{translation}，学生年级：七年级

用JSON生成语境练习：
{
  "example_sentences": [
    {"scene": "场景", "english": "英文句", "chinese": "中文译", "highlight_word": "目标词形式"}
  ],
  "fill_blank": {
    "sentence": "_____ 填空句",
    "answer": "答案",
    "hint": "提示",
    "chinese": "中文译"
  },
  "choice_question": {
    "question": "题目",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "answer": "正确选项",
    "explanation": "解析"
  }
}

要求：
- 例句3个场景：校园、家庭、日常生活
- 句子难度适合初中生
- 填空题挖掉目标单词
- 选择题考察语境用法
```

### 示例

**输入：**
```
单词 invite（v.），释义：邀请，学生年级：七年级
```

**输出：**
```json
{
  "example_sentences": [
    {"scene": "校园", "english": "Our teacher invited a scientist to give us a speech.", "chinese": "老师邀请了一位科学家给我们演讲。", "highlight_word": "invited"},
    {"scene": "家庭", "english": "Mom invited grandparents to have dinner with us.", "chinese": "妈妈邀请爷爷奶奶和我们一起吃饭。", "highlight_word": "invited"},
    {"scene": "日常", "english": "Would you like to invite your friend to the party?", "chinese": "你想邀请朋友来派对吗？", "highlight_word": "invite"}
  ],
  "fill_blank": {
    "sentence": "Li Ming _____ me to his birthday party last Sunday.",
    "answer": "invited",
    "hint": "邀请（注意时态）",
    "chinese": "上周日李明邀请我参加他的生日派对。"
  },
  "choice_question": {
    "question": "选择正确的句子：",
    "options": ["A. She invited me go to the movie.", "B. She invited me to go to the movie.", "C. She invited me going to the movie.", "D. She invited me for go to the movie."],
    "answer": "B",
    "explanation": "invite sb. to do sth. 是固定搭配，to 后接动词原形。"
  }
}
```

---

## Step 4: 写 - 拼写诊断

### 场景
学生拼写错误时，简洁指出错误。

### Prompt

```
学生把 {correct} 写成了 {student_input}，用JSON简洁指出错误：
{"error": "错在哪", "correct": "{correct}"}
只需这两个字段，error不超过10个字。
```

### 示例

| 正确拼写 | 学生输入 | 输出 |
|---------|---------|------|
| daughter | daugther | `{"error": "gh和t顺序反了", "correct": "daughter"}` |
| tomorrow | tommorow | `{"error": "多了一个m", "correct": "tomorrow"}` |
| beautiful | beatiful | `{"error": "少了字母a", "correct": "beautiful"}` |
| friend | freind | `{"error": "e和i位置反了", "correct": "friend"}` |

---

## Step 5: 测 - 学习总结

### 场景
完成当天所有单词学习后，批量总结学习情况。

### Prompt

```
单词 {word}，学习数据：发音{pron_score}分，拼写{spell_attempts}次，记忆质量{memory_quality}/5。

用JSON简洁总结：
{
  "weakness": "薄弱点（无则填null）",
  "review_days": 复习间隔天数,
  "related_words": ["相关词1", "相关词2"]
}

要求：
- weakness: 发音<70/拼写>2次/记忆<3 时标记，否则null
- review_days: 记忆质量 5→7天，4→3天，3→1天，≤2→0（当天）
- related_words: 1-2个同根词或相关词
```

### 示例

| 学习数据 | 输出 |
|---------|------|
| 发音55分，拼写2次，记忆3/5 | `{"weakness": "发音", "review_days": 1, "related_words": ["granddaughter"]}` |
| 发音90分，拼写1次，记忆5/5 | `{"weakness": null, "review_days": 7, "related_words": ["..."]}}` |
| 发音65分，拼写3次，记忆2/5 | `{"weakness": "发音、拼写", "review_days": 0, "related_words": ["..."]}` |

---

## API 参数

```json
{
  "model": "deepseek-chat",
  "response_format": {"type": "json_object"}
}
```

| 步骤 | temperature | max_tokens |
|------|-------------|------------|
| Step 1 听 | 0.6 | 400 |
| Step 2 看 | 0.7 | 600 |
| Step 3 用 | 0.7 | 800 |
| Step 4 写 | 0.5 | 200 |
| Step 5 测 | 0.6 | 300 |

---

## 设计原则

1. **简洁直接** - 不需要冗长的鼓励语言，直接给出有用信息
2. **结构化输出** - JSON 格式便于程序解析
3. **字段精简** - 只返回必要字段，减少 token 消耗
4. **可缓存** - Step 2 的输出可以缓存，相同单词复用
