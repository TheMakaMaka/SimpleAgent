"""TRANSPARENCY-UI：四块「为什么」视图的机械验证。

为什么这个测试存在
------------------
本轮验收是「打开界面看四条」。在那之前，本仓库对前端的机械验证只有
`vue-tsc`（类型）与 `vite build`（能不能构建）——**两者都不执行归约器，
也不渲染任何组件**。于是「面板上到底会不会出现那行字」只能靠人点，
既无法在改动后立刻复查，也无法在评估文档里给出可复现命令（C2）。

这个测试把 `frontend/scripts/replay-check.mjs` 拉进门禁。那个脚本做两件事，
用的是**生产代码本身**：

  1. 用 esbuild 把 `src/store/run.ts` 就地打包，把**固定样例**
     `run_20260927_125647_5a3297` 的 77 条事件喂进去，断言四块视图的读数；
  2. 用**同一份 vite 配置**做 SSR 构建，把 `TransparencyPanel.vue` /
     `VerifyPanel.vue` 用 `vue/server-renderer` 渲染成 HTML，
     断言那几行字**真的在 HTML 里**（读数对、面板没显示，是最阴的失效）。

★ 它**不能**替代人眼验收：排版、折叠、"看不看得懂"仍然只能由人判。
  验收方原话：「不要用"我们自己的测试过了"当作完成依据。」

运行：python tests/unit/test_transparency_ui.py
缺 node（或前端依赖未装）时按**配置分流** SKIP —— 与 `test_two_entrypoints.py`
对"自带副本是旧的"的处理同一条纪律：**不把自己的环境问题报成代码失败**。
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

FRONTEND = os.path.join(ROOT, "frontend")
REPLAY = os.path.join(FRONTEND, "scripts", "replay-check.mjs")
REDUCER = os.path.join(FRONTEND, "src", "store", "run.ts")
COLLECTOR = os.path.join(FRONTEND, "src", "store", "transparency.ts")
PANEL = os.path.join(FRONTEND, "src", "components", "TransparencyPanel.vue")
APP = os.path.join(FRONTEND, "src", "App.vue")
EVAL_DOC = os.path.join(ROOT, "docs", "EVALUATION-TRANSPARENCY2-UI.md")

#: 验收方指定的固定样例。**钉住它**：样例变了，验收故事就变了。
SAMPLE = os.path.join(ROOT, "data", "storage_data", "runs", "run_20260927_125647_5a3297")
SAMPLE_SEQS = [35, 56, 57, 74]

#: PowerShell 5.1 的 `Get-Content`/`Set-Content` 往返会把 UTF-8 中文读成 GBK、
#: 再写成 UTF-8（同时插一个 BOM）。这类文件**能构建、能通过类型检查**，
#: 只有人眼才看得出满屏乱码 —— 所以用两个廉价的机械信号挡住它。
#: 实测（2026-09-27）全仓库命中数为 0，不会误伤。
MOJIBAKE_MARKS = ["锛", "鈥", "鏂", "鐨", "涓嶆", "锟斤拷"]
BOM = b"\xef\xbb\xbf"

checks: list[tuple[str, bool]] = []
skipped: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def skip(name: str, reason: str) -> None:
    skipped.append(name)
    print(f"  SKIP  {name}   {reason}")


def read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


# ============================================================
print("=" * 74)
print("[1] 固定样例必须是验收方说的那一条")
print("=" * 74)
events_path = os.path.join(SAMPLE, "events.jsonl")
if not os.path.isfile(events_path):
    check("固定样例存在", False, os.path.relpath(events_path, ROOT))
else:
    events = [json.loads(l) for l in io.open(events_path, encoding="utf-8") if l.strip()]
    kinds = [e.get("kind") for e in events]
    print(f"  {len(events)} 条事件 · 状态 {events[-1].get('status')}")
    check("固定样例存在且非空", len(events) > 0)
    # 判据演化的骨架：失败 → 通过 → 被拒 → 最终记录
    seqs = [e["seq"] for e in events if e.get("kind") in ("verify_probe", "verify_skipped", "verify")]
    check("★ 样例里判据事件的序号与验收故事一致", seqs == SAMPLE_SEQS, str(seqs))
    check(
        "★ 样例里 (b) 执行失败、(c) 执行通过（且命令是 assert generate_obstacles）",
        bool([e for e in events if e.get("kind") == "verify_probe" and e.get("passed") is False])
        and any(
            e.get("kind") == "verify_probe"
            and e.get("passed") is True
            and "assert generate_obstacles" in (e.get("command") or "")
            for e in events
        ),
    )
    check("★ 样例里没有 `self_report`（C3 依赖后端 C1，本轮无法有）",
          "self_report" not in kinds)
    check("★ 样例里 `orchestrator_decision` 带 reasoning（A2 的数据在）",
          all(e.get("reasoning") for e in events if e.get("kind") == "orchestrator_decision"))


# ============================================================
print()
print("=" * 74)
print("[2] 用**生产代码**跑固定样例：读数 + 真渲染（需 node）")
print("=" * 74)
node = shutil.which("node")
have_deps = os.path.isdir(os.path.join(FRONTEND, "node_modules", "vue"))
if not node:
    skip("replay-check（读数 + SSR 渲染）", "找不到 node")
elif not have_deps:
    skip("replay-check（读数 + SSR 渲染）", "frontend/node_modules 未安装（先 npm install）")
elif not os.path.isfile(REPLAY):
    check("replay-check.mjs 存在", False, os.path.relpath(REPLAY, ROOT))
else:
    proc = subprocess.run(
        [node, os.path.join("scripts", "replay-check.mjs"), "--assert"],
        cwd=FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = proc.stdout or ""
    # 把脚本自己的读数原样打出来 —— 失败时要能直接看到是哪一条
    for ln in out.splitlines():
        print("    | " + ln)
    m = re.search(r"通过 (\d+)/(\d+)", out)
    total = int(m.group(2)) if m else 0
    passed = int(m.group(1)) if m else 0
    check("replay-check 退出码 0（全部读数与渲染断言通过）", proc.returncode == 0,
          f"exit={proc.returncode}")
    check("replay-check 断言条数足够（>=100）", total >= 100, f"{passed}/{total}")

    # 四条验收各自的关键行，独立再确认一次 —— 便于失败时一眼定位
    want = [
        ("验收 1 · 判据演化标出「上一条判据执行失败了」", "上一条判据执行失败了"),
        ("验收 1 · (b) 失败后的 (c) 通过（assert generate_obstacles）", "assert generate_obstacles"),
        ("验收 2 · 第 3 轮 reasoning（为什么又去改 obstacle_generator.py）",
         "需要修复 generate_obstacles 函数的参数问题"),
        ("验收 3 · t2 回合原话", "已生成 `ant_colony.py` 文件"),
        ("验收 4 · 诚实版 not_done 含「跑测试」", "验收 4 前半：not_done 含「跑测试」"),
        ("验收 4 · 谎报版矛盾被后端 fact_check 判出", "验收 4 后半：谎报版被标出矛盾"),
        ("D3 · 判据来源 = model", "判据来源=model"),
        ("B4 · 后端显式前因与推断分开显示", "后端显式前因在 HTML 里"),
        ("A2 · orchestrator_round.tasks 标为「声明」", "orchestrator_round 的声明任务标为"),
        # —— 本轮（TRANSPARENCY2-UI）——
        ("P2 · 19 个任务下当前项永远可见（状态级）", "折叠时**当前项永远可见**"),
        ("P2 · 藏起来的只能是已完成", "**藏起来的只能是已完成**"),
        ("P2 · 程序自己滚动不改变跟随模式", "程序自己滚动**不改变**模式"),
        ("P2 · 渲染出的面板里有折叠行且写明数量", "[渲染] 折叠行在 HTML 里"),
        ("P2 · 失败项一条都不许藏（渲染级）", "所有失败项的描述都在 HTML 里"),
        ("P3 · 四值都由后端产出过", "四值**都**由后端产出过"),
        ("P3 · 后端没给独立性时显示「未给」而不是「非独立」", "后端**没给**独立性"),
        ("P4 · 违反与判不了分开渲染", "「违反」与「判不了」分成两块"),
        ("P4 · 不出现「全部通过」", "不出现"),
        ("P4 · 未产出时显示「尚未产出」而不是通过", "后端未产出时显示「尚未产出」"),
    ]
    for name, needle in want:
        check(name, needle in out)


# ============================================================
print()
print("=" * 74)
print("[2b] C3 夹具：矛盾的判定必须来自**后端自己的 fact_check()**")
print("=" * 74)
# ★ 这一条是关键：`fact_check` **不由前端手写**，而由上游 core/self_report.py 产出，
#   否则"矛盾能不能被检出来"就变成我自己说了算 —— 那正是 C2 要防的"第二个自嗨通道"。
FIXTURE = os.path.join(ROOT, "tests", "fixtures", "transparency-fixture.json")
GEN = os.path.join(ROOT, "tests", "diagnostics", "make_transparency_fixture.py")
check("夹具生成脚本存在（可复现）", os.path.isfile(GEN), os.path.relpath(GEN, ROOT))
if not os.path.isfile(FIXTURE):
    check("夹具存在", False, os.path.relpath(FIXTURE, ROOT))
else:
    fx = json.load(io.open(FIXTURE, encoding="utf-8"))
    check("夹具存在", True, f"{len(json.dumps(fx))} 字节")
    check("★ 夹具声明了它是生成的、不是手编的", "生成" in fx.get("_note", ""))
    honest = fx.get("self_report_honest", {})
    lying = fx.get("self_report_lying", {})
    nd = " ".join(honest.get("not_done") or [])
    check("★ 诚实版 not_done 含「跑测试」", "跑测试" in nd)
    check("★ 诚实版 not_done 含「生成报告」", "生成报告" in nd)
    fc_h = (honest.get("fact_check") or {}).get("contradictions") or []
    fc_l = (lying.get("fact_check") or {}).get("contradictions") or []
    check("★ 诚实版无矛盾（不凭空造矛盾）", not fc_h, str(len(fc_h)))
    check("★ 谎报版有矛盾，且由后端判定", bool(fc_l), ",".join(c.get("kind", "") for c in fc_l))
    check("★ 谎报版的矛盾指向工作区里没有的 report.md",
          any("report.md" in (c.get("claim", "") + c.get("fact", "")) for c in fc_l))
    check("★ 矛盾类型用的是后端定义的 kind",
          all(c.get("kind") in ("artifact-missing", "verify-claim-vs-fact", "check-claim-vs-fact",
                                "lint-failed-not-disclosed", "requirement-evidence-missing",
                                "done-mentions-missing-file") for c in fc_l),
          ",".join(c.get("kind", "") for c in fc_l))
    # 机械事实必须来自固定样例，不能是编的
    check("★ 夹具的机械事实取自固定样例（含 3 个真实产物）",
          set(fx.get("machine_facts", {}).get("touched_files") or []) ==
          {"obstacle_generator.py", "ant_colony.py", "test_ant_colony.py"},
          str(fx.get("machine_facts", {}).get("touched_files")))

    # ---- P3/P4 的夹具同样必须是**后端真函数**产出的 ----
    vd = fx.get("verdicts") or {}
    outcomes = {v.get("outcome") for v in vd.values()}
    check("★ P3 夹具含四值（pass/fail/abstain/invalid）且由 build_verdict 产出",
          {"pass", "fail", "abstain", "invalid"} <= outcomes, str(sorted(outcomes)))
    check("★ P3 夹具里「模型自拟判据的通过」带 model-self-authored（不与调用方同形）",
          any(v.get("outcome") == "pass" and v.get("criterion_trust") == "model-self-authored"
              for v in vd.values()))
    check("★ P3 夹具里有 criterion_independent=true 的调用方判据",
          any(v.get("criterion_independent") is True for v in vd.values()))
    dr = fx.get("decompose_review") or {}
    check("★ P4 夹具来自 review_decomposition（输入是真实那次拆分：19 任务 / 2 交付物）",
          (fx.get("decompose_input") or {}).get("tasks") == 19
          and (fx.get("decompose_input") or {}).get("files") == 2,
          str(fx.get("decompose_input")))
    check("★ P4 夹具 violated 与 undecidable 同时非空（否则验不了「两者分开」）",
          bool(dr.get("violated")) and bool(dr.get("undecidable")),
          f"{len(dr.get('violated') or [])}/{len(dr.get('undecidable') or [])}")
    check("★ P4 夹具 undecidable 非空时 passed=false（后端自己就不算通过）",
          dr.get("undecidable") and dr.get("passed") is False)


# ============================================================
print()
print("=" * 74)
print("[3] 面板必须真的挂在界面上（不能只是写好了没挂）")
print("=" * 74)
app = read(APP)
check("App.vue 引入了 TransparencyPanel", "import TransparencyPanel from '@/components/TransparencyPanel.vue'" in app)
check("App.vue 模板里挂了 <TransparencyPanel", "<TransparencyPanel" in app)
check("★ 默认展开（藏起来等于没做）", "tpCollapsed = ref(false)" in app)

panel = read(PANEL)
check("★ 面板默认落在「判据演化」tab", "props.initialTab ?? 'criteria'" in panel)
check("★ 矛盾/缺失提示在标题栏（不随 tab 隐藏）",
      'class="tp__alarm"' in panel and "矛盾" in panel)
check("★ 四个 tab 都在", all(k in panel for k in
                            ["criteria", "decisions", "turns", "report"]))


# ============================================================
print()
print("=" * 74)
print("[4] 与「前端 case = 事件词表」那条门禁不冲突")
print("=" * 74)
# `tests/unit/test_event_contract.py` 的 [3] 组判据是"前端认了、后端不发 = 死代码"。
# 本轮后端（A1/B1/C1/D1）与本仓库**同轮**交付，`self_report`/`fact_check`
# 此刻谁都还不发。所以本轮**不新增 case**，改由形状驱动的采集器收下它们；
# 等契约声明了再补 case + 校准。这里把这个决定钉住，免得后来者顺手加一个 case
# 把那个门禁弄红（或者更糟：为了让它绿而放宽门禁）。
reducer = read(REDUCER)
for kind in ("self_report", "fact_check"):
    check(f"★ 未为尚未交付的 `{kind}` 加 case（否则死代码门禁会红）",
          f"case '{kind}'" not in reducer)
check("归约器把采集器接了进来", "collectTransparency(" in reducer)
collector = read(COLLECTOR)
check("★ 采集器**声明**了它认得的词表", "export const RECOGNIZED_KINDS" in collector)
check("★ 声明与行为同一处（HANDLERS 的键就是 RecognizedKind）",
      "Record<RecognizedKind," in collector and "HANDLERS[kind as RecognizedKind]" in collector)
for kind in ("orchestrator_round", "verify_criterion", "self_report"):
    check(f"采集器认得上游新事件 `{kind}`", f"'{kind}'" in collector)


# ============================================================
print()
print("=" * 74)
print("[5] 编码门禁：别把 UTF-8 中文写成乱码还能通过构建")
print("=" * 74)
# 起因是一次真实事故：用 PowerShell 5.1 的 Get-Content/Set-Content 往返改一个
# .ts 文件，中文被读成 GBK 再写成 UTF-8 —— **类型检查与构建全都照样通过**，
# 只有人眼看界面才会发现满屏乱码。所以补一个廉价信号。
scanned = 0
bad_bom: list[str] = []
bad_moji: list[str] = []
for dp, dn, fn in os.walk(os.path.join(FRONTEND, "src")):
    for f in fn:
        if not f.endswith((".ts", ".vue")):
            continue
        p = os.path.join(dp, f)
        raw = open(p, "rb").read()
        scanned += 1
        rel = os.path.relpath(p, ROOT)
        if raw.startswith(BOM):
            bad_bom.append(rel)
        text = raw.decode("utf-8", "replace")
        if any(m in text for m in MOJIBAKE_MARKS):
            bad_moji.append(rel)
print(f"  扫了 {scanned} 个前端源文件")
check("前端源码没有 BOM（PS 5.1 覆写的指纹）", not bad_bom, "; ".join(bad_bom[:4]))
check("前端源码没有 GBK 乱码特征", not bad_moji, "; ".join(bad_moji[:4]))


# ============================================================
print()
print("=" * 74)
print("[6] 文档与代码同步")
print("=" * 74)
if not os.path.isfile(EVAL_DOC):
    check("评估文档存在", False, os.path.relpath(EVAL_DOC, ROOT))
else:
    doc = read(EVAL_DOC)
    check("评估文档存在", True, f"{len(doc)} 字符")
    for sec in ["P1", "P2", "P3", "P4"]:
        check(f"评估文档覆盖 {sec}", sec in doc)
    for cit in ["file:line", "文件:行"]:
        if cit in doc:
            check("评估文档给出了「文件:行」级定位", True)
            break
    else:
        check("评估文档给出了「文件:行」级定位", False, "未出现 file:line / 文件:行")

readme = os.path.join(FRONTEND, "README.md")
if os.path.isfile(readme):
    rt = read(readme)
    check("frontend/README.md 登记了新面板与检查脚本",
          "TransparencyPanel" in rt and "replay-check" in rt)


# ============================================================
print()
print("=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}" + (f" · 跳过 {len(skipped)}" if skipped else ""))
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
