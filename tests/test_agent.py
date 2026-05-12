"""PydanticAI Agent 集成测试。"""
from unittest.mock import MagicMock

from bilibili_bot.events import DMEvent, CommentEvent
from bilibili_bot.pipeline.generate import _make_session_key
from bilibili_bot.providers.manager import _result_to_reply


class TestSessionKey:
    def test_dm_session_key(self):
        event = DMEvent(
            source_type="dm", event_key="x", created_at=0,
            talker_id=12345, talker_name="test", dm_content="hi",
        )
        assert _make_session_key(event) == "dm:12345"

    def test_comment_session_key(self):
        event = CommentEvent(
            source_type="msgfeed", event_key="x", created_at=0,
            business_type="video", oid="999", rpid="1",
            author_mid="888", author_name="test", content_text="hi",
        )
        assert _make_session_key(event) == "msgfeed:999:888"


class TestReplyResult:
    def test_creates_success_reply(self):
        result = MagicMock()
        result.output = "你好世界"
        result.all_messages.return_value = []

        reply = _result_to_reply(result)
        assert reply.success is True
        assert reply.text == "你好世界"

    def test_extracts_tool_calls(self):
        result = MagicMock()
        result.output = "回复内容"
        msg = MagicMock()
        part = MagicMock()
        part.tool_name = "search_web"
        msg.parts = [part]
        result.all_messages.return_value = [msg]

        reply = _result_to_reply(result)
        assert reply.tool_calls == ["search_web"]
