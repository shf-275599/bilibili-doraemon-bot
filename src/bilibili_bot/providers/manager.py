from __future__ import annotations

import structlog

from bilibili_bot.providers.base import BaseProvider, ReplyResult
from bilibili_bot.providers.openai_compat import OpenAICompatibleProvider
from bilibili_bot.providers.opencode_fallback import OpenCodeFallbackProvider

logger = structlog.get_logger()


class ProviderManager:
    def __init__(self, config):
        self.config = config
        providers = config.ai.providers
        self.primary_name = config.ai.primary_provider
        self.fallback_name = config.ai.fallback_provider

        self.primary = self._build_provider(self.primary_name, providers[self.primary_name])
        self.fallback = self._build_provider(self.fallback_name, providers[self.fallback_name])

    def _build_provider(self, name: str, provider_config) -> BaseProvider:
        provider_type = provider_config.type
        if provider_type == "openai_compatible":
            return OpenAICompatibleProvider(name, provider_config.model_dump(), self.config)
        if provider_type == "opencode_local":
            return OpenCodeFallbackProvider(name, provider_config.model_dump(), self.config)
        raise ValueError(f"不支持的 provider type: {provider_type}")

    def generate_reply(self, messages: list[dict[str, str]]) -> ReplyResult:
        primary_result = self.primary.generate(messages)
        if primary_result.success:
            return primary_result

        logger.warning(
            "primary_provider_failed",
            provider=self.primary_name,
            error=primary_result.error,
            fallback=self.fallback_name,
        )

        fallback_result = self.fallback.generate(messages)
        if fallback_result.success:
            return fallback_result

        fallback_result.error = (
            f"主 Provider 失败: {primary_result.error} | fallback 失败: {fallback_result.error}"
        )
        return fallback_result
