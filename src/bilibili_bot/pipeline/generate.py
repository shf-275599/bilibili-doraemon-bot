from __future__ import annotations

import structlog

from bilibili_bot.events import Event, CommentEvent, DMEvent
from bilibili_bot.pipeline.base import PipelineStage, PipelineContext, StageResult

logger = structlog.get_logger()


def build_comment_messages(event: CommentEvent, config) -> list[dict[str, str]]:
    business_labels = {"video": "视频", "dynamic": "动态", "dynamic_draw": "图文动态"}
    business_label = business_labels.get(event.business_type, event.business_type)

    user_content = (
        f"来源：{business_label}\n"
        f"是否@我：{'是' if event.at_me else '否'}\n"
        f"评论作者：{event.author_name}\n"
        f"评论内容：{event.content_text}\n\n"
        f"请直接生成一条适合在B站公开回复的中文回复。要求：自然、友好、简洁，"
        f"不超过 {config.ai.max_reply_chars} 个汉字，不要解释自己，"
        f"不要输出多版本，不要加引号。"
    )

    return [
        {"role": "system", "content": config.reply.system_prompt},
        {"role": "user", "content": user_content},
    ]


def build_dm_messages(event: DMEvent, config) -> list[dict[str, str]]:
    user_content = f"用户 {event.talker_name} 发来私信：{event.content}"

    return [
        {"role": "system", "content": config.dm_reply.system_prompt},
        {"role": "user", "content": user_content},
    ]


class AIGenerateStage(PipelineStage):
    def process(self, event: Event, context: PipelineContext) -> StageResult:
        if isinstance(event, CommentEvent):
            messages = build_comment_messages(event, context.config)
        elif isinstance(event, DMEvent):
            messages = build_dm_messages(event, context.config)
        else:
            logger.error("unknown_event_type", event_type=type(event).__name__)
            return StageResult.SKIP

        reply = context.providers.generate_reply(messages)

        if not reply.success:
            logger.error("generate_failed", event_key=event.event_key, error=reply.error)
            context.dedup.mark_failed(event, reply.error, reply.provider)
            context.rate_limiter.record_failure(reply.retriable)
            return StageResult.HALT

        context.reply_text = reply.text
        context.provider_used = reply.provider
        return StageResult.CONTINUE
