"""机械取证：P14（输出契约）· P15（目标项目根）· P11（可信结构地图）。

这是**评估文档引用的原始回显**来源 —— 全部离线、确定性、不调模型。
用法（在仓库根目录执行）：

    D:\\PythonProject\\SimpleAgent2_Cycle_VueWeb\\.venv\\Scripts\\python.exe `
        tests\\diagnostics\\probe_output_and_map.py

判据（任一条不成立即以非零退出）：
  · 三个根是绝对路径且都存在，且 workspace_root != output_root；
  · project_root 与 AGENT_BACKEND_DIR 是**两个概念**（同值/异值两种情形都要判对）；
  · 换根后**扫到的集合真的变**（用仓库自己的 `core/` 当目标根对真值）；
  · 越界写返回结构化 `out-of-scope-write`，且目标文件**没有**被写出去；
  · 声明的交付物存在+哈希一致 ⇒ pass；不存在 ⇒ fail（结构化 `deliverable-missing`）；
  · 解析失败与非 .py **逐条**出现在 `coverage.skipped`；超 limit **逐条**在 `truncated_items`。
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from core import runtime  # noqa: E402
from core.symbol_index import build_index_report  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")


list_workspace = TOOLS_MAP["list_workspace"]["function"]
get_architecture = TOOLS_MAP["get_architecture"]["function"]
write_file = TOOLS_MAP["write_file"]["function"]


async def main() -> int:
    print("=" * 76)
    print("[1] P14/P15：/profile.runtime 的三个根 + 目标项目根（与 AGENT_BACKEND_DIR 分离）")
    print("=" * 76)
    info = runtime.describe()
    for k in ("runtime_root", "workspace_root", "output_root"):
        print(f"  {k:16s} = {info[k]}  exists={os.path.isdir(info[k])}")
    print(f"  effective_root   = {info['effective_root']} "
          f"(source={info['effective_root_source']})")
    os.environ["AGENT_BACKEND_DIR"] = info["workspace_root"]
    try:
        with runtime.use_project_root(ROOT):
            pr = runtime.describe()["project_root"]
            print(f"  project_root.active      = {pr['active']}")
            print(f"  project_root.lifetime    = {pr['lifetime']}")
            print(f"  AGENT_BACKEND_DIR        = {pr['backend_dir']}")
            print(f"  distinct_from_backend_dir= {pr['distinct_from_backend_dir']}")
            check("三个根都是绝对路径且存在",
                  all(os.path.isabs(info[k]) and os.path.isdir(info[k])
                      for k in ("runtime_root", "workspace_root", "output_root")))
            check("输出根与工作区根**分开**",
                  os.path.normcase(info["workspace_root"])
                  != os.path.normcase(info["output_root"]))
            check("目标项目根是任务级（per-task）", pr["lifetime"] == "per-task")
            check("与 AGENT_BACKEND_DIR 判为不同（两者是两个概念）",
                  pr["distinct_from_backend_dir"] is True)
    finally:
        os.environ.pop("AGENT_BACKEND_DIR", None)

    print("\n" + "=" * 76)
    print("[2] P15：换根后扫到的集合随之改变（用仓库自己的 core/ 当目标根对真值）")
    print("=" * 76)
    before = json.loads(await list_workspace())
    target = os.path.join(ROOT, "core")
    with runtime.use_project_root(target):
        after = json.loads(await list_workspace())
        arch = json.loads(await get_architecture(limit=5))
    print(f"  未设 root：root={before['root']} files={before['total']}")
    print(f"  设 root  ：root={after['root']} files={after['total']}")
    print(f"  get_architecture scope={arch['scope']['root']} "
          f"source={arch['scope']['source']} indexed={arch['coverage']['indexed']}")
    check("换根后 root 真的变了",
          os.path.normcase(before["root"]) != os.path.normcase(after["root"]))
    check("换根后文件集合真的变了（不是空转）",
          {f["path"] for f in before["files"]} != {f["path"] for f in after["files"]})
    check("结构工具的范围显式 == 目标项目根",
          os.path.normcase(arch["scope"]["root"]) == os.path.normcase(target)
          and arch["scope"]["source"] == "project_root")
    check("真值抽查：core/runtime.py 在 core 根下被索引到",
          "runtime.py" in {m["path"] for m in arch["modules"]}
          or "runtime.py" in arch["freshness"]["files"])
    check("离开作用域后根还原", os.path.normcase(runtime.effective_root())
          == os.path.normcase(info["workspace_root"]))

    print("\n" + "=" * 76)
    print("[3] P15：越界写 ⇒ 结构化拒绝（且文件真的没写出去）")
    print("=" * 76)
    tmp = tempfile.mkdtemp(prefix="probe_p15_")
    with open(os.path.join(tmp, "code.py"), "w", encoding="utf-8") as f:
        f.write("def f():\n    return 1\n")
    escape_target = os.path.join(os.path.dirname(tmp), "probe_p15_escape.txt")
    try:
        with runtime.use_project_root(tmp):
            raw = await write_file(filename="../../probe_p15_escape.txt", content="x")
            print(f"  越界写返回: {raw[:200]}")
            data = json.loads(raw)
            check("越界写是结构化拒绝（ok=false + code）",
                  data.get("ok") is False
                  and (data.get("error") or {}).get("code") == "out-of-scope-write")
            check("越界目标**没有被写出去**", not os.path.exists(escape_target))
            ok = await write_file(filename="inside.txt", content="hi")
            check("根内写仍然成功（不是把写关掉）", ok.startswith("OK:FILE|"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.exists(escape_target):
            os.remove(escape_target)

    print("\n" + "=" * 76)
    print("[4] P14：声明的交付物必须存在且哈希一致（实际产物 {path,sha256,size}）")
    print("=" * 76)
    tmp2 = tempfile.mkdtemp(prefix="probe_p14_")
    try:
        with runtime.use_project_root(tmp2):
            raw = await write_file(filename="outputs/report.txt", content="deliverable\n")
            print(f"  写出交付物: {raw.splitlines()[0]}")
            good = runtime.check_deliverables(["outputs/report.txt"])
            bad = runtime.check_deliverables(["outputs/never.txt"])
            print(f"  存在  ⇒ passed={good['passed']} actual={good['actual']}")
            print(f"  不存在⇒ passed={bad['passed']} "
                  f"violations={[v['kind'] for v in bad['violations']]}")
            check("声明存在且哈希一致 ⇒ 通过（不是一律报红）",
                  good["passed"] is True and good["actual"][0]["exists"] is True)
            check("实际产物带 {path, sha256, size}",
                  bool(good["actual"][0]["sha256"])
                  and isinstance(good["actual"][0]["size"], int))
            check("声明不存在的交付物 ⇒ 不合格（结构化 deliverable-missing）",
                  bad["passed"] is False
                  and "deliverable-missing" in [v["kind"] for v in bad["violations"]])
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)

    print("\n" + "=" * 76)
    print("[5] P11：覆盖率账目（解析失败/非 .py/超 limit **逐条**留痕）+ 新鲜度")
    print("=" * 76)
    tmp3 = tempfile.mkdtemp(prefix="probe_p11_")
    try:
        for rel, content in (
            ("good.py", "def helper(x):\n    return x + 1\n"),
            ("world.py", "import good\n\ndef world():\n    return good.helper(1)\n"),
            ("broken.py", "def broken(:\n    pass\n"),
            ("notes.md", "not python\n"),
        ):
            with open(os.path.join(tmp3, rel), "w", encoding="utf-8") as f:
                f.write(content)
        with runtime.use_project_root(tmp3):
            rep = build_index_report(runtime.effective_root(), limit=1)
            cov = rep["coverage"]
            print(f"  root={rep['root']} generated_at={rep['generated_at']}")
            print(f"  scanned={cov['scanned']} indexed={cov['indexed']} "
                  f"skipped={cov['skipped']} truncated={cov['truncated']} "
                  f"skipped_dirs={cov['skipped_dirs']}")
            print(f"  by_reason={cov['by_reason']}")
            for item in cov["skipped_items"]:
                print(f"    - {item['path']} :: {item['reason']} :: {item['detail']}")
            for item in cov["truncated_items"]:
                print(f"    - {item['path']} :: {item['reason']} :: {item['detail']}")
            print(f"  freshness.files={rep['hashes']}")
            print(f"  reverse_index={rep['reverse_index']}")
            check("账目自洽（indexed + skipped == scanned）",
                  cov["indexed"] + cov["skipped"] == cov["scanned"])
            check("解析失败**逐条**在 skipped（parse-failed）",
                  any(i["path"] == "broken.py" and i["reason"] == "parse-failed"
                      for i in cov["skipped_items"]))
            check("非 .py **逐条**在 skipped（non-python）",
                  any(i["path"] == "notes.md" and i["reason"] == "non-python"
                      for i in cov["skipped_items"]))
            check("超 limit **逐条**在 truncated_items（禁止静默截断）",
                  any(i["reason"] == "over-limit" for i in cov["truncated_items"]))
            check("每个被解析文件都有内容哈希（新鲜度）",
                  all(k in rep["hashes"] for k in ("good.py", "world.py", "broken.py")))
            check("反向索引：good ← world.py",
                  rep["reverse_index"].get("good") == ["world.py"])
    finally:
        shutil.rmtree(tmp3, ignore_errors=True)

    print("\n" + "=" * 76)
    failed = [n for n, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + ", ".join(failed))
        return 1
    print("★ 全部通过：三个根 · 任务级目标根 · 越界结构化拒绝 · 交付物对账 · 可信结构地图")
    return 0


raise SystemExit(asyncio.run(main()))
