"""PydanticAI Agent 工厂 — 创建配置好的 Agent 实例。"""

from __future__ import annotations

import os

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from bilibili_bot.tools import TOOLS


def create_agent(system_prompt: str, config, provider_name: str) -> Agent:
    """从配置创建 PydanticAI Agent。"""
    provider_cfg = config.ai.providers.get(provider_name)
    if not provider_cfg:
        raise ValueError(f"未找到 AI Provider 配置: {provider_name}")
    if provider_cfg.type != "openai_compatible":
        raise ValueError(f"Provider {provider_name} 类型不是 openai_compatible")

    api_key = os.environ.get(provider_cfg.api_key_env or "", "")
    p = OpenAIProvider(
        base_url=(provider_cfg.base_url or "").rstrip("/"),
        api_key=api_key,
    )
    model = OpenAIChatModel(provider_cfg.model or "", provider=p)
    return Agent(model, system_prompt=system_prompt, tools=TOOLS)
