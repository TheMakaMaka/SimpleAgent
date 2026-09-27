"""体检：一条命令把「哪里不对」查清楚。

为什么要有它
------------
出问题时，人的自然反应是"收集信息 → 整理成报告 → 交给别人判断"。
这个来回本身就是瓶颈，而且整理过程会丢信息。

所以把它做成命令：**它自己采集、自己判断、自己给结论**。三种用法：

    python scripts/doctor.py               # 人读的分节报告
    python scripts/doctor.py --json        # 机器读（Agent 用的就是它）
    python scripts/doctor.py --triage      # 归因最近一次失败的运行
    python scripts/doctor.py --triage <run_id>
    python scripts/doctor.py --e2e         # 额外跑一次演示运行（会起真实流程）

设计原则
--------
1. **服务挂了也要能跑。** 体检最需要它的时候，恰恰是服务起不来的时候。
   所以除了"服务健康"一节，其余全部离线自检。
2. **每条结论都带证据。** 没证据的判断等于猜。
3. **失败不抛异常，只标记 FAIL。** 体检自己崩了就没意义了。
"""

import argparse
import json
import os
import subprocess
import sys
import time
from urllib import error as urlerror
from urllib import request as urlrequest

# 报告里有 ✓ / ✗ / 中文：控制台是 GBK 时直接 UnicodeEncodeError，
# 而**体检崩掉就没意义了**（见上文设计原则 3）。所以先把自己钉成 UTF-8。
# errors="replace" 是兜底：真遇到老终端也只退化显示，不中断体检。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001  （被重定向到非文本流时没有 reconfigure）
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 允许 --backend 指定上游目录（等价于 AGENT_BACKEND_DIR）
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--backend")
_pre_args, _ = _pre.parse_known_args()
if _pre_args.backend:
    os.environ["AGENT_BACKEND_DIR"] = os.path.abspath(_pre_args.backend)

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_TAG = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", SKIP: "SKIP"}


class Section:
    def __init__(self, title: str, note: str = ""):
        self.title = title
        self.note = note
        self.items: list[dict] = []

    def add(self, name: str, status: str, detail: str = "", evidence: list[str] | None = None):
        self.items.append({
            "name": name, "status": status, "detail": detail,
            "evidence": (evidence or [])[:8],
        })
        return self

    @property
    def worst(self) -> str:
        for s in (FAIL, WARN, SKIP, PASS):
            if any(i["status"] == s for i in self.items):
                return s
        return PASS

    def to_dict(self) -> dict:
        return {"title": self.title, "note": self.note, "worst": self.worst, "items": self.items}


SECTIONS: list[Section] = []


def section(title: str, note: str = "") -> Section:
    s = Section(title, note)
    SECTIONS.append(s)
    return s


def _try(fn, *a, **kw):
    """检查项自己不许抛——抛了就变成"体检挂了"，那最没用。"""
    try:
        return fn(*a, **kw), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


# ============================================================
def check_environment() -> None:
    s = section("环境", "Python / Node / 依赖是否齐")
    v = sys.version_info
    s.add("Python ≥ 3.10", PASS if v >= (3, 10) else FAIL, f"{v.major}.{v.minor}.{v.micro}")

    venv = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
    s.add("仓库自带 .venv", PASS if os.path.isfile(venv) else WARN,
          "" if os.path.isfile(venv) else "没有就用 PATH 里的 python")

    for mod in ("fastapi", "uvicorn", "openai", "pydantic"):
        try:
            __import__(mod)
            s.add(f"依赖 {mod}", PASS)
        except ImportError as e:
            s.add(f"依赖 {mod}", FAIL, str(e))

    try:
        import dotenv  # noqa: F401
        s.add("依赖 python-dotenv", PASS, ".env 能自动加载")
    except ImportError:
        s.add("依赖 python-dotenv", WARN, "没装 → 只用环境变量，.env 不生效")


