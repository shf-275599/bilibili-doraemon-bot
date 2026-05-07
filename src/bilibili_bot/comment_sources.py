#!/usr/bin/env python3
"""评论来源采集。"""

from __future__ import annotations

import requests
import time

from bot_config import build_cookie_header, parse_cookies_file, random_user_agent
from comment_normalizer import CommentEvent, normalize_msgfeed_item, normalize_reply_item


class MsgFeedReplySource:
    endpoint = "https://api.bilibili.com/x/msgfeed/reply"

    def __init__(self, config: dict):
        self.config = config
        self.cookies_file = config["cookie"]["cookies_file"]
        self.timeout = config["bot"].get("request_timeout_seconds", 25)

    def fetch(self) -> list[CommentEvent]:
        headers = self._message_headers()
        params = {
            "ps": self.config["sources"]["msgfeed"].get("page_size", 10),
            "pn": 1,
        }
        payload = self._get_json(self.endpoint, headers, params)
        if payload.get("code") != 0:
            if payload.get("code") == -101:
                raise RuntimeError("msgfeed 接口返回未登录，当前 cookies 已失效或缺少消息流可用登录态")
            raise RuntimeError(f"msgfeed 接口失败: code={payload.get('code')} message={payload.get('message')}")
        items = payload.get("data", {}).get("items", [])
        events: list[CommentEvent] = []
        for item in items:
            event = normalize_msgfeed_item(item)
            if event:
                events.append(event)
        return events

    def _message_headers(self) -> dict[str, str]:
        cookies = parse_cookies_file(self.cookies_file)
        return {
            "User-Agent": random_user_agent(),
            "Referer": "https://message.bilibili.com/",
            "Origin": "https://message.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": build_cookie_header(cookies),
        }

    def _space_headers(self, uid: str, dynamic: bool = False) -> dict[str, str]:
        cookies = parse_cookies_file(self.cookies_file)
        referer = f"https://space.bilibili.com/{uid}/dynamic" if dynamic else f"https://space.bilibili.com/{uid}"
        return {
            "User-Agent": random_user_agent(),
            "Referer": referer,
            "Origin": "https://space.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": build_cookie_header(cookies),
        }

    def _get_json(self, url: str, headers: dict[str, str], params: dict | None = None) -> dict:
        response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()


class MentionMsgFeedSource(MsgFeedReplySource):
    endpoint = "https://api.bilibili.com/x/msgfeed/at"

    def fetch(self) -> list[CommentEvent]:
        headers = self._message_headers()
        params = {
            "build": 0,
            "mobi_app": "web",
        }
        payload = self._get_json(self.endpoint, headers, params)
        if payload.get("code") != 0:
            if payload.get("code") == -101:
                raise RuntimeError("@我消息流返回未登录，当前 cookies 对消息中心不可用")
            raise RuntimeError(f"@我消息流失败: code={payload.get('code')} message={payload.get('message')}")
        items = payload.get("data", {}).get("items", [])
        events: list[CommentEvent] = []
        for item in items:
            event = normalize_msgfeed_item(item)
            if event:
                event.source_type = "mention"
                event.at_me = True
                events.append(event)
        return events


class OwnVideoCommentSource(MsgFeedReplySource):
    video_list_endpoint = "https://api.bilibili.com/x/space/arc/search"
    comment_endpoint = "https://api.bilibili.com/x/v2/reply"

    def fetch(self) -> list[CommentEvent]:
        cookies = parse_cookies_file(self.cookies_file)
        uid = str(cookies.get("DedeUserID", ""))
        if not uid:
            raise RuntimeError("缺少 DedeUserID，无法获取自己视频列表")
        headers = self._space_headers(uid)
        source_cfg = self.config["sources"]["own_video"]
        retries = int(source_cfg.get("max_retries", 2))
        payload = None
        for attempt in range(retries + 1):
            payload = self._get_json(self.video_list_endpoint, headers, {
                "mid": uid,
                "pn": 1,
                "ps": source_cfg.get("video_page_size", 5),
                "order": "pubdate",
            })
            if payload.get("code") == 0:
                break
            if payload.get("code") == -799 and attempt < retries:
                time.sleep(source_cfg.get("retry_sleep_seconds", 6))
                continue
            break

        if payload is None or payload.get("code") != 0:
            if payload and payload.get("code") == -799:
                return []
            raise RuntimeError(f"自己视频列表获取失败: code={payload.get('code') if payload else 'unknown'}")

        videos = payload.get("data", {}).get("list", {}).get("vlist", []) or []
        events: list[CommentEvent] = []
        for video in videos:
            aid = video.get("aid")
            if not aid:
                continue
            comments = self._get_json(self.comment_endpoint, headers, {
                "type": 1,
                "oid": aid,
                "pn": 1,
                "ps": source_cfg.get("comment_page_size", 10),
                "sort": 0,
            })
            if comments.get("code") != 0:
                continue
            for reply in comments.get("data", {}).get("replies") or []:
                event = normalize_reply_item(reply, source_type="own_video", business_type="video", oid=str(aid))
                if event:
                    events.append(event)
        return events


class OwnDynamicCommentSource(MsgFeedReplySource):
    dynamic_list_endpoint = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space"
    comment_endpoint = "https://api.bilibili.com/x/v2/reply"

    def fetch(self) -> list[CommentEvent]:
        cookies = parse_cookies_file(self.cookies_file)
        uid = str(cookies.get("DedeUserID", ""))
        if not uid:
            raise RuntimeError("缺少 DedeUserID，无法获取自己动态列表")
        headers = self._space_headers(uid, dynamic=True)
        source_cfg = self.config["sources"]["own_dynamic"]
        payload = self._get_json(self.dynamic_list_endpoint, headers, {"host_mid": uid})
        if payload.get("code") != 0:
            raise RuntimeError(f"自己动态列表获取失败: code={payload.get('code')} message={payload.get('message')}")
        items = (payload.get("data", {}) or {}).get("items", []) or []
        events: list[CommentEvent] = []
        for dynamic in items[: int(source_cfg.get("dynamic_page_size", 5))]:
            basic = dynamic.get("basic", {})
            comment_type = basic.get("comment_type")
            comment_id = basic.get("comment_id_str") or basic.get("rid_str")
            if not comment_type or not comment_id:
                continue
            comments = self._get_json(self.comment_endpoint, headers, {
                "type": comment_type,
                "oid": comment_id,
                "pn": 1,
                "ps": source_cfg.get("comment_page_size", 10),
                "sort": 0,
            })
            if comments.get("code") != 0:
                continue
            business_type = "dynamic_draw" if int(comment_type) == 11 else "dynamic"
            for reply in comments.get("data", {}).get("replies") or []:
                event = normalize_reply_item(reply, source_type="own_dynamic", business_type=business_type, oid=str(comment_id))
                if event:
                    events.append(event)
        return events
