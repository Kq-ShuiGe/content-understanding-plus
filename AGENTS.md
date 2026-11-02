# 给 AI 助手的部署说明

你被要求部署这个仓库。按下面顺序做，**不要只解释**。

## 目标

把 `sidecar/` 跑成一个常驻的 OneBot v11 客户端，接在用户已有的 NapCat / Lagrange 上。

**不要**替换或修改用户现有的机器人框架，也不要动它的配置文件。这个服务是并排跑的第二个客户端。

## 步骤

1. **确认环境**：`python --version` 需要 3.9 以上。没有就让用户先装 Python（安装时勾选 Add to PATH）。

2. **下载仓库**到用户指定目录；没说就用 `~/cu-sidecar`：

   ```
   https://github.com/Kq-ShuiGe/content-understanding-plus/archive/refs/heads/main.zip
   ```

   直连失败（`Connection reset` / 超时）就换镜像，依次尝试：

   ```
   https://gh-proxy.com/https://github.com/Kq-ShuiGe/content-understanding-plus/archive/refs/heads/main.zip
   https://ghproxy.net/https://github.com/Kq-ShuiGe/content-understanding-plus/archive/refs/heads/main.zip
   ```

   也可以在 PowerShell 里直接跑仓库自带的一键脚本：

   ```
   irm https://gh-proxy.com/https://raw.githubusercontent.com/Kq-ShuiGe/content-understanding-plus/main/install.ps1 | iex
   ```

3. **建虚拟环境**：`python -m venv .venv`

4. **装依赖**：
   - Windows：`.venv\Scripts\pip install -r sidecar\requirements.txt`
   - Linux/macOS：`.venv/bin/pip install -r sidecar/requirements.txt`

5. **生成配置**：复制 `sidecar/config.example.toml` 为 `sidecar/config.toml`。

6. **问用户这四样**（不要猜，不要用示例值占位）：

   | 要问的 | 说明 |
   |---|---|
   | NapCat 的 WebSocket 地址 | 默认 `ws://127.0.0.1:3001`。用户可能已经开过别的端口 |
   | 要响应的群号 | 可以留空（= 所有群），但建议先只加一个群测试 |
   | 模型的 `base_url` 和 `api_key` | 可建议 DeepSeek，或本地 Ollama（`http://127.0.0.1:11434/v1`，key 留空） |
   | 要不要开转写 | 要就额外 `pip install faster-whisper`，并下载模型（见下） |

7. **写入 `sidecar/config.toml`**，注意：
   - 必须是 **UTF-8 无 BOM**（带 BOM 会读不出来）
   - 填完可以用 `python -c "import tomllib;tomllib.load(open('sidecar/config.toml','rb'))"` 校验

8. **启动**：
   - Windows：`sidecar\start.bat`
   - 其它：`python sidecar/onebot_sidecar.py -c sidecar/config.toml`

9. **验证**：日志出现 `已连接` 就是接上了。然后让用户在群里发一条 B站链接，看机器人有没有回复。

## 可选：开转写

只有用户明确要「没字幕的视频也能总结」时才做：

```bash
pip install faster-whisper modelscope
modelscope download --model pengzhendong/faster-whisper-small --local_dir D:/models/faster-whisper-small
```

然后 `config.toml` 里：

```toml
enable_asr_fallback = true
whisper_model_dir = "D:/models/faster-whisper-small"
ffmpeg_path = ""        # 装了 ffmpeg 进 PATH 就留空
```

## 不要做

- 不要提交任何含 `api_key` / `sessdata` 的 `config.toml`（已在 `.gitignore` 里）
- 不要改 `cu_core.py` 里的总结提示词，那是调过的
- 不要动用户现有的机器人配置、不要重启用户的机器人框架
- 不要为了「看起来成功」而假装连上了——连不上就如实说，检查 ws_url 和 token

## 其它部署方式

用户如果用 MaiBot（麦麦），把 `maibot/` 复制到 `plugins/content_understanding_plus/` 再重启即可，详见 README。

用户如果用 NoneBot2，`pip install git+https://github.com/Kq-ShuiGe/content-understanding-plus`，详见 README。
