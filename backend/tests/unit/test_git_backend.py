"""git 回退后端自检。

需要系统装好 git；未装时本测试会明确 skip（不算失败），
因为 snapshot 兜底后端是预期行为。
"""

import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import WORKSPACE as WS  # noqa: E402

from core import CheckpointManager  # noqa: E402
from core.checkpoint import _run_git, git_status, resolve_git  # noqa: E402


def w(rel: str, content: str) -> None:
    p = os.path.join(WS, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def r(rel: str) -> str | None:
    p = os.path.join(WS, rel)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return f.read()


def git(*args) -> tuple[int, str]:
    """走 backend 同一条路径（含 safe.directory 处理）。

    不要自己裸调 git：Git >= 2.35.2 对「属主与当前用户不一致」的仓库会拒绝操作，
    backend 已用命令行级 safe.directory 放行，测试必须复用同一逻辑，
    否则会得到与真实行为不符的假失败。
    """
    rc, out, err = _run_git(list(args), WS)
    return rc, (out or "") + (err or "")


def clean() -> None:
    for name in os.listdir(WS):
        if name in ("_tmp", "_debug", "__pycache__", ".git", ".gitignore"):
            continue
        p = os.path.join(WS, name)
        shutil.rmtree(p, ignore_errors=True) if os.path.isdir(p) else os.remove(p)


def main() -> int:
    st = git_status()
    print("=" * 72)
    print("git 状态")
    print("=" * 72)
    print(f"  可用      : {st['available']}")
    print(f"  可执行文件: {st['executable']}")
    print(f"  来自 PATH : {st['from_path']} {st['note']}")
    print(f"  版本      : {st['version']}")

    if not st["available"]:
        print("\n  SKIP: 系统未装 git，回退会走 snapshot 兜底（预期行为）")
        return 0

    clean()
    mgr = CheckpointManager()
    print(f"\n  选中的后端: {mgr.name}")

    checks: list[tuple[str, bool]] = [("后端选中 git", mgr.name == "git")]

    # ---- 基线提交 ----
    w("keep.py", "VALUE = 1\n")
    c1 = mgr.commit("baseline")
    checks.append(("baseline 提交成功", c1 is not None))
    print(f"\n  ① baseline -> {c1.ref[:10] if c1 else None}")

    # ---- 改动 + 第二次提交 ----
    w("keep.py", "VALUE = 2\n")
    w("extra.py", "EXTRA = True\n")
    c2 = mgr.commit("second")
    checks.append(("第二次提交成功", c2 is not None and c2.ref != c1.ref))
    print(f"  ② second   -> {c2.ref[:10] if c2 else None}")

    # ---- 确认 git 历史是干净的（没有把 _tmp/_debug 提交进去）----
    rc, log = git("log", "--oneline")
    checks.append(("git log 有两条提交", len(log.strip().splitlines()) >= 2))
    rc, files = git("ls-files")
    tracked = files.split()
    checks.append(("已忽略 _tmp/_debug/.checkpoints",
                   not any(t.startswith(("_tmp", "_debug", ".checkpoints")) for t in tracked)))
    print(f"  ③ 追踪文件: {tracked}")
    print(f"     git log: {log.strip().splitlines()[:2]}")

    # ---- 回退到 baseline ----
    ok = mgr.rollback(c1.ref)
    checks.append(("回退返回 True", ok))
    checks.append(("keep.py 内容回到 V1", (r("keep.py") or "").strip() == "VALUE = 1"))
    checks.append(("新增的 extra.py 被清除", r("extra.py") is None))
    print(f"  ④ 回退到 baseline: ok={ok}")
    print(f"     keep.py = {(r('keep.py') or '').strip()!r}  extra.py exists={r('extra.py') is not None}")

    # ---- 回退后 HEAD 应指向 baseline ----
    rc, head = git("rev-parse", "HEAD")
    checks.append(("HEAD 指向 baseline", head.strip() == c1.ref))
    print(f"  ⑤ HEAD = {head.strip()[:10]} (期望 {c1.ref[:10]})")

    # ---- 工作区应干净 ----
    rc, status = git("status", "--porcelain")
    checks.append(("回退后工作区干净", not status.strip()))
    print(f"  ⑥ git status: {status.strip() or '(clean)'}")

    # ---- 幂等：重复提交同内容不应炸 ----
    c3 = mgr.commit("no-change")
    checks.append(("无改动时提交不抛异常", c3 is not None))
    print(f"  ⑦ 无改动提交 -> {c3.ref[:10] if c3 else None}")

    clean()
    print("\n" + "=" * 72)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


raise SystemExit(main())
