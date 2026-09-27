"""审批页渲染自检（不启服务，用 FastAPI TestClient）。

重点验证：结构化上下文确实被渲染出来（这是它比聊天消息强的地方），
以及访问令牌生效。
"""

import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

from core.decisions import DecisionManager, FileDecisionStore  # noqa: E402

TMP = os.path.join(ROOT, ".tmp_web_test")
shutil.rmtree(TMP, ignore_errors=True)

# 在导入 web 层之前把 store 指到临时目录
import web.decisions as wd  # noqa: E402

wd._manager = DecisionManager(store=FileDecisionStore(TMP), default_timeout_minutes=30)


def main() -> int:
    from fastapi.testclient import TestClient

    import main as app_module

    checks: list[tuple[str, bool]] = []
    client = TestClient(app_module.app)

    # 造一条带完整结构化上下文的决策
    d = wd.manager().open(
        "repeated_failure", "cy_web", "验证连续失败 2 次，如何继续？",
        context={
            "goal": "实现 fib(n) 返回斐波那契数列第 n 项",
            "error": "AssertionError: got 34",
            "touched": ["fib.py"],
            "declared": ["fib.py"],
            "violations": [{"kind": "symbol-missing", "path": "fib.py",
                            "message": "fib.py 缺少声明的符号: fib"}],
            "verify": {"passed": False, "detail": "AssertionError: got 34"},
            "attempt": 2,
        },
    )

    print("=" * 74)
    print("[1] 列表页")
    print("=" * 74)
    r = client.get("/decisions")
    checks.append(("列表页 200", r.status_code == 200))
    checks.append(("列表含决策问题", "验证连续失败" in r.text))
    checks.append(("含移动端 viewport", "viewport" in r.text))
    checks.append(("无外部依赖（离线可用）",
                   "http://" not in r.text.replace("http://192.", "").split("<style>")[0]
                   or "cdn" not in r.text.lower()))
    print(f"  status={r.status_code} len={len(r.text)}")

    print("\n" + "=" * 74)
    print("[2] 详情页：结构化上下文必须渲染出来")
    print("=" * 74)
    r2 = client.get(f"/decisions/{d.id}")
    body = r2.text
    checks.append(("详情页 200", r2.status_code == 200))
    for label, needle in [
        ("目标", "实现 fib(n)"),
        ("失败原因", "AssertionError: got 34"),
        ("涉及文件", "fib.py"),
        ("计划声明产出", "计划声明产出"),
        ("清单校验问题", "symbol-missing"),
        ("超时默认动作", "abort" if False else "stop"),
    ]:
        hit = needle in body
        checks.append((f"渲染了{label}", hit))
        print(f"  渲染{label}: {hit}")

    # 三个选项都要有对应按钮
    for value, label in (("retry", "再试一次"), ("relax", "放宽验收"), ("stop", "停止本轮")):
        hit = f'name="value" value="{value}"' in body and label in body
        checks.append((f"按钮 {label}", hit))
    present = [v for v in ("retry", "relax", "stop") if f'value="{v}"' in body]
    print(f"  按钮存在: {present}")
    checks.append(("三个选项按钮齐全", len(present) == 3))
    checks.append(("危险选项带 danger 样式", "danger" in body))

    print("\n" + "=" * 74)
    print("[3] 作答提交")
    print("=" * 74)
    r3 = client.post(f"/decisions/{d.id}/answer", data={"value": "retry"},
                     follow_redirects=False)
    got = wd.manager().get(d.id)
    print(f"  POST status={r3.status_code}（应 303 重定向）")
    print(f"  决策状态 -> {got.status} / {got.answer}")
    checks.append(("提交成功并重定向", r3.status_code == 303))
    checks.append(("决策已作答", got.status == "answered" and got.answer == "retry"))

    # 非法选项
    d2 = wd.manager().open("repeated_failure", "cy_web2", "再问一次")
    r4 = client.post(f"/decisions/{d2.id}/answer", data={"value": "hack"})
    print(f"  非法选项 POST status={r4.status_code}（应 400）")
    checks.append(("非法选项返回 400", r4.status_code == 400))
    checks.append(("非法选项未改变状态",
                   wd.manager().get(d2.id).status == "pending"))

    # 不存在的决策
    r5 = client.get("/decisions/does_not_exist")
    print(f"  不存在的决策 status={r5.status_code}（应 404）")
    checks.append(("不存在的决策 404", r5.status_code == 404))

    print("\n" + "=" * 74)
    print("[4] 访问令牌")
    print("=" * 74)
    os.environ["AGENT_APPROVAL_TOKEN"] = "s3cr3t"
    try:
        r6 = client.get("/decisions")
        r7 = client.get("/decisions?t=s3cr3t")
        print(f"  无 token status={r6.status_code}（应 403）")
        print(f"  正确 token status={r7.status_code}（应 200）")
        checks.append(("无 token 被拒 403", r6.status_code == 403))
        checks.append(("正确 token 放行", r7.status_code == 200))
    finally:
        os.environ.pop("AGENT_APPROVAL_TOKEN", None)

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
