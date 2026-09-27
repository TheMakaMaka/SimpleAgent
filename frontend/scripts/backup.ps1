<#
.SYNOPSIS
    给当前这一版可运行状态做一次快照，并能对比「现在改了什么」。

.DESCRIPTION
    项目根目录没有 .git（这是复制版），所以备份走文件级。

    纪律：**做出一版可行的之后，先备份，再继续完善。**
    否则一旦改坏，你既回不去、也说不清改坏了什么。

    备份内容 = 项目源码 + 前端构建产物（让备份开箱可跑）。
    备份排除 = 依赖与缓存 / 运行态数据 / 密钥（见 -ShowExcludes）。

.EXAMPLE
    .\scripts\backup.ps1                              # 打一个带时间戳的快照
    .\scripts\backup.ps1 -Label v2-重试动画            # 带标签
    .\scripts\backup.ps1 -Note "六阶段流水线跑通"      # 记一句这一版做到了什么
    .\scripts\backup.ps1 -List                        # 列出所有快照
    .\scripts\backup.ps1 -Verify                      # 当前代码 vs 最近一次快照，看改了什么
    .\scripts\backup.ps1 -Verify -From 20260925-2345_v1
    .\scripts\backup.ps1 -Restore -From 20260925-2345_v1   # 危险：会覆盖整份源码
    .\scripts\backup.ps1 -Restore -From v8 -Path docs/CHANGELOG.md   # 只退一个文件

.NOTES
    脚本住在 scripts/ 下，所以仓库根要从 $PSScriptRoot 往上退一层；
    `_backups/` 仍放在**仓库根**（不是 scripts/ 下）——它是整仓的快照。

    ⚠ 本文件必须存成 **UTF-8 with BOM**。Windows PowerShell 5.1 读无 BOM 的 .ps1
    会按 ANSI/GBK 解，中文注释与 here-string 立刻变成语法错误。
    `tests/unit/test_ps1_encoding.py` 把这条钉住了——编辑器存丢了 BOM 会红。
#>

