"""CookieStore 单元测试。"""
import os
import time

import pytest

from bilibili_bot.cookie_store import CookieStore


@pytest.fixture
def cookie_file(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t37069843\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tabc123def\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tSESSDATA\tsess%2Cabc\n"
        "\n"
    )
    return str(path)


@pytest.fixture
def store(cookie_file):
    return CookieStore(cookie_file)


def test_get_existing_key(store):
    assert store.get("DedeUserID") == "37069843"


def test_get_missing_key_returns_default(store):
    assert store.get("nonexistent") == ""
    assert store.get("nonexistent", "fallback") == "fallback"


def test_get_all(store):
    all_cookies = store.get_all()
    assert all_cookies["DedeUserID"] == "37069843"
    assert all_cookies["bili_jct"] == "abc123def"
    assert "SESSDATA" in all_cookies


def test_get_all_returns_copy(store):
    all_cookies = store.get_all()
    all_cookies["DedeUserID"] = "modified"
    assert store.get("DedeUserID") == "37069843"


def test_get_header(store):
    header = store.get_header()
    assert "DedeUserID=37069843" in header
    assert "bili_jct=abc123def" in header


def test_reload_picks_up_changes(cookie_file, store):
    new_content = (
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t99999\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tnew_token\n"
    )
    with open(cookie_file, "w") as f:
        f.write(new_content)

    store.reload()
    assert store.get("DedeUserID") == "99999"
    assert store.get("bili_jct") == "new_token"


def test_auto_reload_on_mtime_change(cookie_file, store):
    time.sleep(0.01)
    new_content = (
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t88888\n"
    )
    with open(cookie_file, "w") as f:
        f.write(new_content)

    assert store.get("DedeUserID") == "88888"


def test_no_unnecessary_reload(cookie_file, store):
    initial = store.get("DedeUserID")
    assert store.get("DedeUserID") == initial
    assert store.get("DedeUserID") == initial


def test_write_updates_file_and_memory(store, tmp_path):
    new_file = str(tmp_path / "new_cookies.txt")
    cs = CookieStore(new_file)
    cs.write({"DedeUserID": "123", "bili_jct": "token"})

    assert cs.get("DedeUserID") == "123"
    assert cs.get("bili_jct") == "token"

    cs2 = CookieStore(new_file)
    assert cs2.get("DedeUserID") == "123"


def test_empty_file(tmp_path):
    path = tmp_path / "empty.txt"
    path.write_text("")
    store = CookieStore(str(path))
    assert store.get("anything") == ""
    assert store.get_all() == {}


def test_comment_only_file(tmp_path):
    path = tmp_path / "comments.txt"
    path.write_text("# just a comment\n# another one\n")
    store = CookieStore(str(path))
    assert store.get_all() == {}


def test_malformed_lines_skipped(tmp_path):
    path = tmp_path / "malformed.txt"
    path.write_text(
        "# header\n"
        "bad line\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tvalid_token\n"
    )
    store = CookieStore(str(path))
    assert store.get("bili_jct") == "valid_token"


def test_nonexistent_file(tmp_path):
    path = str(tmp_path / "does_not_exist.txt")
    store = CookieStore(path)
    assert store.get("anything") == ""
    assert store.get_all() == {}
    assert store.get_header() == ""
