from __future__ import annotations

import hashlib
import time
import functools
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bilibili_bot.wbi import get_mixin_key, enc_wbi

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

WBI_KEYS_URL = "https://api.bilibili.com/x/web-interface/nav"


@functools.lru_cache(maxsize=1)
def _parse_cookies_file(filepath: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    path = Path(filepath)
    if not path.exists():
        return cookies

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
    return cookies


class BilibiliSession(requests.Session):
    def __init__(self, cookies_file: str, timeout: int = 25):
        super().__init__()
        self._cookies_file = cookies_file
        self._timeout = timeout
        self._wbi_keys: tuple[str, str] | None = None
        self._wbi_keys_at: float = 0
        self._load_cookies()
        self._setup_retry()

    def _load_cookies(self) -> None:
        cookies = _parse_cookies_file(self._cookies_file)
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        self.headers.update({
            "Cookie": cookie_header,
            "User-Agent": USER_AGENTS[0],
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        })

    def _setup_retry(self) -> None:
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        self.mount("https://", adapter)
        self.mount("http://", adapter)

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return super().request(method, url, **kwargs)

    def get_wbi_keys(self) -> tuple[str, str]:
        now = time.time()
        if self._wbi_keys and now - self._wbi_keys_at < 1800:
            return self._wbi_keys

        resp = self.get(WBI_KEYS_URL)
        resp.raise_for_status()
        data = resp.json()["data"]

        img_key = data["wbi_img"]["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub_key = data["wbi_img"]["sub_url"].rsplit("/", 1)[-1].split(".")[0]

        self._wbi_keys = (img_key, sub_key)
        self._wbi_keys_at = now
        return self._wbi_keys

    def sign_wbi(self, params: dict[str, Any]) -> dict[str, Any]:
        img_key, sub_key = self.get_wbi_keys()
        return enc_wbi(params, img_key, sub_key)

    def get_cookies(self) -> dict[str, str]:
        return _parse_cookies_file(self._cookies_file)
