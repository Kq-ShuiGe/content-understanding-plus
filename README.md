# 让 QQ 机器人真的「看」B站视频

发个链接过去，它不是甩你一句标题，而是**看完再跟你说讲了什么**。

先要官方 AI 总结；没有就抓 CC 字幕让模型总结；字幕也没有，就本地把音频转写下来再总结。三路兜底，输出的是人话，不是「首先其次综上」。

支持 **MaiBot（麦麦）**、**任意 OneBot v11 框架**（NoneBot2 / Koishi / LangBot / AstrBot…）、**NoneBot2 插件**。

---

## 复制到仓库简介（About）

**一句话版：**

> B站视频内容理解：官方AI总结 → CC字幕 → 本地转写，三路兜底，输出人话总结。MaiBot / OneBot / NoneBot2 通用。

**标准版：**

> 让 QQ 机器人真的看懂 B站视频。收到链接后依次尝试：B站官方 AI 总结 → 抓 CC 字幕让模型总结 → 本地 faster-whisper 转写后再总结。三路兜底，输出口语化总结而不是流水账。提供三种接入：MaiBot 插件、OneBot v11 侧挂服务（任何框架可用，不替换你的机器人）、NoneBot2 插件。附 DSH 一键部署脚本。

**Topics：** `bilibili` `qqbot` `maibot` `nonebot` `onebot` `napcat` `whisper` `llm`

---

## 和其他方案的区别

| | 原版插件 | 本仓库 |
|---|---|---|
| 官方 AI 总结 | ✅ | ✅ |
| 没有总结时的字幕兜底 | ❌ | ✅ |
| 没有字幕时的本地转写 | ❌ | ✅ |
| 自然语言总结（能直接接话） | ❌ | ✅ |
| 空结果不写缓存 | ❌ | ✅ |
| 换框架可用 | ❌ | ✅（OneBot 侧挂 / NoneBot 插件） |

插件**不会**往 B站发评论、不会点赞投币。所有请求只去 B站/抖音自己的接口，以及你自己配的模型服务。

---

## 一图流

```
消息里有 B站链接
   ↓
① 拿视频信息（标题 / UP / 时长 / 简介）
   ↓
② 有官方 AI 总结？ ──有──→ 直接用
   ↓ 没有
③ 有 CC 字幕？ ──有──→ 抓下来（♪ 太多判为歌词，丢弃）
   ↓ 没有
④ 开了转写？ ──是──→ 取最低码率音频 → ffmpeg 转 PCM → faster-whisper
   ↓
⑤ 交给模型：口语化、不分点、200–350 字
   ↓
⑥ 发给用户 / 拼进上下文
```

---

# 三种装法

## 方式一：MaiBot（麦麦）插件

适合已经跑着麦麦的人。

```text
把 maibot/ 整个文件夹复制到 MaiBot/plugins/content_understanding_plus/
重启 MaiBot
```

然后私聊机器人发 `/cu_login` 扫码（想用官方总结和字幕就必须登录）。

配置在 `maibot/config.toml`，**模型走麦麦自己的配置**（`task_name="utils"`），不用额外填 key。

> ⚠️ 插件 id 与原版相同（`YukiSakiko.content_understanding_plugin`），不能和原版共存，升级直接覆盖文件夹。

## 方式二：OneBot v11 侧挂服务（任何框架都能用）

**推荐给不折腾插件的人。** 它不替换你的机器人，而是作为**另一路 WebSocket 客户端**接到 NapCat 上，和现有框架并排跑：

```
QQ ← NapCat ←─ WS ─→ cu-sidecar        ← 这个仓库
              └─ WS ─→ 你原有的框架
```

同一个 QQ 号，不用小号，也不用改你现有代码。

### 1. 拿代码

```powershell
# Windows 一键
irm https://gh-proxy.com/https://raw.githubusercontent.com/Kq-ShuiGe/content-understanding-plus/main/install.ps1 | iex
```

或者手动：

```bash
git clone https://github.com/Kq-ShuiGe/content-understanding-plus
cd content-understanding-plus
python -m venv .venv
.venv\Scripts\pip install -r sidecar/requirements.txt
copy sidecar\config.example.toml sidecar\config.toml
```

