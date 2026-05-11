import pytest
from pathlib import Path

from bilibili_bot.config import BotConfig
from bilibili_bot.atomic_state import AtomicStateStore
from bilibili_bot.cookie_store import CookieStore


@pytest.fixture
def config():
    return BotConfig()


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def atomic_store(tmp_path):
    return AtomicStateStore(tmp_path / "data")


@pytest.fixture
def cookie_file_path(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text(
        "# Netscape HTTP Cookie File\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tDedeUserID\t37069843\n"
        ".bilibili.com\tTRUE\t/\tFALSE\t0\tbili_jct\tabc123def\n"
    )
    return str(path)


@pytest.fixture
def cookie_store(cookie_file_path):
    return CookieStore(cookie_file_path)
