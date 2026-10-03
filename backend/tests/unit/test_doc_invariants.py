"""文档声明的不变量 ↔ 代码实际值（语义漂移的机械防线）。

补的缺口
--------
`test_doc_consistency.py` 只能抓"原文短语"（如 `不会自动加载`）。
但文档里还有一类漂移是**语义**的：它换了个说法描述同一件事，
原文短语法抓不到，而值已经变了。

本文件把**可枚举的不变量**逐条对齐：

  文档里声称的                      必须等于代码里的
  ├─ 角色名清单                     core.config.ROLES
  ├─ profile 名                      tools.registry.PROFILE_*
  ├─ 工具归属某 profile 的成员       工具自己的 profiles 声明
  ├─ 阶段名与推进顺序                core.cycle.CyclePhase / PHASE_ORDER
  ├─ 检查点后端名                    CheckpointManager 实际选中的
  ├─ 门禁工具名                      CheckPipeline 实际调用的
  ├─ /profile 顶层键                  main.profile() 实际返回
  └─ 决策类型（repeated_failure 等） core.decisions 的预设选项集

这些都是**程序可判定**的，所以能作门禁；语义解释是否贴切仍需人/模型判断。
"""

import inspect
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

DOCS = {
    "README.md": os.path.join(ROOT, "README.md"),
    "CYCLE.md": os.path.join(ROOT, "CYCLE.md"),
    "ARCHITECTURE.md": os.path.join(ROOT, "docs", "ARCHITECTURE.md"),
    "MODULES.md": os.path.join(ROOT, "docs", "MODULES.md"),
    "OPERATIONS.md": os.path.join(ROOT, "docs", "OPERATIONS.md"),
}


