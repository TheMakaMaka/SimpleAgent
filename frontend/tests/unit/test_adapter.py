"""适配器层与标准参数入口的自检。"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402

from core import (  # noqa: E402
    DEFAULT_COUPLING, LLMClient, ModelCapabilities, ModelCapabilityError,
    ModelCoupling, ModelLimits, ModelProfile, Worker, extract_json,
)
from core.config import LLMConfig  # noqa: E402
from core.model_profile import QWEN_COUPLING  # noqa: E402

print("=== [1] 预算从 context_window 推导 ===")
for cw in (2048, 8192, 32768, 131072):
    lim = ModelLimits.from_context_window(cw)
    print(f"  ctx={cw:<7} maxtok={lim.max_tokens:<6} rounds={lim.max_rounds:<3} "
          f"steps={lim.max_steps:<3} attempts={lim.max_attempts:<2} clip={lim.tool_result_chars}")

print("\n=== [2] 覆盖项生效 ===")
print("  max_rounds=99 ->", ModelLimits.from_context_window(8192, max_rounds=99).max_rounds)

print("\n=== [3] 向后兼容：LLMConfig 别名 ===")
print("  LLMConfig is ModelProfile:", LLMConfig is ModelProfile)
p = LLMConfig.from_env(prefix="ORCH")
print("  ", p.describe())

print("\n=== [4] 耦合层：默认不识别任何句式 ===")
print("  默认耦合(空):", DEFAULT_COUPLING.looks_like_plan("我将先写文件"), "(期望 False)")
print("  qwen耦合    :", QWEN_COUPLING.looks_like_plan("我将先写文件"), "(期望 True)")
print("  默认错误前缀:", DEFAULT_COUPLING.matches_error_prefix("Error: x"), "(期望 False)")

print("\n=== [5] JSON 提取与宽松修复 ===")
cases = [
    ('尾逗号', '{"status": "continue", "tasks": [],}'),
    ('行注释', '{"status": "continue", // note\n "tasks": []}'),
    ('围栏包裹', '```json\n{"ok": true}\n```'),
    ('前后废话', '好的，这是结果：{"ok": true} 以上。'),
    ('字符串内含括号', '{"code": "def f():\\n    return {1:2}"}'),
]
for name, raw in cases:
    got = extract_json(raw, repair=True)
    print(f"  {name:<14} -> {got}")
print("  repair=False 时尾逗号 ->", extract_json(cases[0][1], repair=False), "(期望 None)")

print("\n=== [6] 能力校验：不满足必须显式报错 ===")
bad = ModelProfile(name="bad", capabilities=ModelCapabilities(supports_tool_calls=False))
print("  校验问题:", bad.validate())
try:
    LLMClient(bad)
    print("  !! 未报错，不符合预期")
except ModelCapabilityError:
    print("  启动即报错 OK")

print("\n=== [7] Worker 预算来自档位（无魔法数字）===")
w = Worker(LLMClient(p))
print(f"  max_steps={w.limits.max_steps} max_errors={w.limits.max_errors} "
      f"clip={w.limits.tool_result_chars}")
print(f"  coupling.plan_hints={w.coupling.plan_hints}")

print("\n=== [8] 工作流层已无模型特判 ===")
# 用 pathlib 直接扫源文件，不依赖 findstr（跨平台，也不受 CWD 影响）
from pathlib import Path  # noqa: E402

MARKERS = ("我将", "首先我", "接下来我", "我打算", "计划如下")
hits: list[str] = []
for path in sorted((Path(ROOT) / "core").glob("*.py")):
    text = path.read_text(encoding="utf-8")
    # 只看源码行，跳过注释与文档字符串里的说明性提及
    for i, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]
        if any(m in code for m in MARKERS):
            hits.append(f"{path.name}:{i}: {line.strip()}")

only_adapter = all("model_profile.py" in h for h in hits)
print(f"  句式硬编码命中 {len(hits)} 处，全部在 model_profile.py: {only_adapter}")
for h in hits:
    print("   ", h)

checks = [
    ("预算随窗口放大", ModelLimits.from_context_window(131072).max_rounds
     > ModelLimits.from_context_window(8192).max_rounds),
    ("8192 窗口保持 max_tokens=4096", ModelLimits.from_context_window(8192).max_tokens == 4096),
    ("覆盖项生效", ModelLimits.from_context_window(8192, max_rounds=99).max_rounds == 99),
    ("LLMConfig 向后兼容", LLMConfig is ModelProfile),
    ("默认耦合不识别句式", DEFAULT_COUPLING.looks_like_plan("我将先写") is False),
    ("qwen 耦合识别句式", QWEN_COUPLING.looks_like_plan("我将先写") is True),
    ("JSON 尾逗号可修复", extract_json('{"a": 1,}', repair=True) == {"a": 1}),
    ("JSON repair=False 不放行", extract_json('{"a": 1,}', repair=False) is None),
    ("围栏可剥离", extract_json('```json\n{"ok": true}\n```') == {"ok": True}),
    ("能力校验报错", bool(ModelProfile(
        name="bad", capabilities=ModelCapabilities(supports_tool_calls=False)).validate())),
    ("Worker 预算来自档位", Worker(LLMClient(p)).limits.max_steps == p.limits.max_steps),
]
print()
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
print("  " + ("全部通过" if all(ok for _, ok in checks) and only_adapter else "存在失败项"))
