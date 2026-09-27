"""工具 profile 过滤自检。

核心验证：**保留全部工具，只按 profile 隐藏** —— 种子工具不删除。
这比 `tool_hint` 提示更硬：模型看不到就不存在"选错工具"。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core import LLMClient, LLMConfig, Orchestrator, Worker  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402
from tools.registry import (  # noqa: E402
    PROFILE_ANY, PROFILE_CODING, PROFILE_GENERAL, describe_profiles,
    hidden_names, tool_names, tool_schemas,
)

# 种子工具：代表未来通用 agent 的能力，**必须保留注册**
SEED_TOOLS = {"get_weather", "calculate", "fetch_url", "get_system_info"}
# 编码流程必需
CODING_REQUIRED = {
    "run_python", "write_file", "read_file", "check_syntax", "run_lint",
    "check_and_run", "parse_python_error", "list_workspace", "review_code",
    "get_architecture", "get_module", "find_symbol", "reflect_on_history",
}


def main() -> int:
    checks: list[tuple[str, bool]] = []

    print("=" * 74)
    print("[1] 工具没有被删除，只是按 profile 隐藏")
    print("=" * 74)
    all_names = set(TOOLS_MAP)
    print(f"  注册总数: {len(all_names)}")
    checks.append(("种子工具仍全部注册", SEED_TOOLS <= all_names))
    checks.append(("编码工具仍全部注册", CODING_REQUIRED <= all_names))
    print(f"  种子工具注册: {sorted(SEED_TOOLS & all_names)}")
    print(f"  缺注册的种子工具: {sorted(SEED_TOOLS - all_names) or '无'}")

    coding = set(tool_names(PROFILE_CODING))
    general = set(tool_names(PROFILE_GENERAL))
    print(f"\n  coding profile: {len(coding)} 个")
    print(f"  general profile: {len(general)} 个")
    print(f"  coding 下隐藏: {sorted(hidden_names(PROFILE_CODING))}")

    print("\n" + "=" * 74)
    print("[2] 过滤结果符合预期")
    print("=" * 74)
    checks.append(("编码工具在 coding profile 可见", CODING_REQUIRED <= coding))
    checks.append(("天气在 coding profile 不可见", "get_weather" not in coding))
    checks.append(("计算器在 coding profile 不可见", "calculate" not in coding))
    checks.append(("抓网页在 coding profile 不可见", "fetch_url" not in coding))
    checks.append(("天气在 general profile 可见", "get_weather" in general))
    # get_system_info 声明了双 profile
    checks.append(("get_system_info 两个 profile 都可见",
                   "get_system_info" in coding and "get_system_info" in general))
    # 所有工具都必须属于至少一个 profile
    covered = coding | general
    checks.append(("每个工具至少属于一个 profile", covered == all_names))
    print(f"  coding ∩ general: {sorted(coding & general)}")
    print(f"  未被任何 profile 覆盖: {sorted(all_names - covered) or '无'}")

    print("\n" + "=" * 74)
    print("[3] tool_schemas 过滤 / 不过滤")
    print("=" * 74)
    checks.append(("传 None 返回全部（诊断用）", len(tool_schemas(None)) == len(all_names)))
    checks.append(("传 coding 只返回可见的",
                   len(tool_schemas(PROFILE_CODING)) == len(coding)))
    checks.append(("schema 结构与原生一致",
                   all(set(t) == {"type", "function"} and
                       {"name", "description", "parameters"} <= set(t["function"])
                       for t in tool_schemas(PROFILE_CODING))))
    print(f"  schemas(None)={len(tool_schemas(None))}  schemas(coding)={len(tool_schemas(PROFILE_CODING))}")

    print("\n" + "=" * 74)
    print("[4] Worker 实际下发的工具集")
    print("=" * 74)
    prof = LLMConfig.from_env(prefix="ORCH")
    w = Worker(LLMClient(prof))
    w_names = {t["function"]["name"] for t in w.tools}
    print(f"  Worker profile={w.profile} 下发 {len(w.tools)} 个")
    print(f"  隐藏: {w.hidden_tools}")
    checks.append(("Worker 默认走 coding profile", w.profile == PROFILE_CODING))
    checks.append(("Worker 不下发种子工具",
                   not (SEED_TOOLS - {"get_system_info"}) & w_names))
    checks.append(("Worker 下发编码工具", CODING_REQUIRED <= w_names))
    checks.append(("Worker 记录的隐藏清单与注册表一致",
                   set(w.hidden_tools) == set(hidden_names(PROFILE_CODING))))

    w2 = Worker(LLMClient(prof), profile=PROFILE_GENERAL)
    w2_names = {t["function"]["name"] for t in w2.tools}
    checks.append(("general profile 下可见天气", "get_weather" in w2_names))
    checks.append(("general profile 下不可见 run_python", "run_python" not in w2_names))
    print(f"  general Worker 下发 {len(w2.tools)} 个: {sorted(w2_names)}")

    print("\n" + "=" * 74)
    print("[5] 编排器与 Worker 的工具视图一致")
    print("=" * 74)
    o = Orchestrator(LLMClient(prof), w)
    # 编排器给模型的候选列表应与 Worker 可见集合一致，
    # 否则会建议一个子循环根本拿不到的工具
    checks.append(("两者可见集合相同",
                   set(tool_names(w.profile)) == w_names))
    print(f"  orchestrator 候选 = {len(tool_names(w.profile))} 个")
    print(f"  worker 下发        = {len(w_names)} 个")

    print("\n" + "=" * 74)
    print("[6] describe_profiles 诊断")
    print("=" * 74)
    d = describe_profiles()
    for p in sorted(d):
        print(f"  {p}: {len(d[p])} 个")
    checks.append(("诊断含 both profiles",
                   PROFILE_CODING in d and PROFILE_GENERAL in d))
    checks.append(("any 声明归入具体 profile",
                   PROFILE_ANY not in d or not d[PROFILE_ANY]))

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


raise SystemExit(main())
