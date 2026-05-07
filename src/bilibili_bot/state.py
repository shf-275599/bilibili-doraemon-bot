from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class StateStore:
    def __init__(self, root: str | Path = "data"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.processed_path = self.root / "processed.jsonl"
        self.reply_history_path = self.root / "reply-history.jsonl"
        self.state_path = self.root / "bot-state.json"
        self._processed_index: dict[str, dict[str, Any]] = {}
        self._load_processed_index()

    def _load_processed_index(self) -> None:
        if not self.processed_path.exists():
            return

        with self.processed_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    key = record.get("event_key")
                    if key:
                        self._processed_index[key] = record
                except json.JSONDecodeError:
                    continue

    def has_success(self, event_key: str) -> bool:
        record = self._processed_index.get(event_key)
        return bool(record and record.get("reply_status") == "replied")

    def get_record(self, event_key: str) -> dict[str, Any] | None:
        return self._processed_index.get(event_key)

    def append_processed(self, record: dict[str, Any]) -> None:
        self._append_jsonl(self.processed_path, record)
        key = record.get("event_key")
        if key:
            self._processed_index[key] = record

    def append_history(self, record: dict[str, Any]) -> None:
        self._append_jsonl(self.reply_history_path, record)

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}

        try:
            with self.state_path.open("r", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                data = json.load(f)
                fcntl.flock(f, fcntl.LOCK_UN)
                return data
        except (json.JSONDecodeError, OSError):
            return {}

    def save_state(self, state: dict[str, Any]) -> None:
        self._atomic_json_write(self.state_path, state)

    def update_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.load_state()
        current.update(updates)
        self.save_state(current)
        return current

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            fcntl.flock(f, fcntl.LOCK_UN)

    def _atomic_json_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=path.parent, encoding="utf-8"
            ) as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                temp_path = f.name
            os.replace(temp_path, path)
        except Exception:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def compact_processed(self) -> int:
        if not self.processed_path.exists():
            return 0

        before_size = self.processed_path.stat().st_size
        records = list(self._processed_index.values())

        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=self.processed_path.parent, encoding="utf-8"
        ) as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            temp_path = f.name

        os.replace(temp_path, self.processed_path)
        after_size = self.processed_path.stat().st_size
        return before_size - after_size

    def compact_reply_history(self, max_records: int = 10000) -> int:
        if not self.reply_history_path.exists():
            return 0

        before_size = self.reply_history_path.stat().st_size
        records = []

        with self.reply_history_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(line)

        if len(records) <= max_records:
            return 0

        records = records[-max_records:]

        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=self.reply_history_path.parent, encoding="utf-8"
        ) as f:
            for line in records:
                f.write(line + "\n")
            temp_path = f.name

        os.replace(temp_path, self.reply_history_path)
        after_size = self.reply_history_path.stat().st_size
        return before_size - after_size


def utc_timestamp() -> int:
    return int(time.time())
