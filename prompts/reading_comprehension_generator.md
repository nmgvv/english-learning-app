# 高考英语阅读理解出题规律分析与 LLM 生成提示词

## 一、出题规律分析

### 1. 文章结构与难度分布

| 篇目 | 体裁 | 主题 | 难度 | 词数 |
|------|------|------|------|------|
| A篇 | 应用文 | 旅游/广告/通知 | 简单 | 250-300词 |
| B篇 | 记叙文 | 人物故事/哲理故事 | 中等偏易 | 300-350词 |
| C篇 | 说明文 | 科普/环保/社会现象 | 中等 | 350-400词 |
| D篇 | 议论文/说明文 | 前沿科技/学术研究 | 较难 | 380-450词 |

### 2. 四大题型及占比

| 题型 | 占比 | 设问特征 |
|------|------|----------|
| 细节理解题 | 50-60% | What/When/Where/Who/Why/How, Which...is true/false |
| 推理判断题 | 20-30% | infer, suggest, imply, conclude, indicate, be likely to |
| 主旨大意题 | 10-15% | main idea, best title, mainly about, purpose |
| 词义猜测题 | 5-10% | The word "..." means, refers to, closest in meaning |

### 3. 题目设问句型模板

#### 细节理解题
- According to the passage, which of the following is TRUE/NOT TRUE?
- What can we learn from the passage about...?
- The author mentions ... to show that...
- Which of the following is NOT mentioned in the passage?
- How many/much/long...?

#### 推理判断题
- What can be inferred from the passage?
- It can be concluded from the passage that...
- The author's attitude towards ... is...
- What is the author's purpose in writing this passage?
- The passage is most likely taken from...

#### 主旨大意题
- What is the main idea of the passage?
- What is the best title for this passage?
- The passage is mainly about...
- What does the passage mainly discuss?

#### 词义猜测题
- The underlined word "..." in Paragraph X probably means...
- The phrase "..." in Line X refers to...
- Which of the following is closest in meaning to "..."?

### 4. 选项设置规律

#### 正确答案特征
1. **同义替换**：用近义词/短语替换原文表达
2. **语态转换**：主动↔被动语态转换
3. **委婉表达**：含 can/may/might/possible/some 等词
4. **高度概括**：归纳总结原文信息

#### 干扰项设置手法
1. **张冠李戴**：把A的特征说成B的
2. **以偏概全**：用部分信息代替整体
3. **无中生有**：添加原文没有的信息
4. **曲解原意**：改变原文的程度/范围/态度
5. **偷换概念**：在不显眼处替换关键词
6. **过度推理**：推断超出原文范围
7. **绝对化表达**：使用 always/never/must/all/none 等绝对词

### 5. 文章难度标准

- **词汇**：生词率低于3%，符合高考大纲要求
- **句长**：平均句长20词左右，含长难句
- **易读度**：Flesch指数58-70（中等难度）
- **总词数**：4篇合计1540-1630词

---

## 二、LLM 生成提示词

### 提示词 1：生成完整阅读理解题（通用版）

