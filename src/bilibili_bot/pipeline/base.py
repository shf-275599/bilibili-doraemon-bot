from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from bilibili_bot.events import Event


class StageResult(Enum):
    CONTINUE = "continue"
    SKIP = "skip"
    HALT = "halt"


@dataclass
class PipelineContext:
    config: Any
    client: Any
    dedup: Any
    providers: Any
    rate_limiter: Any
    dry_run: bool = False
    reply_text: str = ""
    provider_used: str = ""
    auto_skip: Any = None
    store: Any = None


class PipelineStage(ABC):
    @abstractmethod
    def process(self, event: Event, context: PipelineContext) -> StageResult:
        pass


class Pipeline:
    def __init__(self, stages: list[PipelineStage]):
        self.stages = stages

    def run(self, event: Event, context: PipelineContext) -> bool:
        for stage in self.stages:
            result = stage.process(event, context)
            if result == StageResult.SKIP:
                return False
            if result == StageResult.HALT:
                return False
        return True
