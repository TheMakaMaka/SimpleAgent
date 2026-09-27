"""离线校验：标定方案本身是自洽的。

"低定制高拓展"不能只是口号——要有东西把守。这个测试问四个问题：

  1. **事实来自代码**：标定里的阶段、事件、工具真的等于代码里的现状吗？
     （阶段 == 上游 `PHASE_ORDER`；事件 == 各处 `_emit`/`emit_progress` 的并集）
  2. **没有漏标**：后端会发的事件里，有没有哪个没被标定（会显示成自动兜底的名字）？
  3. **没有死标**：标定里有没有哪个事件后端根本不发（多半是上游删了事件）？
  4. **前端兜底没漂**：`frontend/src/api/spec.ts` 的 `DEFAULT_SPEC`
     是后端拿不到时的备用值；它必须仍然覆盖后端的阶段与端点，
     否则"后端挂了界面还看得懂"这条就名存实亡。

第 4 条尤其重要：它是**跨语言**的一致性，没有类型系统帮忙，只能靠测试。

运行：python tests/unit/test_spec.py
"""

import ast
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import BACKEND, ROOT  # noqa: E402,F401

import bridge.spec as spec_mod  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


SPEC_TS = os.path.join(ROOT, "frontend", "src", "api", "spec.ts")
spec = spec_mod.build_spec()


# ============================================================
print("=" * 74)
print("[1] 事实来自代码，不是手写")
print("=" * 74)
from core.cycle import PHASE_ORDER  # noqa: E402

phase_ids = [s["id"] for s in spec["pipeline"]["stages"] if s["kind"] == "phase"]
check("阶段 == 上游 PHASE_ORDER（顺序也一致）",
      phase_ids == [p.value for p in PHASE_ORDER],
      f"{phase_ids} vs {[p.value for p in PHASE_ORDER]}")

check("门禁步骤插在声明的位置",
      [s["id"] for s in spec["pipeline"]["stages"]].index("manifest")
      > [s["id"] for s in spec["pipeline"]["stages"]].index("write"))

from tools.registry import TOOLS_MAP  # noqa: E402

check("工具清单 == 上游注册表", len(spec["tools"]) == len(TOOLS_MAP),
      f'{len(spec["tools"])} vs {len(TOOLS_MAP)}')
check("工具名逐一对应",
      {t["name"] for t in spec["tools"]} == set(TOOLS_MAP))

# 事件：标定里的事件集合必须等于扫描出来的集合
scanned = set(spec_mod.event_kinds())
check("事件集合 == 扫描结果", set(spec["events"]) == scanned,
      f'标定 {len(spec["events"])} / 扫描 {len(scanned)}')

# 上游若新增阶段，这里会立刻红——这是刻意的：新阶段需要标定中文名与图标
check("每个阶段都有 label 与非空 hint",
      all(s["label"] and s["hint"] for s in spec["pipeline"]["stages"]),
      str([s["id"] for s in spec["pipeline"]["stages"] if not s["hint"]]))
check("每个阶段都有 icon",
      all(s.get("icon") for s in spec["pipeline"]["stages"]))


# ============================================================
print("\n" + "=" * 74)
print("[2] 没有漏标 / 没有死标")
print("=" * 74)
diag = spec["diagnostics"]
check("无未标定事件", not diag["uncalibrated_events"], str(diag["uncalibrated_events"]))
# 死标定：标了、但当前生效的上游不发它。
# ★ 按配置分流：自带副本是旧的，而标定表要为**契约声明的新上游**备好条目
#   （这正是"上游加性新增 → 消费方跟上"该有的样子）。
#   上游落后时把这种"预备"叫"死标定"是**配置**造成的，不是标定表错了。
from bridge import staleness as _staleness  # noqa: E402

_stale = _staleness.probe()["stale"]
if _stale and diag["dead_calibrations"]:
    print(f"  SKIP  死标定检查（当前上游落后；标定表为契约的新上游备着）"
          f"：{diag['dead_calibrations']}")
    print("       → 设 AGENT_BACKEND_DIR 指向真上游即可验这一条")
else:
    check("无死标定（标了但代码不发）", not diag["dead_calibrations"],
          str(diag["dead_calibrations"]))
check("标定文件解析无错", not diag["errors"], str(diag["errors"]))

# 未标定的工具是允许的（种子/通用工具不出现在编码界面），但要能数出来
unc_tools = [t["name"] for t in spec["tools"] if not t["calibrated"]]
print(f"       未标中文名的工具 {len(unc_tools)} 个（允许，前端回退成原名）: {unc_tools}")

