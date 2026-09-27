"""封装优化角色自检：形态指纹 → 变化点识别 → 审核闸门 → 副本安装。

重点验证「审核」不是摆设：
  - 自动占位符（p1）未重命名 → 拒绝
  - 单次运行（过拟合）→ 拒绝
  - 验证模板缺失（无法判定成败）→ 拒绝
  - 审核通过只进**副本**，不动正式库
  - 未经实测不允许提升到正式库
"""

import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.compress import Fact, FileFact, Snapshot  # noqa: E402
from core.package import (  # noqa: E402
    PACKAGE_SCORE_THRESHOLD, analyze, auto_rename_map, diff_token,
    extract_parameters, score_candidate,
)
from core.promote import (  # noqa: E402
    CandidateStore, StagingStore, audit, discard_staging, install_to_staging,
    promote_staging_to_live,
)
from core.shape import group_by_shape, shape_of, verify_skeleton  # noqa: E402
from core.skills import SkillParameter, SkillStore  # noqa: E402

TMP = os.path.join(ROOT, ".tmp_package_test")


def snap(cid: str, files: list[tuple[str, list[str]]], verify: str,
         status: str = "passed", goal: str = "") -> Snapshot:
    return Snapshot(
        cycle_id=cid, goal=goal, status=status, verify_command=verify,
        files=[FileFact(path=p, symbols=s, status="exists") for p, s in files],
    )


def samples() -> dict[str, Snapshot]:
    """三次「单文件单函数、标量入参」的同类成功运行 + 一次不同形态 + 一次失败。

    注意：三次的 verify **结构**必须一致才应归为一组。
    拿列表入参（`f([3,1,2])`）与标量入参（`f(10)`）是不同结构——
    指纹会（正确地）把它们分开，这是设计意图，不是 bug。
    """
    return {
        "cy1": snap("cy1", [("fib.py", ["fib"])],
                    "import fib\nassert fib.fib(10) == 55\nprint('PASS')"),
        "cy2": snap("cy2", [("fact.py", ["factorial"])],
                    "import fact\nassert fact.factorial(5) == 120\nprint('PASS')"),
        "cy3": snap("cy3", [("calc.py", ["square"])],
                    "import calc\nassert calc.square(7) == 49\nprint('PASS')"),
        # 不同形态：两个文件
        "cy4": snap("cy4", [("a.py", ["f"]), ("b.py", ["g"])],
                    "import a\nassert a.f(1) == 1\nprint('PASS')"),
        # 列表入参：结构不同，应单独成组
        "cy6": snap("cy6", [("sort.py", ["bubble_sort"])],
                    "import sort\nassert sort.bubble_sort([3,1,2]) == [1,2,3]\nprint('PASS')"),
        # 失败的不参与分组
        "cy5": snap("cy5", [("bad.py", ["bad"])],
                    "import bad\nassert bad.bad(1) == 2\nprint('PASS')",
                    status="failed"),
    }


