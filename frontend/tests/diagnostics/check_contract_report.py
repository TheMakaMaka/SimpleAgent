"""端到端自检：前端组装的责任自审查上报体，服务端能不能对得上。

为什么需要它
------------
`POST /api/audit` 的判定**全靠上报体**。上报体错了，结论就会指错人 ——
而界面上只显示"兼容 / 要改"，看不出是判对了还是判歪了。

单测（`tests/unit/test_audit.py`）用**合成的**上报体测判定逻辑；
这里走的是**前端真正会发的那一份**：从生成物（`expectations.ts`）
里取出前端认得的事件 / 阶段 / 端点，按 `frontend/src/api/audit.ts` 的
`buildReport()` 同样规则组装，再打给跑着的服务。

它守住三件单测守不住的事：

  1. `/api/spec` 的分区字段真的齐（少一个 `proxied_upstream` 就会漏报上游依赖）；
  2. 前端上报的 `upstream_endpoints` 是**上游路径**而不是 `/api/*`
     —— 混了就是 gap_G3 的同型错误，会让上游去恢复它从未拥有的端点；
  3. 合规上报得到的结论是 `ok`（没有 breaking/degraded 噪声）。

用法（需要服务已在运行）：
    python tests/diagnostics/check_contract_report.py
    $env:AGENT_BASE = "http://127.0.0.1:8210"   # 换端口
"""

import json
import os
import re
import sys

import httpx

BASE = os.getenv("AGENT_BASE", "http://127.0.0.1:8000")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EXPECTATIONS = os.path.join(ROOT, "frontend", "src", "generated", "expectations.ts")


def ts_array(text: str, field: str) -> list[str]:
    m = re.search(rf"{field}:\s*\[(.*?)\]", text, re.S)
    return sorted(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))) if m else []


def build_report(spec: dict) -> dict:
    """与 `frontend/src/api/audit.ts` 的 `buildReport()` 同规则。

    保持同步的办法：两边都以 `/api/spec` 的**分区**为判据，
    而不是各自写死一份名单。
    """
    text = open(EXPECTATIONS, encoding="utf-8").read()
    events = ts_array(text, "events")
    stages = ts_array(text, "stages")
    endpoints = ts_array(text, "endpoints")
    proxied = ts_array(text, "proxied_upstream")

    up_events = set(spec["event_partition"]["upstream"])
    up_phases = set(spec["pipeline"]["upstream_phases"])
    mapped = spec["endpoint_partition"]["mapped"]

    via_bridge = [mapped[k] for k in endpoints if k in mapped]
    up_paths = sorted(set(via_bridge) | set(proxied))

    return {
        "contract_version": spec["implements_contract_version"],
        "schema_version": spec["schema_version"],
        "upstream_event_kinds": [e for e in events if e in up_events],
        "frontend_event_kinds": [e for e in events if e not in up_events],
        "phases": [s for s in stages if s in up_phases],
        "bridge_gate_steps": [s for s in stages if s not in up_phases],
        "upstream_endpoints": up_paths,
        "frontend_endpoints": endpoints,
        "spec_version": "1.0",
    }


