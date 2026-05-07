import pytest
from bilibili_bot.pipeline.filter import FilterStage
from bilibili_bot.pipeline.base import PipelineContext
from bilibili_bot.events import CommentEvent
from bilibili_bot.config import BotConfig


@pytest.fixture
def context(config):
    class MockClient:
        def get_cookies(self):
            return {"DedeUserID": "123"}

    return PipelineContext(
        config=config,
        client=MockClient(),
        dedup=None,
        providers=None,
        rate_limiter=None,
    )


def test_skip_self(context):
    stage = FilterStage()

    event = CommentEvent(
        source_type="msgfeed",
        event_key="video:123:456",
        created_at=1000,
        author_mid="123",
        content_text="test",
    )

    result = stage.process(event, context)
    from bilibili_bot.pipeline.base import StageResult
    assert result == StageResult.SKIP


def test_skip_empty(context):
    stage = FilterStage()

    event = CommentEvent(
        source_type="msgfeed",
        event_key="video:123:456",
        created_at=1000,
        author_mid="456",
        content_text="",
    )

    result = stage.process(event, context)
    from bilibili_bot.pipeline.base import StageResult
    assert result == StageResult.SKIP


def test_pass_normal(context):
    stage = FilterStage()

    event = CommentEvent(
        source_type="msgfeed",
        event_key="video:123:456",
        created_at=1000,
        author_mid="456",
        content_text="正常评论",
    )

    result = stage.process(event, context)
    from bilibili_bot.pipeline.base import StageResult
    assert result == StageResult.CONTINUE
