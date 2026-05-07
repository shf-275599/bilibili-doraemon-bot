import pytest
from pathlib import Path

from bilibili_bot.config import BotConfig


@pytest.fixture
def config():
    return BotConfig()


@pytest.fixture
def tmp_data_dir(tmp_path):
    return tmp_path / "data"
