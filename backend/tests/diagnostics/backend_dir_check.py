"""核对「前端到底会加载哪一份后端」——把静默失效变成可检查的事实。

为什么需要它（实测事故）
------------------------
用户跑真实需求反复失败，而**修复代码一行都没生效** —— 因为前端在用它自带的
`SimpleAgent2_Cycle_VueWeb/backend/` **陈旧副本**（缺 `core/contract.py`，
`core/manifest.py` 停留在 9-25）。失败签名与修之前**逐字相同**：

  · `declared-missing all_files.txt`（而模型明明写了它）
  · `TypeError: install.<locals>._emit() got multiple values for argument 'kind'`

`bridge/paths.py` 的判据是：

    BACKEND_DIR = AGENT_BACKEND_DIR 或 <VueWeb>/backend（兜底）
    BACKEND_IS_BUNDLED = (BACKEND_DIR == <VueWeb>/backend)

**没设环境变量 → 用兜底副本 → 上游的修复全部无效，而服务照常启动。**

用法（在**本仓库**跑；只读，不改任何文件）：

    python tests/diagnostics/backend_dir_check.py
    python tests/diagnostics/backend_dir_check.py --frontend D:\\path\\to\\VueWeb
"""

import argparse
import hashlib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # tests/

from _bootstrap import ROOT  # noqa: E402   （仓库根 = 上游 checkout）

#: 与 `bridge/paths.py` 同源的判据：这些位置放的是"上游 Python 代码"
UPSTREAM_SUBDIRS = ("core", "tools", "storage", "web")
UPSTREAM_FILES = ("main.py",)

DEFAULT_FRONTEND = r"D:\PythonProject\SimpleAgent2_Cycle_VueWeb"


def sha1(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha1(f.read()).hexdigest()[:12]


def collect(base: str) -> dict[str, str]:
    """{相对路径: sha1}，只收上游代码文件。"""
    out: dict[str, str] = {}
    for sub in UPSTREAM_SUBDIRS:
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            continue
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x not in ("__pycache__",)]
            for n in names:
                if n.endswith(".py"):
                    p = os.path.join(root, n)
                    rel = os.path.relpath(p, base).replace("\\", "/")
                    out[rel] = sha1(p)
    for f in UPSTREAM_FILES:
        p = os.path.join(base, f)
        if os.path.isfile(p):
            out[f] = sha1(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontend", default=DEFAULT_FRONTEND,
                    help="前端仓库根（含 bridge/ 与 backend/）")
    args = ap.parse_args()
    fe = os.path.abspath(args.frontend)

    bundled = os.path.join(fe, "backend")
    env_raw = (os.getenv("AGENT_BACKEND_DIR") or "").strip()
    resolved = os.path.abspath(env_raw) if env_raw else bundled
    is_bundled = os.path.realpath(resolved) == os.path.realpath(bundled)

    print("=" * 78)
    print("前端会加载哪一份后端？")
    print("=" * 78)
    print(f"  AGENT_BACKEND_DIR      : {env_raw or '（未设置）'}")
    print(f"  实际解析出的 BACKEND_DIR: {resolved}")
    print(f"  BACKEND_IS_BUNDLED     : {is_bundled}")
    print(f"  上游 checkout（本仓库） : {ROOT}")
    print()

    if not os.path.isdir(resolved):
        print(f"  ⚠️ 解析出的目录不存在：{resolved}")
        return 1

    mine = collect(ROOT)
    theirs = collect(resolved)
    missing = sorted(set(mine) - set(theirs))
    extra = sorted(set(theirs) - set(mine))
    differ = sorted(p for p in (set(mine) & set(theirs)) if mine[p] != theirs[p])

    print("=" * 78)
    print(f"与上游逐文件比对（上游 {len(mine)} 个 .py）")
    print("=" * 78)
    print(f"  加载的副本缺失   : {len(missing)} 个")
    for p in missing[:12]:
        print(f"      - {p}")
    if len(missing) > 12:
        print(f"      …（共 {len(missing)} 个）")
    print(f"  内容落后于上游   : {len(differ)} 个")
    for p in differ[:12]:
        print(f"      ~ {p}")
    if len(differ) > 12:
        print(f"      …（共 {len(differ)} 个）")
    if extra:
        print(f"  副本多出（上游没有）: {len(extra)} 个（多为无害）")

    # 关键能力是否可用（不看文件，看**事实**）
    print()
    print("=" * 78)
    print("内容级判据：两份代码的指纹（统筹方 R4 要的「内容级」）")
    print("=" * 78)
    import sys as _sys
    _sys.path.insert(0, ROOT)
    try:
        from core.identity import code_fingerprint

        fp_mine = code_fingerprint(ROOT)
        fp_theirs = code_fingerprint(resolved)
    except Exception as e:  # noqa: BLE001
        fp_mine = fp_theirs = f"（不可用: {e}）"
    print(f"  上游（本仓库）: {fp_mine}")
    print(f"  被加载的那一份: {fp_theirs}")
    same_fp = fp_mine == fp_theirs and not isinstance(fp_mine, float)
    print(f"  指纹一致      : {same_fp}")
    print("  （指纹只看代码内容 core/tools/storage/web + main.py，"
          "不看文档/测试/产物）")

    print()
    print("=" * 78)
    print("关键能力核查")
    print("=" * 78)
    checks = [
        ("契约机制 core/contract.py", os.path.isfile(os.path.join(resolved, "core", "contract.py"))),
        ("多模态预留 core/vision.py", os.path.isfile(os.path.join(resolved, "core", "vision.py"))),
    ]
    for label, ok in checks:
        print(f"  {'有' if ok else '缺'}  {label}")

    # 两个具体修复是否在加载的那一份里（这是用户遇到的症状）
    def contains(rel: str, needle: str) -> bool:
        p = os.path.join(resolved, rel)
        if not os.path.isfile(p):
            return False
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return needle in f.read()

    print(f"  {'有' if contains('core/manifest.py', '_disk_fact') else '缺'}"
          f"  非 .py 交付物判定（manifest 查磁盘）")
    print(f"  {'有' if contains('core/coding_cycle.py', 'decision_kind') else '缺'}"
          f"  决策路径修复（payload 键 decision_kind）")
    print(f"  {'有' if contains('tools/code_checks.py', '_SKIP_DIRS') else '缺'}"
          f"  list_workspace 跳过策略（复用 _SKIP_DIRS）")

    stale = bool(missing or differ)
    print()
    print("=" * 78)
    if stale and is_bundled:
        print("结论：**正在用一个陈旧的自带副本，上游修复全部无效。**")
        print()
        print("修法（二选一，都在前端那一侧）：")
        print(f"  ① 指向上游（推荐，不用搬代码）：")
        print(f'     $env:AGENT_BACKEND_DIR = "{ROOT}"')
        print(f"     或在 {fe}\\.env 里写 AGENT_BACKEND_DIR={ROOT}")
        print(f"  ② 把上游同步进副本（会搬代码，容易再次落后）：")
        print(f"     用 tests/diagnostics/sync_backend_copy.py --frontend \"{fe}\"")
    elif stale:
        print("结论：指向的后端**落后于本仓库**，建议同步或改指本仓库。")
    else:
        print("结论：加载的这一份与本仓库一致，上游修复均已生效。")
    print("=" * 78)
    return 1 if stale else 0


raise SystemExit(main())
