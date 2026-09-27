"""A2b：**bundled 即拒绝启动**（架构清单 A2b）。

为什么这条要单独测，而且必须用**子进程**
----------------------------------------
A2 的目标是「不删副本，但**让它无法被静默使用**」。事实是它**被静默使用了约 10 轮** ——
启动警告没人看见、探针字段没人去看、上游所有修复一条都没生效。
**「可见」被当成了「足够」，而它不够。**

所以 A2b 把"警告"换成"拒绝"。这条的验收标准里有一条明确写着：

> **负向测试**：断言"拒绝启动"**真的发生** —— 一个只打警告的实现不得通过。

因此这个测试**不能**只断言"有个函数返回 True"。它要**真的起一个进程**，
断言：**进程退出码非 0、且端口没被监听**。只打警告的实现会在这里红。

为什么子进程要**删掉** `AGENT_ALLOW_BUNDLED`
--------------------------------------------
`tests/_bootstrap.py` 会设它（测试要 in-process 拿 `app` 对象；import ≠ 起服务）。
所以负向测试必须把那个变量从**子进程环境**里去掉 —— 否则测的是逃生舱那条路。

运行：python tests/unit/test_bundled_gate.py
"""

import os
import socket
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge import staleness  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


PY = sys.executable
BUNDLED = os.path.join(ROOT, "backend")
RUNTIME = os.path.join(os.environ.get("TEMP", "/tmp"), "sa2_a2b_test_rt")