### 2. NapCat 里开一路 WebSocket

设置 → 网络 → 新建 **WebSocket 客户端**：

| 项 | 值 |
|---|---|
| 地址 | `ws://127.0.0.1:3001` |
| Token | 留空或自己设一个（要和 config.toml 一致） |
| 心跳 | 30 秒 |

已经有别的 WS 客户端也没关系，多开一路就行。

### 3. 改配置

打开 `sidecar/config.toml`，最少改这四行：

```toml
ws_url = "ws://127.0.0.1:3001"      # 上一步填的地址
group_allow = ["你的群号"]           # 留空 = 所有群
llm.base_url = "https://api.deepseek.com/v1"
llm.api_key = "sk-你的key"
```

用本地 Ollama 的话：

```toml
llm.base_url = "http://127.0.0.1:11434/v1"
llm.api_key = ""
llm.model = "qwen2.5:7b"
```

### 4. 跑起来

```powershell
sidecar\start.bat
```

看到 `已连接` 就成了。在群里发个 B站链接试试。

## 方式三：NoneBot2 插件

```bash
pip install git+https://github.com/Kq-ShuiGe/content-understanding-plus
nb plugin install nonebot_plugin_bilivideo   # 或者把目录放进 plugins/
```

`.env` 里配置：

```dotenv
BILIVIDEO_LLM_BASE_URL=https://api.deepseek.com/v1
BILIVIDEO_LLM_API_KEY=sk-xxxx
BILIVIDEO_LLM_MODEL=deepseek-chat
BILIVIDEO_GROUP_ALLOW=[123456789]
BILIVIDEO_DEEP_BY_DEFAULT=true
# 可选
BILIVIDEO_SESSDATA=
BILIVIDEO_ENABLE_ASR_FALLBACK=false
```

---

# 配置说明

## A. MaiBot 插件（`maibot/config.toml`）

| 键 | 默认 | 说明 |
|---|---|---|
| `enable_ai_summary` | `true` | 用 B站官方 AI 总结 |
| `enable_subtitle_fallback` | `true` | 没总结就抓 CC 字幕 |
| `enable_asr_fallback` | `false` | 没字幕就本地转写 |
| `asr_model` | `small` | tiny / base / small / medium |
| `ffmpeg_path` | `""` | 留空自动找 PATH |
| `whisper_model_dir` | `""` | 留空按模型名自动下载 |
| `asr_device` | `cpu` | 有 N 卡改 `cuda` 快十倍 |
| `asr_compute_type` | `int8` | cuda 配 `float16` |
| `cache_ttl_seconds` | `1800` | 同一视频缓存多久 |
| `enable_douyin` | `false` | 抖音支持 |

## B. 侧挂服务（`sidecar/config.toml`）

| 段 | 键 | 说明 |
|---|---|---|
| `[onebot]` | `ws_url` | NapCat 的 WS 地址 |
| | `access_token` | 和 NapCat 里填的一致 |
| | `group_allow` | 响应的群号，空 = 全部 |
| | `private_allow` | 响应的好友，空 = 全部 |
| | `deep_by_default` | 默认就做深度总结 |
| | `notify_when_deep` | 先回一句「我去看看」 |
| `[parse]` | `enable_ai_summary` / `enable_subtitle_fallback` / `enable_asr_fallback` | 三路开关 |
| | `asr_*` / `ffmpeg_path` / `whisper_model_dir` | 转写参数 |
| `[llm]` | `base_url` / `api_key` / `model` | 任何 OpenAI 兼容接口 |
| `[credential]` | `sessdata` 等 | 可选，填了才有官方总结和字幕 |

## C. 转写怎么跑起来（可选）

只有开 `enable_asr_fallback` 才需要：

```bash
pip install faster-whisper
# 国内建议从魔搭下模型
pip install modelscope
modelscope download --model pengzhendong/faster-whisper-small --local_dir D:/models/faster-whisper-small
```

```toml
whisper_model_dir = "D:/models/faster-whisper-small"
```

还要 ffmpeg（要么进 PATH，要么填 `ffmpeg_path`）。