def check_paths() -> None:
    s = section("路径与隔离", "运行根、上游位置、仓库根有没有被污染")
    from bridge import paths as P
    from bridge import staleness as S

    s.add("上游代码目录存在", PASS if os.path.isdir(P.BACKEND_DIR) else FAIL, P.BACKEND_DIR)
    s.add("上游来源", PASS,
          "仓库自带 backend/" if P.BACKEND_IS_BUNDLED
          else f"外部路径（AGENT_BACKEND_DIR）")

    # ---- 上游副本陈旧检测（架构清单 A2）----
    # 判据是 **P.BACKEND_DIR**，不是"import 到了 core 就算对"：
    # 仓库里有两个同名 core 包，import 成功只说明 sys.path 里有它，
    # 不说明用的是哪一份。这条结论必须来自路径事实。
    #
    # 严重度分两档，这个区分是有意的：
    #   bundled 且落后 → **WARN**。用自带副本是**正当选择**（开箱可跑是设计），
    #                    修法只是一行环境变量。判 FAIL 会让默认配置**永远红着**，
    #                    而"永远红着"的检查等于没有检查。
    #   外部却落后     → **FAIL**。你明确指向了一份上游，它却缺必需模块 ——
    #                    那是配错了，不是选择。
    probe = S.probe(reference_dir=S.reference_dir_from_env() or None)
    stale_level = WARN if P.BACKEND_IS_BUNDLED else FAIL
    s.add(
        f"上游 core 模块 {probe['core_module_count']} 个"
        f"（CONTRACT_VERSION={probe['contract_version'] or '读不到'}）",
        PASS if probe["contract_version_readable"] else stale_level,
        "" if probe["contract_version_readable"]
        else "契约版本会静默退回 fallback",
    )
    if probe["stale"]:
        s.add("上游副本陈旧" + ("（仓库自带，可接受）" if P.BACKEND_IS_BUNDLED
                                else "（外部路径，需处理）"),
              stale_level, probe["summary"],
              ["设 AGENT_BACKEND_DIR 指向最新上游 checkout（见 docs/LAYOUT.md）"])
    else:
        s.add("上游副本未发现落后", PASS, "")

    created, err = _try(P.ensure_dirs)
    s.add("运行根可用", FAIL if err else PASS, err or P.RUNTIME_ROOT)

    stray = P.stray_dirs()
    s.add("仓库根无 stray 运行态目录", FAIL if stray else PASS,
          str(stray) if stray else "",
          [f"删掉 {x}/ 并检查上游是否新增了写死相对路径的地方" for x in stray])

    cwd = os.getcwd()
    s.add("CWD == 运行根", PASS if os.path.realpath(cwd) == os.path.realpath(P.RUNTIME_ROOT)
          else WARN, cwd)


def check_contract() -> None:
    s = section("上游契约", "bridge 依赖的上游接口还在不在")
    from bridge import contract, hooks

    rep, err = _try(contract.check)
    if err or rep is None:
        s.add("契约自检可执行", FAIL, err or "")
        return
    s.add(f"上游接口 {len(rep.present)}/{len(rep.present) + len(rep.missing)} 就位",
          PASS if rep.ok else FAIL,
          f"缺 {len(rep.missing)} 个" if rep.missing else "",
          rep.missing)
    for n in dict.fromkeys(rep.notes):   # 去重：同一条提示会重复十几次
        s.add("提示", WARN, n)

    hr, err = _try(hooks.install)
    if err or not hr:
        s.add("挂钩可安装", FAIL, err or "")
        return
    s.add(f"挂钩已装 {len(hr.get('installed', []))} 个",
          PASS if hr.get("installed") else FAIL)
    for n in hr.get("skipped", []):
        s.add("挂钩跳过", WARN, n)


