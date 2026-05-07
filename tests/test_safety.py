import pytest
from bilibili_bot.pipeline.safety import ContentSafetyChecker
from bilibili_bot.config import BotConfig


def test_normal_content():
    config = BotConfig()
    checker = ContentSafetyChecker(config)

    result = checker.check("这是一条正常的评论")
    assert result.safe is True


def test_empty_content():
    config = BotConfig()
    checker = ContentSafetyChecker(config)

    result = checker.check("")
    assert result.safe is False


def test_long_content():
    config = BotConfig()
    checker = ContentSafetyChecker(config)

    result = checker.check("a" * 600)
    assert result.safe is False


def test_sensitive_words():
    config = BotConfig()
    checker = ContentSafetyChecker(config)

    result = checker.check("这个赌博网站真好")
    assert result.safe is False


def test_urls():
    config = BotConfig()
    checker = ContentSafetyChecker(config)

    result = checker.check("看看 http://a.com http://b.com http://c.com http://d.com")
    assert result.safe is False
