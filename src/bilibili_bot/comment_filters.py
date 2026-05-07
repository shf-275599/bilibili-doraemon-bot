#!/usr/bin/env python3
"""基础过滤规则。"""

from __future__ import annotations

import re

from comment_normalizer import CommentEvent


NON_WORD_RE = re.compile(r"[\W_]+", re.UNICODE)


def _meaningful_text(text: str) -> str:
    return NON_WORD_RE.sub("", text or "")


def should_skip_event(event: CommentEvent, config: dict, my_uid: str | None) -> tuple[bool, str]:
    filters = config["filters"]
    blacklist = {str(mid) for mid in filters.get("blacklist_mids", [])}

    if filters.get("skip_self", True) and my_uid and event.author_mid == my_uid:
        return True, "跳过自己的评论"

    if event.author_mid in blacklist:
        return True, "命中黑名单用户"

    if filters.get("skip_empty", True) and not event.content_text.strip():
        return True, "空文本评论"

    normalized = _meaningful_text(event.content_text)
    if filters.get("skip_pure_emoji", True) and not normalized:
        return True, "纯表情或纯符号评论"

    if len(normalized) < int(filters.get("min_meaningful_length", 2)):
        return True, "无意义超短评论"

    return False, "允许处理"
