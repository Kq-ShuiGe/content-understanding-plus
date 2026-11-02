"""content-understanding 核心逻辑：不依赖任何 QQ 机器人框架。

只做四件事：
  1. 从文本里认出 B站视频号（BV 号）
  2. 取视频信息、官方 AI 总结、CC 字幕
  3. 没字幕就本地转写（faster-whisper，可选）
  4. 把文本交给任意 OpenAI 兼容模型，写成人话总结

所有适配层（MaiBot 插件 / OneBot 侧挂 / NoneBot 插件）都只是这层的壳。
"""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import httpx

BV_PATTERN = re.compile(r"\b(BV[0-9A-Za-z]{10})\b")
AV_PATTERN = re.compile(r"\bav(\d{1,12})\b", re.IGNORECASE)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


# ============ 配置 ============


@dataclass
class CoreConfig:
    """核心逻辑需要的全部配置。适配层从自己的配置文件里填进来即可。"""

    # B站登录态（不填也能用：只有标题/UP/简介，没有 AI 总结和字幕）
    sessdata: str = ""
    bili_jct: str = ""
    buvid3: str = ""
    dedeuserid: str = ""

    # 内容来源开关
    enable_ai_summary: bool = True
    enable_subtitle_fallback: bool = True
    enable_asr_fallback: bool = False

    # 转写参数
    asr_model: str = "small"
    ffmpeg_path: str = ""
    whisper_model_dir: str = ""
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"

    # 缓存
    cache_ttl_seconds: int = 1800

    # 模型（任何 OpenAI 兼容接口：DeepSeek / Ollama / LM Studio / 中转）
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 90.0

    def has_credential(self) -> bool:
        return bool(self.sessdata)


# ============ 小工具 ============


def find_bvid(text: str) -> Optional[str]:
    """从一段话里找出第一个 BV 号。"""
    if not text:
        return None
    m = BV_PATTERN.search(text)
    return m.group(1) if m else None


def find_av(text: str) -> Optional[int]:
    if not text:
        return None
    m = AV_PATTERN.search(text)
    return int(m.group(1)) if m else None


def format_duration(seconds: Any) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return "未知"
    return f"{s // 60}:{s % 60:02d}"


def clean_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def find_ffmpeg(explicit: str = "") -> str:
    """配置 > 环境变量 CU_FFMPEG > PATH > 常见位置。"""
    import os
    import shutil

    if explicit and os.path.exists(explicit):
        return explicit
    env = os.environ.get("CU_FFMPEG") or ""
    if env and os.path.exists(env):
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    for cand in (r"C:\ffmpeg\bin\ffmpeg.exe", r"D:\ffmpeg\bin\ffmpeg.exe", "/usr/bin/ffmpeg"):
        if os.path.exists(cand):
            return cand
    return ""


def _credential(cfg: CoreConfig):
    from bilibili_api import Credential

    if not cfg.has_credential():
        return None
    return Credential(
        sessdata=cfg.sessdata or None,
        bili_jct=cfg.bili_jct or None,
        buvid3=cfg.buvid3 or None,
        dedeuserid=cfg.dedeuserid or None,
    )


