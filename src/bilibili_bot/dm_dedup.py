#!/usr/bin/env python3
"""Bilibili 私信去重服务（支持失败重试）。"""

from __future__ import annotations

import time

from dm_source import DMEvent
from state_store import JsonlStateStore


MAX_RETRIES = 3
RETRY_COOLDOWN_SECONDS = 300


class DMDedupService:
    def __init__(self, store: JsonlStateStore):
        self.store = store

    def already_handled(self, event: DMEvent, include_dry_run: bool = False) -> bool:
        state = self.store.load_state()
        handled = state.get("handled_dm", {})
        key = event.event_key()

        if key not in handled:
            return False

        record = handled[key]
        status = record.get("status")

        if status in {"replied", "seen", "skipped"}:
            return True

        if include_dry_run and status == "dry_run":
            return True

        if status == "failed":
            retries = record.get("retries", 0)
            if retries >= MAX_RETRIES:
                return True
            last_retry = record.get("last_retry_at", 0)
            if time.time() - last_retry < RETRY_COOLDOWN_SECONDS:
                return True
            return False

        return False

    def mark_seen(self, event: DMEvent, reason: str) -> None:
        state = self.store.load_state()
        if "handled_dm" not in state:
            state["handled_dm"] = {}

        state["handled_dm"][event.event_key()] = {
            "status": "skipped",
            "reason": reason,
            "talker_id": event.talker_id,
            "talker_name": event.talker_name,
            "content": event.content,
            "msg_key": event.msg_key,
        }
        self.store.save_state(state)

    def mark_replied(self, event: DMEvent, reply_text: str, provider: str) -> None:
        state = self.store.load_state()
        if "handled_dm" not in state:
            state["handled_dm"] = {}

        state["handled_dm"][event.event_key()] = {
            "status": "replied",
            "reply_text": reply_text,
            "provider": provider,
            "talker_id": event.talker_id,
            "talker_name": event.talker_name,
            "content": event.content,
            "msg_key": event.msg_key,
        }
        self.store.save_state(state)

    def mark_dry_run(self, event: DMEvent, reply_text: str, provider: str) -> None:
        state = self.store.load_state()
        if "handled_dm" not in state:
            state["handled_dm"] = {}

        state["handled_dm"][event.event_key()] = {
            "status": "dry_run",
            "reply_text": reply_text,
            "provider": provider,
            "talker_id": event.talker_id,
            "talker_name": event.talker_name,
            "content": event.content,
            "msg_key": event.msg_key,
        }
        self.store.save_state(state)

    def mark_failed(self, event: DMEvent, reason: str, provider: str = "") -> None:
        state = self.store.load_state()
        if "handled_dm" not in state:
            state["handled_dm"] = {}

        key = event.event_key()
        existing = state["handled_dm"].get(key, {})
        retries = existing.get("retries", 0) + 1

        state["handled_dm"][key] = {
            "status": "failed",
            "reason": reason,
            "provider": provider,
            "talker_id": event.talker_id,
            "talker_name": event.talker_name,
            "content": event.content,
            "msg_key": event.msg_key,
            "retries": retries,
            "last_retry_at": time.time(),
        }
        self.store.save_state(state)
