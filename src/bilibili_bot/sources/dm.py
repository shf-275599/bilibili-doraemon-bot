from __future__ import annotations

import structlog

from bilibili_bot.events import Event, DMEvent
from bilibili_bot.sources.base import BaseSource

logger = structlog.get_logger()


class DMSource(BaseSource):
    def __init__(self, config):
        self.config = config
        self.max_reply_per_round = config.sources.dm.max_reply_per_round
        self.skip_keywords = config.sources.dm.skip_keywords
        self.whitelist_mids = config.sources.dm.whitelist_mids

    def fetch(self) -> list[Event]:
        return self.fetch_new_messages()

    def fetch_new_messages(self) -> list[Event]:
        from bilibili_bot.client import BilibiliSession
        client = BilibiliSession(self.config.cookie.cookies_file, self.config.bot.request_timeout_seconds)

        my_uid = client.get_cookies().get("DedeUserID", "")
        if not my_uid:
            logger.error("no_deduid")
            return []

        sessions = self._fetch_sessions(client)
        events = []

        for session in sessions:
            if len(events) >= self.max_reply_per_round:
                break

            talker_id = session.get("talker_id", 0)
            unread_count = session.get("unread_count", 0)

            if unread_count == 0 or str(talker_id) == my_uid:
                continue

            try:
                messages = self._fetch_messages(client, talker_id)
                for msg in messages:
                    event = self._normalize_message(msg, session)
                    if event:
                        if self._should_skip(event):
                            continue
                        events.append(event)
                        break
            except Exception as e:
                logger.warning("dm_fetch_failed", talker_id=talker_id, error=str(e))

        return events

    def _fetch_sessions(self, client) -> list[dict]:
        resp = client.get(
            "https://api.vc.bilibili.com/session_svr/v1/session_svr/get_sessions",
            params={"session_type": 1, "size": 20, "build": 0, "mobi_app": "web"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            return []

        return data.get("data", {}).get("session_list", [])

    def _fetch_messages(self, client, talker_id: int) -> list[dict]:
        resp = client.get(
            "https://api.vc.bilibili.com/svr_sync/v1/svr_sync/fetch_session_msgs",
            params={"talker_id": talker_id, "size": 10},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            return []

        return data.get("data", {}).get("messages", []) or []

    def _normalize_message(self, msg: dict, session: dict) -> DMEvent | None:
        msg_type = msg.get("msg_type", 0)
        if msg_type != 1:
            return None

        content_str = msg.get("content", "{}")
        try:
            import json
            content_data = json.loads(content_str)
            text = content_data.get("content", "")
        except:
            text = content_str

        return DMEvent(
            source_type="dm",
            event_key=f"dm:{msg.get('sender_uid')}:{msg.get('msg_key')}",
            created_at=msg.get("timestamp", 0),
            raw_payload=msg,
            talker_id=msg.get("sender_uid", 0),
            talker_name=session.get("account_info", {}).get("name", ""),
            dm_content=text,
            msg_type=msg_type,
            msg_key=msg.get("msg_key", 0),
        )

    def _should_skip(self, event: DMEvent) -> bool:
        for keyword in self.skip_keywords:
            if keyword in event.content:
                return True
        return False