```
你是一位资深的高考英语命题专家，请根据以下要求生成一道高考英语阅读理解题。

【基本参数】
- 篇目类型：{A篇/B篇/C篇/D篇}
- 目标词汇：{可选，需要包含的单词列表}
- 主题领域：{如：科技/环保/人物故事/旅游/社会现象}

【文章要求】
1. 体裁：
   - A篇：应用文（广告/通知/指南）
   - B篇：记叙文（人物故事/哲理故事）
   - C篇：说明文（科普/社会现象）
   - D篇：议论文/学术说明文

2. 难度：
   - A篇：简单，250-300词
   - B篇：中等偏易，300-350词
   - C篇：中等，350-400词
   - D篇：较难，380-450词

3. 语言特点：
   - 生词率低于3%
   - 句子平均长度约20词
   - 包含2-3个长难句（从句/非谓语/倒装等）
   - 使用高中课标词汇为主

【题目要求】
每篇设置4道选择题（A/B/C/D四个选项），题型分布：
- 2道细节理解题
- 1道推理判断题
- 1道主旨大意题或词义猜测题

【选项设置规则】
正确答案：
- 使用同义替换，不直接复制原文
- 可使用被动/主动语态转换
- 使用委婉表达（may/might/probably/likely）

干扰项（每题3个）：
- 1个"张冠李戴"：混淆文中不同对象
- 1个"曲解原意"：改变程度/范围/态度
- 1个"无中生有"或"过度推理"

【输出格式】
```json
{
  "passage": "文章正文",
  "word_count": 文章词数,
  "questions": [
    {
      "number": 1,
      "type": "细节理解题",
      "question": "题目",
      "options": {
        "A": "选项A",
        "B": "选项B",
        "C": "选项C",
        "D": "选项D"
      },
      "answer": "正确答案字母",
      "explanation": "解析说明",
      "distractor_analysis": {
        "A": "干扰手法说明",
        "B": "...",
        "C": "...",
        "D": "..."
      }
    }
  ],
  "vocabulary": ["文中重点词汇列表"],
  "difficulty": "难度等级"
}
```
```

### 提示词 2：批量生成细节理解题

```
你是高考英语命题专家。请根据以下文章生成{N}道细节理解题。

【原文】
{文章内容}

【出题要求】
1. 题型：细节理解题
2. 设问方式（随机使用）：
   - According to the passage, ...
   - What can we learn about ... from the passage?
   - Which of the following is TRUE/NOT TRUE about ...?
   - The author mentions ... to show that ...

3. 正确答案要求：
   - 必须使用同义替换，禁止直接复制原文
   - 信息准确，可在原文找到依据

4. 干扰项要求（每题3个干扰项）：
   - 干扰项1：张冠李戴（混淆文中不同对象的信息）
   - 干扰项2：曲解原意（改变原文的程度、范围或态度）
   - 干扰项3：无中生有（添加原文未提及的信息）

5. 干扰项禁止事项：
   - 不能出现明显的语法错误
   - 不能与原文完全矛盾（要有一定迷惑性）
   - 不能使用绝对化表达（always/never/all/none）

【输出格式】
对每道题输出：题目、四个选项、正确答案、解析、各干扰项的设置手法
```

### 提示词 3：生成推理判断题

```
你是高考英语命题专家。请根据以下文章生成{N}道推理判断题。

【原文】
{文章内容}

【出题要求】
1. 题型：推理判断题
2. 考查方向（选择1-2种）：
   - 逻辑推理：根据文中信息进行合理推断
   - 作者态度：判断作者对某事物的态度（positive/negative/neutral/objective）
   - 写作目的：分析作者写作意图（to inform/persuade/entertain/criticize）
   - 文章出处：判断文章可能来源（newspaper/magazine/textbook/website）

3. 设问方式：
   - What can be inferred from the passage?
   - It can be concluded that ...
   - The author's attitude towards ... is ...
   - What is the author's purpose in writing this passage?
   - The passage is most probably taken from ...

4. 正确答案要求：
   - 推理要有文中依据，但不能是原文直接陈述
   - 使用委婉词汇：may/might/probably/likely/possible

5. 干扰项要求：
   - 干扰项1：过度推理（推断超出原文范围）
   - 干扰项2：曲解态度（误判作者立场）
   - 干扰项3：以偏概全（用部分信息代替整体）

【输出格式】
题目、选项、答案、推理依据、干扰项分析
```

### 提示词 4：生成词义猜测题

```
你是高考英语命题专家。请根据以下文章生成{N}道词义猜测题。

【原文】
{文章内容}

【出题要求】
1. 选词标准：
   - 选择有上下文线索可推断的词/短语
   - 可以是多义词在特定语境中的含义
   - 可以是代词指代内容
   - 可以是短语/句子的深层含义

2. 设问方式：
   - The underlined word "..." in Paragraph X probably means ...
   - What does the phrase "..." in Line X refer to?
   - The word "..." is closest in meaning to ...
   - By saying "...", the author means ...

3. 正确答案要求：
   - 符合上下文语境
   - 使用简洁的同义表达

4. 干扰项要求：
   - 干扰项1：该词的其他常见含义（但不符合此语境）
   - 干扰项2：与上下文部分相关但不准确
   - 干扰项3：字面意思（如果考查引申义）

【输出格式】
标出原文中的目标词、题目、选项、答案、上下文线索分析
```

