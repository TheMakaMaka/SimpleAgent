# 把最新版后端接进来：覆盖 backend/ 之后跑一次这个。
#
#   .\scripts\adopt-backend.ps1 -From D:\path\to\new\backend
#   .\scripts\adopt-backend.ps1 -Check            # 只自检，不动文件
#
# 它做三件事：
#   1. 备份当前 backend/（后悔药）
#   2. 覆盖进来（-From 时）
#   3. **契约自检**：bridge 依赖的上游接口还在不在；
#      少了哪个、会导致前端少看到什么，逐条列出来
#
# 为什么需要这一步
# ----------------
# bridge 依赖上游的 14 个具体接口（类名、方法名）。上游迭代时它们可能悄悄变掉，
# 表现为"事件少了几个""某个面板一直是空的"——**不报错的失效最难查**。
# 这个脚本把它变成一张清单。

param(
    [string]$From = "",
    [switch]$Check,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# ---------- 1) 覆盖前先备份 ----------
if ($From -and -not $Check) {
    if (-not (Test-Path $From)) { throw "找不到目录: $From" }
    Write-Host "[1/3] 备份当前 backend/ …" -ForegroundColor Cyan

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $bak = Join-Path $root "_backups\backend-$stamp"
    New-Item -ItemType Directory -Force -Path $bak | Out-Null
    Copy-Item -Path (Join-Path $backend "*") -Destination $bak -Recurse -Force
    Write-Host "      已备份到 _backups\backend-$stamp" -ForegroundColor DarkGray

    Write-Host "[2/3] 覆盖 backend/ …" -ForegroundColor Cyan
    if (-not $Force) {
        $ans = Read-Host "确认用 $From 覆盖 backend/？（输入 yes 继续）"
        if ($ans -ne "yes") { Write-Host "已取消。" -ForegroundColor DarkGray; return }
    }
    Get-ChildItem -Path $backend -Exclude "__pycache__" | Remove-Item -Recurse -Force
    Copy-Item -Path (Join-Path $From "*") -Destination $backend -Recurse -Force
    Write-Host "      完成" -ForegroundColor DarkGray
}
else {
    Write-Host "[1/3] 未指定 -From，跳过备份" -ForegroundColor DarkGray
    Write-Host "[2/3] 未指定 -From，跳过覆盖" -ForegroundColor DarkGray
}

# ---------- 3) 契约自检 ----------
Write-Host ""
Write-Host "[3/3] 契约自检" -ForegroundColor Cyan
Write-Host ("=" * 70)

$probe = @"
import sys
sys.path.insert(0, r'$root')
import bridge.bootstrap as b
b.install()
import bridge.hooks as h
h.install()
import bridge.contract as c
rep = c.check(verbose=True)
print(rep.summary())
print()
print('--- 挂钩点实际签名（与 bridge/contract.py 对照）---')
for k, v in c.describe_calls().items():
    print(f'  {k:44} {v}')
sys.exit(0 if rep.ok else 2)
"@

$tmp = Join-Path $env:TEMP "adopt_probe_$([guid]::NewGuid().ToString('N')).py"
Set-Content -Path $tmp -Value $probe -Encoding UTF8
try {
    & $python $tmp
    $code = $LASTEXITCODE
}
finally {
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
}

Write-Host ("=" * 70)
if ($code -eq 0) {
    Write-Host "✓ bridge 与这份后端兼容。" -ForegroundColor Green
    Write-Host "  跑一遍验证：python tests/run_unit.py" -ForegroundColor DarkGray
    Write-Host "              .\scripts\run.ps1" -ForegroundColor DarkGray
} else {
    Write-Host "✗ 有接口对不上。按上面的清单改 bridge/contract.py 的依赖表，" -ForegroundColor Yellow
    Write-Host "  并在 bridge/hooks.py 里调整对应的包装。" -ForegroundColor Yellow
    Write-Host "  改完再跑一次本脚本。" -ForegroundColor DarkGray
}
exit $code
