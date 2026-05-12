"""AI 生成阶段 — 构建消息并调用 ProviderManager。

v3 Agent 重构: 不再手动拼接历史消息。Agent 内部维护对话历史。
只需构建当前消息的上下文，Agent 通过 session_key 自动关联历史。
"""

from __future__ import annotations

import structlog
from datetime import datetime, timedelta, timezone

from bilibili_bot.events import Event, CommentEvent, DMEvent
from bilibili_bot.pipeline.base import PipelineStage, PipelineContext, StageResult

CST = timezone(timedelta(hours=8))

logger = structlog.get_logger()


def _build_comment_prompt(event: CommentEvent) -> str:
    """构建单条评论的上下文 prompt（不含历史，Agent 管理历史）。"""
    business_labels = {
        "video": "视频", "dynamic": "动态",
        "dynamic_draw": "图文动态", "article": "专栏文章",
    }
    business_label = business_labels.get(event.business_type, event.business_type)

    now = datetime.now(CST)
    parts = [f"时间：{now.strftime('%m月%d日 %H:%M')} | 来源：{business_label}"]

    if event.video_title:
        label_map = {"dynamic": "动态内容", "dynamic_draw": "动态内容", "article": "文章标题"}
        label = label_map.get(event.business_type, "内容标题")
        parts.append(f"{label}：{event.video_title}")
        if event.images:
            img_label = "文章配图" if event.business_type == "article" else "动态图片"
            parts.append(f"{img_label}：共 {len(event.images)} 张")
    elif event.images:
        type_label = "专栏文章" if event.business_type == "article" else "图文动态"
        parts.append(f"{type_label}，包含 {len(event.images)} 张图片")

    if event.bvid:
        parts.append(f"BV号：{event.bvid}")
    if event.video_desc:
        desc_label = "文章摘要" if event.business_type == "article" else "简介"
        parts.append(f"{desc_label}：{event.video_desc}")
    if event.up_name:
        parts.append(f"UP主：{event.up_name}")

    if event.thread_context:
        parts.append(f"\n对话上下文：{event.thread_context}")
    if event.parent_content:
        parts.append(f"被回复的评论：{event.parent_content}")

    if event.author_follower:
        parts.append("对方是你的粉丝")
    if event.author_level > 0:
        parts.append(f"对方等级：Lv{event.author_level}")

    parts.append(f"\n{event.author_name} 说：{event.content_text}")
    return "\n".join(parts)


def _build_dm_prompt(event: DMEvent) -> str:
    """构建单条私信的上下文 prompt（不含历史，Agent 管理历史）。"""
    now = datetime.now(CST)
    return (
        f"时间：{now.strftime('%m月%d日 %H:%M')}\n"
        f"{event.talker_name} 发来私信：{event.content}"
    )


def _make_session_key(event: Event) -> str:
    """生成 Agent 会话 key。DM: talker_id, 评论: {type}:{oid}:{mid}"""
    if isinstance(event, DMEvent):
        return f"dm:{event.talker_id}"
    return f"{event.source_type}:{event.target_id}:{event.author_id}"


class AIGenerateStage(PipelineStage):
    def process(self, event: Event, context: PipelineContext) -> StageResult:
        system_prompt = context.config.reply.system_prompt

        if isinstance(event, CommentEvent):
            user_message = _build_comment_prompt(event)
        elif isinstance(event, DMEvent):
            user_message = _build_dm_prompt(event)
        else:
            return StageResult.SKIP

        session_key = _make_session_key(event)
        use_tools = context.config.ai.tools_enabled

        reply = context.providers.chat(
            session_key=session_key,
            system_prompt=system_prompt,
            user_message=user_message,
        )

        if not reply.success:
            logger.error("generate_failed", key=event.event_key, error=reply.error)
            context.dedup.mark_failed(event, reply.error, reply.provider)
            context.rate_limiter.record_failure(reply.retriable)
            return StageResult.HALT

        context.reply_text = reply.text
        context.provider_used = reply.provider
        context.tool_calls = reply.tool_calls
        return StageResult.CONTINUE
