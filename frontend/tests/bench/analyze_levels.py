"""汇总每级实际产出与失败原因，用于判定边界性质。

读取 tests/output/levels_result.json，按关键词把失败归类，输出根因分布。
先跑 run_levels.py 生成结果。
"""

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "tests", "output")
RESULT_PATH = os.path.join(OUT_DIR, "levels_result.json")

if not os.path.exists(RESULT_PATH):
    print(f"找不到 {os.path.relpath(RESULT_PATH, ROOT)}，请先运行 tests/bench/run_levels.py")
    raise SystemExit(1)

results = json.load(open(RESULT_PATH, encoding="utf-8"))

print("=" * 78)
print("各级失败原因归类")
print("=" * 78)
for r in results:
    lv = r["level"]
    print(f"\nL{lv} {r['name']}")
    print(f"  结果    : {'PASS' if r['passed'] else 'FAIL'}")
    print(f"  尝试/任务: {r['attempts']} / {r['tasks']}")
    print(f"  失败阶段: {r['phase']}")
    print(f"  原因    : {r['error']}")
    print(f"  涉及文件: {r.get('touched')}")

print("\n" + "=" * 78)
print("失败原因分类（人工规则匹配）")
print("=" * 78)
CATS = {
    "断言值不符（逻辑错）": ("AssertionError", "assert"),
    "异常语义未满足": ("ValueError", "IndexError", "未抛"),
    "接口签名不符": ("positional argument", "TypeError", "missing", "unexpected keyword"),
    "模块/导入缺失": ("ModuleNotFound", "No module named", "ImportError"),
    "交付清单不完整": ("交付清单不完整", "declared-missing", "symbol-missing"),
    "递归/深度问题": ("RecursionError",),
    "属性错误": ("AttributeError",),
}
for r in results:
    if r["passed"]:
        continue
    err = r["error"] or ""
    hit = [name for name, keys in CATS.items() if any(k in err for k in keys)]
    print(f"L{r['level']:<3} {r['name']:<28} -> {', '.join(hit) or '其他: ' + err[:60]}")