def main() -> int:
    checks: list[tuple[str, bool]] = []
    skipped: list[tuple[str, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, bool(ok)))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))

    def skip(name: str, why: str) -> None:
        """**不能测**（与"测了没过"是两回事）。

        典型场景：服务用仓库自带的 backend/ 副本，它缺 `core/contract.py`，
        于是上游 `/contract/check` 根本不存在 —— 跨侧对账**按配置就不可能**。
        把它记成 FAIL 会让默认配置**永远红着**；而"永远红着"的检查等于没有检查。
        所以这里明确 SKIP 并写明原因（真正的问题由 §[0] 的陈旧检测报出）。
        """
        skipped.append((name, why))
        print(f"  SKIP  {name}   —— {why}")

    print("=" * 74)
    print(f"目标：{BASE}")
    print("=" * 74)

    with httpx.Client(base_url=BASE, timeout=30.0) as c:
        spec = c.get("/api/spec").json()

        print("\n[0] /api/health 的上游来源探针（架构清单 A2）")
        # 判据是 paths.BACKEND_DIR，不是"能 import core" ——
        # 仓库里有两个同名 core 包，能 import 只说明 sys.path 里有它。
        h = c.get("/api/health").json()
        check("★ /api/health 含 backend_dir", "backend_dir" in h, str(h.get("backend_dir")))
        check("★ /api/health 含 backend_is_bundled",
              isinstance(h.get("backend_is_bundled"), bool),
              str(h.get("backend_is_bundled")))
        check("★ 含陈旧结论 backend_stale",
              isinstance(h.get("backend_stale"), bool), str(h.get("backend_stale")))
        check("含陈旧原因 backend_stale_reason",
              isinstance(h.get("backend_stale_reason"), str),
              (h.get("backend_stale_reason") or "")[:60])
        check("含 core 模块数与契约版本（判断落后在哪的依据）",
              isinstance(h.get("backend_core_modules"), int)
              and "backend_contract_version" in h,
              f"{h.get('backend_core_modules')} / "
              f"{h.get('backend_contract_version') or '(读不到)'}")
        if h.get("backend_is_bundled"):
            check("★ bundled 模式必须同时报出落后（不许静默）",
                  h.get("backend_stale") is True,
                  (h.get("backend_stale_reason") or "")[:80])
        else:
            check("指向上游外部 checkout 时不该被误判为落后",
                  h.get("backend_stale") is False,
                  (h.get("backend_stale_reason") or "")[:80])

        print("\n[1] /api/spec 的契约分区字段齐备")
        check("带 implements_contract_version", bool(spec.get("implements_contract_version")))
        check("带来源（不冒充 backend）",
              spec.get("implements_contract_version_source") in ("upstream", "fallback"),
              str(spec.get("implements_contract_version_source")))
        check("pipeline.upstream_phases == 5",
              len(spec["pipeline"]["upstream_phases"]) == 5,
              str(spec["pipeline"]["upstream_phases"]))
        check("pipeline.bridge_gate_steps 含 manifest",
              "manifest" in spec["pipeline"]["bridge_gate_steps"],
              str(spec["pipeline"]["bridge_gate_steps"]))
        check("阶段并集 == 全部 stages",
              set(spec["pipeline"]["upstream_phases"])
              | set(spec["pipeline"]["bridge_gate_steps"])
              == {s["id"] for s in spec["pipeline"]["stages"]})
        # ★ 期望值**从契约 + 已登记滞后**推导，不写死：
        #   上游加性新增事件时（`verify_skipped` 那次 33→34，`TRANSPARENCY-UI`
        #   这次 34→37），红的是常数而不是接口。同一教训见 CHANGELOG §31.3。
        try:
            from bridge import partition as _part

            _lag = len(getattr(_part, "CONTRACT_LAG_KINDS", frozenset()))
        except Exception:  # noqa: BLE001
            _lag = 0
        _want_up = 12 + _lag
        check(f"event_partition {_want_up} + 21",
              len(spec["event_partition"]["upstream"]) == _want_up
              and len(spec["event_partition"]["frontend"]) == 21,
              f"{len(spec['event_partition']['upstream'])} + "
              f"{len(spec['event_partition']['frontend'])}"
              + (f"（契约 12 + 已登记滞后 {_lag}）" if _lag else ""))
        check("endpoint_partition 带 proxied_upstream",
              bool(spec["endpoint_partition"].get("proxied_upstream")),
              str(spec["endpoint_partition"].get("proxied_upstream")))

        rep = build_report(spec)

        print("\n[2] 上报体按来源分开（gap_G2 / gap_G3 / gap_G4）")
        check(f"upstream_event_kinds == 上游 {_want_up} 个",
              len(rep["upstream_event_kinds"]) == _want_up,
              str(len(rep["upstream_event_kinds"])))
        check("phases == 上游 5 个（不含 manifest）",
              len(rep["phases"]) == 5 and "manifest" not in rep["phases"],
              str(rep["phases"]))
        check("manifest 走 bridge_gate_steps",
              rep["bridge_gate_steps"] == ["manifest"], str(rep["bridge_gate_steps"]))
        check("★ upstream_endpoints 是上游路径，不含 /api/*",
              all(not p.startswith("/api/") for p in rep["upstream_endpoints"]),
              str(rep["upstream_endpoints"]))
        check("★ upstream_endpoints 覆盖 vite proxy 的 7 条",
              len(rep["upstream_endpoints"]) >= 7, str(rep["upstream_endpoints"]))
        check("frontend_endpoints 是 bridge 端点 key（口径不同）",
              "audit" in rep["frontend_endpoints"], str(rep["frontend_endpoints"]))

        print("\n[3] POST /api/audit 的结论")
        r = c.post("/api/audit", json=rep)
        check("HTTP 200", r.status_code == 200, str(r.status_code))
        out = r.json()
        print(f"       verdict = {out.get('verdict')} — {out.get('verdict_text')}")
        print(f"       blocking={out.get('blocking_count')} info={out.get('info_count')}")
        for owner, items in (out.get("responsibility") or {}).items():
            for i in items:
                print(f"       [{owner}/{i['severity']}] {i['id']}  {i['title']}")
        check("★ 合规上报 → verdict == ok", out.get("verdict") == "ok",
              str(out.get("verdict")))
        check("★ 无阻塞项（blocking_count == 0）",
              out.get("blocking_count") == 0, str(out.get("blocking_count")))
        check("前端被认下（client_reported）", out.get("client_reported") is True)
        check("不是旧格式上报", out.get("client_legacy_shape") is False)
        check("带上了契约版本与来源",
              bool(out.get("implements_contract_version"))
              and bool(out.get("contract_version_source")))
        # 契约 response_contract：additive 字段必须在，缺了消费方就没法履约
        check("★ 响应带 warnings（additive 字段）", "warnings" in out,
              str(sorted(out))[:120])
        check("合规上报时 warnings 为空", out.get("warnings") == [],
              str(out.get("warnings")))

        print("\n[4] 被传输层证伪的 ops 事实（契约 v1.0.5）")
        # 陈旧 service_down：这条请求**已经送达**，所以它自相矛盾。
        # 契约要求：不参与 verdict，但进 warnings + ops 栏，且**消费方必须展示**。
        rep_ops = dict(rep, ops={"service_down": True})
        r2 = c.post("/api/audit", json=rep_ops)
        check("HTTP 200", r2.status_code == 200, str(r2.status_code))
        out2 = r2.json()
        print(f"       verdict = {out2.get('verdict')}")
        for w in out2.get("warnings", []):
            print(f"       ⚠ {w}")
        print(f"       ops 栏 = {out2.get('ops')}")
        check("★ 陈旧 service_down → verdict 仍是 ok（不驱动判定）",
              out2.get("verdict") == "ok", str(out2.get("verdict")))
        check("★ 但 warnings 非空（只看 verdict 的路径由它兜底）",
              len(out2.get("warnings") or []) == 1, str(out2.get("warnings")))
        check("★ ops 栏保留了该事实（运维要看到上次已知状态）",
              (out2.get("ops") or {}).get("service_down") is True,
              str(out2.get("ops")))
        check("该事实没有被计成 blocker",
              out2.get("blocking_count") == 0, str(out2.get("blocking_count")))
        check("warnings 文案点明「被传输层证伪」",
              "证伪" in (out2.get("warnings") or [""])[0],
              str(out2.get("warnings")))

        print("\n[5] markdown 里 warnings 与 verdict 并列（不是藏在附录）")
        md = out2.get("markdown") or ""
        check("markdown 带提示段", "提示" in md, md[:120])
        check("提示段说明它不参与结论", "不参与结论" in md)

        print("\n[6] 权威范围自述（架构清单 A1a）")
        check("★ /api/audit 自述 authority", out.get("authority") == "local-self-check",
              str(out.get("authority")))
        check("★ 并说明跨侧归属以上游为准",
              "/contract/check" in (out.get("authority_note") or ""),
              (out.get("authority_note") or "")[:60])

        print("\n[7] ★ 两个入口对同一跨侧不一致给出同一个 owner（A1a）")
        # 造一个**双方都看得见**的跨侧不一致：前端漏认一个上游事件。
        #   上游 /contract/check 会回 P-event-unknown-to-frontend
        #   本地 /api/audit     会回同一条（现在 id 就是那个 code）
        # 两边 owner 必须一致 —— 这是"同一件事只有一个判据"的在线证明。
        upstream_events = spec["event_partition"]["upstream"]
        partial = dict(rep, upstream_event_kinds=upstream_events[:-1],
                       frontend_event_kinds=[])
        missing_one = upstream_events[-1]

        local = c.post("/api/audit", json=partial).json()
        local_hits = [
            i for owner, items in (local.get("responsibility") or {}).items()
            for i in items if i.get("code") == "P-event-unknown-to-frontend"
        ]
        check(f"本地入口认出了这条不一致（漏 {missing_one}）",
              len(local_hits) == 1, str([i["id"] for i in local_hits]))
        if local_hits:
            check("★ 本地判定的 id 就是契约 code（不是自造名字）",
                  local_hits[0]["id"] == "P-event-unknown-to-frontend",
                  local_hits[0]["id"])
            local_owner = local_hits[0]["owner"]
        else:
            local_owner = "<无>"

        try:
            # ★ 必须看**状态码**：bundled 副本没有 /contract/check 时 FastAPI 回 404，
            #   而 404 的 body 是合法 JSON（`{"detail":"Not Found"}`），
            #   直接 `.json()` 会"成功"解析出一个空 dict —— 于是被当成"上游答了但没命中"
            #   记成 FAIL（**实测踩到**）。所以这里显式判 200。
            r_up = c.post("/contract/check", json=partial)
            if r_up.status_code != 200:
                raise RuntimeError(f"HTTP {r_up.status_code}")
            up = r_up.json()
            up_hits = [i for i in (up.get("issues") or [])
                       if i.get("code") == "P-event-unknown-to-frontend"]
            print(f"       上游 verdict={up.get('verdict')} "
                  f"命中 {len(up_hits)} 条")
            for i in up_hits[:3]:
                print(f"         [{i.get('owner')}/{i.get('severity')}] {i.get('code')}")
            up_owner = up_hits[0].get("owner") if up_hits else "<无>"
            check("★ 上游入口也认出了同一条", bool(up_hits), str(up_owner))
            check("★★ 两个入口给出的 owner **一致**",
                  local_owner == up_owner,
                  f"本地={local_owner} 上游={up_owner}")
        except Exception as e:  # noqa: BLE001
            # 上游对账入口用不了。分两种，**严重度完全不同**：
            #   · 配置导致（用自带副本 / 陈旧）→ **SKIP**：跨侧对账按配置不可能，
            #     缺什么已由 §[0] 的陈旧检测报出。判 FAIL 会让默认配置永远红着。
            #   · 指着上游却仍然坏 → **FAIL**：那是真的有问题（含上游 500）。
            why = (f"上游 /contract/check 不可用（{type(e).__name__}: {e}）—— "
                   f"backend_is_bundled={h.get('backend_is_bundled')}，"
                   f"陈旧={h.get('backend_stale')}")
            if h.get("backend_is_bundled") or h.get("backend_stale"):
                skip("★★ 两个入口 owner 一致（在线形式）", why + "；跨侧对账按配置不可能")
            else:
                check("★ 上游对账入口可用（指向上游时必须可用）", False, why)

    print("\n" + "=" * 74)
    failed = [n for n, ok in checks if not ok]
    print(f"通过 {len(checks) - len(failed)}/{len(checks)}"
          + (f" · SKIP {len(skipped)}" if skipped else ""))
    if skipped:
        print("跳过（按配置不可测，不是失败）：")
        for n, why in skipped:
            print(f"  - {n}：{why}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
