"""Bilibili Bot 工具系统 —— PydanticAI Tool 定义与执行。"""

from __future__ import annotations

import functools
import subprocess
import threading
import time
from pathlib import Path

import requests
import structlog
from pydantic_ai import Tool

logger = structlog.get_logger()

# 包根目录（src/bilibili_bot/ 的上两级 → 项目根）
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPTS_DIR = _PACKAGE_ROOT / "scripts"
COOKIES_FILE = str(_PACKAGE_ROOT / "config" / "bilibili-cookies.txt")
WHISPER_MODEL = str(
    _PACKAGE_ROOT / "models" / "whisper"
    / "models--Systran--faster-whisper-base"
    / "snapshots" / "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"
)

TRANSCRIBE_COOLDOWN = 30
MAX_CACHE_SIZE = 50

_last_transcribe_at: float = 0
_transcript_cache: dict[str, str] = {}
_transcribe_lock = threading.Lock()


def _with_tool_logging(func):
    """包装工具函数，记录 structlog 日志。"""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(
            "tool_call_start",
            tool=func.__name__,
            args=kwargs if kwargs else {},
        )
        result = func(*args, **kwargs)
        logger.info("tool_call_end", tool=func.__name__, result_preview=result[:200] if result else "")
        return result

    return wrapper


def _get_video_content(bvid: str) -> str:
    """摘要优先 → 不可用则 Whisper 转录降级。"""
    if not bvid:
        return "错误：未提供 BV 号"

    summary = _try_ai_summary(bvid)
    if summary:
        return f"【AI 摘要】{summary}"

    logger.info("summary_unavailable_fallback_transcript", bvid=bvid)
    transcript = _try_whisper_transcript(bvid)
    if transcript:
        return f"【语音转录】（AI摘要不可用，已自动使用语音识别）\n{transcript}"

    logger.warning("video_content_all_failed", bvid=bvid)
    return f"无法获取视频 {bvid} 的内容：AI 摘要和语音转录均不可用。"