def read(p: str) -> str:
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def main() -> int:
    checks: list[tuple[str, bool]] = []
    texts = {k: read(v) for k, v in DOCS.items()}
    blob = "\n".join(texts.values())

    print("=" * 74)
    print("[1] 角色名清单 ↔ core.config.ROLES")
    print("=" * 74)
    import core.config as cfg

    real_roles = set(cfg.ROLES)
    # 文档里以 `` `role` `` 形式出现、且带环境前缀说明的角色
    doc_roles = set(re.findall(r"\|\s*`(\w+)`\s*\|\s*`[A-Z]+`\s*\|", texts["MODULES.md"]))
    print(f"  代码角色: {sorted(real_roles)}")
    print(f"  文档列出的角色（MODULES ROLES 表）: {sorted(doc_roles)}")
    missing = sorted(real_roles - doc_roles)
    extra = sorted(doc_roles - real_roles)
    checks.append(("文档列出了全部角色", not missing))
    print(f"  {'PASS' if not missing else 'FAIL'}  未列出的角色: {missing or '无'}")
    checks.append(("文档没有多余角色", not extra))
    print(f"  {'PASS' if not extra else 'FAIL'}  文档多出的角色: {extra or '无'}")

    print("\n" + "=" * 74)
    print("[2] profile 名 ↔ tools.registry")
    print("=" * 74)
    from tools.registry import (
        PROFILE_ANY, PROFILE_CODING, PROFILE_GENERAL, describe_profiles,
    )

    real_profiles = {PROFILE_CODING, PROFILE_GENERAL}
    doc_profiles = set(re.findall(r"###\s*(\w+)\s*profile（\d+\s*个）", texts["MODULES.md"]))
    print(f"  代码: {sorted(real_profiles)}  文档: {sorted(doc_profiles)}")
    checks.append(("文档列出全部 profile", real_profiles == doc_profiles))

    # 每个 profile 的成员数
    d = describe_profiles()
    for prof in sorted(real_profiles):
        m = re.search(rf"###\s*{prof}\s*profile（(\d+)\s*个）", texts["MODULES.md"])
        real = len(d.get(prof, []))
        ok = bool(m) and int(m.group(1)) == real
        checks.append((f"{prof} profile 成员数正确", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {prof}: 文档 "
              f"{m.group(1) if m else '?'}，实际 {real}")

    print("\n" + "=" * 74)
    print("[3] 阶段名与推进顺序 ↔ core.cycle")
    print("=" * 74)
    from core.cycle import PHASE_ORDER

    real_phases = [p.value for p in PHASE_ORDER]
    print(f"  代码 PHASE_ORDER: {real_phases}")
    # 文档里阶段名一律大写（PLAN/WRITE/...），所以比对要**大小写不敏感**——
    # 早期版本用大小写敏感匹配，误报"没提到 plan"。
    phases_blob = texts["CYCLE.md"].upper()
    for ph in real_phases:
        found = re.search(rf"\b{ph.upper()}\b", phases_blob) is not None
        checks.append((f"CYCLE 提到阶段 {ph.upper()}", found))
        if not found:
            print(f"  FAIL  CYCLE 未提到阶段 {ph.upper()}")

    # 数据流描述里的阶段顺序必须与 PHASE_ORDER 一致。
    # 允许中间插别的环节（如 MANIFEST），所以按"出现在 PHASE_ORDER 里的阶段名"抽取。
    m = re.search(r"PLAN\s*→([^\n]{0,120})", texts["CYCLE.md"], re.IGNORECASE)
    if m:
        seq = [x.lower() for x in re.findall(r"[A-Z]{4,}", "PLAN→" + m.group(1))]
        seq = [s for s in seq if s in real_phases]
        ok = seq == real_phases
        checks.append(("CYCLE 流程图顺序 == PHASE_ORDER", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  文档流程: {seq}")
    else:
        checks.append(("CYCLE 含阶段流程图", False))
        print("  FAIL  未找到阶段流程图")

    print("\n" + "=" * 74)
    print("[4] 检查点后端名 ↔ CheckpointManager")
    print("=" * 74)
    from core.checkpoint import FileSnapshotBackend, GitBackend

    real_backends = {GitBackend.name, FileSnapshotBackend.name, "none"}
    print(f"  代码后端名: {sorted(real_backends)}")
    for b in ("git", "snapshot", "none"):
        found = f"`{b}`" in blob
        checks.append((f"文档提到后端 {b}", found))
        if not found:
            print(f"  FAIL  文档未提到后端 {b}")

    print("\n" + "=" * 74)
    print("[5] 门禁工具名 ↔ CheckPipeline 实际调用")
    print("=" * 74)
    from core.pipeline import CheckPipeline

    src = inspect.getsource(CheckPipeline)
    # 只取形如 self._call("名字", ...) 的**调用**；
    # `def _call(self, name: str, ...)` 的定义行会把形参名 `name` 的提示词误抓成
    # 一个叫 "tool" 的假工具，所以要排除定义行。
    calls = re.findall(r'self\._call\(\s*\n?\s*"(\w+)"', src)
    # run_verify 里通过 self._call(\n  "check_and_run", ...) 调用
    calls += re.findall(r'"(check_and_run)"', src)
    gate_tools = sorted({t for t in calls if t and t != "tool"})
    print(f"  CheckPipeline 调用的工具: {gate_tools}")
    checks.append(("识别出门禁工具", len(gate_tools) >= 3))
    for t in gate_tools:
        found = f"`{t}`" in texts["MODULES.md"]
        checks.append((f"MODULES 提到门禁工具 {t}", found))
        if not found:
            print(f"  FAIL  MODULES 未提到门禁工具 {t}")

    print("\n" + "=" * 74)
    print("[6] 决策类型 ↔ core.decisions 预设")
    print("=" * 74)
    import core.decisions as dec

    real_kinds = set(re.findall(r'^DecisionKind = Literal\[(.*?)\]',
                                read(os.path.join(ROOT, "core", "decisions.py")),
                                re.MULTILINE | re.DOTALL)[0].replace('"', '').split(", "))
    real_kinds = {k.strip() for k in real_kinds if k.strip()}
    print(f"  代码决策类型: {sorted(real_kinds)}")
    for k in sorted(real_kinds):
        found = f"`{k}`" in blob
        checks.append((f"文档提到决策类型 {k}", found))
        if not found:
            print(f"  FAIL  文档未提到决策类型 {k}")

    print("\n" + "=" * 74)
    print("[7] 文档清单 ↔ 实际 docs/*.md（防孤儿文档）")
    print("=" * 74)
    # 缺口：新增一篇文档很容易，但**没人会记得**把它登记进 README 的文档表。
    # 孤儿文档等于不存在——读者根本不知道要看它。这条把它变成机械检查。
    readme = texts["README.md"]
    doc_files = sorted(
        n for n in os.listdir(os.path.join(ROOT, "docs")) if n.endswith(".md")
    )
    # README 里以 `docs/xxx.md` 或 `xxx.md` 反引号形式被引用即算登记
    orphans = [
        n for n in doc_files
        if f"docs/{n}" not in readme and f"`{n}`" not in readme
    ]
    print(f"  docs/ 下的文档: {doc_files}")
    print(f"  未被 README 引用的: {orphans or '无'}")
    checks.append(("README 登记了全部 docs/*.md", not orphans))

    # 反向：README 引用的 docs 文件必须真实存在
    referenced = set(re.findall(r"`docs/([\w.-]+\.md)`", readme))
    missing_files = sorted(n for n in referenced if n not in doc_files)
    print(f"  README 引用但不存在的: {missing_files or '无'}")
    checks.append(("README 引用的 docs 文件都存在", not missing_files))

    print("\n" + "=" * 74)
    print("[8] 责任划分规则数 / 词表 ↔ core.contract")
    print("=" * 74)
    # 缺口（统筹方实测发现）：`ISSUE_RULES` 是 21 条，而 VERSIONS / PENDING /
    # MODULES 都写"20 条"。这正是 `U-` 类规则要抓的"声明 vs 实现不符"，
    # 只不过发生在文档与代码之间。这条把它变成机械检查。
    import core.contract as ct

    real_n = len(ct.ISSUE_RULES)
    print(f"  代码里 ISSUE_RULES: {real_n} 条")
    # 只查**当前状态类**文档（CHANGELOG / VERSIONS 是历史记录，不参与）
    state_docs = {
        "MODULES.md": texts["MODULES.md"],
        "FRONTEND_CONTRACT.md": read(
            os.path.join(ROOT, "docs", "FRONTEND_CONTRACT.md")),
        "PENDING_DECISIONS.md": read(
            os.path.join(ROOT, "docs", "PENDING_DECISIONS.md")),
    }

    claimed: list[tuple[str, int]] = []
    for name, text in state_docs.items():
        for line in text.splitlines():
            # 只认**同一条目里点了名**的行，避免误抓"prompt 的 12 条规则"
            if "ISSUE_RULES" not in line and "责任划分规则" not in line:
                continue
            for m in re.finditer(r"(\d+)\s*条", line):
                claimed.append((name, int(m.group(1))))
    print(f"  文档里点名的规则数: {claimed or '（无）'}")
    wrong = [(n, c) for n, c in claimed if c != real_n]
    for n, c in wrong:
        print(f"  FAIL  {n} 写 {c} 条，实际 {real_n} 条")
    checks.append(("文档声称的规则数 == ISSUE_RULES 条数", not wrong))
    checks.append(("至少一处文档声明了规则数（否则这条检查是空转）",
                   bool(claimed)))

    # 词表：4 个归属 / 6 个结论 —— 两侧必须同一套词表
    fc = state_docs["FRONTEND_CONTRACT.md"]
    miss_owner = [o for o in ct.OWNER_ORDER if f"`{o}`" not in fc]
    miss_verdict = [v for v in ct.VERDICTS if f"`{v}`" not in fc]
    print(f"  FRONTEND_CONTRACT 未提到的归属: {miss_owner or '无'}")
    print(f"  FRONTEND_CONTRACT 未提到的结论: {miss_verdict or '无'}")
    checks.append(("FRONTEND_CONTRACT 列全了 4 个归属值", not miss_owner))
    checks.append(("FRONTEND_CONTRACT 列全了 6 个结论值", not miss_verdict))

    print("\n" + "=" * 74)
    print("[8.1] §6.5 规则表**逐行**比对（条数对不代表每一行都对）")
    print("=" * 74)
    # 缺口（统筹方 D5 指出）：上面那两条只查"条数"与"词表出现过"。
    # 若某一行把 owner/severity 写错（D4 就是：`P-phase-unknown` 那行当时还写着
    # `后端 | breaking`），条数仍是 23、4 个归属与 6 个结论也都出现过 —— **两条都通过**。
    # 这类漂移"没有症状"：服务照跑、界面照显、其它测试全绿。只有逐行比对才看得见。
    CN_OWNER = {"后端": ct.OWNER_BACKEND, "前端": ct.OWNER_FRONTEND,
                "协商": ct.OWNER_BOTH, "双方协商": ct.OWNER_BOTH,
                "ops": ct.OWNER_OPS, "`ops`": ct.OWNER_OPS}
    row_re = re.compile(r"^\|\s*`([UPO]-[a-z][a-z-]+)`\s*\|(.*)$")
    seen_rows: dict[str, tuple[str, str]] = {}
    row_bad: list[str] = []
    for line in fc.splitlines():
        m = row_re.match(line.strip())
        if not m:
            continue
        code, rest = m.group(1), m.group(2)
        # 去掉 markdown 强调与反引号再比对 —— 否则 `**协商**` 会被当成"未知归属"，
        # 让这条检查自己产生假告警（第一版就是这么误报 D4 的）。
        cells = [c.strip().strip("*").strip("`").strip() for c in rest.split("|")]
        # U- 表：| code | 级别 | 触发 |       → 归属恒为 backend
        # P-/O- 表：| code | 归谁 | 级别 | … | → 第 1、2 格是归属与级别
        if cells and cells[0] in CN_OWNER:
            owner, severity = CN_OWNER[cells[0]], (cells[1] if len(cells) > 1 else "")
        else:
            owner, severity = ct.OWNER_BACKEND, (cells[0] if cells else "")
        severity = severity.strip("`")
        if code not in ct.ISSUE_RULES:
            row_bad.append(f"{code}: 文档里有、规则表里没有")
            continue
        seen_rows[code] = (owner, severity)
        real = ct.ISSUE_RULES[code]
        if owner != real.owner:
            row_bad.append(f"{code}: owner 文档={owner} 代码={real.owner}")
        if severity != real.severity:
            row_bad.append(f"{code}: severity 文档={severity} 代码={real.severity}")

    missing_rows = sorted(set(ct.ISSUE_RULES) - set(seen_rows))
    print(f"  从 §6.5 解析到 {len(seen_rows)} 行（规则表共 {len(ct.ISSUE_RULES)} 条）")
    print(f"  未在表里出现的 code: {missing_rows or '无'}")
    print(f"  逐行不一致: {row_bad or '无'}")
    checks.append(("§6.5 规则表逐行 owner/severity 与代码一致", not row_bad))
    checks.append(("§6.5 覆盖了全部 code（否则逐行比对会漏）", not missing_rows))

    print("\n" + "=" * 74)
    print("[9] 行尾未被悄悄改动（LF 文件被整份翻成 CRLF）")
    print("=" * 74)
    # 实测踩过的坑：`pathlib.Path.write_text()` 在 Windows 上会把 `\n` 翻译成
    # `\r\n`。仓库里行尾**本来就是混合的**（`core/*.py` 多为 LF，
    # `README.md` / `CYCLE.md` / `docs/*.md` 多为 CRLF），所以一次
    # read_text→write_text 就能把某个 LF 文件整份翻掉 ——
    # diff 里出现 1700 行变更，而真实改动只有 60 行。
    #
    # 判据不引入新约定，只要求：**工作区的行尾与索引一致**（= 没被悄悄改）。
    # 这样既守住"别悄悄改行尾"，也不必先统一全仓。
    #
    # ⚠️ 实现教训：第一版给**每个文件起一个 `git show` 进程**（约 200 次子进程），
    # 把整个测试拖到超时 —— **慢门禁等于会被绕过的门禁**。
    # 改用**一次** `git ls-files --eol`：它直接给出 i/(索引) 与 w/(工作区) 的
    # 行尾，既快又能顺带抓 `mixed`。
    try:
        import subprocess

        from core.checkpoint import resolve_git

        git_exe = resolve_git()
    except Exception:  # noqa: BLE001
        git_exe = None

    if not git_exe:
        print("  （跳过：找不到 git，无法与索引比对）")
        checks.append(("行尾检查可执行（git 可用）", True))
    else:
        p = subprocess.run(
            [git_exe, "-c", f"safe.directory={ROOT}", "ls-files", "--eol"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        drifted: list[str] = []
        mixed: list[str] = []
        scanned = 0
        for line in (p.stdout or "").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            meta, path = parts[0], parts[1]
            path = path.strip().strip('"')
            if not path.endswith((".py", ".md", ".json")):
                continue
            fields = meta.split()
            idx = next((f[2:] for f in fields if f.startswith("i/")), "")
            wrk = next((f[2:] for f in fields if f.startswith("w/")), "")
            scanned += 1
            if wrk == "mixed":
                mixed.append(path)
            # `none` = 空文件；`-text` 之类不是本检查关心的情况
            if idx in ("lf", "crlf") and wrk in ("lf", "crlf") and idx != wrk:
                drifted.append(f"{path}（索引 {idx} → 工作区 {wrk}）")
        print(f"  用一次 `git ls-files --eol` 扫了 {scanned} 个文件")
        print(f"  行尾与索引不一致: {drifted or '无'}")
        print(f"  工作区行尾混合(mixed): {mixed or '无'}")
        checks.append(("工作区行尾与索引一致（没被悄悄改）", not drifted))
        checks.append(("没有行尾混合的文件", not mixed))
        checks.append(("行尾检查确实扫到了文件（否则是空转）", scanned > 50))

    # ---- 第 10 组也并进同一份汇总（否则 backup.py 会抓到"4/4"那行） ----
    group10_event_count(checks)

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败项:")
        for f in failed:
            print(f"  - {f}")
    return 1 if failed else 0
# ===========================================================================
# 第 10 组：文档里写的"上游 N 种事件"必须等于代码里的事件种类数
#   （配套 `REUSE-SYMBOL-SCOPE`：v1.22 曾把 18 写成 19 —— 把 `cycle_end` 新增的
#    两个 payload 键当成了一个新事件。这是 **U- 类"声明 vs 实现不符"**，
#    这类数字必须有机械门禁，否则只能靠人眼。）
#
#   2026-10-03（`ENVELOPE-WIRING` / D30）补两块：
#     ① 判据只认 `上游 N 种事件` 一种写法 ⇒ 扫不到
#        `upstream_event_kinds`（当前 N 个）—— 而 `docs/PENDING_DECISIONS.md`
#        写的正是后者（写着 13，实测 18）。现按两种写法抓，并纳入该文档；
#     ② 新增**反向**：合成一段陈旧声明，判据必须判"不一致"（证明它抓得住）。
# ===========================================================================
def _event_count_claims(text: str) -> list[tuple[str, int]]:
    """抓文档里"上游事件种类数"的两种声明写法：`上游 N 种事件` / `当前 N 个`。

    第二种是 2026-10-03 补的：`docs/PENDING_DECISIONS.md` 里写的是
    「`upstream_event_kinds` 只写上游的事件（当前 **13** 个）」——
    实测是 18，而旧判据只认"上游 N 种事件"，**扫不到它**（漏掉了声明写法）。
    """
    out: list[tuple[str, int]] = []
    for m in re.finditer(r"上游[^0-9\n]{0,14}(\d+)\s*种事件", text):
        out.append(("上游 N 种事件", int(m.group(1))))
    for m in re.finditer(r"`upstream_event_kinds`[^。\n]{0,80}?当前\s*\**(\d+)\**\s*个", text):
        out.append(("upstream_event_kinds 当前 N 个", int(m.group(1))))
    return out


def group10_event_count(checks: list[tuple[str, bool]]) -> None:
    import re as _re

    from core import contract as _ct

    actual = len(_ct.EVENTS)
    # 加 PENDING_DECISIONS.md：它就是本轮实测漂移（13 vs 18）的所在文档。
    docs = ["docs/FRONTEND_CONTRACT.md", "README.md", "docs/OPERATIONS.md",
            "docs/MODULES.md", "CYCLE.md", "docs/PENDING_DECISIONS.md"]
    hits = 0
    print("\n" + "=" * 74)
    print(f"[10] 文档声明的事件种类数 == 代码里的 {actual}")
    print("=" * 74)
    for rel in docs:
        path = os.path.join(ROOT, rel)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for form, got in _event_count_claims(text):
            hits += 1
            ok = got == actual
            print(f"  {rel}: 声明 {got} / 实际 {actual}  [{form}]  "
                  f"{'OK' if ok else 'DRIFT'}")
            checks.append((f"{rel} 的事件种类数与代码一致（{actual}）", ok))
    if hits == 0:
        # 一条都没扫到 = 空转，本身就该红（否则门禁形同不存在）
        print("  没有扫到任何『上游 N 种事件』的声明")
        checks.append(("文档里确实有『上游 N 种事件』的声明（否则门禁空转）", False))
    else:
        checks.append(("事件数门禁确实扫到了声明（否则空转）", True))

    # ★ 反向（2026-10-03 补）：判据本身必须**能红**。
    # 上面那条只证明"当前文档与代码一致"，不证明"判据抓得住不一致"。
    # 用一段合成的陈旧声明走同一解析路径：必须报出与 actual 不符。
    stale_sample = "上游 999 种事件；`upstream_event_kinds` 只写上游（当前 999 个）。"
    detected = [n for _form, n in _event_count_claims(stale_sample)]
    caught = bool(detected) and all(n != actual for n in detected)
    print(f"  反向：合成声明 {detected} ⇒ 判据{'抓到' if caught else '没抓到'}")
    checks.append(("★ 事件数判据有牙齿（合成的陈旧声明必须被判不一致）", caught))


raise SystemExit(main())
