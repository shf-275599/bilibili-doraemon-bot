#!/usr/bin/env python3
"""基础频率控制与退避。"""

from __future__ import annotations

import random
import time


class RateController:
    def __init__(self, config: dict):
        self.config = config
        cfg = config["rate_limit"]
        self.min_request_interval = cfg.get("min_request_interval_seconds", 3)
        self.reply_delay_min = cfg.get("reply_delay_min_seconds", 8)
        self.reply_delay_max = cfg.get("reply_delay_max_seconds", 20)
        self.backoff_base = cfg.get("backoff_base_seconds", 10)
        self.circuit_breaker_failures = cfg.get("circuit_breaker_failures", 5)
        self.circuit_breaker_cooldown = cfg.get("circuit_breaker_cooldown_seconds", 600)
        self.source_circuit_breaker_failures = cfg.get("source_circuit_breaker_failures", 3)
        self.max_hourly_replies = cfg.get("max_hourly_replies", 20)
        self.max_daily_replies = cfg.get("max_daily_replies", 100)
        self.failure_count = 0
        self.cooldown_until = 0.0
        self.last_request_at = 0.0
        self.reply_timestamps: list[float] = []
        self.source_failures: dict[str, int] = {}
        self.source_cooldowns: dict[str, float] = {}

    def wait_for_request_slot(self) -> float:
        now = time.time()
        elapsed = now - self.last_request_at
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            time.sleep(sleep_time)
            now = time.time()
        self.last_request_at = now
        return now

    def can_send(self) -> tuple[bool, str]:
        self._prune_reply_timestamps()
        if time.time() < self.cooldown_until:
            return False, f"熔断冷却中，直到 {int(self.cooldown_until)}"
        if len([ts for ts in self.reply_timestamps if time.time() - ts < 3600]) >= self.max_hourly_replies:
            return False, "已达到每小时回复上限"
        if len([ts for ts in self.reply_timestamps if time.time() - ts < 86400]) >= self.max_daily_replies:
            return False, "已达到每日回复上限"
        return True, "允许发送"

    def can_run_source(self, name: str) -> tuple[bool, str]:
        until = self.source_cooldowns.get(name, 0.0)
        if time.time() < until:
            return False, f"来源 {name} 冷却中，直到 {int(until)}"
        return True, "允许采集"

    def wait_before_send(self) -> float:
        delay = random.uniform(self.reply_delay_min, self.reply_delay_max)
        time.sleep(delay)
        return delay

    def record_success(self) -> None:
        self.failure_count = 0
        self.cooldown_until = 0.0
        self.reply_timestamps.append(time.time())
        self._prune_reply_timestamps()

    def record_source_success(self, name: str) -> None:
        self.source_failures[name] = 0
        self.source_cooldowns[name] = 0.0

    def record_failure(self, retriable: bool) -> float:
        self.failure_count += 1
        delay = self.backoff_base * (2 ** max(0, self.failure_count - 1))
        if self.failure_count >= self.circuit_breaker_failures:
            self.cooldown_until = time.time() + self.circuit_breaker_cooldown
        if retriable:
            time.sleep(delay)
        return delay

    def record_source_failure(self, name: str) -> float:
        count = self.source_failures.get(name, 0) + 1
        self.source_failures[name] = count
        delay = self.backoff_base * max(1, count)
        if count >= self.source_circuit_breaker_failures:
            cooldown = self.config["bot"].get("source_failure_cooldown_seconds", 180)
            self.source_cooldowns[name] = time.time() + cooldown
        return delay

    def snapshot(self) -> dict:
        self._prune_reply_timestamps()
        now = time.time()
        return {
            "failure_count": self.failure_count,
            "cooldown_until": int(self.cooldown_until),
            "hourly_replies": len([ts for ts in self.reply_timestamps if now - ts < 3600]),
            "daily_replies": len([ts for ts in self.reply_timestamps if now - ts < 86400]),
            "source_failures": self.source_failures,
            "source_cooldowns": {k: int(v) for k, v in self.source_cooldowns.items()},
            "last_request_at": int(self.last_request_at),
        }

    def _prune_reply_timestamps(self) -> None:
        now = time.time()
        self.reply_timestamps = [ts for ts in self.reply_timestamps if now - ts < 86400]