# 每个事件都要有 tone，且 tone 必须是前端认得的
KNOWN_TONES = {"info", "ok", "warn", "error", "model", "tool", "phase"}
bad_tones = {k: v["tone"] for k, v in spec["events"].items() if v["tone"] not in KNOWN_TONES}
check("事件 tone 都是前端认识的", not bad_tones, str(bad_tones))

KNOWN_STATUS_TONES = {"neutral", "live", "ok", "warn", "err"}
bad_st = {k: v["tone"] for k, v in spec["statuses"].items() if v["tone"] not in KNOWN_STATUS_TONES}
check("状态 tone 都是前端认识的", not bad_st, str(bad_st))


# ============================================================
print("\n" + "=" * 74)
print("[3] 端点：标定里声明的路径必须真的注册在 app 上")
print("=" * 74)
try:
    import bridge.app as bridge_app  # noqa: E402  导入即构建 app

    routes = {
        getattr(r, "path", "")
        for r in bridge_app.app.routes
        if getattr(r, "path", "").startswith("/api/")
    }
    wanted = set(spec["endpoints"].values())
    missing = sorted(w for w in wanted if w not in routes)
    check("标定里的 /api/* 端点全部已注册", not missing, str(missing))

    # 反向：注册了但没进标定的端点，前端拿不到它的路径
    extra = sorted(r for r in routes if r not in wanted)
    check("已注册的 /api/* 端点都进了标定", not extra, str(extra))
except Exception as e:  # 上游起不来时不该让这个测试挂掉，但要说清楚
    check("能构建 app 以核对端点", False, f"{type(e).__name__}: {e}")


# ============================================================
print("\n" + "=" * 74)
print("[4] 前端兜底 spec 不许漂（跨语言一致性，只能靠测试）")
print("=" * 74)
if not os.path.isfile(SPEC_TS):
    check("frontend/src/api/spec.ts 存在", False)
