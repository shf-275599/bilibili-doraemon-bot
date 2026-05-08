"""联网搜索工具 —— Tavily Search（AI 原生搜索 API）。"""

from __future__ import annotations

import os
import requests


def web_search(query: str, num_results: int = 3) -> str:
    if not query.strip():
        return "错误：未提供搜索关键词"

    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return "搜索功能不可用：未配置 TAVILY_API_KEY"

    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
                "include_answer": False,
            },
            timeout=15,
        )
        data = resp.json()

        if resp.status_code != 200:
            err = data.get("detail", {}).get("error", str(data))
            return f"Tavily 搜索失败: {err}"

        results = data.get("results", [])
        if not results:
            return f"未找到与「{query}」相关的结果"

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "无标题")
            content = r.get("content", "")[:200]
            url = r.get("url", "")
            lines.append(f"{i}. {title}")
            lines.append(f"   {content}")
            if url:
                lines.append(f"   {url}")
        return "\n".join(lines)

    except Exception as e:
        return f"Tavily 搜索请求失败: {e}"
