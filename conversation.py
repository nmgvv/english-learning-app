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

    async def _call_qwen(self, system_prompt: str, user_prompt: str) -> dict:
        """调用阿里云百炼 Qwen-Plus API"""
        if not self.is_available():
            raise Exception("阿里云百炼 API 未配置")

        # 清除代理环境变量
        for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
            os.environ.pop(key, None)

        async with httpx.AsyncClient(proxy=None, timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
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
                "total_rounds": 总轮数
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

        system_prompt = f"""你是一位友好的英语老师，正在和一位中国初中生进行英语对话练习。
你需要用给定的单词设计一个{complexity}的对话场景（{total_rounds}轮），引导学生使用这些单词。
回复必须使用 JSON 格式。"""

        user_prompt = f"""学生刚学习了以下 {len(limited_words)} 个单词：
{words_text}

请开始对话。要求：
1. 先用中文打招呼，鼓励学生（1-2句话）
2. 然后用简单英语提出第一个问题（{sentence_limit}）
3. 问题要贴近初中生生活
4. 选择2-3个目标单词供本轮使用

返回 JSON：
{{"greeting": "中文开场白", "question": "英文问题", "question_chinese": "问题中文翻译", "target_words": ["单词1", "单词2"]}}"""

        result = await self._call_qwen(system_prompt, user_prompt)

        # 保存对话状态
        self.conversations[conversation_id] = {
            "words": limited_words,
            "round": 1,
            "total_rounds": total_rounds,
            "history": [],
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
        评估学生回复

        Args:
            conversation_id: 对话 ID
            user_input: 学生的英语回复（来自 ASR）
            target_words: 当前轮的目标单词

        Returns:
            {
                "words_used": ["使用的单词"],
                "feedback": "英文反馈",
                "feedback_chinese": "中文反馈",
                "correction": "语法纠正（如有）",
                "next_question": "下一个问题（如未完成）",
                "next_question_chinese": "问题中文",
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

        # 检查哪些目标单词被使用
        words_used = [w for w in target_words if w.lower() in user_input.lower()]
        conv["words_used"].update(words_used)

        # 记录历史
        conv["history"].append({
            "round": current_round,
            "input": user_input,
            "target_words": target_words,
            "words_used": words_used
        })

        is_complete = current_round >= total_rounds

        system_prompt = """你是一位友好的英语老师，正在评估中国初中生的英语口语回复。
请用鼓励的语气给出反馈，指出用得好的地方，温和地纠正错误。
重要：反馈内容使用中文为主，方便学生理解。如果有语法纠正，用中英对照的方式说明。
回复必须使用 JSON 格式。"""

        # 获取剩余未使用的单词
        used_lower = {w.lower() for w in conv["words_used"]}
        remaining_words = [w["word"] for w in conv["words"]
                          if w["word"].lower() not in used_lower]

        if is_complete:
            user_prompt = f"""学生回复："{user_input}"
目标单词：{target_words}
当前第 {current_round}/{total_rounds} 轮
这是最后一轮

请评估回复并总结对话。

返回 JSON：
{{
    "words_used": ["学生使用的目标单词"],
    "feedback": "中文反馈（鼓励性的评价，如：说得很好！你正确使用了xxx单词）",
    "feedback_chinese": "同上，保持一致",
    "correction": "语法纠正（中英对照，如：'建议改成 xxx，因为...'）或 null",
    "is_complete": true
}}"""
        else:
            user_prompt = f"""学生回复："{user_input}"
目标单词：{target_words}
当前第 {current_round}/{total_rounds} 轮
剩余单词：{remaining_words[:6]}

请评估回复并提出下一个问题。

返回 JSON：
{{
    "words_used": ["学生使用的目标单词"],
    "feedback": "中文反馈（鼓励性的评价，如：说得很好！你正确使用了xxx单词）",
    "feedback_chinese": "同上，保持一致",
    "correction": "语法纠正（中英对照，如：'建议改成 xxx，因为...'）或 null",
    "next_question": "下一个英文问题（简单，10词以内）",
    "next_question_chinese": "问题的中文翻译",
    "next_target_words": ["下轮目标单词"],
    "is_complete": false
}}"""

        result = await self._call_qwen(system_prompt, user_prompt)
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