def check_spec() -> None:
    s = section("标定自洽", "事实 == 代码现状？有没有漏标/死标？")
    from bridge import spec as S

    sp, err = _try(S.build_spec)
    if err or not sp:
        s.add("标定可构建", FAIL, err or "")
        return
    d = sp["diagnostics"]
    s.add(f"事件 {d['event_count']} 个", PASS)
    s.add("无未标定事件", FAIL if d["uncalibrated_events"] else PASS,
          str(d["uncalibrated_events"]), d["uncalibrated_events"])
    s.add("无死标定", FAIL if d["dead_calibrations"] else PASS, str(d["dead_calibrations"]))
    s.add("覆盖文件解析无错", FAIL if d["errors"] else PASS, "; ".join(d["errors"]))

    # 阶段必须等于上游 PHASE_ORDER
    try:
        from core.cycle import PHASE_ORDER

        want = [p.value for p in PHASE_ORDER]
        got = [x["id"] for x in sp["pipeline"]["stages"] if x["kind"] == "phase"]
        s.add("阶段 == 上游 PHASE_ORDER", PASS if got == want else FAIL,
              f"{got} vs {want}")
    except Exception as e:  # noqa: BLE001
        s.add("能读到上游 PHASE_ORDER", FAIL, str(e))

    # 端点双向：声明 vs 真实路由
    def _routes():
        import bridge.app as B

        return {getattr(r, "path", "") for r in B.app.routes
                if getattr(r, "path", "").startswith("/api/")}

    routes, err = _try(_routes)
    if err:
        s.add("能构建 app 核对端点", FAIL, err)
    else:
        declared = set(sp["endpoints"].values())
        miss = sorted(declared - routes)
        extra = sorted(routes - declared)
        s.add("声明的端点都已注册", PASS if not miss else FAIL, str(miss))
        s.add("已注册的端点都进了标定", PASS if not extra else FAIL, str(extra))

    # 跨语言：前端词表 == 后端词表
    ec = S.event_contract()
    if not ec["frontend_available"]:
        s.add("前端归约器可读", WARN, "frontend/src/store/run.ts 不在，跳过词表核对")
    else:
        s.add("前端认得后端全部事件", PASS if not ec["missing_in_frontend"] else FAIL,
              str(ec["missing_in_frontend"]), ec["missing_in_frontend"])
        s.add("前端无孤儿 case", PASS if not ec["orphan_in_frontend"] else FAIL,
              str(ec["orphan_in_frontend"]))


