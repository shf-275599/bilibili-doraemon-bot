from __future__ import annotations

import json
import subprocess
from typing import Any

from bilibili_bot.providers.base import BaseProvider, ReplyResult


class OpenCodeFallbackProvider(BaseProvider):
    def generate(self, messages: list[dict[str, str]]) -> ReplyResult:
        user_prompt = "\n\n".join(part["content"] for part in messages)
        user_prompt = user_prompt.replace("\x00", "")

        if len(user_prompt) > 10000:
            user_prompt = user_prompt[:10000]

        command = [
            self.provider_config.get("command", "opencode"),
            "run",
            "--format",
            "json",
            "--dir",
            self.provider_config.get("dir", "."),
            user_prompt,
        ]

        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.global_config.ai.timeout_seconds + 30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            return ReplyResult(False, provider=self.name, error=str(exc), retriable=True)

        if proc.returncode != 0:
            return ReplyResult(
                False,
                provider=self.name,
                error=proc.stderr.strip() or proc.stdout.strip(),
                retriable=True,
            )

        final_text = ""
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "text":
                final_text = payload.get("part", {}).get("text", final_text)

        if not final_text.strip():
            return ReplyResult(
                False,
                provider=self.name,
                error="OpenCode fallback 未返回文本",
                retriable=False,
                raw=proc.stdout,
            )

        return ReplyResult(True, text=final_text.strip(), provider=self.name, raw=proc.stdout)
