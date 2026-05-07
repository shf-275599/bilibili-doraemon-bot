from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from bilibili_bot.state import StateStore

COOKIE_INFO_URL = "https://passport.bilibili.com/x/passport-login/web/cookie/info"
COOKIE_REFRESH_URL = "https://passport.bilibili.com/x/passport-login/web/cookie/refresh"
COOKIE_CONFIRM_URL = "https://passport.bilibili.com/x/passport-login/web/confirm/refresh"
CORRESPOND_BASE_URL = "https://www.bilibili.com/correspond/1/"
CORRESPOND_PUBLIC_KEY = b"""-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDLgd2OAkcGVtoE3ThUREbio0Eg
Uc/prcajMKXvkCKFCWhJYJcLkcM2DKKcSeFpD/j6Boy538YXnR6VhcuUJOhH2x71
nzPjfdTcqMz7djHum0qSZA0AyCBDABUqCrfNgCiJ00Ra7GmRj+YCK1NJEuewlb40
JNrRuoEUXpabUzGB8QIDAQAB
-----END PUBLIC KEY-----"""
REFRESH_CSRF_RE = re.compile(r'<div id="1-name">([^<]+)</div>')


@dataclass
class CookieHealth:
    valid: bool
    should_refresh: bool = False
    refreshed: bool = False
    message: str = ""
    timestamp_ms: int = 0


class CookieRefreshManager:
    def __init__(self, config, store: StateStore | None = None):
        self.config = config
        self.cookies_file = config.cookie.cookies_file
        self.timeout = config.bot.request_timeout_seconds
        self.check_interval_seconds = config.cookie.check_interval_minutes * 60
        self.store = store
        self._last_check_at = self._load_last_check()

    def _load_last_check(self) -> float:
        if self.store is None:
            return 0.0
        state = self.store.load_state()
        return state.get("cookie_refresh", {}).get("last_check_at", 0.0)

    def _save_last_check(self) -> None:
        if self.store is None:
            return
        state = self.store.load_state()
        if "cookie_refresh" not in state:
            state["cookie_refresh"] = {}
        state["cookie_refresh"]["last_check_at"] = self._last_check_at
        self.store.save_state(state)

    def _headers(self) -> dict[str, str]:
        from bilibili_bot.client import _parse_cookies_file, USER_AGENTS
        cookies = _parse_cookies_file(self.cookies_file)
        cookie_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        return {
            "User-Agent": USER_AGENTS[0],
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_header,
        }

    def _cookie_dict(self) -> dict[str, str]:
        from bilibili_bot.client import _parse_cookies_file
        return _parse_cookies_file(self.cookies_file)

    def check_health(self) -> CookieHealth:
        cookies = self._cookie_dict()
        bili_jct = cookies.get("bili_jct", "")
        headers = self._headers()

        try:
            nav = requests.get(
                self.config.cookie.healthcheck_endpoint,
                headers=headers,
                timeout=self.timeout,
            )
            nav.raise_for_status()
            nav_data = nav.json()

            if nav_data.get("code") != 0:
                return CookieHealth(valid=False, message=f"登录态失效: {nav_data.get('message')}")

            info = requests.get(
                COOKIE_INFO_URL,
                headers=headers,
                params={"csrf": bili_jct},
                timeout=self.timeout,
            )
            info.raise_for_status()
            info_data = info.json()

            if info_data.get("code") != 0:
                return CookieHealth(
                    valid=True,
                    should_refresh=False,
                    message=f"cookie/info 返回异常: {info_data.get('message')}",
                )

            return CookieHealth(
                valid=True,
                should_refresh=bool(info_data.get("data", {}).get("refresh", False)),
                message="OK",
                timestamp_ms=int(info_data.get("data", {}).get("timestamp") or 0),
            )

        except Exception as e:
            return CookieHealth(valid=False, message=f"检查失败: {e}")

    def maybe_refresh(self) -> CookieHealth:
        now = time.time()
        if now - self._last_check_at < self.check_interval_seconds:
            return CookieHealth(
                valid=True,
                message=f"距离上次检查未满 {self.check_interval_seconds // 60} 分钟",
            )

        self._last_check_at = now
        self._save_last_check()

        status = self.check_health()
        if not status.valid:
            return status

        if not self.config.cookie.refresh_enabled:
            status.message = "refresh disabled"
            return status

        if not status.should_refresh:
            status.message = "cookie valid and no refresh required"
            return status

        refresh_env = self.config.cookie.refresh_token_env
        refresh_token = os.environ.get(refresh_env, "")
        if not refresh_token:
            status.message = f"需要刷新，但缺少环境变量 {refresh_env}"
            return status

        try:
            correspond_path = self._generate_correspond_path(
                status.timestamp_ms or int(time.time() * 1000)
            )
            refresh_csrf = self._get_refresh_csrf(correspond_path)
            new_refresh_token = self._perform_refresh(refresh_csrf, refresh_token)
            self._confirm_refresh(refresh_token)
            status.refreshed = True
            status.message = f"cookie refresh success; new refresh token={new_refresh_token[:8]}..."
        except Exception as e:
            status.message = f"刷新失败: {e}"

        return status

    def _generate_correspond_path(self, timestamp_ms: int) -> str:
        pub_key = serialization.load_pem_public_key(CORRESPOND_PUBLIC_KEY)
        encrypted = pub_key.encrypt(
            f"refresh_{timestamp_ms}".encode(),
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return encrypted.hex()

    def _get_refresh_csrf(self, correspond_path: str) -> str:
        headers = self._headers()
        response = requests.get(
            f"{CORRESPOND_BASE_URL}{correspond_path}",
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        match = REFRESH_CSRF_RE.search(response.text)
        if not match:
            raise RuntimeError("无法从 correspond 页面提取 refresh_csrf")
        return match.group(1)

    def _perform_refresh(self, refresh_csrf: str, refresh_token: str) -> str:
        cookies = self._cookie_dict()
        headers = self._headers()
        response = requests.post(
            COOKIE_REFRESH_URL,
            headers=headers,
            data={
                "csrf": cookies.get("bili_jct", ""),
                "refresh_csrf": refresh_csrf,
                "source": "main_web",
                "refresh_token": refresh_token,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("code") != 0:
            raise RuntimeError(f"刷新 Cookie 失败: code={payload.get('code')} message={payload.get('message')}")

        updated = cookies.copy()
        for key, value in response.cookies.items():
            updated[key] = value

        self._write_cookies(updated)
        return str(payload.get("data", {}).get("refresh_token", ""))

    def _confirm_refresh(self, old_refresh_token: str) -> None:
        cookies = self._cookie_dict()
        headers = self._headers()
        response = requests.post(
            COOKIE_CONFIRM_URL,
            headers=headers,
            data={
                "csrf": cookies.get("bili_jct", ""),
                "refresh_token": old_refresh_token,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()

        if payload.get("code") != 0:
            raise RuntimeError(f"确认 Cookie 刷新失败: code={payload.get('code')} message={payload.get('message')}")

    def _write_cookies(self, cookies: dict[str, str]) -> None:
        lines = ["# Netscape HTTP Cookie File\n"]
        for name, value in cookies.items():
            lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")

        with open(self.cookies_file, "w", encoding="utf-8") as f:
            f.writelines(lines)
