"""review_code 工具自检：确认能抓到各类质量问题。"""

import asyncio
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from tools import TOOLS_MAP  # noqa: E402

review = TOOLS_MAP["review_code"]["function"]

BAD = '''
import os
import json
from typing import *

def process(items=[], flag=True):
    try:
        for i in items:
            if i:
                for j in i:
                    if j:
                        for k in j:
                            if k:
                                for m in k:
                                    if m:
                                        print(m)
    except:
        pass
    return None

def huge():
    a = 1
''' + "\n".join(f"    a += {i}" for i in range(60)) + '''
    return a

def broad():
    try:
        int("x")
    except Exception:
        pass
'''

GOOD = '''
from typing import Iterable


def total(values: Iterable[int]) -> int:
    """返回所有值之和。"""
    return sum(values)


def safe_int(raw: str, default: int = 0) -> int:
    """把字符串转成整数，失败时返回默认值。"""
    try:
        return int(raw)
    except ValueError:
        return default
'''


async def main():
    print("=" * 74)
    print("【坏代码】应报出多类问题")
    print("=" * 74)
    r = json.loads(await review(code=BAD))
    print(f"ok={r['ok']}  lint={r['lint']}  counts={r['issue_counts']}")
    print(f"metrics={r['metrics']}")
    for it in r["issues"]:
        print(f"  [{it['severity']:<6}] {it['code']:<28} line={it.get('line')} :: {it['message'][:52]}")

    print("\n" + "=" * 74)
    print("【好代码】high 应为 0")
    print("=" * 74)
    g = json.loads(await review(code=GOOD))
    print(f"ok={g['ok']}  counts={g['issue_counts']}  metrics={g['metrics']}")
    for it in g["issues"]:
        print(f"  [{it['severity']:<6}] {it['code']:<28} line={it.get('line')} :: {it['message'][:52]}")

    print("\n" + "=" * 74)
    print("【语法错误】应直接返回且不crash")
    print("=" * 74)
    s = json.loads(await review(code="def f(:\n    pass\n"))
    print(f"ok={s['ok']} syntax_ok={s['syntax_ok']} issues={s['issues']}")

    print("\n" + "=" * 74)
    print("【空代码】")
    print("=" * 74)
    e = json.loads(await review(code="   "))
    print(f"ok={e['ok']} -> {e['issues'][0]['message']}")

    print("\n" + "=" * 74)
    print("断言检查")
    print("=" * 74)
    codes = {i["code"] for i in r["issues"]}
    checks = [
        ("抓到裸 except", "bare-except" in codes),
        ("抓到宽 except", "broad-except" in codes),
        ("抓到可变默认参数", "mutable-default" in codes),
        ("抓到未使用导入", "unused-import" in codes),
        ("抓到 star import", "star-import" in codes),
        ("抓到函数过长", "long-function" in codes),
        ("抓到嵌套过深", "deep-nesting" in codes),
        ("坏代码 ok=False", r["ok"] is False),
        ("好代码 high=0", g["issue_counts"]["high"] == 0),
        ("语法错误不崩溃", s["syntax_ok"] is False),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")


asyncio.run(main())
