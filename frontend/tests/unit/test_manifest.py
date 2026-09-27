"""symbol_index + manifest 自检。用 L8 的真实失败形态做验证。"""

import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core.manifest import (  # noqa: E402
    DeclaredFile, architecture_view, check_manifest, parse_declared,
)
from core.symbol_index import build_index, dangling_imports, find_symbol  # noqa: E402

TEST_DIR = os.path.join(WS, "_mtest")


def w(rel: str, content: str) -> None:
    p = os.path.join(TEST_DIR, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def main():
    shutil.rmtree(TEST_DIR, ignore_errors=True)
    os.makedirs(TEST_DIR, exist_ok=True)

    # ---------- 复刻 L8 的真实形态 ----------
    # storage.py 存在但内部调用不存在的函数；contacts.py 从未写出；
    # cli.py 存在但 run() 缺 args
    w("storage.py", (
        "import json\n"
        "\n"
        "def save(path, data):\n"
        "    with open(path, 'w') as f:\n"
        "        json.dump(data, f)\n"
        "\n"
        "def load(path):\n"
        "    try:\n"
        "        with open(path) as f:\n"
        "            return json.load(f)\n"
        "    except FileNotFoundError:\n"
        "        return {}\n"
    ))
    w("cli.py", (
        "import storage\n"
        "\n"
        "def run():\n"
        "    print(storage.__doc__)\n"
    ))
    w("helper.py", (
        "from . import nothere\n"      # 相对导入，无法解析
        "import brokenpkg.sub\n"      # 本地包成员缺失
        "\n"
        "class Util:\n"
        "    def do(self, x):\n"
        "        return x\n"
    ))
    w("brokenpkg/__init__.py", "")

    index = build_index(TEST_DIR)
    print("=" * 74)
    print("[1] 符号索引")
    print("=" * 74)
    for path, e in sorted(index.items()):
        syms = ", ".join(f"{s.signature}" for s in e.symbols) or "(无)"
        print(f"  {path:<16} module={e.module:<16} deps={e.local_deps}")
        print(f"  {'':<16} symbols: {syms}")

    print("\n" + "=" * 74)
    print("[2] find_symbol 反查")
    print("=" * 74)
    print("  find_symbol('save') ->", find_symbol(index, "save"))
    print("  find_symbol('Util') ->", [h['path'] for h in find_symbol(index, "Util")])

    print("\n" + "=" * 74)
    print("[3] 悬空导入检测")
    print("=" * 74)
    for d in dangling_imports(index):
        print(f"  {d}")

    print("\n" + "=" * 74)
    print("[4] manifest：声明 3 个文件，实际只写了 2 个")
    print("=" * 74)
    declared = parse_declared([
        {"path": "storage.py", "role": "JSON 持久化", "symbols": ["save", "load"]},
        {"path": "contacts.py", "role": "Contacts 类", "symbols": ["Contacts"]},
        {"path": "cli.py", "role": "命令行入口", "symbols": ["run"]},
    ])
    m = check_manifest(declared, index=index)
    print(f"  checked={m.checked} passed={m.passed} blocking={len(m.blocking)}")
    for v in m.violations:
        print(f"  [{v['severity']:<7}] {v['kind']:<20} {v.get('path') or v.get('from')} :: {v['message'][:50]}")

    print("\n  --- 喂给模型的紧凑陈述 ---")
    for ln in m.to_prompt().splitlines():
        print(f"  {ln}")

    print("\n" + "=" * 74)
    print("[5] 边界情形")
    print("=" * 74)
    # 5a 未声明 → 不做判定
    m0 = check_manifest([], index=index)
    print(f"  未声明清单: checked={m0.checked} passed={m0.passed} note={m0.note}")

    # 5b 全部齐备 → passed
    w("complete.py", "def alpha(x):\n    return x\n\nclass Beta:\n    def m(self):\n        return 1\n")
    idx2 = build_index(TEST_DIR)
    m1 = check_manifest(
        [DeclaredFile(path="complete.py", symbols=["alpha", "Beta"])], index=idx2
    )
    print(f"  齐备: passed={m1.passed} violations={len(m1.violations)}")

    # 5c 符号是类方法 → 也应被接受（run 可能是方法）
    m2 = check_manifest([DeclaredFile(path="complete.py", symbols=["m"])], index=idx2)
    print(f"  符号是类方法 m: passed={m2.passed} (期望 True)")

    # 5d 声明了不存在的符号
    m3 = check_manifest([DeclaredFile(path="complete.py", symbols=["nope"])], index=idx2)
    print(f"  符号缺失: passed={m3.passed} (期望 False) kinds={[v['kind'] for v in m3.violations if v['severity']=='error']}")

    # 5e 声明了语法坏掉的文件
    w("bad.py", "def f(:\n    pass\n")
    idx3 = build_index(TEST_DIR)
    m4 = check_manifest([DeclaredFile(path="bad.py", symbols=["f"])], index=idx3)
    print(f"  文件坏掉: kinds={[v['kind'] for v in m4.violations if v['severity']=='error']}")

    # 5f 容错：files 写成 dict / 字符串
    print("  dict 写法:", [d.path for d in parse_declared({"a.py": "角色A"})])
    print("  字符串写法:", [d.path for d in parse_declared(["b.py"])])
    print("  符号逗号分隔:", parse_declared([{"path": "c.py", "symbols": "x, y z"}])[0].symbols)

    # 5g 路径归一化：模型常写 workspace/ 前缀，必须与索引键对齐
    n1 = parse_declared([{"path": "workspace/d.py"}])[0].path
    n2 = parse_declared([{"path": "./e.py"}])[0].path
    n3 = parse_declared([{"path": "/workspace/f.py"}])[0].path
    n4 = parse_declared([{"path": "workspace\\g.py"}])[0].path
    print(f"  路径归一化: {n1!r} {n2!r} {n3!r} {n4!r} (期望 'd.py' 'e.py' 'f.py' 'g.py')")

    print("\n" + "=" * 74)
    print("[6] 架构视图（步骤 3 的数据来源）")
    print("=" * 74)
    av = architecture_view(idx3)
    print(f"  totals={av['totals']}")
    for mod in av["modules"][:4]:
        ex = ", ".join(e["signature"] for e in mod["exports"]) or "(无)"
        print(f"  {mod['path']:<14} exports=[{ex}]  depends_on={mod['depends_on']}")

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    err_kinds = {v["kind"] for v in m.violations if v["severity"] == "error"}
    checks = [
        ("索引到全部文件", len(index) == 4),
        ("解析出 storage.save/load", "save" in index["storage.py"].symbol_names()),
        ("解析出类方法", any(m.startswith("do(") for m in index["helper.py"].symbols[0].methods)),
        ("检出相对导入悬空", any(d["kind"] == "relative-import-unresolved" for d in dangling_imports(index))),
        ("检出包成员缺失", any(d["kind"] == "package-member-missing" for d in dangling_imports(index))),
        ("manifest 拦下缺失文件", "declared-missing" in err_kinds),
        ("manifest 拦下缺失符号", "symbol-missing" in {v["kind"] for v in m3.violations if v["severity"] == "error"}),
        ("manifest passed=False", m.passed is False),
        ("未声明时不判定", m0.checked is False),
        ("齐备时 passed", m1.passed is True),
        ("接受类方法作为符号", m2.passed is True),
        ("坏文件被拦", "declared-broken" in {v["kind"] for v in m4.violations}),
        ("dict 写法容错", [d.path for d in parse_declared({"a.py": "r"})] == ["a.py"]),
        ("逗号符号容错", parse_declared([{"path": "c.py", "symbols": "x, y z"}])[0].symbols == ["x", "y", "z"]),
        ("workspace/ 前缀归一化", n1 == "d.py"),
        ("./ 前缀归一化", n2 == "e.py"),
        ("绝对路径归一化", n3 == "f.py"),
        ("反斜杠归一化", n4 == "g.py"),
        ("架构视图有输出", av["totals"]["files"] == len(idx3)),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    shutil.rmtree(TEST_DIR, ignore_errors=True)


main()