def _try_ai_summary(bvid: str) -> str:
    script = SCRIPTS_DIR / "bilibili_wbi.py"
    if not script.exists():
        return ""

    try:
        result = subprocess.run(
            ["python3", str(script), bvid, COOKIES_FILE],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            text = result.stdout.strip()
            if text and len(text) > 20:
                return text[:5000]
        return ""
    except subprocess.TimeoutExpired:
        logger.warning("ai_summary_timeout", bvid=bvid)
        return ""
    except Exception as e:
        logger.warning("ai_summary_error", bvid=bvid, error=str(e))
        return ""


def _try_whisper_transcript(bvid: str) -> str:
    global _last_transcribe_at, _transcript_cache

    with _transcribe_lock:
        if bvid in _transcript_cache:
            logger.info("transcript_cache_hit", bvid=bvid)
            return _transcript_cache[bvid]

        now = time.time()
        if _last_transcribe_at > 0 and now - _last_transcribe_at < TRANSCRIBE_COOLDOWN:
            remaining = int(TRANSCRIBE_COOLDOWN - (now - _last_transcribe_at))
            logger.info("transcribe_cooldown", bvid=bvid, remaining=remaining)
            return f"语音转录冷却中（{remaining}秒后可重试）。请稍后再问。"

        _last_transcribe_at = now

    try:
        from bilibili_bot.tools.transcribe import transcribe_video
        result = transcribe_video(bvid, WHISPER_MODEL, COOKIES_FILE)
    except ImportError:
        return "语音转录模块不可用"
    except Exception as e:
        logger.warning("whisper_transcript_error", bvid=bvid, error=str(e))
        return f"语音转录失败: {e}"

    if result:
        with _transcribe_lock:
            _transcript_cache[bvid] = result
            if len(_transcript_cache) > MAX_CACHE_SIZE:
                _transcript_cache.pop(next(iter(_transcript_cache)))

    return result


def _search_web(query: str) -> str:
    if not query:
        return "错误：未提供搜索关键词"
    try:
        from bilibili_bot.tools.web_search import web_search
        return web_search(query, daily_limit=30)
    except ImportError:
        return "搜索功能不可用"


def _get_content(content_type: str, content_id: str) -> str:
    """获取B站动态或专栏的完整内容。"""
    if not content_type or not content_id:
        return "错误：未提供内容类型或ID"

    if content_type == "dynamic":
        return _get_dynamic_content(content_id)
    elif content_type == "article":
        return _get_article_content(content_id)
    else:
        return f"不支持的内容类型: {content_type}，可选 dynamic/article"


def _get_dynamic_content(dynamic_id: str) -> str:
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/polymer/web-dynamic/v1/detail",
            params={"id": dynamic_id, "timezone_offset": -480},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            return f"获取动态失败: {data.get('message', '未知错误')}"

        item = (data.get("data", {}) or {}).get("item", {}) or {}
        modules = item.get("modules", {}) or {}

        if isinstance(modules, list):
            return _extract_opus_text_from_modules(modules)

        dyn = modules.get("module_dynamic", {}) or {}
        desc = dyn.get("desc", {}) or {}
        text = desc.get("text", "") or ""

        if not text and item.get("type") == "DYNAMIC_TYPE_FORWARD":
            orig = item.get("orig", {}) or {}
            om = orig.get("modules", {}) or {}
            om_dyn = om.get("module_dynamic", {}) or {}
            om_desc = om_dyn.get("desc", {}) or {}
            text = om_desc.get("text", "") or ""

        if not text:
            return "该动态没有文字内容"

        draw = dyn.get("major", {}) or {}
        draw_items = draw.get("draw", {}) or {}
        items_list = draw_items.get("items", []) or []
        img_count = len(items_list)

        result = text[:3000]
        if img_count:
            result += f"\n\n（该动态包含 {img_count} 张图片）"
        return result

    except Exception as e:
        return f"获取动态内容失败: {e}"


def _get_article_content(article_id: str) -> str:
    try:
        resp = requests.get(
            "https://api.bilibili.com/x/article/view",
            params={"id": article_id},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") != 0:
            return f"获取文章失败: {data.get('message', '未知错误')}"

        article = data.get("data", {}) or {}
        title = article.get("title", "")
        summary = article.get("summary", "")
        content = article.get("content", "")

        import re
        content_text = re.sub(r"<[^>]+>", "", content)[:3000] if content else ""

        parts = []
        if title:
            parts.append(f"标题：{title}")
        if summary:
            parts.append(f"摘要：{summary[:500]}")
        if content_text:
            parts.append(f"正文：{content_text}")

        img_urls = article.get("image_urls", []) or []
        if img_urls:
            parts.append(f"\n（该文章包含 {len(img_urls)} 张图片）")

        return "\n\n".join(parts) if parts else "该文章没有内容"

    except Exception as e:
        return f"获取文章内容失败: {e}"


def _extract_opus_text_from_modules(modules: list) -> str:
    for mod in modules:
        if mod.get("module_type") == "MODULE_TYPE_CONTENT":
            content = mod.get("module_content", {}) or {}
            paragraphs = content.get("paragraphs", []) or []
            parts = []
            for para in paragraphs:
                text_node = para.get("text", {}) or {}
                for node in text_node.get("nodes", []) or []:
                    word = node.get("word", {}) or {}
                    w = word.get("words", "")
                    if w:
                        parts.append(w)
            return "".join(parts)[:3000]
    return "该动态没有文字内容"


# ── PydanticAI Tool 定义 ──

def get_video_content(bvid: str) -> str:
    """获取B站视频的内容总结。先尝试AI摘要，不可用时自动降级为语音转录。
    当用户询问'这个视频讲了什么'、'视频内容'或需要了解视频时调用。
    """
    return _get_video_content(bvid)


def get_content(content_type: str, content_id: str) -> str:
    """获取B站动态或专栏的完整文字内容。当用户在动态/专栏评论区@bot，
    需要了解动态/文章具体内容时调用。
    content_type: 'dynamic' 或 'article'
    content_id: 动态ID或文章ID
    """
    return _get_content(content_type, content_id)


def search_web(query: str) -> str:
    """搜索互联网获取信息。当用户询问实时新闻、特定知识点、
    或需要查找资料时调用。返回搜索结果摘要。
    """
    return _search_web(query)


TOOLS = [
    Tool(_with_tool_logging(get_video_content)),
    Tool(_with_tool_logging(get_content)),
    Tool(_with_tool_logging(search_web)),
]
