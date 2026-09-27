"""PowerShell 脚本必须存成 **UTF-8 with BOM**。

为什么值得单测
--------------
本机跑的是 **Windows PowerShell 5.1**（不是 pwsh 7）。它读**无 BOM** 的 `.ps1`
时按 ANSI/GBK 解码，于是文件里的中文注释和 here-string 立刻变成语法错误：

```
At D:\\...\\scripts\\backup.ps1:184 char:1
+ | 椤?| 鍊?|
+ ~
An empty pipe element is not allowed.
```

这个坑已经踩过两次：一次是初次写脚本，一次是**用编辑工具改完之后**
（工具按 UTF-8 无 BOM 写回，BOM 被静默丢掉）。症状具有欺骗性——
报的是"语法错误"，看起来像代码写错了，而不是编码问题。

所以把它变成机械检查：BOM 丢了就红，并直接告诉你哪一行命令能修。

运行：python tests/unit/test_ps1_encoding.py
"""

import glob
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

BOM = b"\xef\xbb\xbf"

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


scripts = sorted(glob.glob(os.path.join(ROOT, "scripts", "*.ps1")))
check("找得到 .ps1 脚本", bool(scripts), f"{len(scripts)} 个")

for path in scripts:
    rel = os.path.relpath(path, ROOT)
    raw = open(path, "rb").read()

    has_bom = raw.startswith(BOM)
    check(f"{rel} 有 UTF-8 BOM", has_bom,
          "" if has_bom else "PowerShell 5.1 会按 GBK 解，中文注释直接变语法错误")

    if not has_bom:
        continue

    # BOM 在，还要确认它**真的是** UTF-8（而不是别的编码恰好带了这三个字节）
    body = raw[len(BOM):]
    try:
        text = body.decode("utf-8")
        check(f"{rel} 内容可按 UTF-8 解码", True)
    except UnicodeDecodeError as e:
        check(f"{rel} 内容可按 UTF-8 解码", False, f"{type(e).__name__}: {e}")
        continue

    # 只有 ASCII 的脚本无所谓 BOM；有中文就必须有它（否则一定是坑）
    non_ascii = [ln for ln, line in enumerate(text.splitlines(), 1)
                 if any(ord(ch) > 127 for ch in line)]
    if non_ascii:
        check(f"{rel} 含非 ASCII 且已带 BOM（两者必须同时成立）", has_bom,
              f"首个非 ASCII 行：{non_ascii[0]}")

    # 换行风格：CRLF 更稳（Notepad / 5.1 都认），但这里只做提示不判红
    crlf = body.count(b"\r\n")
    lf = body.count(b"\n") - crlf
    print(f"      （{rel}: {len(text.splitlines())} 行, CRLF {crlf} / LF {lf}）")

# 排除清单里必须有 .interface_contract —— 它是统筹方的只读镜像，不属于本仓库。
# 漏了会让 -Verify 报出"不是本仓库发生的"新增/删除（实测发生过）。
bak = os.path.join(ROOT, "scripts", "backup.ps1")
if os.path.isfile(bak):
    btext = open(bak, encoding="utf-8-sig").read()
    check("★ backup.ps1 排除了 .interface_contract（外部只读镜像）",
          '".interface_contract"' in btext,
          "漏了它，-Verify 会把统筹方的同步报成本仓库的改动")
    # 这条同样要有：-Verify 是"机械核对改动清单"的手段（评估文档 C4 用）
    check("backup.ps1 支持文件级回退（-Path）", "[string[]]$Path" in btext,
          "评估文档 C8 要的粒度回退")

print()
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
    print()
    print("修法（给所有 .ps1 补 BOM）：")
    print('  .venv\\Scripts\\python.exe -c "'
          "import glob;BOM=b'\\xef\\xbb\\xbf';"
          "[open(f,'wb').write(BOM+open(f,'rb').read()) "
          "for f in glob.glob('scripts/*.ps1') "
          "if not open(f,'rb').read().startswith(BOM)]\"")
raise SystemExit(1 if failed else 0)
