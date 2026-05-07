from __future__ import annotations

from abc import ABC, abstractmethod

from bilibili_bot.events import Event


class BaseSource(ABC):
    @abstractmethod
    def fetch(self) -> list[Event]:
        pass
