"""D6：把「双入口对拍」变成**常驻测试**。

守的是什么
----------
A1a 的全部承诺是一句话：**同一件事只有一个判据**。
它的验收标准是"对同一跨侧不一致，两个入口给出的 owner 归属一致"。

统筹方已经**亲手做过一次真对拍**（构造 `invented_event`，同时打两个入口，四项全同），
所以那条标准**当时**是满足的。但：

    **一次性对拍挡不住回归。**

只有把对拍变成常驻测试，那句承诺才有东西守着 —— 否则哪天
`_cross()` 被改回手写常量、或契约 JSON 读不到而静默回退到一张过期的镜像表，
**没有任何测试会红**。

为什么能在这里做（同进程双入口）
--------------------------------
`/api/audit` 是 bridge 自己的路由；`/contract/check` 是**上游**的路由
（`bridge/app.py` 把上游 app 与 bridge 路由合成同一个 app，所以两者在本进程内都可达）。

**关键约束**：`/contract/check` 只在上游**真的实现了它**时才存在 ——
仓库自带的 `backend/` 副本缺 `core/contract.py`，没有这个端点。
那种情况下这个测试**跳过**（不是失败）：跨侧对账按配置就不可能，
而"缺什么"已由 `bridge/staleness.py` 与 `test_staleness.py` 负责报出。

对拍的四项：`code` / `owner` / `severity` / `verdict`。

运行：python tests/unit/test_two_entrypoints.py
"""

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from bridge import staleness  # noqa: E402

checks: list[tuple[str, bool]] = []
skips: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def skip(name: str, why: str) -> None:
    skips.append((name, why))
    print(f"  SKIP  {name}   —— {why}")


# ============================================================
# 前置：两个入口在不在
# ============================================================
print("=" * 74)
print("[0] 两个入口可达吗")
print("=" * 74)

import bridge.bootstrap as bootstrap  # noqa: E402

bootstrap.install()

from fastapi.testclient import TestClient  # noqa: E402

import bridge.app as bridge_app  # noqa: E402

client = TestClient(bridge_app.app)

routes = {getattr(r, "path", "") for r in bridge_app.app.routes}
check("`/api/audit` 已注册（bridge 自己的入口）", "/api/audit" in routes,
      str(sorted(p for p in routes if "audit" in p or "contract" in p)))

probe = staleness.probe()
has_upstream_recon = "/contract/check" in routes
if not has_upstream_recon:
    skip("上游 /contract/check 可达", probe["summary"][:90])
else:
    check("`/contract/check` 已注册（上游的跨侧入口）", True)

if not has_upstream_recon:
    print()
    print("=" * 74)
    print("跳过原因")
    print("=" * 74)
    print(f"  当前上游：{probe['backend_dir']}")
    print(f"  is_bundled={probe['is_bundled']} stale={probe['stale']}")
    print(f"  {probe['summary']}")
    print()
    print("  跨侧对账需要上游实现 `/contract/check`；仓库自带的副本没有它。")
    print("  这不是失败 —— 缺什么由 bridge/staleness.py 负责报出。")
    print("  想跑这个测试：设 AGENT_BACKEND_DIR 指向最新上游 checkout。")
    print()
    print("  对拍在**离线**形式下仍有覆盖：tests/unit/test_audit_authority.py")
    print("  断言「每条跨侧判定的 (owner, severity) 都等于契约」。")
    print(f"\n通过 {len(checks) - 0}/{len(checks)} · SKIP {len(skips)}")
    raise SystemExit(0)


# ============================================================
# 构造一个**双方都看得见**的跨侧不一致
# ============================================================
spec = client.get("/api/spec").json()
upstream_events = spec["event_partition"]["upstream"]
upstream_phases = spec["pipeline"]["upstream_phases"]

# 上报体：故意漏掉一个上游事件 + 凭空多画一个阶段 + 契约版本落后
report = {
    "contract_version": spec["implements_contract_version"],
    "schema_version": spec["schema_version"],
    "upstream_event_kinds": upstream_events[:-1],        # 漏一个 → P-event-unknown-to-frontend
    "frontend_event_kinds": [],
    "phases": list(upstream_phases) + ["invented_phase"],  # 多一个 → P-phase-unknown
    "bridge_gate_steps": list(spec["pipeline"]["bridge_gate_steps"]),
    "frontend_endpoints": list(spec["endpoints"].keys()),
    "upstream_endpoints": list(spec["endpoint_partition"]["upstream"]),
}

