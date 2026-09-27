"""上游副本陈旧检测（架构清单 **A2** / **A3**）。

为什么值得单测
--------------
`VueWeb/backend/` 是一份**过期副本**，实测缺 `core/contract.py` 与 `core/vision.py`，
另有 9 个 `core` 模块与上游不一致。缺 `contract.py` 的后果最隐蔽：

    新契约机制（CONTRACT_VERSION / ISSUE_RULES / /contract/check）整体不可用
    而 **服务照常启动、界面照常显示、没有任何一处报错**

**不报错的失效最难查。** A2 就是治它：把"我在用哪份上游、它落后在哪"变成
显式且被检查的事实。所以这个测试的重点不是"能探到"，而是
**负向**：指向一份坏掉的上游时，它必须**真的报出来**——
一个恒真的探针等于没有探针。

A3 的判据也在这里钉住：**判据是 `paths.BACKEND_DIR`，不是"import 到了 core 就算对"**
（仓库里有两个同名 `core` 包，import 成功只说明 `sys.path` 里有它）。

运行：python tests/unit/test_staleness.py
"""

import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge import paths, staleness  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def make_fake_upstream(with_contract: bool, with_vision: bool = True,
                       cv: str = "1.0") -> str:
    """造一份"假上游"：可控地决定它缺什么。"""
    d = tempfile.mkdtemp(prefix="sa2_fake_up_")
    core = os.path.join(d, "core")
    os.makedirs(core, exist_ok=True)
    with open(os.path.join(core, "cycle.py"), "w", encoding="utf-8") as f:
        f.write("PHASE_ORDER = []\n")
    if with_contract:
        with open(os.path.join(core, "contract.py"), "w", encoding="utf-8") as f:
            f.write(f'"""契约。"""\nCONTRACT_VERSION = "{cv}"  # 快照版本\n')
    if with_vision:
        with open(os.path.join(core, "vision.py"), "w", encoding="utf-8") as f:
            f.write('"""视觉。"""\n')
    return d


temps: list[str] = []


# ============================================================
print("=" * 74)
print("[1] 仓库自带的副本：必须被认出是 bundled，且报出落后")
print("=" * 74)
r = staleness.probe(os.path.join(ROOT, "backend"))
check("认得这是仓库自带的副本（bundled）", r["is_bundled"] is True, str(r["is_bundled"]))
check("★ 报出落后（缺 core/contract.py）", r["stale"] is True, r["summary"][:80])
check("落后原因里点名 core/contract.py",
      "core/contract.py" in " ".join(r["reasons"]), str(r["reasons"])[:120])
check("落后原因里说明了**后果**（不是只报缺文件）",
      "静默" in " ".join(r["reasons"]), str(r["reasons"])[:160])
check("CONTRACT_VERSION 读不到 → 记录为不可读",
      r["contract_version_readable"] is False and r["contract_version"] == "",
      r["contract_version"])
check("core 模块数被记下", r["core_module_count"] > 0, str(r["core_module_count"]))
check("markers 结构齐备",
      all({"file", "what", "present", "consequence"} <= set(m) for m in r["markers"]))

w = staleness.startup_warning(r)
check("★ bundled 模式产生启动警告", bool(w))
check("★ 警告文本可被断言（返回字符串而不是直接 print）",
      isinstance(w, str) and "仓库自带" in w and "AGENT_BACKEND_DIR" in w, (w or "")[:60])
check("警告里给出可执行的下一步（体检命令）",
      "doctor.py" in (w or "") and "/api/health" in (w or ""))
check("警告里报出 core 模块数与契约版本",
      "core 模块" in (w or "") and "CONTRACT_VERSION" in (w or ""))


# ============================================================
print("\n" + "=" * 74)
print("[2] ★ 负向测试：指向一份坏掉的上游 → 必须真的报落后")
print("=" * 74)
bad = make_fake_upstream(with_contract=False)
temps.append(bad)
rb = staleness.probe(bad)
check("缺 core/contract.py → stale", rb["stale"] is True, rb["summary"][:80])
check("★ 原因里点名 core/contract.py",
      any("core/contract.py" in x for x in rb["reasons"]), str(rb["reasons"])[:120])
check("不是 bundled（外部路径）", rb["is_bundled"] is False)
check("契约版本不可读", rb["contract_version_readable"] is False)
check("启动警告包含「陈旧检测」", "陈旧检测" in (staleness.startup_warning(rb) or ""))

