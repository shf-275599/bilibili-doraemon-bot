from __future__ import annotations

import re
from dataclasses import dataclass

import structlog

from bilibili_bot.events import Event
from bilibili_bot.pipeline.base import PipelineStage, PipelineContext, StageResult

logger = structlog.get_logger()

PII_PATTERNS = [
    (r"\b1[3-9]\d{9}\b", "手机号"),
    (r"\b\d{17}[\dXx]\b", "身份证号"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "邮箱"),
    (r"\b\d{16,19}\b", "银行卡号"),
]


@dataclass
class SafetyCheckResult:
    safe: bool
    reason: str = ""
    risk_level: str = "none"


class ContentSafetyChecker:
    def __init__(self, config):
        self.sensitive_words = config.content_safety.sensitive_words
        self.max_length = config.content_safety.max_length
        self.max_url_count = config.content_safety.max_url_count
        self.block_pii = config.content_safety.block_pii
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        if self.sensitive_words:
            pattern = "|".join(re.escape(w) for w in self.sensitive_words)
        else:
            pattern = "(?!x)x"
        self.sensitive_pattern = re.compile(pattern, re.IGNORECASE)
        self.url_pattern = re.compile(r"https?://[^\s]+|www\.[^\s]+", re.IGNORECASE)

    def check(self, text: str) -> SafetyCheckResult:
        if not text or not text.strip():
            return SafetyCheckResult(False, "空内容", "high")

        if len(text) > self.max_length:
            return SafetyCheckResult(
                False,
                f"内容过长（{len(text)} 字，上限 {self.max_length}）",
                "medium",
            )

        sensitive_matches = self.sensitive_pattern.findall(text)
        if sensitive_matches:
            return SafetyCheckResult(
                False,
                f"包含敏感词: {', '.join(set(sensitive_matches[:3]))}",
                "high",
            )

        url_count = len(self.url_pattern.findall(text))
        if url_count > self.max_url_count:
            return SafetyCheckResult(
                False,
                f"包含过多链接（{url_count} 个，上限 {self.max_url_count}）",
                "medium",
            )

        if self.block_pii:
            pii_found = []
            for pattern, pii_type in PII_PATTERNS:
                if re.search(pattern, text):
                    pii_found.append(pii_type)
            if len(pii_found) >= 1:
                return SafetyCheckResult(
                    False,
                    f"包含个人信息: {', '.join(pii_found)}",
                    "high",
                )

        return SafetyCheckResult(True, "内容安全", "none")


class SafetyCheckStage(PipelineStage):
    def __init__(self):
        self._checker = None

    def _get_checker(self, config) -> ContentSafetyChecker:
        if self._checker is None:
            self._checker = ContentSafetyChecker(config)
        return self._checker

    def process(self, event: Event, context: PipelineContext) -> StageResult:
        checker = self._get_checker(context.config)
        check = checker.check(context.reply_text)

        if not check.safe:
            logger.error(
                "safety_check_failed",
                event_key=event.event_key,
                reason=check.reason,
                risk_level=check.risk_level,
            )
            context.dedup.mark_failed(event, f"内容安全审查: {check.reason}", context.provider_used)
            return StageResult.HALT

        return StageResult.CONTINUE
