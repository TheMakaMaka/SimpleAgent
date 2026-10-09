"""P21 / M1 诊断探针：把四条验收的**机械输出**打出来（给人看，也给评估文档引）。

与 `tests/unit/test_memory_store.py` 的分工：
  · 单测 = **门禁**（会红/会绿，`raise SystemExit` 表达结论）；
  · 本探针 = **取证**（把原始回显打出来，供评估文档 §4 逐段粘贴）。

四段，与 `WORK-ORDER.md`【P21】的 M1 验收表一一对应：

  [A] 写入/读取可机械复现        —— 同输入 ⇒ 同 id / 同字节；重放逐字节相同
  [B] 越界写被结构化拒绝          —— 贴完整拒绝信封 + 证明目标文件没被写出去
  [C] 库根在两侧仓库之外（可机判）—— 贴默认根与三条隔离判据的计算结果
  [D] 有归档而非删除              —— 贴归档前后索引/计数/归档层文件，并证明读得回原文

外加一段 **[E] 只记分不决策**：两路召回的分数、漏召/误召读数、候选阈值曲线 ——
它是 M2 的输入，**本探针不选阈值、不改变任何行为**。

用法（仓库根目录）：

    D:\\PythonProject\\SimpleAgent2_Cycle_VueWeb\\.venv\\Scripts\\python.exe tests\\diagnostics\\probe_memory_store.py
"""

import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from core.context_store import scope, units as units_mod  # noqa: E402
from core.context_store.store import ContextStore  # noqa: E402

TEMPS: list[str] = []


def tmp_root() -> str:
    path = tempfile.mkdtemp(prefix="p21_probe_", dir=os.path.join(ROOT, ".tmp"))
    TEMPS.append(path)
    return path


def store() -> ContextStore:
    # 本轮硬边界只许写本仓库 ⇒ 探针的库根造在 .tmp/（显式逃生口）。
    # 默认根在两侧仓库之外，[C] 段用**纯路径计算**证明，不往那儿写东西。
    return ContextStore(tmp_root(), allow_inside_repos=True)


