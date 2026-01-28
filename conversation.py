"""
AI 对话练习模块

提供基于已学单词的语音对话练习功能。
使用阿里云百炼 Qwen-Plus API 生成对话内容和评估学生回复。

Usage:
    from conversation import ConversationManager

    manager = ConversationManager()

    # 开始对话
    result = await manager.start_conversation(words)

    # 评估回复
    feedback = await manager.evaluate_response(conversation_id, user_input, target_words)

    # 获取总结
    summary = await manager.get_summary(conversation_id)
"""

import uuid
import json
import os
import httpx
from typing import List, Dict, Set


class ConversationManager:
    """对话管理器"""

    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = "qwen-plus"

        # 内存中存储对话状态（生产环境应使用数据库）
        self.conversations: Dict[str, dict] = {}

    def is_available(self) -> bool:
        """检查服务是否可用"""
        return bool(self.api_key)

    async def _call_qwen(self, system_prompt: str, user_prompt: str, history: List[Dict] = None) -> dict:
        """调用阿里云百炼 Qwen-Plus API

        Args:
            system_prompt: 系统提示
            user_prompt: 用户提示
            history: 对话历史 [{"role": "user/assistant", "content": "..."}, ...]
        """
        if not self.is_available():
            raise Exception("阿里云百炼 API 未配置")

        # 清除代理环境变量
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
            os.environ.pop(key, None)

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]

        # 添加对话历史
        if history:
            messages.extend(history)

        # 添加当前用户消息
        messages.append({"role": "user", "content": user_prompt})

        async with httpx.AsyncClient(proxy=None, timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # 解析 JSON（处理可能的 markdown 代码块）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return json.loads(content)
            else:
                raise Exception(f"API error: {response.status_code} - {response.text}")

    def _calculate_rounds(self, word_count: int) -> int:
        """根据单词数量计算对话轮数"""
        if word_count < 10:
            return 3
        elif word_count < 20:
            return 5
        elif word_count < 40:
            return 7
        else:
            return 10

    async def start_conversation(self, words: List[Dict], mode: str = "guided", rounds: int = None) -> Dict:
        """
        开始对话

        Args:
            words: 已学单词列表 [{"word": "...", "translation": "..."}, ...]
            mode: 对话模式（目前只支持 "guided"）
            rounds: 对话轮数（可选，不传则根据单词数量自动计算）

        Returns:
            {
                "conversation_id": "uuid",
                "greeting": "中文开场白",
                "question": "英文问题",
                "question_chinese": "问题中文翻译",
                "target_words": ["单词1", "单词2"],
                "total_rounds": 总轮数,
                "scenario": "场景描述"
            }
        """
        conversation_id = str(uuid.uuid4())

        # 根据单词数量决定使用多少单词和对话轮数
        word_count = len(words)
        total_rounds = rounds if rounds else self._calculate_rounds(word_count)

        # 限制单词数量，避免 prompt 过长，但根据轮数适当调整
        max_words = min(word_count, total_rounds * 4)  # 每轮约使用2-4个单词
        limited_words = words[:max_words]
        words_text = "\n".join([f"- {w['word']}（{w['translation']}）" for w in limited_words])

        # 根据单词数量调整对话复杂度描述
        if word_count < 10:
            complexity = "非常简单"
            sentence_limit = "8词以内"
        elif word_count < 20:
            complexity = "简单"
            sentence_limit = "10词以内"
        elif word_count < 40:
            complexity = "适中"
            sentence_limit = "12词以内"
        else:
            complexity = "稍有挑战"
            sentence_limit = "15词以内"

        # 设计连贯的情景对话
        system_prompt = f"""你是一位友好的英语老师，正在和一位中国初中生进行英语对话练习。

重要要求：
1. 你需要设计一个**连贯的情景对话**，而不是独立的问答
2. 整个对话应该围绕一个具体场景展开（如：去图书馆、周末计划、介绍家人等）
3. 每轮对话要自然衔接，像真实聊天一样
4. 引导学生在对话中自然地使用目标单词
5. 对话复杂度：{complexity}，句子长度：{sentence_limit}
6. 总共 {total_rounds} 轮对话

回复必须使用 JSON 格式。"""

        user_prompt = f"""学生刚学习了以下 {len(limited_words)} 个单词：
{words_text}

请开始一个连贯的情景对话。要求：
1. 先设计一个贴近初中生生活的对话场景（如：讨论周末、介绍爱好、学校生活等）
2. 用中文简短介绍场景和打招呼（2-3句话）
3. 然后用简单英语开始对话的第一句（{sentence_limit}），自然地开启话题
4. 选择2-3个本轮希望学生使用的目标单词

返回 JSON：
{{
    "scenario": "场景描述（中文，如：你们正在讨论周末的计划）",
    "greeting": "中文开场白（介绍场景并鼓励学生）",
    "question": "英文开场对话（自然、口语化）",
    "question_chinese": "对话的中文翻译",
    "target_words": ["单词1", "单词2"]
}}"""

        result = await self._call_qwen(system_prompt, user_prompt)

        # 保存对话状态，包括 LLM 消息历史用于连续对话
        self.conversations[conversation_id] = {
            "words": limited_words,
            "words_text": words_text,
            "complexity": complexity,
            "sentence_limit": sentence_limit,
            "round": 1,
            "total_rounds": total_rounds,
            "scenario": result.get("scenario", ""),
            "history": [],  # 学生回复历史
            "llm_history": [  # LLM 对话历史（用于保持上下文）
                {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}
            ],
            "words_used": set(),
            "all_target_words": result.get("target_words", [])
        }

        result["conversation_id"] = conversation_id
        result["total_rounds"] = total_rounds
        return result

    async def evaluate_response(
        self,
        conversation_id: str,
        user_input: str,
        target_words: List[str]
    ) -> Dict:
        """
        评估学生回复并继续对话

        Args:
            conversation_id: 对话 ID
            user_input: 学生的英语回复（来自 ASR）
            target_words: 当前轮的目标单词

        Returns:
            {
                "words_used": ["使用的单词"],
                "feedback": "中文反馈",
                "correction": "语法纠正（如有）",
                "response": "老师的英文回应（继续对话）",
                "response_chinese": "回应的中文翻译",
                "next_target_words": ["下轮单词"],
                "round": 当前轮数,
                "total_rounds": 总轮数,
                "is_complete": 是否完成
            }
        """
        conv = self.conversations.get(conversation_id)
        if not conv:
            return {"error": "对话不存在"}

        current_round = conv["round"]
        total_rounds = conv["total_rounds"]
        scenario = conv.get("scenario", "")
        complexity = conv.get("complexity", "简单")
        sentence_limit = conv.get("sentence_limit", "10词以内")

        # 检查哪些目标单词被使用
        words_used = [w for w in target_words if w.lower() in user_input.lower()]
        conv["words_used"].update(words_used)

        # 记录学生回复历史
        conv["history"].append({
            "round": current_round,
            "input": user_input,
            "target_words": target_words,
            "words_used": words_used
        })

        # 添加学生回复到 LLM 历史
        conv["llm_history"].append({
            "role": "user",
            "content": f"学生回复：{user_input}"
        })

        is_complete = current_round >= total_rounds

        # 获取剩余未使用的单词
        used_lower = {w.lower() for w in conv["words_used"]}
        remaining_words = [w["word"] for w in conv["words"]
                          if w["word"].lower() not in used_lower]

        # 系统提示强调连贯对话和发音混淆检测
        system_prompt = f"""你是一位友好的英语老师，正在和一位中国初中生进行连贯的情景对话练习。

对话场景：{scenario}
对话复杂度：{complexity}
句子长度限制：{sentence_limit}

重要要求：
1. 你的回复要**自然衔接学生的话**，像真实聊天一样继续对话
2. **绝对不能重复问同一个问题！** 即使学生没有正确使用目标单词，也要继续推进对话，问一个新的相关问题
3. 反馈要简短、鼓励性的
4. 如果学生语法有错误，在 correction 中指出，但回应中要继续新话题，不要纠缠同一个问题
5. **发音混淆检测**：学生的回复来自语音识别，可能存在发音相近的词被错误识别的情况（如 sun/son, their/there, to/too/two 等）。如果你发现句子中某个词在语境下不合理，但换成发音相近的另一个词就合理了，请在 pronunciation_issue 中指出
6. 回复必须使用 JSON 格式"""

        if is_complete:
            user_prompt = f"""学生刚才说："{user_input}"
本轮目标单词：{target_words}
当前第 {current_round}/{total_rounds} 轮（最后一轮）

请：
1. 对学生的回复做出自然的回应，结束这段对话
2. 给出简短的中文反馈
3. 检查是否有发音混淆（如学生说的某个词在语境下不合理，可能是识别错误）

返回 JSON：
{{
    "words_used": ["学生使用的目标单词"],
    "feedback": "简短中文反馈（如：很好！/说得不错！）",
    "correction": "语法纠正（如有问题才填，否则为 null）",
    "response": "英文回应（自然地结束对话，如：That sounds great! Have a nice weekend!）",
    "response_chinese": "回应的中文翻译",
    "pronunciation_issue": {{
        "detected": false,
        "original_word": "识别出的词",
        "suggested_word": "可能想说的词",
        "reason": "为什么认为是发音混淆"
    }},
    "is_complete": true
}}
注意：pronunciation_issue.detected 为 false 时，其他字段可省略"""
        else:
            user_prompt = f"""学生刚才说："{user_input}"
本轮目标单词：{target_words}
当前第 {current_round}/{total_rounds} 轮
还可以引导使用的单词：{remaining_words[:6]}

请：
1. 对学生的回复做出自然的回应（不是评价，而是像朋友聊天一样接话）
2. **必须问一个新问题**，绝对不能重复之前问过的问题！即使学生没有正确使用目标单词也要继续推进对话
3. 选择2-3个下轮目标单词
4. 检查是否有发音混淆（如学生说的某个词在语境下不合理，可能是识别错误）

返回 JSON：
{{
    "words_used": ["学生使用的目标单词"],
    "feedback": "简短中文反馈（如：很好！/说得不错！）",
    "correction": "语法纠正（如有问题才填，否则为 null）",
    "response": "英文回应（自然接话+新问题，不能重复之前的问题！）",
    "response_chinese": "回应的中文翻译",
    "next_target_words": ["下轮目标单词"],
    "pronunciation_issue": {{
        "detected": false,
        "original_word": "识别出的词",
        "suggested_word": "可能想说的词",
        "reason": "为什么认为是发音混淆"
    }},
    "is_complete": false
}}
注意：pronunciation_issue.detected 为 false 时，其他字段可省略"""

        # 调用 LLM，传递对话历史以保持上下文
        result = await self._call_qwen(system_prompt, user_prompt, conv["llm_history"])

        # 兼容处理：如果 LLM 返回旧格式 next_question，映射为新格式 response
        if "next_question" in result and "response" not in result:
            result["response"] = result["next_question"]
            result["response_chinese"] = result.get("next_question_chinese", "")

        # 保存 LLM 回复到历史
        conv["llm_history"].append({
            "role": "assistant",
            "content": json.dumps(result, ensure_ascii=False)
        })

        result["round"] = current_round + 1
        result["total_rounds"] = total_rounds
        result["is_complete"] = is_complete

        if not is_complete:
            conv["round"] += 1
            conv["all_target_words"] = result.get("next_target_words", [])

        return result

    async def get_summary(self, conversation_id: str) -> Dict:
        """
        获取对话总结

        Args:
            conversation_id: 对话 ID

        Returns:
            {
                "total_rounds": 总轮数,
                "words_practiced": ["练习的单词"],
                "words_used_correctly": ["正确使用的单词"],
                "words_missed": ["未使用的单词"],
                "overall_feedback": "总体反馈",
                "score": 得分(0-100)
            }
        """
        conv = self.conversations.get(conversation_id)
        if not conv:
            return {"error": "对话不存在"}

        all_words = [w["word"] for w in conv["words"]]
        words_used = list(conv["words_used"])
        words_used_lower = {w.lower() for w in words_used}
        words_missed = [w for w in all_words if w.lower() not in words_used_lower]

        # 计算得分：使用单词数 / 总单词数（最多计算前10个）
        max_words = min(10, len(all_words))
        used_count = min(len(words_used), max_words)
        score = int(used_count / max_words * 100) if max_words > 0 else 0

        # 根据得分生成反馈
        if score >= 80:
            feedback = f"太棒了！你在对话中使用了 {len(words_used)} 个目标单词，表现非常出色！"
        elif score >= 60:
            feedback = f"做得不错！你使用了 {len(words_used)} 个目标单词，继续加油！"
        elif score >= 40:
            feedback = f"有进步！你使用了 {len(words_used)} 个目标单词，下次试着多用一些新学的词。"
        else:
            feedback = f"你使用了 {len(words_used)} 个目标单词，多多练习，一定会越来越好！"

        return {
            "total_rounds": conv["total_rounds"],
            "words_practiced": all_words[:10],
            "words_used_correctly": words_used,
            "words_missed": words_missed[:5],
            "overall_feedback": feedback,
            "score": score
        }

    def cleanup_conversation(self, conversation_id: str):
        """清理对话数据"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]


# 全局实例
_manager: ConversationManager = None


def get_conversation_manager() -> ConversationManager:
    """获取全局对话管理器实例"""
    global _manager
    if _manager is None:
        _manager = ConversationManager()
    return _manager


# 命令行测试
if __name__ == "__main__":
    import asyncio

    # 加载环境变量
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    async def test():
        manager = ConversationManager()

        print("对话管理器测试")
        print("=" * 50)
        print(f"服务可用: {manager.is_available()}")

        if not manager.is_available():
            print("阿里云百炼 API 未配置，跳过测试")
            return

        # 模拟已学单词
        words = [
            {"word": "father", "translation": "n. 父亲"},
            {"word": "mother", "translation": "n. 母亲"},
            {"word": "family", "translation": "n. 家庭"},
            {"word": "happy", "translation": "adj. 快乐的"},
            {"word": "love", "translation": "v. 爱"},
        ]

        print("\n开始对话...")
        result = await manager.start_conversation(words)
        print(f"开场白: {result.get('greeting')}")
        print(f"问题: {result.get('question')}")
        print(f"中文: {result.get('question_chinese')}")
        print(f"目标单词: {result.get('target_words')}")

        conversation_id = result["conversation_id"]

        # 模拟学生回复
        print("\n模拟学生回复...")
        user_input = "My father and mother are very happy."
        feedback = await manager.evaluate_response(
            conversation_id,
            user_input,
            result.get("target_words", [])
        )
        print(f"反馈: {feedback.get('feedback')}")
        print(f"中文: {feedback.get('feedback_chinese')}")
        print(f"下一个问题: {feedback.get('next_question')}")

        # 获取总结
        print("\n获取总结...")
        summary = await manager.get_summary(conversation_id)
        print(f"总体反馈: {summary.get('overall_feedback')}")
        print(f"得分: {summary.get('score')}")

    asyncio.run(test())