def _extract_ai_summary(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    result = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(result, dict):
        return ""
    model_result = result.get("model_result") or {}
    summary = model_result.get("summary") if isinstance(model_result, dict) else ""
    return str(summary or "").strip()


# ============ 内容获取 ============


async def grab_subtitle(video: Any, cid: Any, client: httpx.AsyncClient) -> str:
    """抓 CC 字幕全文。纯歌词（♪ 太多）直接丢弃。"""
    try:
        data = await video.get_subtitle(cid=cid)
    except Exception:
        return ""
    subs = (data or {}).get("subtitles") or []
    if not subs:
        return ""
    url = ""
    for item in subs:
        u = str(item.get("subtitle_url") or "")
        if u:
            url = u
            if str(item.get("lan", "")).startswith("ai-zh"):
                break
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    try:
        resp = await client.get(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
        payload = resp.json()
    except Exception:
        return ""
    body = payload.get("body") or []
    parts = [str(x.get("content") or "").strip() for x in body if isinstance(x, dict)]
    text = "".join(p for p in parts if p).strip()
    if text and text.count("♪") > max(6, len(text) * 0.03):
        return ""
    return text


async def transcribe(video: Any, cid: Any, cfg: CoreConfig) -> str:
    """下载最低码率音频轨 → ffmpeg 转 PCM → faster-whisper 转写。失败返回空串。"""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return ""

    model_src: Any = cfg.asr_model
    if cfg.whisper_model_dir:
        p = Path(cfg.whisper_model_dir)
        if (p / "model.bin").exists():
            model_src = str(p)
    else:
        for cand in (
            Path.cwd() / f"faster-whisper-{cfg.asr_model}",
            Path.home() / ".cache" / f"faster-whisper-{cfg.asr_model}",
        ):
            if (cand / "model.bin").exists():
                model_src = str(cand)
                break

    try:
        download = await video.get_download_url(cid=cid)
    except Exception:
        return ""

    dash = (download or {}).get("dash") or {}
    audios = dash.get("audio") or []
    url = ""
    if audios:
        chosen = sorted(audios, key=lambda a: int(a.get("bandwidth") or 0))[0]
        url = str(chosen.get("baseUrl") or chosen.get("base_url") or "")
    if not url:
        durl = (download or {}).get("durl") or []
        if durl:
            url = str(durl[0].get("url") or "")
    if not url:
        return ""

    tmp = Path(tempfile.gettempdir()) / "cu_audio.m4a"
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            resp = await c.get(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
            tmp.write_bytes(resp.content)
    except Exception:
        return ""

    ff = find_ffmpeg(cfg.ffmpeg_path)

    def _run() -> str:
        try:
            import subprocess

            import numpy as np

            raw = tmp.with_suffix(".raw")
            if ff:
                subprocess.run(
                    [ff, "-y", "-loglevel", "error", "-i", str(tmp),
                     "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", str(raw)],
                    check=True, timeout=180,
                    creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                audio = np.fromfile(str(raw), dtype=np.int16).astype(np.float32) / 32768.0
            else:
                audio = str(tmp)

            model = WhisperModel(
                model_src, device=cfg.asr_device or "cpu", compute_type=cfg.asr_compute_type or "int8"
            )
            segments, _info = model.transcribe(audio, language="zh", vad_filter=True, beam_size=1)
            return "".join(s.text for s in segments).strip()
        except Exception:
            return ""

    try:
        return await asyncio.to_thread(_run)
    except Exception:
        return ""
    finally:
        for leftover in (tmp, tmp.with_suffix(".raw")):
            try:
                if leftover.exists():
                    leftover.unlink()
            except Exception:
                pass


async def summarize(text: str, hint: str, cfg: CoreConfig) -> str:
    """把长文本写成人话总结（200–350 字）。"""
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) > 12000:
        text = text[:12000]

    prompt = (
        f"下面是一个B站视频的{hint}。假设你刚看完，现在用聊天口吻跟朋友说说它讲了什么。\n"
        "要求：\n"
        "1. 像人说话，口语化，可以用「其实」「说白了」「有意思的是」这种自然连接；\n"
        "2. 不要分点、不要列表、不要小标题、不要「首先/其次/综上」这类书面语；\n"
        "3. 开头一句话点明主题，然后顺着往下讲：讲了什么、怎么论证的、结论或最有意思的地方；\n"
        "4. 200-350 字，不要复述原文，不要评价视频好坏，不要说「这个视频」四个字开头。\n\n"
        f"{text}"
    )
    if not cfg.llm_api_key and "localhost" not in cfg.llm_base_url and "127.0.0.1" not in cfg.llm_base_url:
        return ""

    headers = {"Content-Type": "application/json"}
    if cfg.llm_api_key:
        headers["Authorization"] = f"Bearer {cfg.llm_api_key}"
    payload = {
        "model": cfg.llm_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 900,
        "temperature": 0.7,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=cfg.llm_timeout) as c:
            r = await c.post(f"{cfg.llm_base_url.rstrip('/')}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        return clean_html_tags(str(content))
    except Exception:
        return ""


# ============ 主流程 ============


_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


async def fetch_video(bvid: str, cfg: CoreConfig, deep: bool = True) -> Optional[dict[str, Any]]:
    """取视频信息 + 总结。

    deep=False：只用官方 AI 总结 / 字幕节选，快（3–5 秒内）
    deep=True ：字幕或转写交给模型总结（可能几十秒到几分钟）
    """
    from bilibili_api.video import Video

    cache_key = f"{bvid}:{'deep' if deep else 'fast'}"
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    cred = _credential(cfg)
    video = Video(bvid=bvid, credential=cred)
    try:
        info = await video.get_info()
    except Exception:
        return None

    stat = info.get("stat") or {}
    result: dict[str, Any] = {
        "bvid": info.get("bvid", bvid),
        "title": info.get("title", ""),
        "up": (info.get("owner") or {}).get("name", "未知UP"),
        "duration": info.get("duration", 0),
        "view": stat.get("view", 0),
        "like": stat.get("like", 0),
        "desc": (info.get("desc") or "")[:200],
        "ai_summary": "",
        "summary_source": "",
    }

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        if cfg.enable_ai_summary and cred is not None:
            try:
                data = await asyncio.wait_for(video.get_ai_conclusion(cid=info.get("cid")), timeout=4.0)
                result["ai_summary"] = _extract_ai_summary(data)
            except Exception:
                pass

            if not result["ai_summary"] and cfg.enable_subtitle_fallback:
                subtitle = await grab_subtitle(video, info.get("cid"), client)
                if subtitle:
                    if deep:
                        summary = await summarize(subtitle, "字幕全文", cfg)
                        if summary:
                            result["subtitle_summary"] = summary
                            result["summary_source"] = "字幕"
                    if not result.get("subtitle_summary"):
                        excerpt = subtitle[:2000]
                        if len(subtitle) > 2000:
                            excerpt += f"……（后略，字幕共 {len(subtitle)} 字）"
                        result["subtitle_excerpt"] = excerpt
                        result["summary_source"] = result["summary_source"] or "字幕节选"

            if (
                deep
                and not result.get("subtitle_summary")
                and not result.get("ai_summary")
                and cfg.enable_asr_fallback
            ):
                transcript = await transcribe(video, info.get("cid"), cfg)
                if transcript:
                    summary = await summarize(transcript, "语音转写全文", cfg)
                    if summary:
                        result["subtitle_summary"] = summary
                        result["summary_source"] = "语音转写"

    if result.get("ai_summary") or result.get("subtitle_summary") or result.get("subtitle_excerpt"):
        if len(_CACHE) > 200:
            _CACHE.clear()
        _CACHE[cache_key] = (now + cfg.cache_ttl_seconds, result)
    return result


def clear_cache(bvid: str = "") -> None:
    """清缓存：给了 bvid 只清它，否则全清。"""
    if not bvid:
        _CACHE.clear()
        return
    for key in [k for k in _CACHE if k.startswith(bvid)]:
        _CACHE.pop(key, None)


def render_context(info: dict[str, Any]) -> str:
    """拼成给模型看的上下文块（MaiBot 插件就是把这句塞进用户消息）。"""
    lines = [
        f"[B站视频信息: 《{info.get('title', '')}》 | UP: {info.get('up', '未知UP')} "
        f"| 时长: {format_duration(info.get('duration'))}]"
    ]
    if (info.get("ai_summary") or "").strip():
        lines.append(f"[B站官方AI总结]: {info['ai_summary'].strip()}")
    elif (info.get("subtitle_summary") or "").strip():
        src = info.get("summary_source") or "字幕"
        lines.append(f"[视频内容总结（来自{src}）]: {info['subtitle_summary'].strip()}")
    elif (info.get("subtitle_excerpt") or "").strip():
        lines.append(f"[视频字幕节选]: {info['subtitle_excerpt'].strip()}")
    elif info.get("desc"):
        lines.append(f"[视频简介]: {info['desc'].strip()}")
    return "\n".join(lines)


def render_push(info: dict[str, Any]) -> str:
    """拼成直接发给用户的那条消息。"""
    title = (info.get("title") or "").strip()
    up = (info.get("up") or "").strip()
    duration = format_duration(info.get("duration"))
    body = (
        (info.get("ai_summary") or "").strip()
        or (info.get("subtitle_summary") or "").strip()
        or (info.get("subtitle_excerpt") or "").strip()
        or (info.get("desc") or "").strip()
    )
    head = f"《{title}》"
    if up or duration:
        head += f"\n{up} · {duration}".rstrip(" ·")
    parts = [head]
    if body:
        parts.append(body)
    parts.append(f"https://www.bilibili.com/video/{info.get('bvid', '')}")
    return "\n\n".join(p for p in parts if p)
