"""回复质量反馈追踪：定期检查机器人评论的点赞/回复数，数据存 data/feedback.jsonl。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

COMMENT_TYPE_MAP = {"video": 1, "dynamic": 17, "dynamic_draw": 11}
MAX_CHECKS_PER_RUN = 10
LOOKBACK_DAYS = 7
LOOKBACK_SECONDS = LOOKBACK_DAYS * 86400
REPLY_DETAIL_URL = "https://api.bilibili.com/x/v2/reply/reply"


def _load_reply_history(reply_history_path: Path, since_ts: float) -> list[dict[str, Any]]:
    if not reply_history_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with reply_history_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("replied_at", 0) >= since_ts:
                records.append(record)
    return records


def _load_checked_rpids(feedback_path: Path) -> set[str]:
    checked: set[str] = set()
    if not feedback_path.exists():
        return checked
    with feedback_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                rpid = record.get("rpid")
                if rpid:
                    checked.add(str(rpid))
            except json.JSONDecodeError:
                continue
    return checked


def check_reply_quality(client: Any, store: Any) -> list[dict[str, Any]]:
    """检查最近 7 天回复的点赞/回复数，每次最多 MAX_CHECKS_PER_RUN 条。"""
    now = time.time()
    since_ts = now - LOOKBACK_SECONDS
    feedback_path = store.root / "feedback.jsonl"

    history = _load_reply_history(store.reply_history_path, since_ts)
    if not history:
        logger.info("feedback_no_history", lookback_days=LOOKBACK_DAYS)
        return []

    seen_keys: dict[str, dict[str, Any]] = {}
    for record in history:
        key = record.get("event_key", "")
        if key:
            seen_keys[key] = record
    unique_records = list(seen_keys.values())

    checked_rpids = _load_checked_rpids(feedback_path)

    unchecked = [
        r for r in unique_records
        if r.get("event", {}).get("rpid") and str(r["event"]["rpid"]) not in checked_rpids
    ]

    if not unchecked:
        logger.info("feedback_all_checked", total=len(unique_records))
        return []

    to_check = unchecked[:MAX_CHECKS_PER_RUN]
    logger.info("feedback_checking", count=len(to_check), remaining=len(unchecked) - len(to_check))

    results: list[dict[str, Any]] = []
    for record in to_check:
        event = record.get("event", {})
        oid = event.get("oid", "")
        rpid = event.get("rpid", "")
        business_type = event.get("business_type", "video")
        reply_text = record.get("reply_text", "")

        if not oid or not rpid:
            continue

        api_type = COMMENT_TYPE_MAP.get(business_type, 1)

        try:
            resp = client.get(
                REPLY_DETAIL_URL,
                params={"type": api_type, "oid": oid, "root": rpid, "pn": 1, "ps": 1},
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 0:
                logger.warning("feedback_api_error", rpid=rpid, code=data.get("code"), msg=data.get("message"))
                likes, child_replies = 0, 0
            else:
                reply_data = data.get("data", {})
                root_reply = reply_data.get("root_reply", {})
                if root_reply:
                    likes = root_reply.get("like", 0)
                    child_replies = reply_data.get("page", {}).get("count", 0)
                else:
                    likes, child_replies = 0, 0

        except Exception as e:
            logger.warning("feedback_request_failed", rpid=rpid, error=str(e))
            likes, child_replies = 0, 0

        results.append({
            "rpid": str(rpid),
            "oid": str(oid),
            "likes": likes,
            "replies": child_replies,
            "checked_at": int(now),
            "reply_text_preview": reply_text[:50],
        })

    return results


def save_feedback(store: Any, results: list[dict[str, Any]]) -> None:
    """追加检查结果到 data/feedback.jsonl。"""
    if not results:
        return

    feedback_path = store.root / "feedback.jsonl"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)

    with feedback_path.open("a", encoding="utf-8") as f:
        for record in results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info("feedback_saved", count=len(results), path=str(feedback_path))


def get_quality_summary(store: Any) -> str:
    """读取 feedback.jsonl，返回近 7 天回复质量摘要。"""
    feedback_path = store.root / "feedback.jsonl"
    if not feedback_path.exists():
        return "暂无回复质量数据"

    now = time.time()
    since_ts = now - LOOKBACK_SECONDS

    records: list[dict[str, Any]] = []
    with feedback_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("checked_at", 0) >= since_ts:
                    records.append(record)
            except json.JSONDecodeError:
                continue

    if not records:
        return "暂无回复质量数据"

    total_likes = sum(r.get("likes", 0) for r in records)
    avg_likes = total_likes / len(records)

    best = max(records, key=lambda r: r.get("likes", 0))
    best_preview = best.get("reply_text_preview", "")
    best_likes = best.get("likes", 0)

    with_engagement = sum(1 for r in records if r.get("likes", 0) > 0 or r.get("replies", 0) > 0)
    engagement_rate = with_engagement / len(records) * 100

    return (
        f"近{LOOKBACK_DAYS}天回复质量：已检查 {len(records)} 条，"
        f"平均点赞 {avg_likes:.1f}，互动率 {engagement_rate:.0f}%，"
        f"最高点赞回复「{best_preview}」({best_likes}赞)"
    )