def child_env(*, allow_bundled: bool, backend_dir: str | None) -> dict:
    e = dict(os.environ)
    e["AGENT_RUNTIME_ROOT"] = RUNTIME
    e["PYTHONIOENCODING"] = "utf-8"
    # ★ 必须显式控制这两个：不控制的话，"测试导入用"的逃生舱会漏进子进程
    e.pop("AGENT_ALLOW_BUNDLED", None)
    e.pop("AGENT_BACKEND_DIR", None)
    if allow_bundled:
        e["AGENT_ALLOW_BUNDLED"] = "1"
    if backend_dir:
        e["AGENT_BACKEND_DIR"] = backend_dir
    return e


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_uvicorn(port: int, env: dict, timeout: float = 45.0):
    """起一个 uvicorn 子进程；返回 (returncode, stdout+stderr, 进程)。

    返回的进程若还活着，调用方负责 kill。
    """
    proc = subprocess.Popen(
        [PY, "-m", "uvicorn", "bridge.app:app",
         "--host", "127.0.0.1", "--port", str(port), "--app-dir", ROOT],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out, proc
    except subprocess.TimeoutExpired:
        return None, "", proc


# ============================================================
print("=" * 74)
print("[1] 纯函数：判据是**形态**（is_bundled），不是状态（stale）")
print("=" * 74)
bundled = staleness.probe(BUNDLED)
check("自带副本的 probe 认得 is_bundled=True", bundled["is_bundled"] is True,
      str(bundled["is_bundled"]))
check("★ bundled → 该拒绝", staleness.should_refuse(bundled, allow=False) is True)
check("★ 逃生舱 → 不拒绝", staleness.should_refuse(bundled, allow=True) is False)

# 造一个"恰好同步"的假上游：**它不 stale，但仍应被拒** ——
# 这就是"判形态不判状态"的可执行表述。
import shutil  # noqa: E402
import tempfile  # noqa: E402

fake = tempfile.mkdtemp(prefix="sa2_fake_synced_")
try:
    os.makedirs(os.path.join(fake, "core"), exist_ok=True)
    for name in ("contract.py", "vision.py", "cycle.py"):
        with open(os.path.join(fake, "core", name), "w", encoding="utf-8") as f:
            f.write('CONTRACT_VERSION = "9.9"\n')
    synced = staleness.probe(fake)
    check("假的'同步'目录：stale=False（标记齐备）", synced["stale"] is False,
          str(synced["reasons"]))
    check("★ 它不是 bundled → 不该拒绝（判形态）",
          staleness.should_refuse(synced, allow=False) is False)
    check("★ 而只要它是 bundled，即使 stale=False 也要拒 —— "
          "本项用 bundled 目录验证该分支",
          staleness.should_refuse(
              {**bundled, "stale": False}, allow=False) is True,
          "should_refuse 只看 is_bundled")

    # 拒绝文本必须含三件事
    msg = staleness.refusal_message(bundled)
    check("拒绝文本含**实际 backend_dir**", bundled["backend_dir"] in msg)
    check("★ 拒绝文本含**带后果的**陈旧理由（不只是'缺文件'）",
          "静默" in msg or "不可用" in msg, msg[:0] or "见理由段")
    check("★ 拒绝文本含**可复制的修复命令**（AGENT_BACKEND_DIR=）",
          "AGENT_BACKEND_DIR=" in msg)
    check("拒绝文本给出逃生舱用法", staleness.ALLOW_BUNDLED_FLAG in msg
          or staleness.ALLOW_BUNDLED_ENV in msg)
    check("拒绝文本点明「降级必须留痕」", "留痕" in msg)
finally:
    shutil.rmtree(fake, ignore_errors=True)

check("逃生舱识别：环境变量",
      staleness.allow_bundled_requested([]) is True,
      "(本进程内 _bootstrap 已设为 1)")
check("逃生舱识别：命令行 flag",
      staleness.allow_bundled_requested(["--allow-bundled"]) is True)

# 「没给逃生舱」必须**在没有环境变量**的前提下测 ——
# `_bootstrap` 给本进程设了 `AGENT_ALLOW_BUNDLED=1`（测试要 in-process 拿 app），
# 不摘掉它的话这里测的是环境变量那条路，不是 flag 解析。
import unittest.mock as _mock  # noqa: E402

with _mock.patch.dict(os.environ, {}, clear=False):
    os.environ.pop("AGENT_ALLOW_BUNDLED", None)
    check("★ 没给逃生舱时为 False（环境变量已摘掉）",
          staleness.allow_bundled_requested([]) is False,
          str(staleness.allow_bundled_requested([])))
    check("★ 摘掉环境变量后，只有 flag 才放行",
          staleness.allow_bundled_requested(["--port", "1"]) is False
          and staleness.allow_bundled_requested(["--port", "1",
                                                 "--allow-bundled"]) is True)
    check("★ 环境变量与 flag 任一即可（两条路都认）",
          (os.environ.__setitem__("AGENT_ALLOW_BUNDLED", "1") or True)
          and staleness.allow_bundled_requested([]) is True)


# ============================================================
print("\n" + "=" * 74)
print("[2] ★★ 负向测试：真的起进程，断言**拒绝启动发生了**")
print("=" * 74)
port = free_port()
check(f"端口 {port} 起前空闲", port_free(port))
t0 = time.time()
rc, out, proc = run_uvicorn(port, child_env(allow_bundled=False, backend_dir=None))
elapsed = time.time() - t0

check("★ 进程**退出了**（不是还在跑）", rc is not None,
      "" if rc is not None else f"仍在运行（{elapsed:.1f}s）—— 只打警告的实现会卡在这里")
check(f"★ 退出码非 0（实测 {rc}）", rc is not None and rc != 0, str(rc))
check("★★ 端口**没有被监听**", port_free(port),
      "" if port_free(port) else "端口被监听了 —— 说明只是警告，没有真的拒绝")
check("拒绝输出含 backend_dir", BUNDLED in out, out[:0] or "")
check("★ 拒绝输出含带后果的理由",
      "core/contract.py" in out and ("静默" in out or "不可用" in out))
check("★ 拒绝输出含可复制的修复命令", "AGENT_BACKEND_DIR=" in out)
check("退出很快（不是先起来再关）", elapsed < 30, f"{elapsed:.1f}s")
if proc.poll() is None:
    proc.kill()


# ============================================================
print("\n" + "=" * 74)
print("[3] 逃生舱：`--allow-bundled` 能起，且**留痕**")
print("=" * 74)
port2 = free_port()
proc2 = subprocess.Popen(
    [PY, "-m", "bridge", "--allow-bundled", "--port", str(port2)],
    cwd=ROOT, env=child_env(allow_bundled=False, backend_dir=None),
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True, encoding="utf-8", errors="replace",
)
started = False
try:
    for _ in range(40):
        time.sleep(1)
        if not port_free(port2):
            started = True
            break
        if proc2.poll() is not None:
            break
    check("★ `python -m bridge --allow-bundled` 起来了（端口在听）", started,
          "" if started else ("进程提前退出" if proc2.poll() is not None else "超时"))

    if started:
        import json
        import urllib.request

        with urllib.request.urlopen(
                f"http://127.0.0.1:{port2}/api/health", timeout=10) as r:
            h = json.loads(r.read().decode("utf-8"))
        check("★★ /api/health 报 backend_bundled_override=true",
              h.get("backend_bundled_override") is True,
              str(h.get("backend_bundled_override")))
        check("同时仍如实报 backend_is_bundled=true",
              h.get("backend_is_bundled") is True, str(h.get("backend_is_bundled")))
        check("★ /api/health 含 frontend_asset",
              isinstance(h.get("frontend_asset"), str) and bool(h["frontend_asset"]),
              str(h.get("frontend_asset")))
        check("★ frontend_asset == dist/index.html 引用的那个 bundle",
              h.get("frontend_asset") == staleness.frontend_asset(),
              f"{h.get('frontend_asset')} vs {staleness.frontend_asset()}")
        check("backend_dir 也暴露了", bool(h.get("backend_dir")),
              str(h.get("backend_dir")))
    else:
        for name in ("/api/health 报 backend_bundled_override=true",
                     "同时仍如实报 backend_is_bundled=true",
                     "/api/health 含 frontend_asset",
                     "frontend_asset == dist/index.html 引用的那个 bundle",
                     "backend_dir 也暴露了"):
            check(name, False, "实例没起来，无法断言")
finally:
    try:
        proc2.kill()
        proc2.wait(timeout=10)
    except Exception:  # noqa: BLE001
        pass


# ============================================================
print("\n" + "=" * 74)
print("[4] 指向上游时**不该**被拒（别把闸门做成恒真）")
print("=" * 74)
upstream = os.environ.get("AGENT_BACKEND_DIR", "").strip()
if upstream and os.path.isdir(upstream):
    r = staleness.probe(upstream)
    check("★ 真上游：is_bundled=False → 不拒绝",
          r["is_bundled"] is False and staleness.should_refuse(r, allow=False) is False,
          f"bundled={r['is_bundled']} stale={r['stale']}")
else:
    print("  SKIP  未设 AGENT_BACKEND_DIR，没有真上游可比")
    print("       （闸门「只在 bundled 时拒」这点由 [1] 的假目录断言覆盖）")

check("★ 闸门不是恒真：非 bundled 目录一律放行",
      staleness.should_refuse(staleness.probe(ROOT), allow=False) is False,
      "仓库根不是上游目录，probe 不会判成 bundled")


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
