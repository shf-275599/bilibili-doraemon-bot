from __future__ import annotations

import structlog

from bilibili_bot.events import Event, CommentEvent, BUSINESS_TYPE_MAP
from bilibili_bot.sources.base import BaseSource

logger = structlog.get_logger()


class MsgFeedReplySource(BaseSource):
    def __init__(self, config):
        self.config = config
        self.page_size = config.sources.msgfeed.page_size

    def fetch(self) -> list[Event]:
        from bilibili_bot.client import BilibiliSession
        client = BilibiliSession(self.config.cookie.cookies_file, self.config.bot.request_timeout_seconds)

        resp = client.get(
            "https://api.bilibili.com/x/msgfeed/reply",
            params={"platform": "web", "build": 0, "mobi_app": "web"},
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            logger.error("msgfeed_failed", code=data.get("code"), message=data.get("message"))
            return []

        items = data.get("data", {}).get("items", [])
        events = []

        for item in items[:self.page_size]:
            try:
                event = self._normalize_item(item)
                if event:
                    events.append(event)
            except Exception as e:
                logger.warning("normalize_failed", error=str(e))

        self._enrich_bvid(events, client)
        return events

    def _enrich_bvid(self, events: list[CommentEvent], client) -> None:
        """为 video 类型的 CommentEvent 补充 bvid（aid → bvid 转换）。"""
        for event in events:
            if event.business_type == "video" and event.oid and not event.bvid:
                try:
                    resp = client.get(
                        "https://api.bilibili.com/x/web-interface/view",
                        params={"aid": event.oid},
                    )
                    data = resp.json()
                    if data.get("code") == 0:
                        event.bvid = data.get("data", {}).get("bvid", "")
                except Exception as e:
                    logger.debug("bvid_enrich_failed", oid=event.oid, error=str(e))

    def _normalize_item(self, item: dict) -> CommentEvent | None:
        user = item.get("user", {})
        item_data = item.get("item", {})

        business_id = item_data.get("business_id", 1)
        business_type = BUSINESS_TYPE_MAP.get(business_id, "video")

        return CommentEvent(
            source_type="msgfeed",
            event_key=f"{business_type}:{item_data.get('subject_id')}:{item_data.get('source_id')}",
            created_at=item.get("reply_time", 0),
            raw_payload=item,
            business_type=business_type,
            oid=str(item_data.get("subject_id", "")),
            rpid=str(item_data.get("source_id", "")),
            root_rpid=str(item_data.get("root_id", "")),
            parent_rpid=str(item_data.get("source_id", "")),
            author_mid=str(user.get("mid", "")),
            author_name=user.get("nickname", ""),
            content_text=item_data.get("source_content", ""),
            at_me=True,
            bvid="",
        )
