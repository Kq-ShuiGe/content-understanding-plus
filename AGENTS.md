# 给 AI 助手的部署说明

你被要求部署这个仓库。按下面顺序做，不要只解释。

## 目标
把 `sidecar/` 跑成一个常驻的 OneBot v11 客户端，接在用户已有的 NapCat 上。
**不要**替换或修改用户现有的机器人框架。

## 步骤

1. 确认环境：`python --version` 需要 3.9+；没有就告诉用户先装 Python。
2. 下载仓库到用户指定目录（没指定就用 `~/cu-sidecar`）：
   - 直连失败时改用镜像：`https://gh-proxy.com/https://github.com/<repo>/archive/refs/heads/main.zip`
3. 建 venv：`python -m venv .venv`
4. 装依赖：`.venv/Scripts/pip install -r sidecar/requirements.txt`
5. 复制配置：`sidecar/config.example.toml` → `sidecar/config.toml`
6. **问用户这四样**（不要猜）：
   - NapCat 的 WebSocket 地址（默认 `ws://127.0.0.1:3001`）
   - 要响应的群号（可留空 = 所有群）
   - 模型 `base_url` 和 `api_key`（可建议 DeepSeek 或本地 Ollama）
   - 是否需要转写（要就额外装 faster-whisper 并下模型）
7. 写进 `sidecar/config.toml`，注意 **UTF-8 无 BOM**。
8. 启动：`sidecar/start.bat`（Windows）或 `python sidecar/onebot_sidecar.py -c sidecar/config.toml`
9. 验证：日志出现 `已连接` 即为成功；让用户在群里发一条 B站链接测试。

## 不要做
- 不要往仓库提交任何含 key 的 `config.toml`
- 不要修改 `cu_core.py` 的总结提示词（那是调过的）
- 不要动用户现有的机器人配置
