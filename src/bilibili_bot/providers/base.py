from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ReplyResult:
    success: bool
    text: str = ""
    provider: str = ""
    error: str = ""
    retriable: bool = False
    raw: Any = None


class BaseProvider(ABC):
    def __init__(self, name: str, provider_config: dict[str, Any], global_config):
        self.name = name
        self.provider_config = provider_config
        self.global_config = global_config

    @abstractmethod
    def generate(self, messages: list[dict[str, str]]) -> ReplyResult:
        pass