print("\n" + "=" * 74)
print("[1] 同时打两个入口")
print("=" * 74)
r_local = client.post("/api/audit", json=report)
r_up = client.post("/contract/check", json=report)
check("本地 /api/audit 200", r_local.status_code == 200, str(r_local.status_code))
check("上游 /contract/check 200", r_up.status_code == 200, str(r_up.status_code))
if r_local.status_code != 200 or r_up.status_code != 200:
    print(f"\n  body(local)={r_local.text[:200]}")
    print(f"  body(up)   ={r_up.text[:200]}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    raise SystemExit(1)

local = r_local.json()
up = r_up.json()


def flatten(payload: dict) -> dict:
    """把两个入口的 issues 摊成 `{code: {owner, severity}}`。

    形状不同（本地 `responsibility.<owner>[]`，上游 `issues[]`），
    但**内容应当一致** —— 这正是 A1a 要的。
    """
    out: dict[str, dict] = {}
    if "responsibility" in payload:
        rows = [i for items in payload["responsibility"].values() for i in items]
    else:
        rows = payload.get("issues") or []
    for i in rows:
        code = i.get("code") or i.get("id")
        if code:
            out.setdefault(code, {"owner": i.get("owner"),
                                  "severity": i.get("severity")})
    return out


lo, upo = flatten(local), flatten(up)
common = sorted(set(lo) & set(upo))

print(f"       本地 {len(lo)} 条 · 上游 {len(upo)} 条 · 共有 code {len(common)} 条")
for c in common:
    print(f"         {c:34s} 本地={lo[c]['owner']}/{lo[c]['severity']}"
          f"  上游={upo[c]['owner']}/{upo[c]['severity']}")

check("两边都报出了跨侧不一致（不是空对空）", len(common) >= 2, str(common))


# ============================================================
print("\n" + "=" * 74)
print("[2] ★ 对拍四项：code / owner / severity / verdict")
print("=" * 74)

# ---- code：共有的 code 集合就是"同一件事"的集合 ----
mism_code = {c: (lo[c], upo[c]) for c in common
             if lo[c] != upo[c]}
check("★ 同一 code 的两个入口都认得（code 对齐）", len(common) >= 2, str(common))

# ---- owner / severity ----
bad_owner = [c for c in common if lo[c]["owner"] != upo[c]["owner"]]
bad_sev = [c for c in common if lo[c]["severity"] != upo[c]["severity"]]
check("★★ owner 逐条一致（A1a 的验收标准）", not bad_owner,
      str({c: (lo[c]["owner"], upo[c]["owner"]) for c in bad_owner}))
check("★★ severity 逐条一致", not bad_sev,
      str({c: (lo[c]["severity"], upo[c]["severity"]) for c in bad_sev}))

# 正面钉住本场景的两条
for code, want in (("P-event-unknown-to-frontend", "frontend"),
                   ("P-phase-unknown", "both")):
    check(f"{code} 两个入口都是 {want}",
          lo.get(code, {}).get("owner") == want and upo.get(code, {}).get("owner") == want,
          f"本地={lo.get(code, {}).get('owner')} 上游={upo.get(code, {}).get('owner')}")

# ---- verdict ----
check("★ 两边都给得出 verdict",
      bool(local.get("verdict")) and bool(up.get("verdict")),
      f"本地={local.get('verdict')} 上游={up.get('verdict')}")

from bridge.contract_vocab import VERDICTS  # noqa: E402

lv, uv = local.get("verdict"), up.get("verdict")
check("★ 两个 verdict 都在契约 6 值内",
      lv in VERDICTS and uv in VERDICTS, f"本地={lv} 上游={uv}")

# verdict **允许不同**：两侧覆盖面不同 —— 本地还管"本地环境"项
# （钩子、构建产物、标定自洽），那些是上游观测不到的。
# 但**跨侧那部分**必须一致：共有 code 的 owner 集合。
lo_owners = {lo[c]["owner"] for c in common}
up_owners = {upo[c]["owner"] for c in common}
check("★★ 共有 code 的 owner 集合一致（跨侧那部分是同一答案）",
      lo_owners == up_owners, f"本地={sorted(lo_owners)} 上游={sorted(up_owners)}")
print(f"       verdict：本地={lv} 上游={uv}"
      f"（允许不同：本地还管本地环境项；跨侧那部分已逐条对齐）")


# ============================================================
print("\n" + "=" * 74)
print("[3] 判据**只有一份**：本地不自行下结论")
print("=" * 74)
from bridge.audit import DEVIATIONS, UPSTREAM_RULES  # noqa: E402
from bridge.contract_vocab import load_upstream_rules  # noqa: E402

live = load_upstream_rules()
check("★ 本地跨侧归属优先读契约（不是手写常量）", bool(live), f"{len(live)} 条")
check("★ 声明偏离表为空", DEVIATIONS == {}, str(sorted(DEVIATIONS)))
check("★ 离线回退表与契约逐条一致",
      all(live.get(k) == v for k, v in UPSTREAM_RULES.items()),
      str({k: (v, live.get(k)) for k, v in UPSTREAM_RULES.items()
           if live.get(k) != v})[:200])


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}"
      + (f" · SKIP {len(skips)}" if skips else ""))
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
