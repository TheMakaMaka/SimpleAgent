"""打印当前项目的「谁是谁」：哪些是上游后端、哪些是适配层、哪些是前端。

为什么要脚本而不是手写清单
--------------------------
手写的清单一定会漂移——这正是这个项目一直在治理的病。
所以清单**生成**，只把**分类规则**写死在这里；文件增减自动反映。

用法（在仓库根执行）：

    python scripts/layout.py            # 人看的树
    python scripts/layout.py --counts   # 只要每类的数量
    python scripts/layout.py --json     # 给别的脚本消费

分类是**按目录+文件名规则**判定的，不读任何清单文件——所以它不会说谎。

`--check` 会在分类失败（出现没归类的顶层目录或文件）时返回非零，
适合放进回归清单：新加一个顶层目录却忘了归类，会被抓住。
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {
    "__pycache__", "node_modules", "dist", ".git", ".venv", "venv",
    ".idea", ".vscode", ".ruff_cache", ".npm-cache", ".checkpoints",
    "_backups", "output",
}

#: 我在上游测试里改过的文件（其余上游测试一字未动）
MODIFIED_UPSTREAM_TESTS = {
    "tests/_bootstrap.py",           # sys.path 指向 backend/，CWD 切到运行根
    "tests/unit/test_approval_web.py",   # import web.decisions（上游包名）
    "tests/unit/test_doc_consistency.py",  # 路径解析 + 新增裸路径检查
}

#: 我新增的测试
ADDED_TESTS = {
    "tests/unit/test_isolation.py",
    "tests/unit/test_event_contract.py",
    "tests/unit/test_spec.py",
    "tests/unit/test_webui_runtime.py",
    "tests/diagnostics/check_webui_stream.py",
}

#: 我改过的上游文档 / 根文件
MODIFIED_DOCS = {
    "README.md", "CYCLE.md", ".env.example", ".gitignore",
    "docs/ARCHITECTURE.md", "docs/MODULES.md",
    "docs/OPERATIONS.md", "docs/CHANGELOG.md",
    "tests/README.md",
}

#: 顶层目录 → 类别
TOP_KIND = {
    "backend": "upstream",     # 上游代码，可整包替换
    "bridge": "adapter",       # 我写的适配层（上游没有）
    "frontend": "frontend",    # 前端
    "tests": "tests",
    "docs": "docs",
    "scripts": "scripts",
    "data": "runtime",         # 运行态，不入库
}


def walk(base: str, exts: tuple[str, ...] | None = None):
    for dp, dn, fn in os.walk(base):
        dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
        for f in sorted(fn):
            if exts and not f.endswith(exts):
                continue
            yield os.path.relpath(os.path.join(dp, f), ROOT).replace("\\", "/")


def classify() -> dict:
    out: dict[str, list[str]] = {
        "upstream": [], "adapter": [], "frontend": [],
        "tests_upstream": [], "tests_mine": [],
        "docs_upstream": [], "docs_mine": [],
        "scripts": [], "root": [], "runtime": [], "unclassified": [],
    }

    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if os.path.isfile(p):
            rel = name
            if rel in MODIFIED_DOCS or rel in {
                "spec.override.example.json",
            }:
                out["docs_mine"].append(rel)
            else:
                out["root"].append(rel)
            continue
        if not os.path.isdir(p) or name in SKIP_DIRS or name.startswith("."):
            continue
        kind = TOP_KIND.get(name)
        if kind is None:
            out["unclassified"].append(name + "/")
            continue

        if kind == "upstream":
            out["upstream"] = sorted(walk(p))
        elif kind == "adapter":
            out["adapter"] = sorted(walk(p, (".py", ".md")))
        elif kind == "frontend":
            out["frontend"] = sorted(walk(p, (".ts", ".vue", ".json", ".html", ".md", ".css")))
        elif kind == "runtime":
            out["runtime"].append(name + "/")
        elif kind == "scripts":
            out["scripts"] = sorted(walk(p, (".ps1", ".py")))
        elif kind == "tests":
            for rel in walk(p, (".py", ".md", ".json")):
                if rel in ADDED_TESTS:
                    out["tests_mine"].append(rel)
                elif rel in MODIFIED_UPSTREAM_TESTS:
                    out["tests_mine"].append(rel + "   ← 改过")
                else:
                    out["tests_upstream"].append(rel)
        elif kind == "docs":
            for rel in walk(p, (".md", ".png")):
                (out["docs_mine"] if rel in MODIFIED_DOCS else out["docs_upstream"]).append(rel)

    return out


LABELS = [
    ("upstream", "上游后端 backend/", "整包替换 —— 上游出新版就覆盖它"),
    ("adapter", "适配层 bridge/", "★ 上游没有这个目录，**千万别覆盖**"),
    ("frontend", "前端 frontend/", "改渲染时才动；不含任何后端事实"),
    ("tests_upstream", "测试 · 上游原有", "上游出新版时会被覆盖"),
    ("tests_mine", "测试 · 我新增/改过", "★ 别被覆盖（几把锁都在这儿）"),
    ("docs_upstream", "文档 · 上游原有", "上游出新版时会被覆盖"),
    ("docs_mine", "文档 · 我改过", "★ 别被覆盖"),
    ("scripts", "脚本 scripts/", "★ 我新增的（备份 / 启动 / 迁移）"),
    ("root", "根目录文件", "上游原有"),
    ("runtime", "运行态 data/", "跑出来的，不入库，转移时忽略"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", action="store_true", help="只打印每类数量")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--check", action="store_true", help="有未分类项则返回非零")
    args = ap.parse_args()

    data = classify()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if args.counts:
        for key, label, _note in LABELS:
            print(f"  {label:<26} {len(data[key]):>3} 项")
        return 0

    for key, label, note in LABELS:
        items = data[key]
        print("=" * 78)
        print(f"{label}   （{len(items)} 项）")
        print(f"  {note}")
        print("=" * 78)
        if key == "runtime":
            print("  （仅目录，内容见 data/README.md）")
        for rel in items:
            print(f"  {rel}")
        print()

    if data["unclassified"]:
        print("=" * 78)
        print(f"⚠ 未分类（顶层新增了东西，去 scripts/layout.py 归类）: {data['unclassified']}")
        print("=" * 78)
        if args.check:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
