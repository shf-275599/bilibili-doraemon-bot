"""AI Provider 管理 — 基于 PydanticAI Agent 的会话级对话管理。

每个会话（DM: talker_id，评论: video_id:user_id）维护独立的 Agent 实例，
Agent 内部自动管理对话历史，支持多轮上下文。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog
from pydantic_ai import Agent

from bilibili_bot.providers.base import BaseProvider, ReplyResult
from bilibili_bot.providers.openai_compat import (
    OpenAICompatibleProvider,
    _agent_result_to_reply,
    _create_pydantic_agent,
)

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage

logger = structlog.get_logger()

SESSION_TTL = 3600
MAX_SESSIONS = 500


class ProviderManager:
    def __init__(self, config):
        self._config = config
        providers = config.ai.providers
        self.primary_name = config.ai.primary_provider
        self.primary = self._build_provider(
            self.primary_name, providers[self.primary_name]
        )
        self._sessions: dict[str, _AgentSession] = {}

    def _build_provider(self, name: str, provider_config) -> BaseProvider:
        provider_type = provider_config.type
        if provider_type == "openai_compatible":
            return OpenAICompatibleProvider(
                name, provider_config.model_dump(), self._config
            )
        raise ValueError(f"不支持的 provider type: {provider_type}")

    def chat(
        self,
        session_key: str,
        system_prompt: str,
        user_message: str,
        use_tools: bool = True,
    ) -> ReplyResult:
        """以会话方式生成回复。Agent 内部维护历史。

        session_key: 会话标识（DM用 talker_id, 评论用 video_id:user_id）
        system_prompt: 角色设定
        user_message: 当前用户消息（含上下文）
        """
        session = self._get_or_create_session(session_key, system_prompt, use_tools)
        session.touch()

        try:
            result = session.agent.run_sync(
                user_prompt=user_message,
                message_history=session.history,
            )
            session.history = result.all_messages()
            return _agent_result_to_reply(result, self.primary_name)
        except Exception as e:
            logger.warning("agent_chat_failed", error=str(e), session=session_key)
            return self.primary.generate([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ])

    def _get_or_create_session(
        self, key: str, system_prompt: str, use_tools: bool
    ) -> _AgentSession:
        self._prune()
        if key in self._sessions:
            return self._sessions[key]

        agent = _create_pydantic_agent(
            system_prompt, self._config, self.primary_name
        ) if use_tools else None

        if not use_tools or agent is None:
            agent = _create_pydantic_agent(
                system_prompt, self._config, self.primary_name
            )

        session = _AgentSession(agent=agent, created_at=time.time())
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda k: self._sessions[k].last_used)
            del self._sessions[oldest]
        self._sessions[key] = session
        return session

    def _prune(self) -> None:
        now = time.time()
        expired = [
            k for k, v in self._sessions.items()
            if now - v.last_used > SESSION_TTL
        ]
        for k in expired:
            del self._sessions[k]

    def generate_reply(self, messages: list[dict[str, str]]) -> ReplyResult:
        """降级路径：纯 HTTP 调用（无工具，无会话）。"""
        return self.primary.generate(messages)


class _AgentSession:
    def __init__(self, agent: Agent, created_at: float):
        self.agent = agent
        self.created_at = created_at
        self.last_used = created_at
        self.history: list[ModelMessage] = []

    def touch(self) -> None:
        self.last_used = time.time()