# 空目录（连 core/ 都没有）也要报，而不是当成功
empty = tempfile.mkdtemp(prefix="sa2_empty_")
temps.append(empty)
re_ = staleness.probe(empty)
check("★ 连 core/ 都没有 → 报落后（不是静默通过）", re_["stale"] is True, re_["summary"][:60])
check("说明这不是上游代码",
      any("core/" in x or "不存在" in x for x in re_["reasons"]), str(re_["reasons"])[:80])

# 不存在的目录
nx = staleness.probe(os.path.join(tempfile.gettempdir(), "sa2_no_such_dir_xyz"))
check("★ 目录不存在 → 报落后", nx["stale"] is True, nx["summary"][:60])
check("目录不存在时模块数为 0", nx["core_module_count"] == 0)


# ============================================================
print("\n" + "=" * 74)
print("[3] 健康的一份上游：不许误报")
print("=" * 74)
good = make_fake_upstream(with_contract=True, cv="2.5")
temps.append(good)
rg = staleness.probe(good)
check("★ 标记齐备 → 不报落后（探针不是恒真）", rg["stale"] is False, rg["summary"])
check("读出了 CONTRACT_VERSION", rg["contract_version"] == "2.5", rg["contract_version"])
check("注释没被当成版本值（只取字面量）", "#" not in rg["contract_version"],
      rg["contract_version"])
check("★ 健康且非 bundled → 没有启动警告",
      staleness.startup_warning(rg) is None, str(staleness.startup_warning(rg)))

# 缺 vision 但 contract 在 → 仍然报（两个标记各自独立）
half = make_fake_upstream(with_contract=True, with_vision=False)
temps.append(half)
rh = staleness.probe(half)
check("★ 缺 core/vision.py 也报（标记各自独立）", rh["stale"] is True, rh["summary"][:60])
check("但不影响契约版本可读", rh["contract_version_readable"] is True)

# 真实的完整上游
real = os.getenv("AGENT_BACKEND_DIR", "").strip()
if real and os.path.isdir(real):
    rr = staleness.probe(real)
    check(f"真实上游 {real} 未被误判为落后", rr["stale"] is False, rr["summary"][:80])
    check("真实上游能读到 CONTRACT_VERSION", rr["contract_version_readable"] is True)
else:
    print("       （未设 AGENT_BACKEND_DIR，跳过真实上游那两条）")


# ============================================================
print("\n" + "=" * 74)
print("[4] 与参照物对比（可选能力）")
print("=" * 74)
full = make_fake_upstream(with_contract=True)
temps.append(full)
for extra in ("task.py", "memory.py"):
    with open(os.path.join(full, "core", extra), "w", encoding="utf-8") as f:
        f.write("x = 1\n")
# 用"完整版"当参照，看"残缺版"少什么
part = make_fake_upstream(with_contract=True)
temps.append(part)
rp = staleness.probe(part, reference_dir=full)
check("★ 给出了比参照物少的模块清单",
      set(rp["missing_vs_reference"]) == {"task.py", "memory.py"},
      str(rp["missing_vs_reference"]))
check("参照物模块数被记下", rp["reference_module_count"] >= 4,
      str(rp["reference_module_count"]))
check("比参照物少也算落后", rp["stale"] is True, rp["summary"][:80])
check("不给参照物时不报这项（不猜）",
      not staleness.probe(part)["missing_vs_reference"])
check("参照物环境变量读得到（未设时为空串）",
      staleness.reference_dir_from_env() == os.getenv("AGENT_UPSTREAM_DIR", "").strip())


# ============================================================
print("\n" + "=" * 74)
print("[5] A3：判据是 paths.BACKEND_DIR，不是「import 到了 core」")
print("=" * 74)
check("★ 探针默认取 paths.BACKEND_DIR",
      staleness.probe()["backend_dir"] == os.path.abspath(paths.BACKEND_DIR),
      staleness.probe()["backend_dir"])
check("★ bundled 的判据是路径相等（不是 sys.path 顺序）",
      staleness.probe(os.path.join(ROOT, "backend"))["is_bundled"] is True
      and staleness.probe(good)["is_bundled"] is False)
# 两个同名 core 包都在 sys.path 可达（backend/ 在 sys.path 里）——
# 所以"能 import core"完全不能说明用的是哪一份。
import core  # noqa: E402

check("★ 说明：本进程确实是能 import core 的（所以 import 成功不能当判据）",
      bool(getattr(core, "__file__", "")) or bool(dir(core)),
      "core 已可 import")


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
for d in temps:
    shutil.rmtree(d, ignore_errors=True)

failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
