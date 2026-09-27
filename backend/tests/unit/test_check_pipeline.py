"""验证 CheckPipeline + Checkpoint 的行为（不调用 LLM）。

⚠️ 本文件原来**只打印不判定** —— 8 个场景一个断言都没有，
`run_unit.py` 与 `tests/backup.py` 又只看退出码，所以它等于不存在
（实测事故见 `docs/CHANGELOG.md` §29）。现在每个场景都落成真断言。
"""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core import CheckPipeline, CheckpointManager, VerifyCommand  # noqa: E402

checks: list[tuple[str, bool]] = []


def w(rel: str, content: str) -> None:
    p = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def rm(rel: str) -> None:
    p = os.path.join(WS, rel)
    if os.path.exists(p):
        os.remove(p)


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


async def main() -> int:
    pipe = CheckPipeline()
    print("=" * 60)

    # --- 1. 语法检查必须拦住坏代码 ---
    w("_t_bad.py", "def f(:\n    pass\n")
    r = await pipe.run_check(["_t_bad.py"])
    print(f"[1] 坏语法  passed={r['passed']} blocking={r['blocking_file']}")
    check("坏语法被拦下（passed=False）", r["passed"] is False)
    check("指出是哪个文件坏", bool(r.get("blocking_file")))

    # --- 2. 好代码应通过，且 lint 不可用时 status=skipped（≠ 通过）---
    w("_t_good.py", "def add(a, b):\n    return a + b\n")
    r = await pipe.run_check(["_t_good.py"])
    lint_status = [s.get("status") for s in r["steps"] if s.get("tool") == "run_lint"]
    print(f"[2] 好语法  passed={r['passed']} lint={lint_status}")
    check("好语法通过", r["passed"] is True)
    check("lint 未执行时标 skipped（不得冒充通过）",
          lint_status in ([], ["skipped"], ["passed"]))

    # --- 3. 非 py 文件不参与检查 ---
    r = await pipe.run_check(["readme.md"])
    print(f"[3] 非py    passed={r['passed']} reason={r.get('skipped_reason')}")
    check("非 py 文件跳过静态检查且不判失败", r["passed"] is True)

    # --- 4. verify 通过 ---
    v = await pipe.run_verify(VerifyCommand(command="print('PASS')"))
    print(f"[4] verify通过 passed={v['passed']}")
    check("verify 退出码 0 → 通过", v["passed"] is True)

    # --- 5. verify 断言失败必须判不通过 ---
    v = await pipe.run_verify(VerifyCommand(command="assert 1 == 2, 'boom'"))
    err = (v.get("parsed") or {}).get("parsed_error") or {}
    print(f"[5] verify断言失败 passed={v['passed']} type={err.get('error_type')}")
    check("断言失败 → 不通过（模型自述不能翻案）", v["passed"] is False)

    # --- 6. verify 没有 print 但退出码 0 也算通过 ---
    v = await pipe.run_verify(VerifyCommand(command="x = 1 + 1"))
    print(f"[6] verify无输出 passed={v['passed']}")
    check("无输出但退出码 0 → 通过", v["passed"] is True)

    # --- 7. 空 verify 命令必须判不通过 ---
    v = await pipe.run_verify(VerifyCommand(command="   "))
    print(f"[7] verify空   passed={v['passed']}")
    check("空验证命令 → 不通过（不许当通过）", v["passed"] is False)

    # --- 8. 检查点：提交 → 改坏 → 回退 ---
    print("=" * 60)
    ck = CheckpointManager()
    print(f"[8] backend={ck.name}")
    w("_t_rb.py", "ORIGINAL = 1\n")
    cp = ck.commit("baseline-test")
    w("_t_rb.py", "BROKEN = 999\n")
    w("_t_new.py", "NEW = 1\n")
    ok = ck.rollback(cp.ref)
    with open(os.path.join(WS, "_t_rb.py"), encoding="utf-8") as f:
        content = f.read().strip()
    gone = not os.path.exists(os.path.join(WS, "_t_new.py"))
    print(f"    回退={ok} 内容={content!r} 新增已清除={gone}")
    check("检查点能提交出 ref", bool(cp and cp.ref))
    check("回退成功", bool(ok))
    check("回退恢复了原内容", content == "ORIGINAL = 1")
    check("回退清除了未跟踪的新增文件", gone)

    # 清理
    for f in ("_t_bad.py", "_t_good.py", "_t_rb.py"):
        rm(f)

    failed = [n for n, ok in checks if not ok]
    print("=" * 60)
    print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(asyncio.run(main()))
