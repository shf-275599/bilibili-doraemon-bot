"""PydanticAI Agent 集成测试。"""
from unittest.mock import MagicMock

from bilibili_bot.events import DMEvent, CommentEvent
from bilibili_bot.pipeline.generate import _make_session_key


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

    def test_mention_session_key(self):
        event = CommentEvent(
            source_type="mention", event_key="x", created_at=0,
            business_type="dynamic", oid="777", rpid="2",
            author_mid="666", author_name="test", content_text="hi",
        )
        assert _make_session_key(event) == "mention:777:666"


class TestAgentResultConversion:
    def test_creates_success_reply(self):
        from bilibili_bot.providers.openai_compat import _agent_result_to_reply

        result = MagicMock()
        result.output = "你好世界"

        reply = _agent_result_to_reply(result, "test-provider")
        assert reply.success is True
        assert reply.text == "你好世界"
        assert reply.provider == "test-provider"
