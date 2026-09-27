"""架构视图工具自检：get_architecture / get_module / find_symbol。

这三个工具是只读查询，数据来自 AST 结构事实，因此可以确定性验证。
"""

import asyncio
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from tools import TOOLS_MAP  # noqa: E402

D = WS  # 放在 workspace 根目录，保证 `import X` 形式的依赖真实可解析
PREFIX = "_archtest_"

get_architecture = TOOLS_MAP["get_architecture"]["function"]
get_module = TOOLS_MAP["get_module"]["function"]
find_symbol = TOOLS_MAP["find_symbol"]["function"]


def w(rel: str, content: str) -> None:
    p = os.path.join(D, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def cleanup() -> None:
    for name in os.listdir(WS):
        if name.startswith(PREFIX):
            p = os.path.join(WS, name)
            shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


async def main():
    cleanup()
    w(f"{PREFIX}util.py", (
        "import math\n"
        "\n"
        "def clamp(x, lo, hi):\n"
        "    return max(lo, min(x, hi))\n"
        "\n"
        "class Box:\n"
        "    def __init__(self, v):\n"
        "        self.v = v\n"
        "    def get(self):\n"
        "        return self.v\n"
    ))
    w(f"{PREFIX}main.py", (
        f"import {PREFIX}util\n"
        "\n"
        "def run(args):\n"
        f"    return {PREFIX}util.clamp(5, 0, 3)\n"
    ))

    util_path = f"{PREFIX}util.py"
    main_path = f"{PREFIX}main.py"

    print("=" * 72)
    print("[1] get_architecture")
    print("=" * 72)
    arch = json.loads(await get_architecture())
    print(f"  ok={arch['ok']} totals={arch['totals']}")
    for m in arch["modules"]:
        print(f"  {m['path']:<16} exports={m['exports']} deps={m['depends_on']}")

    print("\n" + "=" * 72)
    print("[2] get_architecture(limit=1) 应截断")
    print("=" * 72)
    arch1 = json.loads(await get_architecture(limit=1))
    print(f"  返回模块数={len(arch1['modules'])} truncated={arch1['truncated']}")

    print("\n" + "=" * 72)
    print(f"[3] get_module('{util_path}')  含类方法与反向依赖")
    print("=" * 72)
    mod = json.loads(await get_module(util_path))
    print(f"  ok={mod['ok']} symbols={[(s['name'], s['kind']) for s in mod['symbols']]}")
    box = next(s for s in mod["symbols"] if s["name"] == "Box")
    print(f"  Box.methods={box['methods']}")
    print(f"  depended_by={mod['depended_by']} (期望 ['{main_path}'])")

    print("\n" + "=" * 72)
    print("[3b] get_module('util.py') 唯一同名时自动补全路径")
    print("=" * 72)
    byname = json.loads(await get_module("util.py"))
    print(f"  只给文件名 -> ok={byname['ok']} path={byname.get('path')}")

    print("\n" + "=" * 72)
    print("[4] get_module 路径容错（workspace/ 前缀）")
    print("=" * 72)
    m2 = json.loads(await get_module(f"workspace/{util_path}"))
    print(f"  workspace/ 前缀 -> ok={m2['ok']} path={m2.get('path')}")

    print("\n" + "=" * 72)
    print("[5] get_module 不存在时应给出候选")
    print("=" * 72)
    bad = json.loads(await get_module("nope.py"))
    print(f"  ok={bad['ok']} error={bad['error']}")
    print(f"  available 含 {util_path}: {util_path in bad['available']}")

    print("\n" + "=" * 72)
    print("[6] find_symbol")
    print("=" * 72)
    fs = json.loads(await find_symbol("clamp"))
    print(f"  found={fs['found']} defs={fs['definitions']}")
    miss = json.loads(await find_symbol("does_not_exist"))
    print(f"  未实现时才是 found={miss['found']}（这是正常的“还没写”，不是错误）")
    empty = json.loads(await find_symbol(""))
    print(f"  空名字: ok={empty['ok']} error={empty['error']}")

    # 只统计本测试自己创建的模块：workspace 里可能有别的残留文件
    # （其它测试或上一次跑批留下的），不能假设 workspace 是空的。
    test_modules = [m for m in arch["modules"] if m["path"].startswith(PREFIX)]

    checks = [
        ("get_architecture 找到本测试的两个模块",
         {m["path"] for m in test_modules} == {util_path, main_path}),
        ("util 导出 clamp 与 Box",
         {e.split("(")[0] for e in next(
             m for m in test_modules if m["path"] == util_path)["exports"]}
         == {"clamp", "Box"}),
        ("main_app 依赖 util",
         next(m for m in test_modules if m["path"] == main_path)["depends_on"]
         == [f"{PREFIX}util"]),
        ("limit 生效且标记截断", len(arch1["modules"]) == 1 and arch1["truncated"] is True),
        ("get_module 解析类方法", "get(self)" in box["methods"]),
        ("get_module 反向依赖正确", mod["depended_by"] == [main_path]),
        ("get_module 唯一同名自动补全", byname["ok"] is True and byname["path"] == util_path),
        ("get_module 路径归一化", m2["ok"] is True and m2["path"] == util_path),
        ("get_module 缺失时给候选", bad["ok"] is False and util_path in bad["available"]),
        ("find_symbol 命中", fs["found"] is True and fs["definitions"][0]["path"] == util_path),
        ("find_symbol 未命中不算错误", miss["ok"] is True and miss["found"] is False),
        ("find_symbol 空名字报错", empty["ok"] is False),
        ("结果均为合法 JSON", all(isinstance(x, dict) for x in (arch, mod, fs))),
    ]

    cleanup()

    print("\n" + "=" * 72)
    print("断言检查")
    print("=" * 72)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
