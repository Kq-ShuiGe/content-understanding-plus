@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist "sidecar\config.toml" (
    echo 还没有 config.toml，先复制 sidecar\config.example.toml 为 config.toml 再改配置。
    pause
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sidecar\onebot_sidecar.py -c sidecar\config.toml
) else (
    python sidecar\onebot_sidecar.py -c sidecar\config.toml
)
pause