def main() -> int:
    shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP, exist_ok=True)
    checks: list[tuple[str, bool]] = []
    snaps = samples()

    # ============================================================
    print("=" * 74)
    print("[1] 形态指纹：同类归组，异类分开，失败的不参与")
    print("=" * 74)
    groups = group_by_shape(snaps)
    print(f"  分组数: {len(groups)}")
    for k, v in groups.items():
        print(f"    {[s.cycle_id for s in v]}  {v[0].describe()}")

    all_ids = [s.cycle_id for v in groups.values() for s in v]
    checks.append(("只包含成功的 cycle", "cy5" not in all_ids))
    checks.append(("同类三次归为一组", any(
        {s.cycle_id for s in v} == {"cy1", "cy2", "cy3"} for v in groups.values())))
    checks.append(("两文件的形态单独成组", any(
        {s.cycle_id for s in v} == {"cy4"} for v in groups.values())))
    checks.append(("列表入参与标量入参分开（结构确实不同）", any(
        {s.cycle_id for s in v} == {"cy6"} for v in groups.values())))

    print("\n  verify_skeleton:")
    for cid in ("cy1", "cy2", "cy3"):
        print(f"    {cid}: {verify_skeleton(snaps[cid].verify_command)[:70]}")
    checks.append(("同类验证命令骨架一致",
                   len({verify_skeleton(snaps[c].verify_command)
                        for c in ("cy1", "cy2", "cy3")}) == 1))

    # ============================================================
    print("\n" + "=" * 74)
    print("[2] 变化点识别")
    print("=" * 74)
    r1 = diff_token(["fib.py", "fact.py", "sort.py"])
    r2 = diff_token(["fib.fib", "fact.factorial"])
    r3 = diff_token(["same.py", "same.py"])
    r4 = diff_token(["only_one.py"])
    print(f"  ['fib.py','fact.py','sort.py'] -> {r1}")
    print(f"  ['fib.fib','fact.factorial']   -> {r2}")
    print(f"  完全一致                        -> {r3}")
    print(f"  只有一项（无法归纳）             -> {r4}")
    checks.append(("抽出固定外壳与变化值", r1 is not None and r1[0] == "{P}.py"
                   and r1[1] == ["fib", "fact", "sort"]))
    checks.append(("多变化段不硬凑（返回 None 或保守）", r2 is None or "{P}" in r2[0]))
    checks.append(("完全一致时无变量", r3 is not None and "{P}" not in r3[0]))
    checks.append(("单元素无法归纳", r4 is None))

    params, goal_tmpl, verify_tmpl, files = extract_parameters(
        [snaps["cy1"], snaps["cy2"], snaps["cy3"]],
        [shape_of(snaps[c]) for c in ("cy1", "cy2", "cy3")],
    )
    print(f"\n  识别出参数: {[(p.placeholder, p.kind, p.examples) for p in params]}")
    print(f"  验证模板: {verify_tmpl!r}")
    print(f"  文件契约: {files}")
    checks.append(("识别出路径变量", any(p.kind == "path" for p in params)))
    checks.append(("识别出符号变量", any(p.kind == "symbol" for p in params)))
    checks.append(("验证模板已参数化", "{" in verify_tmpl and "import" in verify_tmpl))
    checks.append(("文件契约含模板路径", files and "{" in files[0]["path"]))
    checks.append(("自动名是无语义的 p1/p2", all(p.placeholder.startswith("p") for p in params)))

    # ============================================================
    print("\n" + "=" * 74)
    print("[3] 打分（可核查的判据）")
    print("=" * 74)
    s2, r2_ = score_candidate(2, params, verify_tmpl, goal_tmpl)
    s4, r4_ = score_candidate(4, params, verify_tmpl, goal_tmpl)
    s_noverify, _ = score_candidate(4, params, "", goal_tmpl)
    s_noparam, _ = score_candidate(4, [], verify_tmpl, goal_tmpl)
    print(f"  2 次成功: {s2}   4 次成功: {s4}")
    print(f"  缺验证模板: {s_noverify}   无参数: {s_noparam}")
    checks.append(("证据越多分越高", s4 > s2))
    checks.append(("缺验证模板显著扣分", s_noverify < s4 - 0.15))
    checks.append(("无参数扣分", s_noparam < s4))
    # 阈值设为 0.7：2 次成功（约 0.65）不足以自动过关——
    # 两次成功区分不出"固定形态"与"碰巧相似"
    checks.append(("2 次成功不达阈值（需 ≥3 次）", s2 < PACKAGE_SCORE_THRESHOLD))
    s3, _ = score_candidate(3, params, verify_tmpl, goal_tmpl)
    checks.append(("3 次成功达阈值", s3 >= PACKAGE_SCORE_THRESHOLD))
    print(f"  3 次成功: {s3}  阈值: {PACKAGE_SCORE_THRESHOLD}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[4] analyze：产出候选")
    print("=" * 74)
    cands = analyze(snaps)
    print(f"  候选数: {len(cands)}")
    for c in cands:
        print(f"    {c.describe()}")
    checks.append(("产出候选", len(cands) >= 1))
    top = cands[0] if cands else None
    checks.append(("候选包含 3 次运行",
                   top is not None and set(top.cycles) == {"cy1", "cy2", "cy3"}))
    checks.append(("候选带打分理由",
                   top is not None and len(top.score_reasons) >= 3))

    # ============================================================
    print("\n" + "=" * 74)
    print("[5] 审核闸门：必须真的拦得住")
    print("=" * 74)
    staging = StagingStore(root=os.path.join(TMP, "staging"))
    live = SkillStore(root=os.path.join(TMP, "live"))
    cand_store = CandidateStore(root=os.path.join(TMP, "cand"))
    cand_store.save(top)

    # 5a 未重命名 → 拒绝
    a1 = audit(top, live_store=live, proposed_id="skill_x")
    print("  未重命名:")
    for c in a1.checks:
        print(f"    [{'OK' if c['ok'] else 'NG'}] {c['check']} {c['detail']}")
    checks.append(("未重命名被判不合格", not a1.approved))
    checks.append(("拦截点正确", "参数已重命名为有语义的名字" in a1.failed))

    # 5b 用弱语义建议重命名后 → 通过（字面量参数也必须命名）
    renamed = auto_rename_map(top)
    print(f"\n  自动弱语义命名: {renamed}")
    a2 = audit(top, renamed=renamed, live_store=live, proposed_id="skill_x")
    print(f"  重命名后: approved={a2.approved} score={a2.score}")
    for c in a2.checks:
        if not c["ok"]:
            print(f"    NG {c['check']} {c['detail']}")
    checks.append(("弱语义命名后可过审核", a2.approved))

    # 5c 参数名重复 → 拒绝
    dup = {p.placeholder: "same" for p in top.parameters}
    a3 = audit(top, renamed=dup, live_store=live, proposed_id="skill_x")
    checks.append(("参数名重复被拒", not a3.approved))
    print(f"  重名: approved={a3.approved} failed={a3.failed}")

    # 5d 与正式库冲突 → 拒绝
    tmp_skill = top.to_skill(skill_id="skill_x", renamed=renamed)
    live.save(tmp_skill)
    a4 = audit(top, renamed=renamed, live_store=live, proposed_id="skill_x")
    checks.append(("ID 冲突被拒", not a4.approved))
    print(f"  ID 冲突: approved={a4.approved}")
    live.delete("skill_x")

    # 5e 单次运行（过拟合）→ 拒绝
    one = snap("cy_only", [("x.py", ["f"])], "import x\nassert x.f(1) == 1")
    one_cands = analyze({"cy_only": one})
    checks.append(("单次成功不产出候选（过拟合防护）", one_cands == []))
    print(f"  单次运行候选数: {len(one_cands)}")

    # ============================================================
    print("\n" + "=" * 74)
    print("[6] 副本机制：审核通过也不直接进正式库")
    print("=" * 74)
    skill, res = install_to_staging(top, skill_id="staged_skill", name="副本技能",
                                    renamed=renamed, staging=staging, live_store=live,
                                    force=True)
    print(f"  副本已装: {skill is not None}; 正式库有它吗: {live.get('staged_skill') is not None}")
    checks.append(("副本区有技能", staging.get("staged_skill") is not None))
    checks.append(("正式库仍然没有", live.get("staged_skill") is None))

    # 未经实测 → 不允许提升
    ok, msg = promote_staging_to_live("staged_skill", proven=False,
                                      staging=staging, live_store=live)
    print(f"  未实测提升: ok={ok} msg={msg}")
    checks.append(("未实测不允许提升", ok is False))
    checks.append(("副本仍在", staging.get("staged_skill") is not None))
    checks.append(("正式库仍没有", live.get("staged_skill") is None))

    # 实测通过 → 允许提升
    ok2, msg2 = promote_staging_to_live("staged_skill", proven=True,
                                        staging=staging, live_store=live)
    print(f"  实测后提升: ok={ok2} msg={msg2}")
    checks.append(("实测通过可提升", ok2 is True))
    checks.append(("正式库有了", live.get("staged_skill") is not None))
    checks.append(("副本被清理", staging.get("staged_skill") is None))

    # 丢弃副本不影响正式库
    install_to_staging(top, skill_id="to_discard", renamed=renamed,
                       staging=staging, live_store=live, force=True)
    checks.append(("丢弃前副本存在", staging.get("to_discard") is not None))
    discard_staging("to_discard", staging)
    checks.append(("丢弃后副本消失", staging.get("to_discard") is None))
    checks.append(("正式库不受影响", live.get("staged_skill") is not None))

    # ============================================================
    print("\n" + "=" * 74)
    print("[7] 候选持久化")
    print("=" * 74)
    loaded = cand_store.get(top.candidate_id)
    checks.append(("候选可往返", loaded is not None
                   and loaded.candidate_id == top.candidate_id))
    checks.append(("往返后参数保留",
                   len(loaded.parameters) == len(top.parameters)))
    checks.append(("列表可读", any(c.candidate_id == top.candidate_id
                                   for c in cand_store.list())))

    shutil.rmtree(TMP, ignore_errors=True)
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
