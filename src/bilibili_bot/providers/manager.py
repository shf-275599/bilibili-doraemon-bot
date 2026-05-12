"""AI Provider 管理 — PydanticAI Agent 会话级对话管理。

v3.1: deps注入 + Usage追踪 + ModelSettings + run_stream
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import Usage

from bilibili_bot.tools import TOOLS

if TYPE_CHECKING:
    from pydantic_ai.messages import ModelMessage

logger = structlog.get_logger()

SESSION_TTL = 3600
MAX_SESSIONS = 500
HISTORY_MAX = 50


@dataclass
class BotDeps:
    """工具依赖注入。"""
    config: Any = None


@dataclass
class ReplyResult:
    success: bool
    text: str = ""
    provider: str = ""
    error: str = ""
    retriable: bool = False
    tool_calls: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


class ProviderManager:
    def __init__(self, config):
        self._config = config
        self._sessions: dict[str, _AgentSession] = {}
        self._deps = BotDeps(config=config)

    def chat(self, session_key: str, system_prompt: str,
             user_message: str, stream: bool = False) -> ReplyResult:
        session = self._get_or_create_session(session_key, system_prompt)
        session.touch()
        try:
            if stream:
                return self._chat_stream(session, user_message)
            result = session.agent.run_sync(
                user_prompt=user_message,
                message_history=session.history,
                deps=self._deps,
                model_settings=ModelSettings(
                    temperature=self._config.reply.temperature,
                    max_tokens=self._config.reply.max_tokens,
                ),
            )
            session.history = result.all_messages()
            self._trim_history(session)
            return _result_to_reply(result)
        except Exception as e:
            logger.warning("agent_chat_failed", error=str(e), session=session_key)
            return ReplyResult(False, error=str(e), retriable=True)

    def _chat_stream(self, session: _AgentSession, user_message: str) -> ReplyResult:
        import sys
        full_text = ""
        try:
            with session.agent.run_stream(
                user_prompt=user_message,
                message_history=session.history,
                deps=self._deps,
                model_settings=ModelSettings(
                    temperature=self._config.reply.temperature,
                    max_tokens=self._config.reply.max_tokens,
                ),
            ) as stream:
                for text in stream.stream_text(delta=True):
                    full_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
                sys.stdout.write("\n")
            return ReplyResult(True, text=full_text.strip(), provider="deepseek")
        except Exception as e:
            return ReplyResult(False, error=str(e), retriable=True)

    def _get_or_create_session(self, key: str, system_prompt: str) -> _AgentSession:
        self._prune()
        if key in self._sessions:
            return self._sessions[key]
        cfg = self._config.ai.providers[self._config.ai.primary_provider]
        api_key = os.environ.get(cfg.api_key_env or "", "")
        p = OpenAIProvider(base_url=(cfg.base_url or "").rstrip("/"), api_key=api_key)
        model = OpenAIChatModel(cfg.model or "", provider=p)
        agent = Agent(model, system_prompt=system_prompt, tools=TOOLS, deps_type=BotDeps)
        session = _AgentSession(agent=agent, created_at=time.time())
        if len(self._sessions) >= MAX_SESSIONS:
            oldest = min(self._sessions, key=lambda k: self._sessions[k].last_used)
            del self._sessions[oldest]
        self._sessions[key] = session
        return session

    def _prune(self) -> None:
        now = time.time()
        for k in list(self._sessions):
            if now - self._sessions[k].last_used > SESSION_TTL:
                del self._sessions[k]

    def _trim_history(self, session: _AgentSession) -> None:
        if len(session.history) <= HISTORY_MAX:
            return
        session.history = [session.history[0]] + session.history[-30:]


class _AgentSession:
    def __init__(self, agent: Agent, created_at: float):
        self.agent = agent
        self.created_at = created_at
        self.last_used = created_at
        self.history: list[ModelMessage] = []

    def touch(self) -> None:
        self.last_used = time.time()


def _result_to_reply(result) -> ReplyResult:
    tool_calls: list[str] = []
    token_usage: dict[str, int] = {}
    try:
        for msg in result.all_messages():
            for part in msg.parts:
                name = getattr(part, "tool_name", "") or ""
                if name and name not in tool_calls:
                    tool_calls.append(name)
    except Exception:
        pass
    try:
        u: Usage = result.usage()
        token_usage = {"request": u.request_tokens or 0,
                       "response": u.response_tokens or 0,
                       "total": u.total_tokens or 0}
    except Exception:
        pass
    return ReplyResult(success=True, text=str(result.output),
                       provider="deepseek", tool_calls=tool_calls, usage=token_usage)