[CmdletBinding()]
param(
    [string]$Label = "",
    [string]$Note = "",
    [switch]$List,
    [switch]$Verify,
    [switch]$Restore,
    [string]$From = "",
    [string[]]$Path = @(),
    [switch]$ShowExcludes,
    [switch]$Force,
    [switch]$NoAutoBackup,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot          # scripts/ → 仓库根
$backupRoot = Join-Path $root "_backups"

# Python：备份前的验证与 VERSIONS.md 追加都要用它。
# 找不到 .venv 就回退到 PATH —— 找不到时**不报错**，只是那两步降级：
# 备份本身不依赖 Python，不该因为缺它就把快照作废。
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# ============================================================
# 排除清单：只写一份，备份 / 对比 / 恢复共用
#
# 分四类，理由各不相同：
#   依赖与缓存  —— 可重建，且体积巨大（.venv / node_modules 数百 MB）
#   运行态数据  —— 是"跑出来的"，不是"写出来的"；备份它会让每次快照都不同
#   密钥        —— .env 含 API key，与仓库同样的保密要求
#   外部只读资产 —— 别人（统筹方）的镜像，**不属于本仓库**
# ============================================================
$excludeDirs = @(
    ".venv", "venv", "env",
    "node_modules", ".npm-cache",
    "_backups",
    "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache",
    ".idea", ".vscode",
    # 运行态数据排除：它是"跑出来的"，备份它会让每次快照都不相同，
    # -Verify 立刻失去意义（见 docs/OPERATIONS.md §11.4）。
    # 排除的是**三个子目录**而不是整个 data/：data/README.md 是说明文档，
    # 属于源码，要跟着快照走（整体排除 data/ 会把它一起丢掉）。
    "data\workspace", "data\storage_data", "data\sessions",
    "tests\output",
    # ★ .interface_contract/ 是**统筹方的只读镜像**，不属于本仓库。
    #
    # 为什么必须排除（实测踩到，不是洁癖）：
    #   1. 它的内容由统筹方按自己的节奏同步（本轮 8 → 9 个文件，新增 DISPATCH.md），
    #      留在备份里会让 -Verify 报出**不是本仓库发生的**"新增/删除"；
    #   2. 备份的语义是"我的源码是什么样"。混进别人的镜像会让这句话不成立；
    #   3. 上游仓库用嵌套 .gitignore（内容 `*`）挡掉它；本仓库不是 git 仓库，
    #      .gitignore 不生效，**只能靠这个清单**。
    # docs/LAYOUT.md §3 的"千万别被覆盖的清单"里也把它列为只读资产。
    ".interface_contract",
    ".git"
)
$excludeFiles = @(".env", ".env.local", ".DS_Store", "Thumbs.db")

# 注意：frontend/dist **要备份**——它是构建产物，但有了它备份才开箱可跑。
# 它没有被排除，这是刻意的。

# 写 UTF-8 **不带 BOM** 的文本。
#
# 为什么不直接用 Set-Content -Encoding utf8：Windows PowerShell 5.1 的 `utf8`
# 是**带 BOM** 的，而带 BOM 的 JSON 会让不少解析器（含部分 JS/Python 工具）出问题。
# 这里显式指定编码，避免依赖宿主版本的行为差异。
function Write-Utf8NoBom([string]$Path, [string]$Text) {
    [System.IO.File]::WriteAllText($Path, $Text, (New-Object System.Text.UTF8Encoding $false))
}

function Get-ProjectFiles {
    <# 返回相对路径列表（相对仓库根），已应用排除规则 #>
    $all = Get-ChildItem -Path $root -Recurse -File -Force -ErrorAction SilentlyContinue
    $out = New-Object System.Collections.Generic.List[string]

    foreach ($f in $all) {
        $rel = $f.FullName.Substring($root.Length + 1)

        $skip = $false
        foreach ($d in $excludeDirs) {
            if ($rel -eq $d -or $rel.StartsWith("$d\") -or $rel -like "*\$d\*") { $skip = $true; break }
        }
        if ($skip) { continue }
        if ($excludeFiles -contains $f.Name) { continue }
        if ($f.Extension -eq ".pyc") { continue }
        if ($f.Name -like "*.tmp") { continue }

        $out.Add($rel)
    }
    return $out
}

function Get-Manifest([string]$dir) {
    $path = Join-Path $dir "manifest.json"
    if (-not (Test-Path $path)) { return $null }
    return Get-Content -Raw -Encoding utf8 $path | ConvertFrom-Json
}

function New-Snapshot {
    # 必须显式声明 param()：没有它时 `-Label` 不会被绑定，函数体会去读**脚本作用域**
    # 的 $Label——从别的函数里调用时那个值可能是空的，标签就悄悄丢了。
    # 这是实测踩到的坑（自动快照全叫成了 `_snapshot`）。
    param(
        [string]$Label = "",
        [string]$Note = ""
    )

    if (-not $Label) { $Label = "snapshot" }
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $safeLabel = ($Label -replace '[\\/:*?"<>| ]', '-')
    $name = "${stamp}_${safeLabel}"
    $dest = Join-Path $backupRoot $name

    $files = Get-ProjectFiles
    Write-Host "备份 $($files.Count) 个文件 → _backups\$name" -ForegroundColor Cyan

    $entries = New-Object System.Collections.Generic.List[object]
    $totalBytes = 0
    foreach ($rel in $files) {
        $src = Join-Path $root $rel
        $dst = Join-Path $dest (Join-Path "files" $rel)
        $dstDir = Split-Path $dst -Parent
        if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
        Copy-Item -LiteralPath $src -Destination $dst -Force

        $hash = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
        $size = (Get-Item -LiteralPath $src).Length
        $totalBytes += $size
        $entries.Add([pscustomobject]@{ path = $rel; size = $size; sha256 = $hash })
    }

    $byTop = @{}
    foreach ($e in $entries) {
        $top = ($e.path -split '[\\/]')[0]
        if (-not $byTop.ContainsKey($top)) { $byTop[$top] = 0 }
        $byTop[$top]++
    }

    $manifest = [pscustomobject]@{
        name       = $name
        label      = $Label
        note       = $Note
        created_at = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        host       = $env:COMPUTERNAME
        file_count = $entries.Count
        total_bytes = $totalBytes
        by_top_dir = $byTop
        excluded   = @{ dirs = $excludeDirs; files = $excludeFiles }
        files      = $entries
    }
    $json = $manifest | ConvertTo-Json -Depth 6
    Write-Utf8NoBom (Join-Path $dest "manifest.json") $json

    Write-BackupDoc -Dest $dest -Manifest $manifest
    Write-Host "完成：$([math]::Round($totalBytes/1MB,2)) MB" -ForegroundColor Green
    Write-Host "恢复：.\backup.ps1 -Restore -From $name" -ForegroundColor DarkGray
    return $name
}

function Get-TopDirPairs($byTop) {
    $pairs = @()
    if ($null -eq $byTop) { return $pairs }
    if ($byTop -is [System.Collections.IDictionary]) {
        foreach ($k in $byTop.Keys) {
            $pairs += [pscustomobject]@{ name = [string]$k; count = $byTop[$k] }
        }
    }
    else {
        foreach ($p in $byTop.PSObject.Properties) {
            $pairs += [pscustomobject]@{ name = $p.Name; count = $p.Value }
        }
    }
    return $pairs
}

function Write-BackupDoc {
    param($Dest, $Manifest)

    # 用单引号 here-string（不插值、反引号是普通字符），再做占位符替换。
    # 双引号 here-string 里 markdown 的反引号会被当成转义符，且结束符必须顶格——
    # 函数体里两者都很难写对，所以这里刻意避开。
    # by_top_dir 的内存形态是 Hashtable、读回来是 PSCustomObject。
    # 对 Hashtable 直接取 .PSObject.Properties 会枚举到 Count/Keys/Values 这些
    # **哈希表自身**的属性——这是一个已经踩过的坑（表格里曾列出 Keys/Values）。
    $rows = @()
    foreach ($p in (Get-TopDirPairs $Manifest.by_top_dir | Sort-Object name)) {
        # 目录带 `/`、文件不带——两者混在一张表里，靠后缀区分
        $suffix = if (Test-Path (Join-Path $root $p.name) -PathType Container) { '/' } else { '' }
        $rows += '| `' + $p.name + $suffix + '` | ' + $p.count + ' |'
    }
    $topLines = $rows -join "`n"

    $noteLine = if ($Manifest.note) { $Manifest.note } else { '（未填写）' }
    $sizeMb = [math]::Round($Manifest.total_bytes / 1MB, 2)

    $template = @'
# 备份：__NAME__

**用途**：回到一个**已验证可运行**的状态，并说清之后改了什么。

| 项 | 值 |
|---|---|
| 备份时间 | __CREATED__ |
| 标签 | __LABEL__ |
| 说明 | __NOTE__ |
| 文件数 | __COUNT__ |
| 体积 | __SIZE__ MB |

## 这一版做到了什么

__NOTE__

> 这句由 `.\backup.ps1 -Note "..."` 写入。留空说明当时没记——下次记得记。

## 目录构成

| 顶层 | 文件数 |
|---|---|
__TOP__

## 不含什么

| 排除项 | 为什么 |
|---|---|
| `.venv/`、`node_modules/`、`.npm-cache/` | 依赖与缓存，可重建，体积大 |
| `data/` | **运行态数据**（workspace / storage_data / sessions），备份它会让每次快照都不相同 |
| `.env` / `.env.local` | 含 API key，与仓库同样的保密要求 |
| `__pycache__/`、`.idea/` 等 | 缓存与编辑器配置 |

`frontend/dist/` **在**备份里——它是构建产物，但带上它这份备份开箱即可运行。
`data/` 整个不在备份里：快照只回答"源码是什么样"，运行态由 `data/` 自己管。

## 怎么恢复

```powershell
.\backup.ps1 -List                                  # 看有哪些快照
.\backup.ps1 -Verify -From __NAME__                 # 先看当前比这一版改了什么
.\backup.ps1 -Restore -From __NAME__                # 覆盖当前源码（会先自动再备份一次）
```

恢复后按 `docs/OPERATIONS.md` §11 的清单重跑一遍验证。

## 完整性

`manifest.json` 里每个文件都带 `sha256`，随时可核对：

```powershell
.\backup.ps1 -Verify -From __NAME__
```

`[新增]` / `[删除]` / `[改动]` 三类差异都会被列出。
'@

    $doc = $template.Replace('__NAME__', $Manifest.name).
        Replace('__CREATED__', $Manifest.created_at).
        Replace('__LABEL__', $Manifest.label).
        Replace('__NOTE__', $noteLine).
        Replace('__COUNT__', [string]$Manifest.file_count).
        Replace('__SIZE__', [string]$sizeMb).
        Replace('__TOP__', $topLines)

    Write-Utf8NoBom (Join-Path $Dest "BACKUP.md") $doc
}
function Get-Snapshots {
    if (-not (Test-Path $backupRoot)) { return @() }
    return Get-ChildItem -Path $backupRoot -Directory | Sort-Object Name -Descending
}

function Resolve-Snapshot([string]$name) {
    $snaps = Get-Snapshots
    if (-not $snaps.Count) { throw "还没有任何备份。先跑一次 .\backup.ps1" }
    if (-not $name) { return $snaps[0] }
    $hit = $snaps | Where-Object { $_.Name -eq $name -or $_.Name -like "*$name*" } | Select-Object -First 1
    if (-not $hit) { throw "找不到备份：$name（用 .\backup.ps1 -List 查看）" }
    return $hit
}

function Compare-Snapshot([string]$name) {
    <# 当前树 vs 某个快照 → {name, created, note, added[], removed[], changed[]}。
       抽出来是为了让 -Verify 与「写 VERSIONS.md」共用同一套判据——
       两处各写一遍迟早会分叉。 #>
    $snap = Resolve-Snapshot $name
    $manifest = Get-Manifest $snap.FullName
    if (-not $manifest) { throw "$($snap.Name) 里没有 manifest.json，无法对比" }

    $old = @{}
    foreach ($e in $manifest.files) { $old[$e.path] = $e.sha256 }

    $new = @{}
    foreach ($rel in (Get-ProjectFiles)) {
        $new[$rel] = (Get-FileHash -LiteralPath (Join-Path $root $rel) -Algorithm SHA256).Hash
    }

    return [pscustomobject]@{
        name    = $snap.Name
        created = $manifest.created_at
        note    = $manifest.note
        added   = @($new.Keys | Where-Object { -not $old.ContainsKey($_) } | Sort-Object)
        removed = @($old.Keys | Where-Object { -not $new.ContainsKey($_) } | Sort-Object)
        changed = @($new.Keys | Where-Object { $old.ContainsKey($_) -and $old[$_] -ne $new[$_] } | Sort-Object)
    }
}

function Invoke-Verify([string]$name) {
    $d = Compare-Snapshot $name

    Write-Host "对比基准：$($d.name)（$($d.created)）" -ForegroundColor Cyan
    if ($d.note) { Write-Host "  说明：$($d.note)" -ForegroundColor DarkGray }

    Write-Host ""
    if (-not ($d.added.Count + $d.removed.Count + $d.changed.Count)) {
        Write-Host "与备份完全一致——没有改动。" -ForegroundColor Green
        return
    }

    if ($d.changed.Count) {
        Write-Host "[改动] $($d.changed.Count)" -ForegroundColor Yellow
        $d.changed | ForEach-Object { Write-Host "   ~ $_" }
    }
    if ($d.added.Count) {
        Write-Host "[新增] $($d.added.Count)" -ForegroundColor Green
        $d.added | ForEach-Object { Write-Host "   + $_" }
    }
    if ($d.removed.Count) {
        Write-Host "[删除] $($d.removed.Count)" -ForegroundColor Red
        $d.removed | ForEach-Object { Write-Host "   - $_" }
    }
    Write-Host ""
    Write-Host "改动合计 $($d.added.Count + $d.removed.Count + $d.changed.Count) 个文件。" -ForegroundColor Yellow
    Write-Host "若这一版也跑通了，记得再备份一次：.\backup.ps1 -Label <这一版的名字>" -ForegroundColor DarkGray
}

function Invoke-Preflight {
    <# 备份前跑一遍**离线**验证，供 VERSIONS.md 记录"验证结果"。

       为什么跑：目录名记不下"这一版验过没有"。上游是"验证不过拒绝备份"；
       本仓库改成"照备份，但如实记下没过" —— 因为**最需要备份的时候恰恰是
       东西坏掉的时候**，拒绝备份会让人失去唯一的退路。这是刻意的偏离，
       已写在 docs/VERSIONS.md 的头部说明里。

       只跑离线的三项：单元测试 / 目录归属 / 前端类型。
       端到端那项需要一个跑着的服务：没起服务时记为"未跑"，**不算失败**。 #>
    param([switch]$Skip)

    if ($Skip) { return [pscustomobject]@{ text = "—（-SkipVerify）"; ok = $true } }

    # ★ 本函数要跑**子进程**，而脚本级 $ErrorActionPreference 是 Stop：
    #   PowerShell 5.1 下用 `2>&1` 收原生命令的 stderr 会把它变成 ErrorRecord，
    #   于是"测试往 stderr 打了一句警告"就会**终止整次备份**。
    #   实测踩到：单测里一句 [rollback] 警告直接让 backup.ps1 挂掉。
    #   所以这一节局部放宽，返回前恢复 —— **验证结果要如实记录，
    #   而不是让备份崩掉**。
    $eap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    # ★ 再钉一层编码：子进程输出是 UTF-8，而 PowerShell 5.1 按
    #   [Console]::OutputEncoding 解码它。控制台是 GBK 时 `通过 17/17`
    #   会被解成乱码，下面的正则就匹配不到 —— 验证结果会记成"未识别输出"
    #   （**实测踩到**）。
    $enc = [Console]::OutputEncoding
    try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }

    # 取子进程输出里**汇总**那一条 `通过 X/Y`。
    # 必须取**最后**一条：单个测试文件自己也会打印 `通过 X/Y`，
    # 取第一条会把"某个文件的 23/23"当成"全量结果"（**实测踩到**）。
    function Get-Summary {
        param([string]$Text)
        $all = [regex]::Matches($Text, "通过\s+(\d+)/(\d+)")
        if ($all.Count -eq 0) { return $null }
        return $all[$all.Count - 1]
    }

    $parts = @()
    $allOk = $true

    Write-Host "  · 单元测试…" -ForegroundColor DarkGray
    $out = & $python (Join-Path $root "tests\run_unit.py") 2>&1 | Out-String
    $m = Get-Summary $out
    if ($m) {
        $parts += "单测 $($m.Groups[1].Value)/$($m.Groups[2].Value)"
        if ($m.Groups[1].Value -ne $m.Groups[2].Value) { $allOk = $false }
    }
    else { $parts += "单测 未识别输出"; $allOk = $false }

    Write-Host "  · 目录归属…" -ForegroundColor DarkGray
    & $python (Join-Path $root "scripts\layout.py") --check *> $null
    if ($LASTEXITCODE -eq 0) { $parts += "layout 通过" }
    else { $parts += "layout **失败**"; $allOk = $false }

    $frontend = Join-Path $root "frontend"
    $hasNpm = [bool](Get-Command npm -ErrorAction SilentlyContinue)
    if ((Test-Path (Join-Path $frontend "node_modules")) -and $hasNpm) {
        Write-Host "  · 前端类型…" -ForegroundColor DarkGray
        Push-Location $frontend
        try {
            $null = npm run typecheck 2>&1 | Out-String
            if ($LASTEXITCODE -eq 0) { $parts += "typecheck 零错误" }
            else { $parts += "typecheck **失败**"; $allOk = $false }
        }
        finally { Pop-Location }
    }
    else { $parts += "typecheck 未跑（缺 node_modules 或 npm）" }

    try {
        $null = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" `
            -TimeoutSec 3 -UseBasicParsing
        Write-Host "  · 端到端（:8000 有服务）…" -ForegroundColor DarkGray
        $out2 = & $python (Join-Path $root "tests\diagnostics\check_webui_stream.py") 2>&1 | Out-String
        $m2 = Get-Summary $out2
        if ($m2) {
            $parts += "端到端 $($m2.Groups[1].Value)/$($m2.Groups[2].Value)"
            if ($m2.Groups[1].Value -ne $m2.Groups[2].Value) { $allOk = $false }
        }
        else { $parts += "端到端 未识别输出"; $allOk = $false }
    }
    catch { $parts += "端到端 未跑（:8000 无服务）" }
    finally {
        $ErrorActionPreference = $eap
        try { [Console]::OutputEncoding = $enc } catch { }
    }

    return [pscustomobject]@{ text = ($parts -join " · "); ok = $allOk }
}

function Add-VersionRecord {
    <# 调 scripts/versions.py 追加一条到 docs/VERSIONS.md。
       失败**不影响备份**：记录是为了追溯，不该因此把已打好的快照作废。 #>
    param([string]$Snapshot, [string]$Label, [string]$Note,
          [string]$VerifyText, [string]$DiffText, [string]$Baseline,
          [string[]]$Files)

    $mod = Join-Path $root "scripts\versions.py"
    if (-not (Test-Path $mod)) {
        Write-Host "  [!] 找不到 scripts\versions.py，跳过 VERSIONS.md 记录" -ForegroundColor Yellow
        return
    }
    $a = @($mod, "append", "--label", $Label, "--snapshot", $Snapshot,
           "--verify", $VerifyText)
    if ($Note) { $a += @("--note", $Note) }
    if ($DiffText) { $a += @("--diff", $DiffText) }
    if ($Baseline) { $a += @("--baseline", $Baseline) }
    if ($Files -and $Files.Count) { $a += @("--files", ($Files -join "|")) }
    & $python @a
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [!] VERSIONS.md 追加失败（exit $LASTEXITCODE）——备份本身是好的" -ForegroundColor Yellow
    }
}

function Invoke-Restore([string]$name, [string[]]$Paths) {
    $snap = Resolve-Snapshot $name
    $manifest = Get-Manifest $snap.FullName

    if ($Paths -and $Paths.Count) {
        # ---- 文件级回退：只覆盖点名的文件 ----
        # 整树恢复（下面那一支）够用但太重：改坏一个文档也要先删掉整份源码树。
        # 这一支补上 C8 要的"粒度回退"——成本与风险都按**文件**算。
        $src = Join-Path $snap.FullName "files"
        Write-Host "文件级回退 ← $($snap.Name)（$($manifest.created_at)）" -ForegroundColor Yellow
        $inSnap = @{}
        foreach ($e in $manifest.files) { $inSnap[$e.path] = $e }

        $missing = @()
        $planned = @()
        foreach ($p in $Paths) {
            # 归一化：允许正反斜杠、允许前导 .\
            $rel = ($p -replace '^\.\\', '') -replace '/', '\'
            if ($inSnap.ContainsKey($rel)) { $planned += $rel } else { $missing += $rel }
        }
        if ($missing.Count) {
            Write-Host "[!] 这些路径不在该快照里，跳过：" -ForegroundColor Red
            $missing | ForEach-Object { Write-Host "   ? $_" }
        }
        if (-not $planned.Count) {
            Write-Host "没有可回退的文件，什么都没改。" -ForegroundColor DarkGray
            return
        }

        Write-Host ""
        Write-Host "将处理 $($planned.Count) 个文件：" -ForegroundColor Cyan
        foreach ($rel in $planned) {
            $to = Join-Path $root $rel
            $state = ""
            $mark = "+ 新增"
            if (Test-Path -LiteralPath $to) {
                $same = (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash -eq $inSnap[$rel].sha256
                $mark = if ($same) { "= 已一致" } else { "~ 会改动" }
            }
            Write-Host ("   {0}  {1}{2}" -f $mark, $rel, $state)
        }

        if (-not $Force) {
            Write-Host ""
            $ans = Read-Host "确认覆盖这 $($planned.Count) 个文件？输入 yes 继续（或 -Force 跳过）"
            if ($ans -ne "yes") { Write-Host "已取消，什么都没改。" -ForegroundColor DarkGray; return }
        }

        # 只把**被点名文件**的当前版本另存一份，而不是打整仓快照：
        # 粒度回退就配粒度的后悔药。当前不存在的文件无需后悔药。
        $undo = Join-Path $snap.FullName ("undo-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
        $saved = 0
        foreach ($rel in $planned) {
            $to = Join-Path $root $rel
            if (-not (Test-Path -LiteralPath $to)) { continue }
            $dst = Join-Path $undo $rel
            $dstDir = Split-Path $dst -Parent
            if (-not (Test-Path $dstDir)) { New-Item -ItemType Directory -Force -Path $dstDir | Out-Null }
            Copy-Item -LiteralPath $to -Destination $dst -Force
            $saved++
        }

        foreach ($rel in $planned) {
            $to = Join-Path $root $rel
            $toDir = Split-Path $to -Parent
            if (-not (Test-Path $toDir)) { New-Item -ItemType Directory -Force -Path $toDir | Out-Null }
            Copy-Item -LiteralPath (Join-Path $src $rel) -Destination $to -Force
        }
        Write-Host ""
        Write-Host "已回退 $($planned.Count) 个文件。" -ForegroundColor Green
        if ($saved) {
            Write-Host "覆盖前的原件留在这里（想反悔就拷回来）：" -ForegroundColor DarkGray
            Write-Host "   _backups\$($snap.Name)\undo-*\" -ForegroundColor DarkGray
        }
        Write-Host "核对：.\backup.ps1 -Verify -From $($snap.Name)" -ForegroundColor DarkGray
        return
    }

    Write-Host "即将用备份覆盖当前源码：" -ForegroundColor Yellow
    Write-Host "  备份：$($snap.Name)（$($manifest.created_at)）"
    Write-Host "  文件：$($manifest.file_count) 个"
    Write-Host "  影响：backend/ frontend/ tests/ docs/ scripts/ 等" -ForegroundColor Yellow
    Write-Host "  提示：只想退某几个文件时用 -Path，例如" -ForegroundColor DarkGray
    Write-Host "        .\backup.ps1 -Restore -From $($snap.Name) -Path docs/CHANGELOG.md" -ForegroundColor DarkGray

    # 自动快照**永远做**（除非显式 -NoAutoBackup）。
    # -Force 只跳过确认，不跳过保命措施——恢复本身也可能后悔，
    # 把「先留退路」和「别烦我」绑在同一个开关上是错的。
    if (-not $NoAutoBackup) {
        Write-Host ""
        Write-Host "先给当前状态留一个自动快照…" -ForegroundColor Cyan
        $auto = New-Snapshot -Label "auto-before-restore" -Note "恢复 $($snap.Name) 之前的自动快照"
        Write-Host "已存为 _backups\$auto（后悔了可以从这里回来）" -ForegroundColor DarkGray
    }

    if (-not $Force) {
        Write-Host ""
        $ans = Read-Host "确认覆盖？输入 yes 继续（或下次用 -Force 跳过此确认）"
        if ($ans -ne "yes") { Write-Host "已取消，什么都没改。" -ForegroundColor DarkGray; return }
    }

    $src = Join-Path $snap.FullName "files"
    if (-not (Test-Path $src)) { throw "$($snap.Name) 里没有 files/ 目录" }

    # 先删掉当前源码树（按同样的排除规则，别把依赖和运行态数据删了）
    foreach ($rel in (Get-ProjectFiles)) {
        Remove-Item -LiteralPath (Join-Path $root $rel) -Force -ErrorAction SilentlyContinue
    }
    # 再整体拷回
    Copy-Item -Path (Join-Path $src "*") -Destination $root -Recurse -Force

    Write-Host "已恢复到 $($snap.Name)。" -ForegroundColor Green
    Write-Host "别忘了：前端产物已一并恢复，但 node_modules 不在备份里——" -ForegroundColor DarkGray
    Write-Host "若 frontend/node_modules 缺失，先在 frontend/ 下 npm install。" -ForegroundColor DarkGray
    Write-Host "运行态数据（data/）不受影响：它本来就不在备份范围内。" -ForegroundColor DarkGray
    Write-Host "验证清单见 docs/OPERATIONS.md §11。" -ForegroundColor DarkGray
}

# ============================================================
# 入口
# ============================================================
if ($ShowExcludes) {
    Write-Host "排除的目录："
    $excludeDirs | ForEach-Object { Write-Host "   $_" }
    Write-Host "排除的文件："
    $excludeFiles | ForEach-Object { Write-Host "   $_" }
    return
}

if ($List) {
    $snaps = Get-Snapshots
    if (-not $snaps.Count) { Write-Host "还没有任何备份。先跑：.\backup.ps1" -ForegroundColor Yellow; return }
    Write-Host "共 $($snaps.Count) 个备份（新 → 旧）：" -ForegroundColor Cyan
    foreach ($s in $snaps) {
        $m = Get-Manifest $s.FullName
        if ($m) {
            $note = if ($m.note) { " · $($m.note)" } else { "" }
            Write-Host ("  {0}  {1,4} 文件  {2,7} MB{3}" -f $s.Name, $m.file_count,
                [math]::Round($m.total_bytes / 1MB, 2), $note)
        }
        else {
            Write-Host "  $($s.Name)  （缺少 manifest.json）" -ForegroundColor Yellow
        }
    }
    return
}

if ($Verify) { Invoke-Verify $From; return }
if ($Restore) { Invoke-Restore $From $Path; return }

# ============================================================
# 打快照
#
# 顺序刻意是「先量差异 → 再验证 → 再快照 → 再记录」：
#   · 差异必须在快照**之前**算（快照一打，基准就变成它自己了）；
#   · 验证结果记进 VERSIONS.md，让人看得出这一版验过没有。
# ============================================================
$prevName = ""
$snaps = Get-Snapshots
if ($snaps.Count) { $prevName = $snaps[0].Name }

$diffText = ""
$diffFiles = @()
if ($prevName) {
    try {
        $d = Compare-Snapshot $prevName
        $diffText = ("{0} 改动 / {1} 新增 / {2} 删除（对比 ``{3}``）" -f `
            $d.changed.Count, $d.added.Count, $d.removed.Count, $d.name)
        # ★ 用显式 List 逐条 Add，不要写 `(a | ForEach) + (b | ForEach) + ...`：
        #   管道表达式为空时返回 $null，与数组相加在 5.1 下会报
        #   “Method invocation failed ... 'op_Addition'”（**实测踩到**），
        #   于是"改了什么"被记成一条错误信息。
        $diffFiles = New-Object System.Collections.Generic.List[string]
        foreach ($f in $d.changed) { $diffFiles.Add("~ $f") }
        foreach ($f in $d.added) { $diffFiles.Add("+ $f") }
        foreach ($f in $d.removed) { $diffFiles.Add("- $f") }
    }
    catch {
        $diffText = "—（对比 $prevName 失败：$($_.Exception.Message)）"
    }
}
else {
    $diffText = "—（这是第一个备份，没有基准）"
}

Write-Host "备份前验证…" -ForegroundColor Cyan
$pre = Invoke-Preflight -Skip:$SkipVerify
Write-Host "  验证结果：$($pre.text)" -ForegroundColor $(if ($pre.ok) { "DarkGray" } else { "Yellow" })
if (-not $pre.ok) {
    Write-Host "  [!] 验证未全过——**仍然备份**（最需要备份的时候正是东西坏掉的时候），" -ForegroundColor Yellow
    Write-Host "      但 VERSIONS.md 会如实记为未通过。" -ForegroundColor Yellow
}
Write-Host ""

$made = New-Snapshot -Label $Label -Note $Note
Add-VersionRecord -Snapshot $made -Label $(if ($Label) { $Label } else { "snapshot" }) `
    -Note $Note -VerifyText $pre.text -DiffText $diffText -Baseline $prevName -Files $diffFiles
Write-Host "版本记录已追加 → docs\VERSIONS.md" -ForegroundColor DarkGray
Write-Host "（改成打快照不打验证：加 -SkipVerify）" -ForegroundColor DarkGray
