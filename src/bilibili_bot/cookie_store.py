"""Cookie 存储 — 无缓存，每次请求前按需重载。

替代 v2 的 _parse_cookies_file + lru_cache 模式。
mtime 检测：文件被外部修改时自动重载。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class CookieStore:
    """Netscape 格式 Cookie 文件存储。

    自动感知外部文件变更（os.path.getmtime），无需手动 reload。
    write() 使用原子写入（tempfile + os.replace）。
    """

    def __init__(self, filepath: str | Path) -> None:
        self._path = Path(filepath)
        self._cookies: dict[str, str] = {}
        self._mtime: float = 0.0
        self.reload()

    def get(self, key: str, default: str = "") -> str:
        """获取单个 cookie 值（自动检测文件变更）。"""
        self._maybe_reload()
        return self._cookies.get(key, default)

    def get_all(self) -> dict[str, str]:
        """获取全部 cookie 的副本（自动检测文件变更）。"""
        self._maybe_reload()
        return dict(self._cookies)

    def get_header(self) -> str:
        """返回 HTTP Cookie 请求头字符串。"""
        self._maybe_reload()
        return "; ".join(f"{k}={v}" for k, v in self._cookies.items())

    def reload(self) -> None:
        """从文件强制重新加载。"""
        if not self._path.exists():
            self._cookies = {}
            self._mtime = 0.0
            return

        cookies: dict[str, str] = {}
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]

        self._cookies = cookies
        self._mtime = os.path.getmtime(self._path)

    def write(self, cookies: dict[str, str]) -> None:
        """原子写入 Cookie 文件并更新内存缓存。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Netscape HTTP Cookie File\n"]
        for name, value in cookies.items():
            lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=self._path.parent, encoding="utf-8"
            ) as f:
                f.writelines(lines)
                tmp_path = f.name
            os.replace(tmp_path, self._path)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        self._cookies = dict(cookies)
        self._mtime = os.path.getmtime(self._path)

    def _maybe_reload(self) -> None:
        """如果文件 mtime 变更则自动重载。"""
        if not self._path.exists():
            return
        try:
            current_mtime = os.path.getmtime(self._path)
        except OSError:
            return
        if current_mtime != self._mtime:
            self.reload()
