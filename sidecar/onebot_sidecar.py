"""OneBot v11 侧挂服务：给任何 QQ 机器人框架加「看 B站视频」的能力。

它不替换你的机器人，而是作为**另一路 WebSocket 客户端**接到 NapCat / Lagrange 上，
和现有框架并排跑：同一个 QQ 号，互不干扰。

    QQ ← NapCat ← WS → 本进程
                     → 现有框架（NoneBot/Koishi/LangBot/...）

用法：
    python sidecar/onebot_sidecar.py -c sidecar/config.toml

依赖：websockets、httpx、bilibili-api-python（转写可选 faster-whisper）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cu_core  # noqa: E402

try:
    import websockets
except ImportError:  # pragma: no cover
    print("缺少依赖：pip install websockets", file=sys.stderr)
    raise


class Sidecar:
    def __init__(self, cfg: dict, core: cu_core.CoreConfig):
        self.cfg = cfg
        self.core = core
        self.ws = None
        self._cooldown: dict[str, float] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---------- 连接 ----------

    async def run(self):
        url = self.cfg["onebot"]["ws_url"]
        token = self.cfg["onebot"].get("access_token", "")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        delay = 1
        while True:
            try:
                self.log(f"连接 {url} …")
                async with websockets.connect(url, additional_headers=headers, max_size=None) as ws:
                    self.ws = ws
                    self.log("已连接")
                    delay = 1
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                        except Exception:
                            continue
                        self.dispatch(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.log(f"连接断开（{exc}），{delay}s 后重连")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    def dispatch(self, event: dict):
        if event.get("post_type") != "message":
            return
        task = asyncio.create_task(self.on_message(event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    # ---------- 消息 ----------

    async def on_message(self, event: dict):
        msg_type = event.get("message_type")
        if msg_type == "group":
            group_id = str(event.get("group_id", ""))
            allowed = [str(x) for x in self.cfg["onebot"].get("group_allow", [])]
            if allowed and group_id not in allowed:
                return
        elif msg_type == "private":
            user_id = str(event.get("user_id", ""))
            allowed = [str(x) for x in self.cfg["onebot"].get("private_allow", [])]
            if allowed and user_id not in allowed:
                return
        else:
            return

        text = self.segments_to_text(event.get("message") or [])
        if not text or not cu_core.BV_PATTERN.search(text):
            return

        bvid = cu_core.find_bvid(text)
        if not bvid:
            return

        # 防刷：同一视频 60 秒内只处理一次
        now = time.time()
        if now - self._cooldown.get(bvid, 0) < 60:
            return
        self._cooldown[bvid] = now

        deep = bool(self.cfg["onebot"].get("deep_by_default", False))
        if bvid.lower() in text.lower() and "/cu_full" in text:
            deep = True
            cu_core.clear_cache(bvid)

        self.log(f"收到 {bvid}（deep={deep}）")
        asyncio.create_task(self.handle(event, bvid, deep))

    async def handle(self, event: dict, bvid: str, deep: bool):
        reply_to = event.get("message_id")
        try:
            if deep and self.cfg["onebot"].get("notify_when_deep", True):
                wait = "一分钟" if not self.core.enable_asr_fallback else "几分钟"
                await self.send(event, f"收到，我去看这条视频，大概要{wait}。", reply_to)

            info = await cu_core.fetch_video(bvid, self.core, deep=deep)
            if not info:
                await self.send(event, "这个视频我没打开，可能链接不对或者视频被删了。", reply_to)
                return

            text = cu_core.render_push(info)
            await self.send(event, text, reply_to if self.cfg["onebot"].get("quote_reply", True) else None)
        except Exception as exc:
            self.log(f"处理 {bvid} 失败：{exc}")
            try:
                await self.send(event, "刚才没看完，等下再发一次试试？", reply_to)
            except Exception:
                pass

    # ---------- OneBot API ----------

    async def call_api(self, action: str, params: dict) -> dict:
        if self.ws is None:
            return {}
        payload = {"action": action, "params": params, "echo": f"cu-{time.time()}"}
        await self.ws.send(json.dumps(payload, ensure_ascii=False))
        return {}

    async def send(self, event: dict, text: str, reply_to=None):
        message = []
        if reply_to:
            message.append({"type": "reply", "data": {"id": str(reply_to)}})
        message.append({"type": "text", "data": {"text": text}})

        if event.get("message_type") == "group":
            await self.call_api(
                "send_group_msg",
                {"group_id": event.get("group_id"), "message": message},
            )
        else:
            await self.call_api(
                "send_private_msg",
                {"user_id": event.get("user_id"), "message": message},
            )

    @staticmethod
    def segments_to_text(segments) -> str:
        parts = []
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            if seg.get("type") == "text":
                parts.append(str((seg.get("data") or {}).get("text") or ""))
        return "".join(parts)

    @staticmethod
    def log(msg: str):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config(path: Path) -> tuple[dict, cu_core.CoreConfig]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    onebot = data.get("onebot", {})
    parse = data.get("parse", {})
    llm = data.get("llm", {})
    cred = data.get("credential", {})

    core = cu_core.CoreConfig(
        sessdata=cred.get("sessdata", ""),
        bili_jct=cred.get("bili_jct", ""),
        buvid3=cred.get("buvid3", ""),
        dedeuserid=cred.get("dedeuserid", ""),
        enable_ai_summary=parse.get("enable_ai_summary", True),
        enable_subtitle_fallback=parse.get("enable_subtitle_fallback", True),
        enable_asr_fallback=parse.get("enable_asr_fallback", False),
        asr_model=parse.get("asr_model", "small"),
        ffmpeg_path=parse.get("ffmpeg_path", ""),
        whisper_model_dir=parse.get("whisper_model_dir", ""),
        asr_device=parse.get("asr_device", "cpu"),
        asr_compute_type=parse.get("asr_compute_type", "int8"),
        cache_ttl_seconds=int(parse.get("cache_ttl_seconds", 1800)),
        llm_base_url=llm.get("base_url", "https://api.deepseek.com/v1"),
        llm_api_key=llm.get("api_key", ""),
        llm_model=llm.get("model", "deepseek-chat"),
        llm_timeout=float(llm.get("timeout", 90)),
    )
    return {"onebot": onebot}, core


def main():
    ap = argparse.ArgumentParser(description="content-understanding OneBot 侧挂服务")
    ap.add_argument("-c", "--config", default="sidecar/config.toml", help="配置文件路径")
    args = ap.parse_args()

    path = Path(args.config)
    if not path.exists():
        print(f"找不到配置文件：{path}\n先复制 sidecar/config.example.toml 为 config.toml 再改。", file=sys.stderr)
        sys.exit(1)

    cfg, core = load_config(path)
    sidecar = Sidecar(cfg, core)
    try:
        asyncio.run(sidecar.run())
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    main()