### 提示词 5：生成 A 篇应用文阅读

```
你是高考英语命题专家。请生成一篇A篇难度的应用文阅读理解。

【文章类型】（选择一种）
- 旅游景点/活动介绍
- 课程/培训班广告
- 招聘/志愿者招募
- 图书馆/博物馆指南
- 产品/服务介绍
- 比赛/活动通知

【文章要求】
1. 词数：250-300词
2. 结构清晰，信息点明确
3. 包含具体的时间、地点、价格、联系方式等细节
4. 可使用小标题、项目符号等排版元素
5. 难度：简单，属于"送分题"

【题目要求】
设置4道细节理解题，考查：
- 时间/日期信息
- 地点/位置信息
- 价格/费用信息
- 具体要求/条件
- 联系方式/报名方式

【注意事项】
- 信息要具体、可查证
- 干扰项设置：相似数字混淆、相近时间混淆、不同项目信息混淆
```

### 提示词 6：生成 D 篇学术说明文

```
你是高考英语命题专家。请生成一篇D篇难度的学术说明文阅读理解。

【主题领域】（选择一种）
- 前沿科技（AI/量子计算/生物技术）
- 心理学研究
- 环境科学
- 社会学研究
- 医学健康
- 经济学现象

【文章要求】
1. 词数：380-450词
2. 结构：问题提出→研究方法→研究发现→结论/启示
3. 包含：
   - 2-3个专业术语（需在上下文中可推断）
   - 3-4个长难句（从句嵌套/非谓语/倒装）
   - 数据或研究引用
4. 难度：较难，具有区分度

【题目要求】
设置4道题：
- 1道细节理解题（考查研究细节）
- 1道推理判断题（考查研究结论推断）
- 1道主旨大意题（考查文章中心思想）
- 1道词义猜测题（考查专业术语或代词指代）

【语言特点】
- 使用学术性词汇
- 多用被动语态
- 使用逻辑连接词（however/therefore/in contrast/as a result）
```

---

## 三、使用建议

### 1. 生成流程
1. 确定目标篇目（A/B/C/D）
2. 选择主题和目标词汇
3. 使用对应提示词生成文章
4. 检查并调整难度
5. 验证答案和干扰项设置

### 2. 质量检查清单
- [ ] 文章词数符合要求
- [ ] 生词率低于3%
- [ ] 题型分布合理
- [ ] 正确答案有原文依据
- [ ] 干扰项有迷惑性但不绝对化
- [ ] 选项语法正确

### 3. 难度调节方法
- **降低难度**：减少长难句、使用更常见词汇、增加信息冗余
- **提高难度**：增加长难句、使用多义词、需要跨段落整合信息

---

## 四、参考来源

本分析基于以下资料：
- [2025高考新课标 I 卷英语题考点解析](https://zhuanlan.zhihu.com/p/1925297366413574943)
- [2024高考英语阅读理解答题的56条规律](https://www.gaokzx.com/c/202309/80539_2.html)
- [高考英语阅读理解4类题型解题攻略](https://gaokao.eol.cn/zhidao/202103/t20210316_2084992.shtml)
- [高考英语阅读理解干扰项设置规律](https://m.fx361.com/news/2016/1111/317320.html)
- [高中英语阅读理解9大题型+解题技巧](https://www.gaokzx.com/c/202202/58801.html)
- [2018-2020年高考英语全国卷I阅读理解内容效度分析](https://m.fx361.com/news/2022/0929/11412535.html)
- [高考英语阅读理解正确选项的十大特征](https://app.gaokaozhitongche.com/newsfeatured/h/gPgX96rl)
