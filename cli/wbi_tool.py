#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bilibili_bot.client import BilibiliSession
from bilibili_bot.wbi import enc_wbi


def get_video_ai_summary(bvid: str, cookies_file: str) -> dict:
    session = BilibiliSession(cookies_file)

    view_resp = session.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
    )
    view_resp.raise_for_status()
    view_data = view_resp.json()

    if view_data.get("code") != 0:
        return {"error": f"获取视频信息失败: {view_data.get('message')}"}

    aid = view_data["data"]["aid"]
    cid = view_data["data"]["cid"]
    up_mid = view_data["data"]["owner"]["mid"]

    params = {"bvid": bvid, "cid": cid, "up_mid": up_mid}
    signed_params = session.sign_wbi(params)

    summary_resp = session.get(
        "https://api.bilibili.com/x/web-interface/view/conclusion/get",
        params=signed_params,
    )
    summary_resp.raise_for_status()
    return summary_resp.json()


def main():
    parser = argparse.ArgumentParser(description="Bilibili WBI 工具")
    parser.add_argument("bvid", help="视频 BV 号")
    parser.add_argument("--cookies", default="config/bilibili-cookies.txt", help="Cookies 文件路径")
    args = parser.parse_args()

    result = get_video_ai_summary(args.bvid, args.cookies)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
