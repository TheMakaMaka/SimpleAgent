"""文档 ↔ 代码一致性检查。

为什么要有这个测试
------------------
前两轮文档漂移的共同根因不是"某次漏改"，而是**同步靠人肉**：
改了代码/CHANGELOG，忘了改 MODULES/OPERATIONS，文档就开始说谎。

所以把"可机械验证的一致性"变成测试。它不能覆盖语义漂移，
但能抓住最高频的几类：工具数量、已删除的符号、过时措辞、无效的章节引用。

原则（与 CHANGELOG 开头一致）：
  - 上游文档（README / ARCHITECTURE / MODULES / OPERATIONS）**只记当前状态**
  - 修复过程记在 CHANGELOG
  - 因此上游文档里**不得出现"曾经是问题"的痕迹**
"""

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from tools import TOOLS_MAP  # noqa: E402
from tools.registry import PROFILE_CODING, PROFILE_GENERAL, tool_names  # noqa: E402

DOCS = {
    "README.md": os.path.join(ROOT, "README.md"),
    "ARCHITECTURE.md": os.path.join(ROOT, "docs", "ARCHITECTURE.md"),
    "MODULES.md": os.path.join(ROOT, "docs", "MODULES.md"),
    "OPERATIONS.md": os.path.join(ROOT, "docs", "OPERATIONS.md"),
    "CYCLE.md": os.path.join(ROOT, "CYCLE.md"),
    "CHANGELOG.md": os.path.join(ROOT, "docs", "CHANGELOG.md"),
}
# 上游文档 = 只该记当前状态的那些（CHANGELOG 不在此列，它就是记过程的）
UPSTREAM = {k: v for k, v in DOCS.items() if k != "CHANGELOG.md"}

# 已从代码中删除的符号：上游文档不得再当作现有字段引用。
# 例外：允许出现在「已删除」的说明语境里（用白名单行模式排除误报）。
DELETED_SYMBOLS = [
    "debug_head_chars",
    "verify_output_chars",
]
# 命中这些字样说明是在说明"已删除/不存在"，属于正当提及
DELETED_OK_MARKERS = ("不存在", "已删除", "已从")

# 已过时的措辞：这些说法在修复后就是错的。
# 注意用**具体错误写法**而不是宽泛词，避免误报正确表述
# （例如 "不是文档性常量" 是对的，不该被 "文档性常量" 命中）。
STALE_PHRASES = [
    ("未安装 git", "git 后端已接管；改为陈述当前选择行为"),
    ("本机未安装 git", "同上"),
    ("不会自动加载", ".env 已自动加载（main.py 调用 load_dotenv）"),
    ("是文档性常量", "PHASE_ORDER 现在强制校验阶段推进"),
    ("当前部署实际走 `snapshot`", "当前实际走 git；应陈述择优行为而非环境快照"),
    ("且无警告", "回退前已加 dry-run 警告"),
    ("没有任何警告", "回退前已加 dry-run 警告"),
    ("工具**全量下发**", "工具已按 profile 过滤"),
    ("全量下发（17", "工具已按 profile 过滤"),
]

# 运行时生成的产物路径：文档引用它们是正常的，不该校验存在性
GENERATED_PATH_PREFIXES = (
    "tests/output/", "storage_data/", ".checkpoints/", "workspace/",
)


