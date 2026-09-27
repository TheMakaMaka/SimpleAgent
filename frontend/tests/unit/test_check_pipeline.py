"""验证 CheckPipeline + Checkpoint 的行为（不调用 LLM）。"""

import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core import CheckPipeline, CheckpointManager, VerifyCommand  # noqa: E402


def w(rel: str, content: str) -> None:
    p = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def rm(rel: str) -> None:
    p = os.path.join(WS, rel)
    if os.path.exists(p):
        os.remove(p)


async def main():
    pipe = CheckPipeline()
    print("=" * 60)

    # --- 1. 语法检查必须拦住坏代码 ---
    w("_t_bad.py", "def f(:\n    pass\n")
    r = await pipe.run_check(["_t_bad.py"])
    print(f"[1] 坏语法  passed={r['passed']} (期望 False) blocking={r['blocking_file']}")

    # --- 2. 好代码应通过 ---
    w("_t_good.py", "def add(a, b):\n    return a + b\n")
    r = await pipe.run_check(["_t_good.py"])
    lint_status = [
        s.get("status") for s in r["steps"] if s.get("tool") == "run_lint"
    ]
    print(f"[2] 好语法  passed={r['passed']} (期望 True) lint={lint_status} (期望 ['skipped'])")

    # --- 3. 非 py 文件不参与检查 ---
    r = await pipe.run_check(["readme.md"])
    print(f"[3] 非py    passed={r['passed']} reason={r.get('skipped_reason')}")

    # --- 4. verify 通过 ---
    v = await pipe.run_verify(VerifyCommand(command="print('PASS')"))
    print(f"[4] verify通过 passed={v['passed']} (期望 True)")

    # --- 5. verify 断言失败必须判不通过 ---
    v = await pipe.run_verify(VerifyCommand(command="assert 1 == 2, 'boom'"))
    err = (v.get("parsed") or {}).get("parsed_error") or {}
    print(f"[5] verify断言失败 passed={v['passed']} (期望 False) type={err.get('error_type')}")

    # --- 6. verify 没有 print 但退出码 0 也算通过 ---
    v = await pipe.run_verify(VerifyCommand(command="x = 1 + 1"))
    print(f"[6] verify无输出 passed={v['passed']} (期望 True，因为退出码=0)")

    # --- 7. 空 verify 命令必须判不通过 ---
    v = await pipe.run_verify(VerifyCommand(command="   "))
    print(f"[7] verify空   passed={v['passed']} (期望 False)")

    # --- 8. 检查点：提交 → 改坏 → 回退 ---
    print("=" * 60)
    ck = CheckpointManager()
    print(f"[8] backend={ck.name}")
    w("_t_rb.py", "ORIGINAL = 1\n")
    cp = ck.commit("baseline-test")
    print(f"    提交 baseline ref={cp.ref if cp else None}")
    w("_t_rb.py", "BROKEN = 999\n")
    w("_t_new.py", "NEW = 1\n")
    ok = ck.rollback(cp.ref)
    with open(os.path.join(WS, "_t_rb.py"), encoding="utf-8") as f:
        content = f.read().strip()
    print(f"    回退={ok} 内容={content!r} (期望 'ORIGINAL = 1')")
    print(f"    新增文件已清除={not os.path.exists(os.path.join(WS, '_t_new.py'))} (期望 True)")

    # 清理
    for f in ("_t_bad.py", "_t_good.py", "_t_rb.py"):
        rm(f)
    print("=" * 60)
    print("完成")


asyncio.run(main())
