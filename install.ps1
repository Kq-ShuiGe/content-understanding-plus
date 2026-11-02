# 一键部署脚本：下载 → 建 venv → 装依赖 → 生成配置
#
# 用法（PowerShell）：
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Target D:\cu-sidecar
#
# 或者不下载直接用：
#   irm https://gh-proxy.com/https://raw.githubusercontent.com/Kq-ShuiGe/content-understanding-plus/main/install.ps1 | iex

param(
    [string]$Target = "$env:USERPROFILE\cu-sidecar",
    [string]$Ref = "main"
)

$ErrorActionPreference = "Stop"
$repo = "Kq-ShuiGe/content-understanding-plus"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Test-Python {
    foreach ($cmd in @("python", "py")) {
        try {
            $v = & $cmd --version 2>&1
            if ($v -match "Python 3\.(1[0-9]|[89])") { return $cmd }
        } catch { }
    }
    return $null
}

Write-Step "检查 Python"
$python = Test-Python
if (-not $python) {
    Write-Host "没找到 Python 3.9+，先去 https://www.python.org/downloads/ 装一个，装的时候勾上 Add to PATH。" -ForegroundColor Red
    exit 1
}
Write-Host "用 $python"

Write-Step "下载仓库"
$tmp = Join-Path $env:TEMP "cu-plus-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
if ($Ref -eq "main") {
    $urls = @(
        "https://github.com/$repo/archive/refs/heads/main.zip",
        "https://gh-proxy.com/https://github.com/$repo/archive/refs/heads/main.zip",
        "https://ghproxy.net/https://github.com/$repo/archive/refs/heads/main.zip"
    )
} else {
    $urls = @(
        "https://github.com/$repo/archive/refs/tags/$Ref.zip",
        "https://gh-proxy.com/https://github.com/$repo/archive/refs/tags/$Ref.zip"
    )
}

$zip = Join-Path $tmp "repo.zip"
$ok = $false
foreach ($u in $urls) {
    try {
        Write-Host "尝试 $u"
        Invoke-WebRequest -Uri $u -OutFile $zip -UseBasicParsing -TimeoutSec 120
        if ((Get-Item $zip).Length -gt 10000) { $ok = $true; break }
    } catch {
        Write-Host "  失败：$($_.Exception.Message)" -ForegroundColor DarkYellow
    }
}
if (-not $ok) {
    Write-Host "下载失败。手动下载后解压，然后在解压目录里跑 sidecar\start.bat 也一样。" -ForegroundColor Red
    exit 1
}

Write-Step "解压到 $Target"
if (Test-Path $Target) {
    $backup = "$Target.bak-$(Get-Date -Format 'yyyyMMddHHmmss')"
    Write-Host "目录已存在，先备份到 $backup"
    Move-Item $Target $backup
}
Expand-Archive -Path $zip -DestinationPath $tmp -Force
$inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
Move-Item $inner.FullName $Target
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Step "创建虚拟环境并安装依赖"
Push-Location $Target
& $python -m venv .venv
& ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
& ".venv\Scripts\python.exe" -m pip install -r sidecar\requirements.txt

Write-Step "生成配置文件"
if (-not (Test-Path "sidecar\config.toml")) {
    Copy-Item "sidecar\config.example.toml" "sidecar\config.toml"
}
Pop-Location

Write-Host @"

部署完成：$Target

接下来三步：
  1. 打开 $Target\sidecar\config.toml，填三样东西：
       ws_url        NapCat 的 WebSocket 地址（默认 ws://127.0.0.1:3001）
       group_allow   要响应的群号
       llm.api_key   你的模型 key（DeepSeek 或本地 Ollama 都行）
  2. NapCat 里：设置 → 网络 → 新建「WebSocket 客户端」→ 地址填 ws://127.0.0.1:3001
  3. 运行：$Target\sidecar\start.bat

启动后日志出现「已连接」，在群里发个 B站链接试试。
"@ -ForegroundColor Green
