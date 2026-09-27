# 一键起「bridge + 前端」。
#
#   .\scripts\run.ps1                 # 需要时构建前端，然后起服务
#   .\scripts\run.ps1 -Rebuild        # 强制重新构建前端
#   .\scripts\run.ps1 -SkipBuild      # 只起后端（前端没构建过就只挂 /api）
#   .\scripts\run.ps1 -Port 8080
#   .\scripts\run.ps1 -AllowBundled   # ★ 显式允许用仓库自带的 backend/ 副本
#
# 打开 http://127.0.0.1:<Port>/app
#
# ★ **不设 AGENT_BACKEND_DIR 会被拒绝启动**（架构清单 A2b）。
#   判据是"解析到的后端是不是仓库自带的 bundled 副本"，判**形态**不判**状态**：
#   "副本此刻恰好同步"会过期，而这条规则要防的是"以为在跑上游、其实在跑副本"。
#   确实要用副本时加 `-AllowBundled`（等价于 `AGENT_ALLOW_BUNDLED=1`），
#   但该事实会写进 `/api/health` 的 `backend_bundled_override` —— **降级必须留痕**。
#
# 关键：入口是 **bridge.app:app**，不是 backend/main.py。
# `--app-dir` 让 uvicorn 找到 bridge 包，而进程 CWD 留在仓库根——
# 真正的 CWD 切换由 bridge/bootstrap.py 完成（它要切到 data/，那是运行根）。
# **不要 cd 到 backend/**：上游的路径是 CWD 相对的，会因此落错地方。

param(
    [int]$Port = 8000,
    [string]$Host_ = "127.0.0.1",
    [switch]$Rebuild,
    [switch]$SkipBuild,
    [switch]$AllowBundled
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # scripts/ → 仓库根
$frontend = Join-Path $root "frontend"

if ($AllowBundled) {
    # 闸门在 import 期，所以必须在**启动 uvicorn 之前**设好
    $env:AGENT_ALLOW_BUNDLED = "1"
    Write-Host "[!] -AllowBundled：允许使用仓库自带的 backend/ 副本。" -ForegroundColor Yellow
    Write-Host "    上游的修复不会生效；该事实会写入 /api/health 的 backend_bundled_override。" -ForegroundColor Yellow
}

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "[!] 找不到 .venv\Scripts\python.exe，回退到 PATH 里的 python" -ForegroundColor Yellow
    $python = "python"
}

$dist = Join-Path $frontend "dist"
$needsBuild = $Rebuild -or (-not (Test-Path $dist))
if ($SkipBuild) { $needsBuild = $false }

if ($needsBuild) {
    Write-Host "[1/2] 构建前端 (frontend)…" -ForegroundColor Cyan
    Push-Location $frontend
    try {
        if (-not (Test-Path "node_modules")) {
            Write-Host "      安装依赖…"
            npm install --no-audit --no-fund
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "前端构建失败（exit $LASTEXITCODE）" }
    }
    finally {
        Pop-Location
    }
}
else {
    Write-Host "[1/2] 跳过前端构建（frontend/dist 已存在）" -ForegroundColor DarkGray
}

Write-Host "[2/2] 启动服务： http://${Host_}:$Port/app" -ForegroundColor Cyan
Write-Host "      接口文档： http://${Host_}:$Port/docs"
Write-Host "      手机审批： http://${Host_}:$Port/decisions"
Write-Host "      运行数据： $(Join-Path $root 'data')"
Write-Host ""

Push-Location $root
try {
    & $python -m uvicorn bridge.app:app --app-dir $root --host $Host_ --port $Port
}
finally {
    Pop-Location
}