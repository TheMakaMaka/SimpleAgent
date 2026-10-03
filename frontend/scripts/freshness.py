"""交付新鲜度：**`frontend/dist` 是不是当前源码构建出来的**。

为什么要有它
------------
统筹方用 `deploy-freshness.py` 抓到过一次真事故：

```
服务的 js        = index-BcJOtip4.js
当前源码重新构建 = index-BazGZyJn.js      ← 不一致
FRESHNESS state = fail
```

**根因（已查明，附两个时间点）**：`frontend/scripts/gen-expectations.mjs`
在 **13:43:42** 才被改成"前端词表 = `case` ∪ 采集器声明"，而 `dist/index.html`
是 **13:43:17** 构建的 —— **早了 25 秒**。之后我只跑了 `npm run typecheck`
（它只重新生成 `src/generated/expectations.ts`），**没再 `npm run build`**。
于是交付物里的那 34 个事件永远不会变成 37 个：
**编辑过的东西，不一定就是被交付的东西。**

判据
----
**不许看 mtime**，要**真的用当前源码构建一遍**再逐文件比：
构建到临时目录，把 `dist/index.html` 引用的资源名与内容哈希跟它对齐。
和统筹方的工具同一条判据，但离线、可在备份前跑。

用法
----
    python scripts/freshness.py             # 只检查（非 0 = 陈旧）
    python scripts/freshness.py --fix       # 直接重建 dist（写盘）
    python scripts/freshness.py --dist <dir>  # 比另一个 dist（负向测试用）
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FRONTEND = os.path.join(ROOT, "frontend")
DIST = os.path.join(FRONTEND, "dist")

ASSET_RE = re.compile(r'(?:src|href)="([^"]*assets/[^"]+)"')


def _read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def referenced(dist_dir: str) -> dict[str, str]:
    """`index.html` 引用的资源 → 内容哈希前缀。**引用**才是"用户看到的那一版"。"""
    index = os.path.join(dist_dir, "index.html")
    if not os.path.isfile(index):
        return {}
    out: dict[str, str] = {}
    for rel in ASSET_RE.findall(_read(index)):
        name = os.path.basename(rel)
        p = os.path.join(dist_dir, "assets", name)
        out[name] = _sha(p) if os.path.isfile(p) else "（缺文件）"
    return out


def build_fresh(outdir: str) -> tuple[bool, str]:
    """把当前源码构建到 `outdir`。返回 (成功, 说明)。"""
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx:
        return False, "找不到 npx"
    # 先确认生成物是当前的（**不写盘**）：`--check` 不一致就非 0
    gen = subprocess.run(
        [shutil.which("node") or "node", os.path.join("scripts", "gen-expectations.mjs"), "--check"],
        cwd=FRONTEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if gen.returncode != 0:
        return False, ("src/generated/expectations.ts 不是最新的（先跑 npm run gen:expectations）\n"
                       + (gen.stdout or "") + (gen.stderr or ""))
    proc = subprocess.run(
        [npx, "vite", "build", "--outDir", outdir, "--emptyOutDir", "--logLevel", "warn"],
        cwd=FRONTEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return False, ((proc.stdout or "") + (proc.stderr or ""))[-1200:]
    return True, ""


def compare(served: dict[str, str], fresh: dict[str, str]) -> list[str]:
    diffs: list[str] = []
    for name in sorted(set(served) | set(fresh)):
        a, b = served.get(name), fresh.get(name)
        if a is None:
            diffs.append(f"  + 应有却没有：{name}")
        elif b is None:
            diffs.append(f"  - 多出个不该有的：{name}（当前源码构建不出来这个文件名）")
        elif a != b:
            diffs.append(f"  ~ 同名但内容不同：{name}  dist={a}  重建={b}")
    return diffs


def main() -> int:
    argv = sys.argv[1:]
    fix = "--fix" in argv
    dist = DIST
    if "--dist" in argv:
        dist = os.path.abspath(argv[argv.index("--dist") + 1])

    print("=" * 74)
    print("交付新鲜度：frontend/dist 是不是**当前源码**构建出来的")
    print("=" * 74)
    print(f"  比对目标 dist : {os.path.relpath(dist, ROOT) if dist.startswith(ROOT) else dist}")

    if not os.path.isdir(os.path.join(FRONTEND, "node_modules")):
        print("SKIP  frontend/node_modules 未安装（先 npm install）")
        return 0

    served = referenced(dist)
    if not served:
        print(f"FAIL  {os.path.relpath(dist, ROOT)} 里没有 index.html 引用的资源")
        return 1
    print(f"  dist 提供     : {', '.join(sorted(served))}")

    tmp = tempfile.mkdtemp(prefix="dsh-freshness-")
    try:
        ok, err = build_fresh(tmp)
        if not ok:
            print(f"FAIL  无法用当前源码构建：{err}")
            return 1
        fresh = referenced(tmp)
        print(f"  当前源码构建   : {', '.join(sorted(fresh))}")
        for name in sorted(fresh):
            print(f"      {name}  sha256:{fresh[name]}")
        diffs = compare(served, fresh)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not diffs:
        print("\nFRESHNESS state = ok（dist 与当前源码构建的结果逐文件一致）")
        return 0

    print("\n差异（**逐文件比内容，不看 mtime**）：")
    for d in diffs:
        print(d)
    print("\nFRESHNESS state = fail —— dist 落后于 src：用户看到的不是最新交付的那一版。")
    if fix:
        print("\n--fix：重建 dist …")
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        proc = subprocess.run([npm, "run", "build"], cwd=FRONTEND)
        return proc.returncode
    print("修法：cd frontend; npm run build      （或 python scripts/freshness.py --fix）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
