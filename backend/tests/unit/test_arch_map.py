"""P11 门禁：**结构梳理必须可信** —— 覆盖率账目 / 新鲜度 / 范围 / 反向索引。

契约目标（用户 2026-10-03 新需求 + 已批准）：工具做结构梳理，先让地图可信。
本文件钉住四件事（**只补，不重写 arch.py 的现有语义**）：

  1. 输出带 `indexed` / `skipped` / `truncated`，且 **`skipped` 逐条给理由**；
     **禁止静默截断**（旧行为只回一句"只列前 N 个"，而 totals 是全量）；
  2. 每个文件带**内容哈希**，视图自带 `generated_at` + `root`（代码一改可察觉）；
  3. **范围显式**：写明扫的根（设了任务级 project_root 就是它）；
  4. **反向索引**：「谁 import 了 X」。

反空洞（"不是把检查关掉"）：
  · 故意让一个文件**解析失败** ⇒ 它必须出现在 `skipped`（parse-failed），不是静默消失；
    修好它之后必须**从 skipped 移回 indexed**；
  · 故意让 `limit` 小于模块数 ⇒ 被省略的模块必须**逐条**出现在 `truncated_items`；
  · 改一个文件的内容 ⇒ 新鲜度哈希必须变（旧地图才不会被当成仍然有效）。
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core import runtime  # noqa: E402
from core.symbol_index import build_index_report  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402

c = Checker()
get_architecture = TOOLS_MAP["get_architecture"]["function"]
get_module = TOOLS_MAP["get_module"]["function"]
find_symbol = TOOLS_MAP["find_symbol"]["function"]

GOOD = "def helper(x):\n    return x + 1\n"
BROKEN = "def broken(:\n    pass\n"
WORLD = "import good\n\ndef world():\n    return good.helper(1)\n"


def w(root: str, rel: str, content: str) -> None:
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p) or root, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


async def main() -> int:
    root = tempfile.mkdtemp(prefix="p11_map_")
    w(root, "good.py", GOOD)
    w(root, "world.py", WORLD)
    w(root, "broken.py", BROKEN)
    w(root, "notes.md", "not python\n")
    try:
        with runtime.use_project_root(root):
            print("=" * 74)
            print("[1] 覆盖率账目：indexed / skipped / truncated + skipped 逐条理由")
            print("=" * 74)
            rep = build_index_report(runtime.effective_root(), limit=1)
            cov = rep["coverage"]
            print(f"  scanned={cov['scanned']} indexed={cov['indexed']} "
                  f"skipped={cov['skipped']} truncated={cov['truncated']} "
                  f"skipped_dirs={cov['skipped_dirs']}")
            print(f"  by_reason={cov['by_reason']}")
            for item in cov["skipped_items"]:
                print(f"    - {item['path']} :: {item['reason']} :: {item['detail']}")
            for item in cov["truncated_items"]:
                print(f"    - {item['path']} :: {item['reason']} :: {item['detail']}")

            c.check("账目自洽：indexed + skipped == scanned",
                    cov["indexed"] + cov["skipped"] == cov["scanned"])
            c.check("indexed == 2（good.py / world.py）", cov["indexed"] == 2)
            c.check("解析失败**逐条**出现在 skipped（parse-failed，不是静默消失）",
                    any(i["path"] == "broken.py" and i["reason"] == "parse-failed"
                        for i in cov["skipped_items"]))
            c.check("非 .py **逐条**出现在 skipped（non-python）",
                    any(i["path"] == "notes.md" and i["reason"] == "non-python"
                        for i in cov["skipped_items"]))
            c.check("超出 limit 的模块**逐条**记在 truncated_items（禁止静默截断）",
                    cov["truncated"] == 1
                    and any(i["reason"] == "over-limit" for i in cov["truncated_items"]))

            print("\n" + "=" * 74)
            print("[2] 工具输出：get_architecture 带 coverage / freshness / scope / 反向索引")
            print("=" * 74)
            arch = json.loads(await get_architecture(limit=1))
            print(f"  truncated={arch['truncated']} shown={arch['shown']}")
            print(f"  scope={arch['scope']['root']} ({arch['scope']['source']})")
            print(f"  freshness.generated_at={arch['freshness']['generated_at']}")
            print(f"  reverse_index={arch['reverse_index']}")
            c.check("get_architecture 带 coverage 账目",
                    arch["coverage"]["indexed"] == 2
                    and arch["coverage"]["truncated"] == 1)
            c.check("truncated 为 True 且省略项可逐条查到",
                    arch["truncated"] is True
                    and arch["coverage"]["truncated_items"])
            c.check("范围显式：写明扫的根 == 目标项目根",
                    os.path.normcase(arch["scope"]["root"]) == os.path.normcase(root)
                    and arch["scope"]["source"] == "project_root")
            c.check("新鲜度：generated_at + root + hash_algorithm 齐全",
                    bool(arch["freshness"]["generated_at"])
                    and os.path.normcase(arch["freshness"]["root"]) == os.path.normcase(root)
                    and arch["freshness"]["hash_algorithm"] == "sha256")
            c.check("反向索引：谁 import 了 good ⇒ world.py",
                    arch["reverse_index"].get("good") == ["world.py"]
                    or arch["reverse_index"].get("good.py") == ["world.py"])

            print("\n" + "=" * 74)
            print("[3] get_module 带内容哈希 + imported_by（反向索引）")
            print("=" * 74)
            mod = json.loads(await get_module("good.py"))
            print(f"  sha256={mod.get('sha256')[:16]}… imported_by={mod.get('imported_by')}")
            c.check("get_module 带 sha256", bool(mod.get("sha256")))
            c.check("get_module 带 imported_by（同一事实的另一个名字）",
                    mod.get("imported_by") == ["world.py"])

            print("\n" + "=" * 74)
            print("[4] 新鲜度有牙齿：改内容 ⇒ 哈希变（旧地图不再看起来有效）")
            print("=" * 74)
            sha_before = json.loads(await get_architecture())["freshness"]["files"]["good.py"]
            w(root, "good.py", GOOD + "\ndef extra():\n    return 2\n")
            sha_after = json.loads(await get_architecture())["freshness"]["files"]["good.py"]
            print(f"  改前 {sha_before[:16]}… → 改后 {sha_after[:16]}…")
            c.check("内容一改，哈希立刻不同（陈旧可检出）", sha_before != sha_after)

            print("\n" + "=" * 74)
            print("[5] 反空洞：修好 broken.py ⇒ 它必须**从 skipped 移回 indexed**")
            print("=" * 74)
            w(root, "broken.py", "def broken():\n    return 1\n")
            rep2 = build_index_report(runtime.effective_root())
            cov2 = rep2["coverage"]
            print(f"  indexed={cov2['indexed']} skipped={cov2['skipped']} "
                  f"by_reason={cov2['by_reason']}")
            c.check("修好后 indexed 从 2 变 3", cov2["indexed"] == 3)
            c.check("parse-failed 条目消失（skipped 不是恒定的）",
                    not any(i["reason"] == "parse-failed"
                            for i in cov2["skipped_items"]))

            print("\n" + "=" * 74)
            print("[6] find_symbol 未命中时给出覆盖率（判不了 ≠ 通过）")
            print("=" * 74)
            miss = json.loads(await find_symbol("definitely_not_here"))
            print(f"  found={miss['found']} coverage.indexed={miss['coverage']['indexed']} "
                  f"skipped={miss['coverage']['skipped']}")
            c.check("未命中仍回报 coverage（能区分'没找到'与'没扫到'）",
                    miss["found"] is False and "coverage" in miss)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    return c.report()


raise SystemExit(asyncio.run(main()))