def read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main() -> int:
    checks: list[tuple[str, bool]] = []
    texts = {name: read(path) for name, path in DOCS.items()}
    upstream_texts = {name: read(path) for name, path in UPSTREAM.items()}

    total = len(TOOLS_MAP)
    coding = len(tool_names(PROFILE_CODING))
    general = len(tool_names(PROFILE_GENERAL))

    print("=" * 74)
    print(f"[1] 工具数量：代码实际 总 {total} / coding {coding} / general {general}")
    print("=" * 74)

    # README 的已知限制表里若提到工具总数，必须与代码一致
    for name in ("README.md", "ARCHITECTURE.md", "MODULES.md", "OPERATIONS.md"):
        t = texts[name]
        # 抓形如 "17 个工具" / "16 个工具"
        found = set(re.findall(r"(\d+)\s*个工具", t))
        for n in sorted(found):
            ok = int(n) == total
            checks.append((f"{name} 提到的工具数 {n} == 实际 {total}", ok))
            print(f"  {'PASS' if ok else 'FAIL'}  {name}: 写了「{n} 个工具」，实际 {total}")

    # MODULES §17 必须列出全部工具名
    mod = texts["MODULES.md"]
    missing = [n for n in TOOLS_MAP if f"`{n}`" not in mod]
    checks.append(("MODULES 工具清单覆盖全部工具", not missing))
    print(f"  {'PASS' if not missing else 'FAIL'}  MODULES 未列出的工具: {missing or '无'}")

    # 分组数量声明
    for label, n in (("coding", coding), ("general", general)):
        pat = rf"###\s*{label}\s*profile（(\d+)\s*个）"
        m = re.search(pat, mod)
        ok = bool(m) and int(m.group(1)) == n
        checks.append((f"MODULES 声明的 {label} 工具数正确", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: 文档写 "
              f"{m.group(1) if m else '未声明'}，实际 {n}")

    print("\n" + "=" * 74)
    print("[2] 上游文档不得把已删除的字段当作现有字段")
    print("=" * 74)
    for sym in DELETED_SYMBOLS:
        offenders: list[str] = []
        for name, t in upstream_texts.items():
            for line in t.splitlines():
                if sym not in line:
                    continue
                # 说明"不存在/已删除"的提及是正当的
                if any(mk in line for mk in DELETED_OK_MARKERS):
                    continue
                offenders.append(f"{name}: {line.strip()[:60]}")
        ok = not offenders
        checks.append((f"上游文档不把已删除的 {sym} 当现有字段", ok))
        if ok:
            print(f"  PASS  {sym}")
        else:
            for o in offenders:
                print(f"  FAIL  {o}")

    print("\n" + "=" * 74)
    print("[3] 上游文档不得残留过时措辞")
    print("=" * 74)
    for phrase, why in STALE_PHRASES:
        hits = [name for name, t in upstream_texts.items() if phrase in t]
        ok = not hits
        checks.append((f"无过时措辞「{phrase}」", ok))
        if hits:
            print(f"  FAIL  「{phrase}」出现在 {hits} —— {why}")
        else:
            print(f"  PASS  「{phrase}」")

    print("\n" + "=" * 74)
    print("[4] 章节交叉引用有效")
    print("=" * 74)

    def headings_of(name: str) -> set[str]:
        # 只认真正的章节标题：`### 2.2 xxx`。
        # 刻意要求编号后跟 `.`/`、`/空格，避免把代码块里的 `# 注释` 当标题，
        # 也避免把 `## 文档导航` 这类无编号标题算进来（它们不可能被 § 引用）。
        return set(re.findall(
            r"^#{2,4}\s+(\d+(?:\.\d+)*(?:[.\d]*\d)?)\s*[.、\s]",
            texts[name], re.MULTILINE))

    all_headings: set[str] = set()
    for other in DOCS:
        all_headings |= headings_of(other)

    for name, t in upstream_texts.items():
        heads = headings_of(name)
        bad: list[str] = []
        for line in t.splitlines():
            if "§" not in line:
                continue
            # § 引用**可以指向其它文档的章节**（文档之间有交叉引用），
            # 所以用全局标题集校验，而不是只看本文件。
            for ref in re.findall(r"§(\d+(?:\.\d+)*(?:[.\d]*\d)?)", line):
                if ref not in all_headings:
                    bad.append(f"§{ref}")
        ok = not bad
        checks.append((f"{name} 的 §引用有效", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}: 本文件标题 {len(heads)} 个，"
              f"无效引用 {sorted(set(bad)) or '无'}")

    print("\n" + "=" * 74)
    print("[5] 未修清单校验（可机械核对的部分）")
    print("=" * 74)
    # MODULES §19 与 OPERATIONS §9 的每条都必须提到一个真实存在的标识符，
    # 以免留下"墓碑"（已修的项目应该删掉，而不是写"已修复"）
    for doc, sec_pat in (("MODULES.md", r"##\s*19\.(.*)$"),
                         ("OPERATIONS.md", r"###\s*9\.1(.*)$")):
        t = texts[doc]
        m = re.search(sec_pat, t, re.DOTALL)
        body = m.group(1) if m else ""
        # 只认「条目标题里的 ✅ 已修复」——正文里说明"已修复项不在此处"是正当的
        tomb = re.findall(r"^#{3,4}.*已修复", body, re.MULTILINE)
        ok = not tomb
        checks.append((f"{doc} 未修清单不含「已修复」墓碑", ok))
        print(f"  {'PASS' if ok else 'FAIL'}  {doc}: 「已修复」出现 {len(tomb)} 次")

    # 清单里提到的项目路径必须真实存在（运行时生成的产物除外）
    for doc in ("MODULES.md", "OPERATIONS.md"):
        t = texts[doc]
        paths = set(re.findall(r"`((?:core|tools|storage|tests|docs)/[\w./-]+)`", t))
        bad = [
            p for p in paths
            if not p.startswith(GENERATED_PATH_PREFIXES)
            and not os.path.exists(os.path.join(ROOT, p))
        ]
        checks.append((f"{doc} 引用的项目路径都存在", not bad))
        print(f"  {'PASS' if not bad else 'FAIL'}  {doc}: 不存在的路径 {sorted(bad) or '无'}")

    print("\n" + "=" * 74)
    print("[6] CHANGELOG 与上游的分工未被写反")
    print("=" * 74)
    changelog = texts["CHANGELOG.md"]
    ok1 = "不是当前状态的来源" in changelog or "只记「修复过程」" in changelog
    checks.append(("CHANGELOG 声明自己只记过程", ok1))
    print(f"  {'PASS' if ok1 else 'FAIL'}  CHANGELOG 定位声明")

    bad_claim = re.findall(r"以本文件为最新状态|最新状态以", "".join(upstream_texts.values()))
    checks.append(("上游文档不再声称以 CHANGELOG 为准", not bad_claim))
    print(f"  {'PASS' if not bad_claim else 'FAIL'}  上游「以 CHANGELOG 为准」: {len(bad_claim)} 次")

    print("\n" + "=" * 74)
    print("[7] 版本戳：上游文档声明的同步版本 == CHANGELOG 最新条目")
    print("=" * 74)
    sections = [int(n) for n in re.findall(r"^##\s*(\d+)\.", changelog, re.MULTILINE)]
    latest = max(sections) if sections else 0
    print(f"  CHANGELOG 最新条目: §{latest}")
    checks.append(("CHANGELOG 有条目编号", latest > 0))

    # 上游文档应声明 `同步至 CHANGELOG §N`
    for name, t in upstream_texts.items():
        m = re.search(r"同步至\s*CHANGELOG\s*§(\d+)", t)
        if not m:
            checks.append((f"{name} 有同步版本戳", False))
            print(f"  FAIL  {name}: 缺少「同步至 CHANGELOG §N」")
            continue
        declared = int(m.group(1))
        ok = declared == latest
        checks.append((f"{name} 版本戳 == §{latest}", ok))
        state = "PASS" if ok else "FAIL"
        print(f"  {state}  {name}: 声明 §{declared}，实际 §{latest}"
              + ("" if ok else "  ← 文档未同步"))

    print("\n" + "=" * 74)
    print("[8] README 项目结构声明的顶层目录都存在")
    print("=" * 74)
    # README 的"项目结构"块里列的顶层目录/文件，必须真实存在。
    # 这一层是补的：工具数动了但 README 结构说明没动的缺口，
    # 早期检查器只抓数字，抓不到"web/ 存在但结构里没列"这类问题。
    readme = texts["README.md"]
    declared = set(re.findall(r"^(\w+)/(?:\s|$)", readme, re.MULTILINE))
    declared |= set(re.findall(r"^(\w+\.py)(?:\s|$)", readme, re.MULTILINE))
    ignored = {"http", "https", "url"}      # 形如 http:// 的误匹配
    declared -= ignored
    missing = sorted(d for d in declared if not os.path.exists(os.path.join(ROOT, d)))
    checks.append(("README 结构声明的路径都存在", not missing))
    print(f"  {'PASS' if not missing else 'FAIL'}  声明 {len(declared)} 个，"
          f"不存在 {missing or '无'}")

    # 反向：真实存在的顶层包，README 结构里应当提到
    real_pkgs = sorted(
        n for n in os.listdir(ROOT)
        if os.path.isdir(os.path.join(ROOT, n))
        and not n.startswith((".", "_"))
        and n not in {"workspace", "docs", "sessions"}
    )
    not_mentioned = [p for p in real_pkgs if f"{p}/" not in readme]
    checks.append(("README 结构覆盖全部顶层包", not not_mentioned))
    print(f"  {'PASS' if not not_mentioned else 'FAIL'}  实际包 {real_pkgs}，"
          f"未提及 {not_mentioned or '无'}")

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


raise SystemExit(main())
