#!/usr/bin/env python3
"""评论去重服务。"""

from __future__ import annotations

from comment_normalizer import CommentEvent
from state_store import JsonlStateStore, utc_timestamp


class DedupService:
    def __init__(self, store: JsonlStateStore):
        self.store = store

    def already_handled(self, event: CommentEvent, include_dry_run: bool = False) -> bool:
        record = self.store.get_record(event.event_key())
        if not record:
            return False
        statuses = {"replied", "seen"}
        if include_dry_run:
            statuses.add("dry_run")
        return record.get("reply_status") in statuses

    def mark_seen(self, event: CommentEvent, reason: str) -> None:
        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": utc_timestamp(),
            "reply_status": "seen",
            "reason": reason,
            "event": event.to_dict(),
        })

    def mark_failed(self, event: CommentEvent, reason: str, provider: str | None = None) -> None:
        self.store.append_processed({
            "event_key": event.event_key(),
            "seen_at": utc_timestamp(),
            "reply_status": "failed",
            "reason": reason,
            "provider_used": provider,
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