else:
    ts = io.open(SPEC_TS, encoding="utf-8").read()
    check("DEFAULT_SPEC 存在", "DEFAULT_SPEC" in ts)

    # 端点：每个 key 都要在 TS 里出现
    missing_ep = [k for k in spec["endpoints"] if f"{k}:" not in ts]
    check("兜底覆盖全部端点 key", not missing_ep, str(missing_ep))

    # 阶段：每个阶段 id 与 label 都要在 TS 里出现
    missing_stage = [
        s["id"] for s in spec["pipeline"]["stages"]
        if f"id: '{s['id']}'" not in ts
    ]
    check("兜底覆盖全部阶段 id", not missing_stage, str(missing_stage))

    missing_icon = [
        s["id"] for s in spec["pipeline"]["stages"]
        if s.get("icon") and f"icon: '{s['icon']}'" not in ts
    ]
    check("兜底覆盖阶段图标", not missing_icon, str(missing_icon))

    # 状态：每个状态 key 都要在 TS 里
    missing_status = [k for k in spec["statuses"] if f"{k}: {{" not in ts]
    check("兜底覆盖全部状态", not missing_status, str(missing_status))

    # 可调参数：默认值必须一致（不一致会导致"没标定时行为不同"）
    ui = spec["ui"]
    mismatches: list[str] = []
    for group, values in ui.items():
        if group == "examples":
            continue
        for key, val in values.items():
            if f"{key}:" not in ts and f"'{key}':" not in ts:
                mismatches.append(f"{group}.{key} 缺失")
    check("兜底覆盖全部可调参数 key", not mismatches, str(mismatches[:5]))

    checks.append(("兜底 spec_version 标注为 fallback",
                   "spec_version: 'fallback'" in ts))
    print(f"  {'PASS' if checks[-1][1] else 'FAIL'}  兜底 spec_version 标注为 fallback")

    # ---- 契约相关的分区字段：兜底必须与服务端一致 ----
    # 这几项前端用来**组装责任自审查上报体**。兜底漂了，后端不可达时上报的
    # 分区就是错的 —— 而那时恰恰最需要正确的归因。
    for field in ("implements_contract_version", "schema_version",
                  "endpoint_partition", "event_partition",
                  "upstream_phases", "bridge_gate_steps", "proxied_upstream"):
        check(f"兜底覆盖契约字段 {field}", f"{field}:" in ts)

    check("兜底写明契约版本来源（不许冒充 backend）",
          "implements_contract_version_source: 'fallback'" in ts)

    # 阶段分区：兜底的 upstream_phases 必须是真的上游那 5 个
    import json as _json  # noqa: E402

    real = spec["pipeline"]
    check("兜底 upstream_phases 与服务端一致",
          f"upstream_phases: {_json.dumps(real['upstream_phases'])}".replace('"', "'")
          in ts, str(real["upstream_phases"]))
    check("兜底 bridge_gate_steps 与服务端一致",
          f"bridge_gate_steps: {_json.dumps(real['bridge_gate_steps'])}".replace('"', "'")
          in ts, str(real["bridge_gate_steps"]))

    # ★ 端点分区的事实源是 vite.config.ts —— 兜底必须与它一致，
    #   否则前端会漏报一半上游依赖（/skills /candidates /encode /run）。
    from bridge import partition as _P  # noqa: E402

    proxied = _P.proxied_upstream()
    check("从 vite.config.ts 读到了 proxy 表", bool(proxied), str(proxied))

    def ts_array(text: str, field: str) -> list[str]:
        """取出 TS 里 `field: [ ... ]` 这一段里的字符串字面量（两种引号都认）。

        TS 那边是多行缩进的，和一行 JSON 比字符串必然不等 —— 所以按**集合**比。
        """
        m = re.search(rf"{field}:\s*\[(.*?)\]", text, re.S)
        if not m:
            return []
        return sorted(re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)))

    check("兜底 proxied_upstream 与 vite.config.ts 一致",
          ts_array(ts, "proxied_upstream") == proxied,
          f"兜底={ts_array(ts, 'proxied_upstream')} 事实源={proxied}")
    check("兜底 upstream 覆盖 bridge 转发的 3 条",
          set(_P.UPSTREAM_ENDPOINT_MAP.values()) <= set(ts_array(ts, "upstream")),
          str(sorted(_P.UPSTREAM_ENDPOINT_MAP.values())))

    # 生成物（构建期扫出来的期望）也必须在
    GEN = os.path.join(ROOT, "frontend", "src", "generated", "expectations.ts")
    check("expectations.ts 已生成", os.path.isfile(GEN))
    if os.path.isfile(GEN):
        gen = io.open(GEN, encoding="utf-8").read()
        check("生成物带 proxied_upstream（上报上游面要用）",
              "proxied_upstream:" in gen)
        # 生成物是 JSON.stringify 写的：无空格、双引号
        want = _json.dumps(proxied, separators=(",", ":"))
        check("生成物的 proxied_upstream 与 vite.config.ts 一致",
              want in gen, f"期望 {want}")
        check("生成物的 proxied_upstream 非空（扫不到就该构建失败）",
              proxied and len(ts_array(gen, "proxied_upstream")) == len(proxied))


# ============================================================
print("\n" + "=" * 74)
print("[5] 覆盖文件：spec.override.json 能改标定，但改不了事实")
print("=" * 74)
import json  # noqa: E402
import tempfile  # noqa: E402

orig_override = spec_mod.OVERRIDE_FILE
tmpdir = tempfile.mkdtemp(prefix="spec_override_")
try:
    fake = os.path.join(tmpdir, "spec.override.json")
    io.open(fake, "w", encoding="utf-8").write(json.dumps({
        "stage_labels": {"plan": "规划（改过的）"},
        "ui": {"poll": {"health_ms": 9999}},
    }, ensure_ascii=False))
    spec_mod.OVERRIDE_FILE = fake

    over = spec_mod.build_spec()
    plan = next(s for s in over["pipeline"]["stages"] if s["id"] == "plan")
    check("override 能改阶段中文名", plan["label"] == "规划（改过的）", plan["label"])
    check("override 能改可调参数", over["ui"]["poll"]["health_ms"] == 9999)
    check("override 改不了事实：阶段集合仍等于 PHASE_ORDER",
          [s["id"] for s in over["pipeline"]["stages"] if s["kind"] == "phase"]
          == [p.value for p in PHASE_ORDER])
    check("override 改不了事实：事件集合仍等于扫描结果",
          set(over["events"]) == scanned)

    # 坏文件不能把端点整体打挂
    io.open(fake, "w", encoding="utf-8").write("{ 这不是 JSON")
    broken = spec_mod.build_spec()
    check("坏 override 不炸，只是记录错误",
          broken["diagnostics"]["errors"] and broken["pipeline"]["stages"])
finally:
    spec_mod.OVERRIDE_FILE = orig_override
    import shutil

    shutil.rmtree(tmpdir, ignore_errors=True)


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