def show(title: str) -> None:
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def main() -> int:
    show("[A] 写入/读取可机械复现（内容寻址 + 幂等 + 重放同字节）")
    s = store()
    text = "T9 失败是因为 reuse 层把 app.route 判成了「不存在的符号」"
    first = s.write(text, source="T9", keywords=["reuse", "false-positive"],
                    symbols=["app.route"])
    second = s.write(text, source="T9")
    print(f"  文本        : {text}")
    print(f"  第一次写入  : id={first['id']} status={first['status']} "
          f"created={first['created']}")
    print(f"  第二次写入  : id={second['id']} status={second['status']} "
          f"deduped={second['deduped']}")
    print(f"  库内单元数  : {len(s.list_units())}")
    rec = s.read(first["id"])["unit"]
    print("  读回的单元  :")
    print("   " + json.dumps({k: rec[k] for k in
                             ("id", "created_at", "keywords", "symbol_refs",
                              "refs", "source", "sha256", "status")},
                            ensure_ascii=False, indent=2).replace("\n", "\n   "))
    print(f"  读回哈希 == 内容哈希: "
          f"{rec['sha256'] == units_mod.content_sha256(text)}")

    def replay_bytes() -> str:
        st = ContextStore(tmp_root(), allow_inside_repos=True)
        for i, t in enumerate(["第一条", "第二条", "第三条"]):
            st.write(t, source=f"S{i}", created_at=f"2026-10-05T10:0{i}:00")
        with open(os.path.join(st.root(), scope.LAYOUT["units"]), "rb") as f:
            return f.read().decode("utf-8")

    a, b = replay_bytes(), replay_bytes()
    print(f"  重放两次 units.jsonl 逐字节相同: {a == b}")
    print("  units.jsonl（确定性排序，一行一条）:")
    for line in a.splitlines():
        print("   " + line[:110])

    show("[B] 越界写被**结构化拒绝**（原始回显）")
    s2 = store()
    target = os.path.join(ROOT, "workspace", "_p21_probe_should_not_exist.json")
    try:
        s2.path_of("../workspace/_p21_probe_should_not_exist.json", write=True)
        print("  ！没有被拒绝 —— 这是缺陷")
    except scope.StoreScopeError as err:
        print("  请求路径: ../workspace/_p21_probe_should_not_exist.json")
        print("  拒绝信封: " + json.dumps(err.to_result(), ensure_ascii=False))
        print(f"  目标文件是否被写出去: {os.path.exists(target)}")
        print(f"  拒绝码: {err.code}")
        print(f"  允许的根: {list(err.allowed_roots)}")
    try:
        s2.path_of(os.path.join(ROOT, "core", "x.json"), write=True)
    except scope.StoreScopeError as err:
        print(f"  绝对路径越界  : code={err.code} path={err.path}")
    try:
        s2.path_of("   ", write=True)
    except scope.StoreScopeError as err:
        print(f"  空路径        : code={err.code} message={err.message}")
    print(f"  库内合法路径  : {s2.path_of('archive/x.json', write=True)}")
    print(f"  仍在库根之内  : "
          f"{scope.within(s2.path_of('archive/x.json'), s2.root())}")

    show("[C] 库根在**两侧仓库之外**（可机判）")
    print(f"  ENV 开关      : {scope.ENV_STORE_ROOT}")
    print(f"  默认库根      : {scope.DEFAULT_ROOT}")
    print(f"  默认根命中仓库: {scope.repo_of(scope.DEFAULT_ROOT)}")
    for repo in scope.FORBIDDEN_ROOTS:
        print(f"  默认根在 {os.path.basename(repo):32s} 内: "
              f"{scope.within(scope.DEFAULT_ROOT, repo)}")
    print("  把库根指进仓库的后果（三方各试一次）:")
    for repo in scope.FORBIDDEN_ROOTS:
        try:
            scope.assert_outside_repos(os.path.join(repo, ".tmp", "p21-memory"))
            print(f"    {repo} ⇒ ！没有被拒")
        except scope.StoreScopeError as err:
            print(f"    {repo} ⇒ code={err.code}")
    print("  环境变量指向仓库内:")
    os.environ[scope.ENV_STORE_ROOT] = os.path.join(ROOT, ".tmp", "p21-env")
    try:
        try:
            scope.assert_outside_repos(scope.default_root())
            print("    ！没有被拒")
        except scope.StoreScopeError as err:
            print(f"    code={err.code} path={err.path}")
    finally:
        os.environ.pop(scope.ENV_STORE_ROOT, None)

    show("[D] 淘汰 = **归档**，不是删除")
    s3 = store()
    keep = s3.write("要归档的旧记忆：reuse 层误判", source="old",
                    symbols=["app.route"])["id"]
    stay = s3.write("仍在用的记忆", source="new")["id"]
    print(f"  归档前计数: {json.dumps(s3.profile()['counts'], ensure_ascii=False)}")
    arch = s3.archive(keep)
    print(f"  归档返回  : {json.dumps(arch, ensure_ascii=False)}")
    print(f"  归档后计数: {json.dumps(s3.profile()['counts'], ensure_ascii=False)}")
    back = s3.read(keep)
    print(f"  归档后仍读得到原文: {back['ok']} content={back['unit']['content']!r}")
    print(f"  索引里的状态      : status={back['unit']['status']} "
          f"archived_at={back['unit']['archived_at']}")
    print(f"  归档层文件        : {arch['archive_path']} "
          f"（存在={os.path.exists(os.path.join(s3.root(), arch['archive_path']))}）")
    print(f"  删除类方法        : "
          f"{[m for m in dir(s3) if any(k in m.lower() for k in ('delete', 'remove', 'purge', 'drop'))] or '无'}")
    print(f"  profile.delete_path: {s3.profile()['delete_path']}")

    show("[E] 只记分、不决策：两路召回 + 漏召/误召读数 + 候选阈值曲线")
    s4 = store()
    A = s4.write("reuse 层把 app.route 判成不存在符号", source="T9",
                 keywords=["reuse", "false-positive"], symbols=["app.route"])["id"]
    B = s4.write("占位说明（线索在结构引用里）", source="T9b",
                 symbols=["build_index_report"])["id"]
    C = s4.write("认证失败是因为 token 过期", source="V3",
                 keywords=["auth", "token"])["id"]
    D = s4.write("无关的清理脚本", source="D", keywords=["cleanup"])["id"]

    q1 = s4.recall(query="reuse false-positive")
    q2 = s4.recall(symbols=["build_index_report"])
    q3 = s4.recall(query="auth token")
    q4 = s4.recall(query="cleanup")
    q5 = s4.recall(symbols=["no_such_symbol_anywhere"])

    for name, res in (("关键词路 reuse/false-positive", q1),
                      ("符号路 build_index_report", q2),
                      ("关键词路 auth/token", q3),
                      ("关键词路 cleanup", q4),
                      ("符号路 no_such_symbol_anywhere", q5)):
        print(f"  {name:34s} → "
              f"{[(r['id'], r['score'], '+'.join(r['paths'])) for r in res['results']]}")
    print(f"  单元 id 对照: A={A} B={B} C={C} D={D}")
    print(f"  分数分布    : {json.dumps(q1['scores'], ensure_ascii=False)}")

    report = s4.calibrate([
        {"id": "关键词该召 A", "relevant": [A], "result": q1},
        {"id": "符号该召 B（关键词召不回）", "relevant": [B], "result": q2},
        {"id": "关键词该召 C", "relevant": [C], "result": q3},
        {"id": "误召（相关的是 A，实际召回 D…）", "relevant": [A], "result": q4},
        {"id": "漏召（库里有 A，查询召不回）", "relevant": [A], "result": q5},
    ])
    print(f"  合计读数: {json.dumps(report['totals'], ensure_ascii=False)}")
    print("  逐条漏召/误召:")
    for case in report["cases"]:
        print(f"    {case['id']:36s} recall={case['recall']} "
              f"precision={case['precision']} failures={case['failures']} "
              f"missed={case['missed']} false_recalled={case['false_recalled']}")
    print("  候选阈值曲线（前若干行；**不推荐阈值**）:")
    for point in report["threshold_curve"][:8]:
        print(f"    thr={point['threshold']:<8} kept={point['kept']} "
              f"tp={point['tp']} fp={point['fp']} fn={point['fn']} "
              f"P={point['precision']} R={point['recall']} F1={point['f1']}")
    print(f"  点数={len(report['threshold_curve'])} "
          f"recommended_threshold={report['recommended_threshold']}")

    show("profile()（可读事实：根 / 隔离 / 计数 / 两路召回 / 归档 / 不接主链路）")
    prof = s4.profile()
    print(json.dumps({
        "phase": prof["phase"],
        "wired_into_main_chain": prof["wired_into_main_chain"],
        "root": prof["root"],
        "outside_repos": prof["scope"]["outside_repos"],
        "counts": prof["counts"],
        "delete_path": prof["delete_path"],
        "recall_weights": prof["recall"]["weights"],
        "recall_threshold": prof["recall"]["threshold"],
        "recall_paths": list(prof["recall"]["paths"]),
        "unit_keys": prof["units_schema"]["unit_keys"],
    }, ensure_ascii=False, indent=2))

    for p in TEMPS:
        shutil.rmtree(p, ignore_errors=True)
    print("\n探针结束（临时库根已清理；默认库根未被创建）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