def check_service(base: str) -> dict | None:
    s = section("服务", f"探测 {base}")

    def get(path: str, timeout=5):
        with urlrequest.urlopen(base + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    health, err = _try(get, "/api/health")
    if err:
        s.add("服务可达", FAIL, err, ["服务没起？跑 .\\scripts\\run.ps1"])
        return None
    s.add("服务可达", PASS)
    s.add("模型", PASS if not health.get("problems") else FAIL,
          f"{health.get('model', {}).get('name')} @ {health.get('model', {}).get('base_url')}",
          health.get("problems") or [])
    s.add("检查点后端", PASS, str(health.get("checkpoint_backend")))

    spa, err2 = _try(lambda: urlrequest.urlopen(base + "/app/", timeout=5).status)
    s.add("前端 /app 可访问", PASS if err2 is None else WARN,
          "" if err2 is None else "没构建？cd frontend && npm run build")
    return health


def check_history(base: str, limit: int = 200) -> None:
    """历史运行的健康状况 + 失败归因。**这是"审查机制"的主体。**"""
    s = section("历史与归因", "最近运行怎么样、失败的那几次到底为什么")
    from bridge import paths as P
    from bridge.triage import triage

    runs_root = P.RUNS_DIR
    if not os.path.isdir(runs_root):
        s.add("有历史运行", SKIP, "还没有任何运行记录")
        return

    metas = []
    for name in sorted(os.listdir(runs_root), reverse=True)[:limit]:
        p = os.path.join(runs_root, name, "meta.json")
        if not os.path.isfile(p):
            continue
        try:
            metas.append(json.load(open(p, encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue

    if not metas:
        s.add("有历史运行", SKIP)
        return

    total = len(metas)
    by_status: dict[str, int] = {}
    for m in metas:
        by_status[m.get("status", "?")] = by_status.get(m.get("status", "?"), 0) + 1
    s.add(f"最近 {total} 次运行", PASS, " ".join(f"{k}×{v}" for k, v in by_status.items()))

    failures = [m for m in metas if m.get("status") in ("failed", "error", "cancelled")]
    if not failures:
        s.add("无失败运行", PASS)
        return

    s.add(f"失败 {len(failures)} 次", WARN if len(failures) < total else FAIL)

    # 逐条归因（最多 5 条，避免刷屏）
    for m in failures[:5]:
        rid = m.get("run_id", "?")
        ev_path = os.path.join(runs_root, rid, "events.jsonl")
        events = []
        if os.path.isfile(ev_path):
            for line in open(ev_path, encoding="utf-8"):
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        opts = m.get("options") or {}
        t = triage(rid, events, max_attempts=int(opts.get("max_attempts") or 0))
        primary = t.primary
        if primary:
            s.add(f"{rid} → {primary.label}", WARN,
                  primary.summary,
                  [primary.action] + primary.evidence[:3])


# ============================================================
def do_triage(run_id: str | None) -> int:
    """归因指定（或最近一次失败）的运行。"""
    from bridge import paths as P
    from bridge.triage import triage

    runs_root = P.RUNS_DIR
    if not os.path.isdir(runs_root):
        print("还没有任何运行记录。")
        return 1

    if not run_id:
        cands = []
        for name in sorted(os.listdir(runs_root), reverse=True):
            p = os.path.join(runs_root, name, "meta.json")
            if not os.path.isfile(p):
                continue
            try:
                m = json.load(open(p, encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if m.get("status") in ("failed", "error"):
                cands.append(m)
        if not cands:
            print("最近没有失败的运行——没什么可归因的。")
            return 0
        run_id = cands[0].get("run_id")

    ev_path = os.path.join(runs_root, run_id, "events.jsonl")
    if not os.path.isfile(ev_path):
        print(f"找不到 {run_id} 的事件流: {ev_path}")
        return 1

    events = []
    for line in open(ev_path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    meta_path = os.path.join(runs_root, run_id, "meta.json")
    max_attempts = 0
    if os.path.isfile(meta_path):
        try:
            max_attempts = int((json.load(open(meta_path, encoding="utf-8"))
                                .get("options") or {}).get("max_attempts") or 0)
        except Exception:  # noqa: BLE001
            pass

    t = triage(run_id, events, max_attempts=max_attempts)
    if ARGS.json:
        print(json.dumps(t.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(t.to_markdown())
    return 0 if t.status == "passed" else 2


def do_e2e(base: str) -> None:
    """真跑一次演示运行，验证事件链完整。比任何静态检查都硬。"""
    s = section("端到端", "起一次演示运行，核对事件链")

    def post(path, payload):
        req = urlrequest.Request(
            base + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urlrequest.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    res, err = _try(post, "/api/runs", {"goal": "体检：演示运行", "demo": True, "max_attempts": 2})
    if err:
        s.add("能起演示运行", FAIL, err)
        return
    rid = res["run"]["run_id"]
    s.add("能起演示运行", PASS, rid)

    deadline = time.time() + 90
    status, events = "running", []
    while time.time() < deadline:
        time.sleep(1.0)
        try:
            with urlrequest.urlopen(f"{base}/api/runs/{rid}", timeout=10) as r:
                status = json.loads(r.read().decode("utf-8"))["run"]["status"]
            if status in ("passed", "failed", "error", "cancelled", "relaxed"):
                with urlrequest.urlopen(f"{base}/api/runs/{rid}/events?limit=5000", timeout=10) as r:
                    events = json.loads(r.read().decode("utf-8"))["events"]
                break
        except Exception:  # noqa: BLE001
            continue

    s.add("运行到达终态", PASS if status != "running" else FAIL, status)
    kinds = {e.get("kind") for e in events}
    need = {"phase", "tool_call", "manifest", "verify", "run_end"}
    s.add("关键事件齐全", PASS if need <= kinds else FAIL,
          f"缺 {sorted(need - kinds)}", [f"共 {len(events)} 事件 / {len(kinds)} 种"])


# ============================================================
def main() -> int:
    global ARGS
    ap = argparse.ArgumentParser(description="SimpleAgent 体检")
    ap.add_argument("--json", action="store_true", help="输出 JSON（给 Agent 消费）")
    ap.add_argument("--triage", nargs="?", const="", default=None,
                    help="归因最近一次失败（可跟 run_id）")
    ap.add_argument("--e2e", action="store_true", help="额外跑一次演示运行")
    ap.add_argument("--base", default=os.getenv("AGENT_BASE", "http://127.0.0.1:8000"))
    ap.add_argument("--backend", default=None, help="上游代码目录（等价 AGENT_BACKEND_DIR）")
    ap.add_argument("--no-service", action="store_true", help="跳过服务与历史检查")
    ARGS = ap.parse_args()

    if ARGS.triage is not None:
        return do_triage(ARGS.triage or None)

    # 引导必须最先做：它负责 sys.path（否则 import 不到 core/tools）
    # 和 CWD（否则上游的相对路径会落在仓库根）。少了它，后面全是假失败。
    from bridge import bootstrap

    boot, err = _try(bootstrap.install)
    if err or not boot:
        sec = section("引导", "sys.path / .env / 运行根 / 切 CWD")
        sec.add("bootstrap.install", FAIL, err or "")
    else:
        sec = section("引导", "sys.path / .env / 运行根 / 切 CWD")
        sec.add("bootstrap.install", PASS, "；".join(boot["actions"]) or "已就绪")

    # 顺序有讲究：环境 → 路径 → 契约 → 标定 → 服务 → 历史
    # 后面依赖前面：路径不对就别谈契约，契约不对就别谈标定。
    for fn in (check_environment, check_paths, check_contract, check_spec):
        _, err = _try(fn)
        if err:
            section(fn.__name__, "检查本身出错").add("执行", FAIL, err)

    if not ARGS.no_service:
        _, err = _try(check_service, ARGS.base)
        if err:
            section("服务", "").add("执行", FAIL, err)
        _, err = _try(check_history, ARGS.base)
        if err:
            section("历史与归因", "").add("执行", FAIL, err)
        if ARGS.e2e:
            _, err = _try(do_e2e, ARGS.base)
            if err:
                section("端到端", "").add("执行", FAIL, err)

    fails = [i for s in SECTIONS for i in s.items if i["status"] == FAIL]
    warns = [i for s in SECTIONS for i in s.items if i["status"] == WARN]
    verdict = "FAIL" if fails else ("WARN" if warns else "PASS")

    if ARGS.json:
        print(json.dumps({
            "verdict": verdict,
            "sections": [s.to_dict() for s in SECTIONS],
            "fail_count": len(fails),
            "warn_count": len(warns),
        }, ensure_ascii=False, indent=2))
        return 1 if fails else 0

    print("=" * 78)
    print(f"SimpleAgent 体检   {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"仓库根：{ROOT}")
    print("=" * 78)
    for s in SECTIONS:
        print(f"\n[{_TAG[s.worst]}] {s.title}" + (f"   （{s.note}）" if s.note else ""))
        for i in s.items:
            mark = {"PASS": "✓", "WARN": "!", "FAIL": "✗", "SKIP": "-"}[i["status"]]
            line = f"  {mark} {i['name']}"
            if i["detail"]:
                line += f"   {i['detail']}"
            print(line)
            for e in i["evidence"]:
                print(f"      ↳ {e}")
    print()
    print("=" * 78)
    print(f"结论：{verdict}   失败 {len(fails)} 项 · 提示 {len(warns)} 项")
    if verdict != "PASS":
        print("（失败项会直接影响功能；提示项不一定——自己判断）")
    print("=" * 78)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
