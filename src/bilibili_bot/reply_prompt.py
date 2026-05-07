#!/usr/bin/env python3
"""回复 Prompt 构建。"""

from __future__ import annotations

from comment_normalizer import CommentEvent


def build_messages(event: CommentEvent, config: dict) -> list[dict[str, str]]:
    reply_cfg = config["reply"]
    ai_cfg = config["ai"]
    business_label = {
        "video": "视频评论",
        "dynamic": "动态评论",
        "dynamic_draw": "图文动态评论",
    }.get(event.business_type, event.business_type)
    prompt = (
        f"来源：{business_label}\n"
        f"是否@我：{'是' if event.at_me else '否'}\n"
        f"评论作者：{event.author_name}\n"
        f"评论内容：{event.content_text}\n\n"
        f"请直接生成一条适合在B站公开回复的中文回复。"
        f"要求：自然、友好、简洁，不超过 {ai_cfg.get('max_reply_chars', 100)} 个汉字，"
        f"不要解释自己，不要输出多版本，不要加引号。"
    )
    return [
        {"role": "system", "content": reply_cfg["system_prompt"]},
        {"role": "user", "content": prompt},
    ]
