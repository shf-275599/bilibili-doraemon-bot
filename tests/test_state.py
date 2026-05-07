import pytest
from bilibili_bot.state import StateStore


def test_state_store(tmp_path):
    store = StateStore(tmp_path)

    state = {"key": "value"}
    store.save_state(state)

    loaded = store.load_state()
    assert loaded == state


def test_append_processed(tmp_path):
    store = StateStore(tmp_path)

    record = {"event_key": "test:1", "reply_status": "replied"}
    store.append_processed(record)

    assert store.has_success("test:1")
    assert not store.has_success("test:2")


def test_update_state(tmp_path):
    store = StateStore(tmp_path)

    store.save_state({"a": 1})
    result = store.update_state({"b": 2})

    assert result == {"a": 1, "b": 2}
