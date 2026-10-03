"""`REUSE-SYMBOL-SCOPE`（P7b）探针 —— **新判据版**。

统筹方的原脚本（`SimpleAgent2_Integration/04-tests/cases/probe_p7_symbol_collision.py`）
是**复现脚本**：它的"预期"是"A 有误判、B 无误判"。
修好之后那个预期**不再成立**，所以这里按新判据重写：

    A（工作区里有同名 `app.py`）与 B（没有）**都应当 0 条 blocking**，
    并且**两种工作区下结论一致**。

脚本**自证实验是否有效**：若 A 与 B 都不为 0，或 A/B 不一致，就退出码 1。
另外附上"名字撞车不止 app"的样例与"真错仍须红"的反空洞样例。

用法：`python tests/diagnostics/probe_symbol_scope.py`
"""

import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from core.reuse_checks import BLOCKING_KINDS, check_code  # noqa: E402

WS = os.path.join(REPO, "workspace")

FLASK_APP = (
    "from flask import Flask\n"
    "\n"
    "app = Flask(__name__)\n"
    "\n"
    "@app.route('/ping', methods=['GET'])\n"
    "def ping():\n"
    "    return 'Pong!'\n"
)
KEEP = ("_tmp", "_debug", "__pycache__", ".git")


def clean() -> None:
    os.makedirs(WS, exist_ok=True)
    for n in os.listdir(WS):
        if n in KEEP:
            continue
        p = os.path.join(WS, n)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def put(rel: str, content: str) -> None:
    with open(os.path.join(WS, rel), "w", encoding="utf-8") as f:
        f.write(content)


def probe(files: dict, code: str, label: str = "mod.py") -> list:
    clean()
    for rel, c in files.items():
        put(rel, c)
    found, _refs = check_code(code, label=label)
    return [v for v in found if v.get("kind") in BLOCKING_KINDS]


def main() -> int:
    checks: list[tuple[str, bool]] = []

    print("=" * 78)
    print("P7b 复现（新判据）：同一份**正确**的 Flask 代码，两种工作区")
    print("=" * 78)
    print("被测代码（模型写的正确 Flask）：")
    for line in FLASK_APP.splitlines():
        print("    " + line)
    a = probe({"app.py": FLASK_APP}, FLASK_APP)
    b = probe({}, FLASK_APP)
    print(f"\n  A) 工作区里**有** app.py（模型自己刚写的） → blocking={len(a)}")
    for v in a:
        print(f"      [blocking] {v['message'][:96]}")
    print(f"  B) 工作区里**没有** app.py            → blocking={len(b)}")
    for v in b:
        print(f"      [blocking] {v['message'][:96]}")
    checks.append(("A 不再误判（0 条 blocking）", not a))
    checks.append(("B 仍是 0（对照组）", not b))
    checks.append(("★ 两种工作区结论**一致**（原缺陷的症候就是不一致）", len(a) == len(b)))

    print("\n" + "=" * 78)
    print("名字撞车不止 app")
    print("=" * 78)
    for name in ("app", "data", "utils", "config", "main"):
        got = probe({f"{name}.py": "x = 1\n"}, f"{name} = 1\n{name}.anything()\n")
        print(f"  变量 {name} 撞模块 {name}.py → blocking={len(got)}")
        checks.append((f"不误判：变量 {name} 撞模块 {name}.py", not got))
    for tag, code in (("self 属性", "class C:\n    def f(self):\n        return self.db.execute()\n"),
                      ("参数属性", "def f(obj):\n    return obj.attr\n"),
                      ("with as", "def f():\n    with open('x') as fh:\n        return fh.read()\n")):
        got = probe({}, code)
        print(f"  {tag} → blocking={len(got)}")
        checks.append((f"不误判：{tag}", not got))

    print("\n" + "=" * 78)
    print("★ 反空洞：真实的「调用了不存在的符号」必须**仍然红**")
    print("=" * 78)
    anti = [
        ("np.array 但没 import numpy",
         "def f():\n    return np.array([1])\n", {}, "undefined-name"),
        ("from mylib import f（mylib 里只有 g）",
         "from mylib import f\n", {"mylib.py": "def g():\n    return 1\n"},
         "undefined-symbol"),
        ("t1.py 有 foo，t2.py 调 t1.bar", "import t1\nt1.bar()\n",
         {"t1.py": "def foo():\n    return 1\n"}, "undefined-symbol"),
    ]
    for tag, code, files, want in anti:
        got = probe(files, code, label="criterion")
        kinds = [v["kind"] for v in got]
        print(f"  {'红' if want in kinds else '漏'}  {tag} → {kinds}")
        checks.append((f"仍然红：{tag}（{want}）", want in kinds))

    clean()
    print("\n" + "=" * 78)
    print("断言")
    print("=" * 78)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
