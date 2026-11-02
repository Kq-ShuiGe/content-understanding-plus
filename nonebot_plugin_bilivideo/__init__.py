"""NoneBot2 插件：看到 B站链接就看一遍视频再说话。

安装：
    pip install git+https://github.com/Kq-ShuiGe/content-understanding-plus
    # 或把本目录整个放进你的 nonebot plugins 目录

配置（.env 或 .env.prod）：

    BILIVIDEO_LLM_BASE_URL=https://api.deepseek.com/v1
    BILIVIDEO_LLM_API_KEY=sk-xxxx
    BILIVIDEO_LLM_MODEL=deepseek-chat
    BILIVIDEO_DEEP_BY_DEFAULT=true
    BILIVIDEO_SESSDATA=            # 可选，填了才有官方 AI 总结和字幕
"""

from __future__ import annotations

import asyncio

from nonebot import get_plugin_config, logger, on_message
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot.rule import Rule
from pydantic import BaseModel

import cu_core

__plugin_meta__ = PluginMetadata(
    name="B站视频内容理解",
    description="发 B站链接，自动看视频并给出自然语言总结（官方总结 → 字幕 → 本地转写）",
    usage="直接发链接；深度解析用 /cu_full <链接>",
    type="application",
    config=BaseModel,
    supported_adapters={"~onebot.v11"},
)


class Config(BaseModel):
    bilivideo_llm_base_url: str = "https://api.deepseek.com/v1"
    bilivideo_llm_api_key: str = ""
    bilivideo_llm_model: str = "deepseek-chat"
    bilivideo_llm_timeout: float = 90.0

    bilivideo_sessdata: str = ""
    bilivideo_bili_jct: str = ""
    bilivideo_buvid3: str = ""
    bilivideo_dedeuserid: str = ""

    bilivideo_enable_ai_summary: bool = True
    bilivideo_enable_subtitle_fallback: bool = True
    bilivideo_enable_asr_fallback: bool = False
    bilivideo_cache_ttl: int = 1800

    bilivideo_asr_model: str = "small"
    bilivideo_ffmpeg_path: str = ""
    bilivideo_whisper_model_dir: str = ""
    bilivideo_asr_device: str = "cpu"
    bilivideo_asr_compute_type: str = "int8"

    bilivideo_deep_by_default: bool = True
    bilivideo_group_allow: list[int] = []
    bilivideo_at_only: bool = False


plugin_config = get_plugin_config(Config)

CORE = cu_core.CoreConfig(
    sessdata=plugin_config.bilivideo_sessdata,
    bili_jct=plugin_config.bilivideo_bili_jct,
    buvid3=plugin_config.bilivideo_buvid3,
    dedeuserid=plugin_config.bilivideo_dedeuserid,
    enable_ai_summary=plugin_config.bilivideo_enable_ai_summary,
    enable_subtitle_fallback=plugin_config.bilivideo_enable_subtitle_fallback,
    enable_asr_fallback=plugin_config.bilivideo_enable_asr_fallback,
    asr_model=plugin_config.bilivideo_asr_model,
    ffmpeg_path=plugin_config.bilivideo_ffmpeg_path,
    whisper_model_dir=plugin_config.bilivideo_whisper_model_dir,
    asr_device=plugin_config.bilivideo_asr_device,
    asr_compute_type=plugin_config.bilivideo_asr_compute_type,
    cache_ttl_seconds=plugin_config.bilivideo_cache_ttl,
    llm_base_url=plugin_config.bilivideo_llm_base_url,
    llm_api_key=plugin_config.bilivideo_llm_api_key,
    llm_model=plugin_config.bilivideo_llm_model,
    llm_timeout=plugin_config.bilivideo_llm_timeout,
)


def _text_of(event: Event) -> str:
    try:
        return event.get_plaintext()  # type: ignore[attr-defined]
    except Exception:
        return ""


async def _wants_video(event: Event) -> bool:
    text = _text_of(event)
    if not cu_core.BV_PATTERN.search(text):
        return False
    if plugin_config.bilivideo_group_allow:
        gid = getattr(event, "group_id", None)
        if gid is not None and gid not in plugin_config.bilivideo_group_allow:
            return False
    return True


matcher = on_message(rule=Rule(_wants_video), priority=10, block=False)


@matcher.handle()
async def _(bot: Bot, event: MessageEvent):
    text = _text_of(event)
    bvid = cu_core.find_bvid(text)
    if not bvid:
        return

    deep = plugin_config.bilivideo_deep_by_default or "/cu_full" in text
    if "/cu_full" in text:
        cu_core.clear_cache(bvid)
        await matcher.send("收到，我去看这条视频，稍等。")

    try:
        info = await cu_core.fetch_video(bvid, CORE, deep=deep)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"处理 {bvid} 失败：{exc}")
        return

    if not info:
        await matcher.send("这个视频我没打开，可能链接不对或者视频被删了。")
        return

    push = cu_core.render_push(info)
    await bot.send(event, MessageSegment.text(push))
