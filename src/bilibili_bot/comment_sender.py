#!/usr/bin/env python3
"""评论发送器。"""

from __future__ import annotations

import requests

from bot_config import build_cookie_header, parse_cookies_file, random_user_agent, sign_wbi
from comment_normalizer import CommentEvent


def _fetch_wbi_keys(headers: dict[str, str], timeout: int) -> tuple[str, str]:
    response = requests.get("https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"获取 WBI 密钥失败: {payload.get('message')}")
    wbi_img = payload["data"]["wbi_img"]
    img_key = wbi_img["img_url"].split("/")[-1].split(".")[0]
    sub_key = wbi_img["sub_url"].split("/")[-1].split(".")[0]
    return img_key, sub_key


def send_reply(event: CommentEvent, reply_text: str, config: dict) -> tuple[bool, str, bool]:
    try:
        cookies = parse_cookies_file(config["cookie"]["cookies_file"])
        bili_jct = cookies.get("bili_jct", "")
        if not bili_jct:
            return False, "缺少 bili_jct，无法发送评论", False

        timeout = config["bot"].get("request_timeout_seconds", 25)
        headers = {
            "User-Agent": random_user_agent(),
            "Accept": "application/json, text/plain, */*",
            "Cookie": build_cookie_header(cookies),
            "Origin": "https://www.bilibili.com",
        }
        img_key, sub_key = _fetch_wbi_keys(headers, timeout)
        type_map = {"video": 1, "dynamic": 17, "dynamic_draw": 11}
        payload = {
            "type": type_map.get(event.business_type, 1),
            "oid": event.oid,
            "root": event.root_rpid,
            "parent": event.parent_rpid,
            "message": f"{config['reply'].get('prefix', '')}{reply_text}".strip(),
            "csrf": bili_jct,
            "plat": 1,
        }
        signed_payload = sign_wbi(payload, img_key, sub_key)
        response = requests.post(
            "https://api.bilibili.com/x/v2/reply/add",
            data=signed_payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()
        code = result.get("code", -1)
        if code == 0:
            return True, "发送成功", False
        retriable = code in {-509, 12051} or str(code).startswith("12")
        return False, f"发送失败 code={code} message={result.get('message')}", retriable
    except requests.RequestException as exc:
        return False, f"网络异常: {exc}", True
    except RuntimeError as exc:
        return False, f"发送前置失败: {exc}", True
    except Exception as exc:  # noqa: BLE001
        return False, f"未知异常: {exc}", False
