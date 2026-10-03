"""给 `.ps1` 补回 UTF-8 BOM（编辑工具会把它去掉）。

为什么这是个**常设**的小工具，而不是"下次注意"
----------------------------------------------
PowerShell 5.1 读 `.ps1` 时，**没有 BOM 就按 ANSI（本机是 GBK）解**。
于是中文注释会变成乱码，其中一句话里只要出现引号/反斜杠，脚本就**直接语法错误**
——而不是"显示难看"。

改 `.ps1` 的编辑器（含本仓库的编辑工具）默认写 UTF-8 **无 BOM**，
所以每改一次就会踩一次。`tests/unit/test_ps1_encoding.py` 会把这件事逮住
（它就是这么设计的），但恢复动作不该每次手打。

用法：

    python scripts/fix_bom.py            # 检查并补（幂等，已带 BOM 的不动）
    python scripts/fix_bom.py --check     # 只报不改（非 0 = 有文件缺 BOM）
"""

from __future__ import annotations

import glob
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = b"\xef\xbb\xbf"


def ps1_files() -> list[str]:
    out: list[str] = []
    for pat in ("scripts/*.ps1", "*.ps1"):
        out.extend(glob.glob(os.path.join(ROOT, pat)))
    return sorted(set(out))


def main() -> int:
    check = "--check" in sys.argv
    missing: list[str] = []
    fixed: list[str] = []
    for path in ps1_files():
        raw = open(path, "rb").read()
        rel = os.path.relpath(path, ROOT)
        if raw.startswith(BOM):
            continue
        missing.append(rel)
        if not check:
            with open(path, "wb") as f:
                f.write(BOM + raw)
            fixed.append(rel)

    print("=" * 74)
    print("PowerShell 脚本的 UTF-8 BOM")
    print("=" * 74)
    print(f"  扫到 {len(ps1_files())} 个 .ps1；缺 BOM 的 {len(missing)} 个")
    for r in missing:
        print(f"    {'（只报）' if check else '已补'} {r}")
    if not missing:
        print("  全部已带 BOM（PowerShell 5.1 会按 UTF-8 解）")
    elif not check:
        print(f"\n已补 {len(fixed)} 个 —— 再跑 python tests/unit/test_ps1_encoding.py 应转绿")
    else:
        print("\n修法：python scripts/fix_bom.py")
    return 1 if (check and missing) else 0


if __name__ == "__main__":
    raise SystemExit(main())
