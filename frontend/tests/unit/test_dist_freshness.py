"""交付新鲜度：`frontend/dist` 必须**就是当前源码构建出来的那一版**。

为什么单独立一条
----------------
统筹方抓到过一次真事故（`deploy-freshness.py`）：

```
服务的 js        = index-BcJOtip4.js
当前源码重新构建 = index-BazGZyJn.js      ← FRESHNESS state = fail
```

**根因（附两个时间点）**：`frontend/scripts/gen-expectations.mjs` 在 **13:43:42**
才改好，而 `dist/index.html` 是 **13:43:17** 构建的 —— 早了 25 秒。
之后只跑了 `npm run typecheck`（它只重新生成 `src/generated/expectations.ts`），
**没再 `npm run build`**。于是"改过的"与"交付的"分了家。

这条门禁把 `scripts/freshness.py` 拉进回归：
**不看 mtime，真的用当前源码构建一遍，再逐文件比内容与引用。**

★ 负向也必须验：把 dist 里那个 JS 改一个字节，检查器**必须**报陈旧 ——
否则这条门禁可能只是"永远绿"。

运行：python tests/unit/test_dist_freshness.py
缺 node / 未装前端依赖时按**配置分流** SKIP（不把自己的环境问题报成代码失败）。
"""

import io
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

FRONTEND = os.path.join(ROOT, "frontend")
DIST = os.path.join(FRONTEND, "dist")
SCRIPT = os.path.join(ROOT, "scripts", "freshness.py")

checks: list[tuple[str, bool]] = []
skipped: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    skipped.append(name)
    print(f"  SKIP  {name}   {reason}")


def run(dist: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "--dist", dist],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )


print("=" * 74)
print("[1] 前提")
print("=" * 74)
check("scripts/freshness.py 存在", os.path.isfile(SCRIPT))
check("frontend/dist 存在（未构建的话先 npm run build）", os.path.isdir(DIST))

node = shutil.which("node")
deps = os.path.isdir(os.path.join(FRONTEND, "node_modules"))
if not node or not deps:
    skip("新鲜度检查（正向 + 负向）",
         "缺 node" if not node else "frontend/node_modules 未安装")

print()
print("=" * 74)
print("[2] 正向：dist 必须与「用当前源码构建」的结果一致")
print("=" * 74)
if node and deps and os.path.isdir(DIST):
    proc = run(DIST)
    out = proc.stdout or ""
    for ln in out.splitlines():
        if ln.strip():
            print("    | " + ln)
    check("FRESHNESS state = ok", proc.returncode == 0, f"exit={proc.returncode}")
    check("输出里有构建产物的哈希（可写进评估文档）", "sha256:" in out)

    print()
    print("=" * 74)
    print("[3] 负向：把 dist 里的 JS 改一个字节，检查器**必须**报陈旧")
    print("=" * 74)
    # ★ 这条才是"门禁不是永远绿"的证据：真实地制造一次陈旧，看它报不报。
    tmp = tempfile.mkdtemp(prefix="dsh-stale-")
    try:
        shutil.copytree(DIST, os.path.join(tmp, "dist"))
        target = os.path.join(tmp, "dist")
        assets = os.path.join(target, "assets")
        js = [f for f in os.listdir(assets) if f.endswith(".js")]
        if not js:
            check("负向：dist 里有 JS 产物", False, str(os.listdir(assets)))
        else:
            p = os.path.join(assets, js[0])
            # **只改内容、不改文件名**：这正是"改了源码没重建"的形态
            # （同名不同内容）——比"少一个文件"更难被发现。
            with open(p, "ab") as f:
                f.write(b"\n// stale\n")
            proc2 = run(target)
            out2 = proc2.stdout or ""
            check("负向：改脏 dist 之后 state = fail", proc2.returncode != 0,
                  f"exit={proc2.returncode}")
            check("负向：差异里点出「同名但内容不同」", "同名但内容不同" in out2,
                  [ln.strip() for ln in out2.splitlines() if "同名" in ln][:1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print()
print("=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}" + (f" · 跳过 {len(skipped)}" if skipped else ""))
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
