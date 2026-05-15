"""Bilibili 视频 Whisper 语音转录 —— 使用 Systran faster-whisper-base 模型。"""

from __future__ import annotations

import subprocess
import os
import time
import glob

import structlog

logger = structlog.get_logger()

_MODEL = None
AUDIO_DIR = "/home/shf/bilibili-bot/audio"


def transcribe_video(bvid: str, model_path: str, cookies_file: str) -> str:
    """下载视频音频并用 Whisper 转录为文本。

    返回转录文本，失败返回空字符串。
    """
    global _MODEL

    os.makedirs(AUDIO_DIR, exist_ok=True)
    _cleanup_old_audio()

    url = f"https://www.bilibili.com/video/{bvid}"
    audio_path = os.path.join(AUDIO_DIR, f"{bvid}.wav")

    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
        logger.info("transcribe_cache_hit", bvid=bvid)
    else:
        try:
            _download_audio(url, audio_path, cookies_file, max_retries=2)
        except Exception as e:
            logger.warning("transcribe_download_failed", bvid=bvid, error=str(e))
            return ""

    file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
    if file_size < 1000:
        logger.warning("transcribe_audio_too_small", bvid=bvid, size=file_size)
        return ""

    try:
        if _MODEL is None:
            logger.info("whisper_model_loading", path=model_path)
            from faster_whisper import WhisperModel
            _MODEL = WhisperModel(model_path, device="cpu", compute_type="int8")
            logger.info("whisper_model_loaded")

        segments, _info = _MODEL.transcribe(audio_path, beam_size=5, language="zh")
        texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        transcript = " ".join(texts)

        if not transcript:
            logger.warning("transcribe_empty_result", bvid=bvid)
            return ""

        logger.info("transcribe_done", bvid=bvid, chars=len(transcript))
        _safe_remove(audio_path)
        return transcript[:8000]

    except Exception as e:
        logger.warning("transcribe_error", bvid=bvid, error=str(e))
        global _MODEL
        _MODEL = None
        return ""


def _download_audio(url: str, output: str, cookies_file: str, max_retries: int = 3) -> None:
    cmd = [
        "yt-dlp",
        "--cookies", cookies_file,
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--output", output,
        "--no-playlist",
        url,
    ]

    last_error = ""
    for attempt in range(max_retries):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if result.returncode == 0:
            return
        last_error = f"yt-dlp 失败 (code={result.returncode})"
        logger.warning(
            "yt-dlp_retry",
            attempt=attempt + 1,
            max_retries=max_retries,
            error=last_error,
            stderr=result.stderr[-500:] if result.stderr else "",
        )
        if attempt < max_retries - 1:
            time.sleep(5)

    raise RuntimeError(last_error)


def _cleanup_old_audio(max_age_hours: int = 1) -> None:
    cutoff = time.time() - max_age_hours * 3600
    for f in glob.glob(os.path.join(AUDIO_DIR, "*.wav")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
        except OSError:
            pass


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
