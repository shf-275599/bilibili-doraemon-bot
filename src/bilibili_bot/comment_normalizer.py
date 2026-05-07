#!/usr/bin/env python3
"""评论事件归一化。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


BUSINESS_TYPE_MAP = {
    1: "video",
    11: "dynamic_draw",
    17: "dynamic",
}


@dataclass
class CommentEvent:
    source_type: str
    business_type: str
    oid: str
    rpid: str
    root_rpid: str
    parent_rpid: str
    author_mid: str
    author_name: str
    content_text: str
    at_me: bool
    created_at: int
    raw_payload: dict[str, Any]

    def event_key(self) -> str:
        return f"{self.business_type}:{self.oid}:{self.rpid}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_msgfeed_item(item: dict[str, Any]) -> CommentEvent | None:
    payload = item.get("item", {})
    user = item.get("user", {})
    source_id = payload.get("source_id")
    subject_id = payload.get("subject_id")
    if not source_id or not subject_id:
        return None

    business_id = payload.get("business_id", 1)
    root_id = payload.get("root_id") or source_id
    comment_text = payload.get("source_content") or payload.get("title") or ""
    at_me = "@" in comment_text
    return CommentEvent(
        source_type="msgfeed",
        business_type=BUSINESS_TYPE_MAP.get(int(business_id), str(business_id)),
        oid=str(subject_id),
        rpid=str(source_id),
        root_rpid=str(root_id),
        parent_rpid=str(source_id),
        author_mid=str(user.get("mid", "")),
        author_name=str(user.get("nickname") or user.get("uname") or "未知用户"),
        content_text=str(comment_text).strip(),
        at_me=at_me,
        created_at=int(item.get("ctime") or payload.get("ctime") or 0),
        raw_payload=item,
    )


def normalize_reply_item(
    reply: dict[str, Any],
    *,
    source_type: str,
    business_type: str,
    oid: str,
    at_me: bool = False,
) -> CommentEvent | None:
    member = reply.get("member", {})
    content = reply.get("content", {})
    rpid = reply.get("rpid") or reply.get("rpid_str")
    if not rpid:
        return None
    root_raw = reply.get("root")
    if root_raw in (None, 0, "0", ""):
        root_raw = reply.get("root_str")
    root = rpid if root_raw in (None, 0, "0", "") else root_raw

    parent_raw = reply.get("parent")
    if parent_raw in (None, 0, "0", ""):
        parent_raw = reply.get("parent_str")
    parent = rpid if parent_raw in (None, 0, "0", "") else parent_raw

    message = content.get("message") or ""
    if not message:
        message = reply.get("reply_control", {}).get("time_desc", "")
    return CommentEvent(
        source_type=source_type,
        business_type=business_type,
        oid=str(oid),
        rpid=str(rpid),
        root_rpid=str(root),
        parent_rpid=str(parent),
        author_mid=str(member.get("mid", "")),
        author_name=str(member.get("uname") or "未知用户"),
        content_text=str(message).strip(),
        at_me=at_me or ("@" in str(message)),
        created_at=int(reply.get("ctime") or 0),
        raw_payload=reply,
    )
