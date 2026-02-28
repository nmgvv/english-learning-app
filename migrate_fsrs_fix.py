#!/usr/bin/env python3
"""
FSRS 算法修复迁移脚本

修复内容：
1. 使用 last_review（而非 due）计算 elapsed，重新回放所有历史记录
2. 最大间隔从 365 天改为 60 天
3. 应用难度系数（基于历史错误率）

用法：
  cd /var/www/english-app
  /var/www/english-app/english-env/bin/python3 migrate_fsrs_fix.py
"""

import math
from datetime import datetime, timedelta
from collections import defaultdict

# ==================== FSRS-4.5 核心算法（修正版）====================

FSRS_W = [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01,
          1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61]

def init_difficulty(grade):
    return max(1, min(10, FSRS_W[4] - (grade - 3) * FSRS_W[5]))

def init_stability(grade):
    return {1: 1.0, 2: 3.0, 3: 7.0, 4: 14.0}.get(grade, 1.0)

def next_difficulty(d, grade):
    new_d = d - FSRS_W[6] * (grade - 3)
    return max(1, min(10, FSRS_W[7] * init_difficulty(3) + (1 - FSRS_W[7]) * new_d))

def next_recall_stability(d, s, r, grade):
    hard_penalty = FSRS_W[15] if grade == 2 else 1
    easy_bonus = FSRS_W[16] if grade == 4 else 1
    new_s = s * (1 + math.exp(FSRS_W[8]) * (11 - d) *
                 pow(s, -FSRS_W[9]) *
                 (math.exp(FSRS_W[10] * (1 - r)) - 1) *
                 hard_penalty * easy_bonus)
    return max(1.0, new_s)

def next_forget_stability(d, s, r):
    new_s = FSRS_W[11] * pow(d, -FSRS_W[12]) * (pow(s + 1, FSRS_W[13]) - 1) * math.exp(FSRS_W[14] * (1 - r))
    return max(1.0, new_s)

def retrievability(s, t):
    if s <= 0:
        return 0
    return pow(0.9, t / s)

def next_interval(s, desired_r=0.9):
    if s <= 0:
        return 1
    FACTOR = 19.0 / 81.0
    DECAY = -0.5
    interval = (s / FACTOR) * (pow(desired_r, 1.0 / DECAY) - 1)
    return max(1, min(60, round(interval)))  # 最大 60 天


# ==================== 迁移逻辑 ====================

def reconstruct_user(db, user_id, username):
    """根据历史记录重新计算用户的 FSRS 状态"""
    from database import Progress, History

    # 获取用户所有进度和历史
    all_progress = db.query(Progress).filter(Progress.user_id == user_id).all()
    all_history = db.query(History).filter(History.user_id == user_id).order_by(History.time).all()

    # 按 (book_id, word) 分组历史记录
    history_map = defaultdict(list)
    for h in all_history:
        history_map[(h.book_id, h.word)].append(h)

    updated = 0
    skipped = 0

    for prog in all_progress:
        key = (prog.book_id, prog.word)
        word_history = history_map.get(key, [])

        if not word_history:
            # 无历史记录（仅摸底），只修正 due（应用 60 天上限）
            if prog.stability and prog.due and prog.last_review:
                new_interval = next_interval(prog.stability)
                new_due = prog.last_review + timedelta(days=new_interval)
                if new_due != prog.due:
                    prog.due = new_due
                    updated += 1
            skipped += 1
            continue

        # 从第一条历史开始回放
        first = word_history[0]
        grade = first.grade if first.grade else 1
        difficulty = init_difficulty(grade)
        stability = init_stability(grade)
        state = 1 if grade < 3 else 2
        reps = 1
        lapses = 1 if grade == 1 else 0
        last_review = first.time

        # 回放后续所有复习
        for h in word_history[1:]:
            grade = h.grade if h.grade else 1
            reps += 1

            # 关键修复：使用 last_review 计算 elapsed
            elapsed = (h.time - last_review).total_seconds() / 86400  # 精确到小数天
            r = retrievability(stability, max(0, elapsed))

            difficulty = next_difficulty(difficulty, grade)

            if grade == 1:  # 遗忘
                stability = next_forget_stability(difficulty, stability, r)
                lapses += 1
                state = 1
            else:  # 记住
                stability = next_recall_stability(difficulty, stability, r, grade)
                state = 2

            last_review = h.time

        # 计算难度系数
        recent = word_history[-10:]
        if len(recent) >= 3:
            error_count = sum(1 for h in recent if h.result != "correct")
            error_rate = error_count / len(recent)
            coeff = max(0.5, 1.0 - error_rate * 0.5)
        else:
            coeff = 1.0

        # 计算新的 due
        base_interval = next_interval(stability)
        adjusted_interval = max(1, round(base_interval * coeff))
        new_due = last_review + timedelta(days=adjusted_interval)

        # 更新 progress 记录
        old_stability = prog.stability
        prog.difficulty = difficulty
        prog.stability = stability
        prog.state = state
        prog.reps = reps
        prog.lapses = lapses
        prog.last_review = last_review
        prog.due = new_due
        updated += 1

    db.commit()
    print(f"  {username}: 更新 {updated} 条, 跳过 {skipped} 条（无历史）")
    return updated


def show_stats(db, user_id, username):
    """显示用户重构后的统计"""
    from database import Progress
    from collections import Counter

    progress = db.query(Progress).filter(Progress.user_id == user_id).all()
    now = datetime.utcnow()

    stab_buckets = Counter()
    due_today = 0
    for p in progress:
        s = p.stability
        if s <= 1.5: stab_buckets['0-1.5天'] += 1
        elif s <= 3.5: stab_buckets['1.5-3.5天'] += 1
        elif s <= 7.5: stab_buckets['3.5-7.5天'] += 1
        elif s <= 15: stab_buckets['7.5-15天'] += 1
        elif s <= 30: stab_buckets['15-30天'] += 1
        elif s <= 60: stab_buckets['30-60天'] += 1
        else: stab_buckets['60天+'] += 1

        if p.due and p.due <= now.replace(hour=23, minute=59, second=59):
            due_today += 1

    print(f"  {username} 重构后:")
    print(f"    Stability 分布: {dict(stab_buckets)}")
    print(f"    今日待复习: {due_today} 词")


if __name__ == "__main__":
    from database import SessionLocal

    db = SessionLocal()

    print("=" * 60)
    print("FSRS 算法修复迁移")
    print("=" * 60)

    # 迁移蝴蝶 (user_id=7) 和刘禹莹 (user_id=2)
    users = [(7, "蝴蝶"), (2, "刘禹莹")]

    print("\n--- 开始重构 ---")
    for user_id, username in users:
        reconstruct_user(db, user_id, username)

    print("\n--- 重构结果 ---")
    for user_id, username in users:
        show_stats(db, user_id, username)

    db.close()
    print("\n迁移完成!")
