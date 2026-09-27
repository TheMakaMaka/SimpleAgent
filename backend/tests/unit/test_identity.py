"""代码身份（`core/identity.py`）的自检。

守什么
------
实测事故（`docs/CHANGELOG.md` §31）：用户反复失败而修复没生效 ——
前端加载的是**陈旧的自带副本**，而当时的运行记录里**没有任何字段**
能回答"这次跑的到底是哪一份代码"，定位只能靠 traceback 恰好带了路径。

于是加了 `code_dir` + **内容级指纹**。本测试守它三个性质：

  1. **稳定**：同一份代码连算两次相同（否则没法当判据）；
  2. **对内容敏感**：改一个字节就变（否则是摆设）；
  3. **只看代码**：改文档/测试**不应该**让指纹变化
     —— 指纹要回答"代码是哪一版"，不是"整个仓库变没变"。

外加接线检查：`cycle_start` 的**声明**必须带上这两个键
（真实发出由 `test_frontend_contract.py` 的 payload 对账守，
真实运行的记录由 `tests/diagnostics/repro_user_goal.py` 断言）。
"""

import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from core import contract  # noqa: E402
from core.identity import code_fingerprint, describe  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


def make_tree(tmp: str, marker: str = "x = 1\n") -> None:
    for sub in ("core", "tools", "storage", "web"):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)
    with open(os.path.join(tmp, "core", "a.py"), "w", encoding="utf-8") as f:
        f.write(marker)
    with open(os.path.join(tmp, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('hi')\n")


def main() -> int:
    print("=" * 74)
    print("[1] 稳定性与内容敏感性")
    print("=" * 74)
    fp1, fp2 = code_fingerprint(), code_fingerprint()
    print(f"  本仓库指纹: {fp1} / {fp2}")
    check("同一份代码连算两次相同（可作判据）", fp1 == fp2)
    check("指纹是 8 位十六进制", len(fp1) == 8 and all(c in "0123456789abcdef" for c in fp1))

    tmp = tempfile.mkdtemp(prefix="identity_")
    try:
        make_tree(tmp, "x = 1\n")
        a = code_fingerprint(tmp)
        make_tree(tmp, "x = 2\n")          # 只改一个字节
        b = code_fingerprint(tmp)
        print(f"  内容 v1 / v2: {a} / {b}")
        check("改一个字节 → 指纹变化（内容级判据真的有效）", a != b)

        # 3) 只看代码：加文档/测试不该改变指纹
        with open(os.path.join(tmp, "README.md"), "w", encoding="utf-8") as f:
            f.write("# doc\n")
        os.makedirs(os.path.join(tmp, "tests"), exist_ok=True)
        with open(os.path.join(tmp, "tests", "test_x.py"), "w", encoding="utf-8") as f:
            f.write("def test(): pass\n")
        c = code_fingerprint(tmp)
        print(f"  加文档与测试后: {c}")
        check("加文档/测试不影响指纹（指纹只回答『代码是哪一版』）", c == b)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 74)
    print("[2] 事实字段")
    print("=" * 74)
    d = describe()
    print(f"  code_dir      : {d['code_dir']}")
    print(f"  package_dir   : {d['package_dir']}")
    print(f"  fingerprint   : {d['fingerprint']}")
    print(f"  module_files  : {d['module_files']}")
    check("code_dir 是本仓库根（上游 checkout）",
          os.path.realpath(d["code_dir"]) == os.path.realpath(ROOT))
    check("package_dir 是 core/ 且与 code_dir 嵌套一致",
          os.path.basename(d["package_dir"]) == "core"
          and os.path.dirname(d["package_dir"]) == d["code_dir"])
    check("指纹与 describe() 里的一致", d["fingerprint"] == code_fingerprint())
    check("统计了参与指纹的代码文件数（>30）", d["module_files"] > 30)
    check("带一句给运维看的 note", bool(d.get("note")))

    print("\n" + "=" * 74)
    print("[3] 接线：cycle_start 必须声明这两个键")
    print("=" * 74)
    payload = set(contract.EVENTS["cycle_start"].payload)
    print(f"  cycle_start 声明的 payload: {sorted(payload)}")
    check("声明了 code_dir", "code_dir" in payload)
    check("声明了 code_fingerprint", "code_fingerprint" in payload)
    # `backend` 是**检查点后端**，不是代码来源 —— 这个区分容易搞混
    check("note 里点明了 backend ≠ 代码来源",
          "检查点后端" in contract.EVENTS["cycle_start"].note)

    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