CPU 上 `small` 大概是**视频时长的 0.3–0.5 倍**：10 分钟视频要转 3–5 分钟。所以别默认开，遇到没字幕的再单独处理。

---

# 用 DSH 一键部署

如果你在用 [DSH](https://deepseek.com)（DeepSeek Harness），把下面这段**整段丢给 DSH** 就行：

```text
帮我部署 content-understanding-plus 的 OneBot 侧挂服务：
1. 从 https://github.com/Kq-ShuiGe/content-understanding-plus 下载到 D:\cu-sidecar
2. 建 venv 并安装 sidecar/requirements.txt
3. 把 sidecar/config.example.toml 复制成 config.toml
4. 问我 NapCat 的 WebSocket 地址、要响应的群号、模型的 base_url 和 key，填进去
5. 后台启动 sidecar\start.bat，确认日志出现「已连接」
```

不想碰 DSH 也行，直接跑脚本：

```powershell
irm https://gh-proxy.com/https://raw.githubusercontent.com/Kq-ShuiGe/content-understanding-plus/main/install.ps1 | iex
```

脚本会检查 Python、下载、建 venv、装依赖、生成配置，最后告诉你还差哪三样要填。

---

# 命令

| 命令 | 适用 | 作用 |
|---|---|---|
| 直接发链接 | 全部 | 自动处理 |
| `/cu_full <链接>` | 全部 | 深度解析（会先清缓存，转写也在这里走） |
| `/cu_login` | MaiBot | 扫码登录 B站 |
| `/cu_status` | MaiBot | 看登录状态与配置 |
| `/cu_logout` | MaiBot | 退出登录 |

侧挂服务没有登录命令，凭证直接写在 `[credential]` 里。

---

# 常见问题

**Q：机器人完全不回复**
侧挂服务：先看它日志有没有 `已连接`；没有就是 WS 地址/token 不对。再看 `group_allow` 里有没有这个群。
MaiBot：看插件有没有加载成功。

**Q：只有标题，没有总结**
三种可能：没登录 B站（拿不到官方总结和字幕）、这视频既没总结也没字幕、转写没开或找不到 ffmpeg。

**Q：回复很慢**
深度模式本来就要等：字幕总结 3–10 秒，转写可能要几分钟。侧挂服务默认会先回一句「我去看看」。

**Q：同一个视频再发还是老结果**
缓存内会命中，`cache_ttl_seconds` 控制。想强制重来发 `/cu_full`。

**Q：转写报 `metadata_errors`**
`av` 19 和 `faster-whisper` 冲突。本仓库不用 `av`，只走 ffmpeg；`pip uninstall av` 后重装即可。

**Q：MaiBot 日志报 `[E_CAPABILITY_DENIED] 未获授权能力: llm.generate`**
`maibot/_manifest.json` 的 `capabilities` 必须含 `llm.generate`，改完要**重启** MaiBot。

**Q：配置读取失败 `Invalid statement (at line 1, column 1)`**
`config.toml` 带了 UTF-8 BOM。用编辑器另存为「UTF-8 无 BOM」。

**Q：会不会把视频发到别处**
不会。只请求 B站/抖音接口和你自己配的模型地址；转写全程在本机。

---

# 目录结构

```
content-understanding-plus/
├── cu_core.py                     # 核心逻辑，零框架依赖
├── maibot/                        # 方式一：MaiBot 插件
│   ├── _manifest.json
│   ├── plugin.py
│   └── config.toml
├── sidecar/                       # 方式二：OneBot v11 侧挂
│   ├── onebot_sidecar.py
│   ├── config.example.toml
│   └── start.bat
├── nonebot_plugin_bilivideo/      # 方式三：NoneBot2 插件
├── install.ps1                    # Windows 一键部署
└── pyproject.toml
```

想加别的框架？照着 `sidecar/` 抄一个壳，调 `cu_core.fetch_video()` 和 `cu_core.render_push()` 就行。

---

# 致谢

- 原版插件：[YukiSakiko/content_understanding_plugin](https://github.com/YukiSakiko)（MIT）
- 转写：[faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- B站接口：[bilibili-api-python](https://github.com/Nemo2011/bilibili-api)

# 协议

MIT，见 [LICENSE](LICENSE)。
