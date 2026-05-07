import pytest
from bilibili_bot.events import CommentEvent, DMEvent


def test_comment_event():
    event = CommentEvent(
        source_type="msgfeed",
        event_key="video:123:456",
        created_at=1000,
        business_type="video",
        oid="123",
        rpid="456",
        author_mid="789",
        author_name="test",
        content_text="hello",
    )

    assert event.author_id == "789"
    assert event.content == "hello"
    assert event.target_id == "123"


def test_dm_event():
    event = DMEvent(
        source_type="dm",
        event_key="dm:123:456",
        created_at=1000,
        talker_id=123,
        talker_name="test",
        dm_content="hello",
    )

    assert event.author_id == "123"
    assert event.content == "hello"
    assert event.target_id == "123"
