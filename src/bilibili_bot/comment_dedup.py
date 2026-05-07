#!/usr/bin/env python3
"""评论去重服务（支持失败重试）。"""

from __future__ import annotations

from comment_normalizer import CommentEvent
from state_store import JsonlStateStore, utc_timestamp


MAX_RETRIES = 3
RETRY_COOLDOWN_SECONDS = 300


class DedupService:
    def __init__(self, store: JsonlStateStore):
        self.store = store

    def already_handled(self, event: CommentEvent, include_dry_run: bool = False) -> bool:
        record = self.store.get_record(event.event_key())
        if not record:
            return False

        status = record.get("reply_status")

        if status in {"replied", "seen"}:
            return True

        if include_dry_run and status == "dry_run":
            return True

        if status == "failed":
            retries = record.get("retries", 0)
            if retries >= MAX_RETRIES:
                return True
            last_retry = record.get("last_retry_at", 0)
            if utc_timestamp() - last_retry < RETRY_COOLDOWN_SECONDS:
                return True
            return False

        return False

    def mark_seen(self, event: CommentEvent, reason: str) -> None:
        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": utc_timestamp(),
            "reply_status": "seen",
            "reason": reason,
            "event": event.to_dict(),
        })

    def mark_failed(self, event: CommentEvent, reason: str, provider: str | None = None) -> None:
        record = self.store.get_record(event.event_key())
        retries = record.get("retries", 0) if record else 0

        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": utc_timestamp(),
            "reply_status": "failed",
            "reason": reason,
            "provider_used": provider,
            "retries": retries,
            "last_retry_at": utc_timestamp(),
            "event": event.to_dict(),
        })

    def mark_replied(self, event: CommentEvent, reply_text: str, provider: str) -> None:
        ts = utc_timestamp()
        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": ts,
            "replied_at": ts,
            "reply_status": "replied",
            "provider_used": provider,
            "reply_text_hash": hash(reply_text),
            "event": event.to_dict(),
        })
        self.store.append_history({
            "event_key": event.event_key(),
            "replied_at": ts,
            "provider_used": provider,
            "reply_text": reply_text,
            "event": event.to_dict(),
        })

    def mark_dry_run(self, event: CommentEvent, reply_text: str, provider: str) -> None:
        ts = utc_timestamp()
        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": ts,
            "replied_at": ts,
            "reply_status": "dry_run",
            "provider_used": provider,
            "reply_text_hash": hash(reply_text),
            "event": event.to_dict(),
        })
        self.store.append_history({
            "event_key": event.event_key(),
            "replied_at": ts,
            "provider_used": f"{provider}:dry-run",
            "reply_text": reply_text,
            "event": event.to_dict(),
        })
