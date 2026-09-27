"""检查与验证流水线：由程序调度，不经模型决策。

这是「一轮编码流程」里最关键的一层：check 和 verify 阶段不接受模型的自述结论，
只接受工具返回的结构化结果。模型在 write 阶段写了什么，这里就检什么。

流程：
  check   : 对本次 cycle 新增/修改的 .py 文件跑 check_syntax，再跑 run_lint
  verify  : 执行 VerifyCommand（一段 Python 代码），以退出码为唯一判据
"""

import json
import os
from typing import Any

from .context import get_declared_files
from .cycle import VerifyCommand
from .manifest import Manifest, check_manifest, parse_declared
from tools import TOOLS_MAP, is_error_result

WORKSPACE_DIR = os.path.abspath("workspace")


class CheckPipeline:
    """检查与验证流水线。

    注意 verify_timeout 目前**不是**实际生效的超时：真正的执行超时来自
    `tools/python_exec.py` 与 `tools/verify.py` 的 TIMEOUT_SECONDS（60 秒）。
    保留该参数是为了将来把超时统一收归预算管理，避免现在就在两处各写一个值。
    """

    def __init__(self, run_lint: bool = True, verify_timeout: float = 90.0):
        self.run_lint = run_lint
        self.verify_timeout = verify_timeout

    # ---------- 取工具 ----------
    @staticmethod
    def _fn(name: str):
        entry = TOOLS_MAP.get(name)
        if not entry:
            raise RuntimeError(f"检查流水线依赖的工具未注册: {name}")
        return entry["function"]

    async def _call(self, name: str, **kwargs) -> dict:
        """调用注册表里的工具，返回 (是否异常, 原始文本, 解析后的 dict|None)。"""
        raw = await self._fn(name)(**kwargs)
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                parsed = None
        except (json.JSONDecodeError, TypeError):
            parsed = None
        return {"tool": name, "raw": raw, "parsed": parsed}

    # ---------- check 阶段 ----------
    @staticmethod
    def run_manifest(strict_extra_files: bool = True) -> Manifest:
        """文件清单校验：声明 vs 实际。

        放在静态检查**之前**：如果该产出的文件压根不存在，对它做语法检查
        没有意义，而且报出来的症状是间接的（ModuleNotFoundError），
        不如直接指出「计划要产出 X，但 X 不存在」。

        strict_extra_files=True 时，声明之外多出来的 .py 也会作为 warning 列出，
        便于发现「模型顺手建了没声明的文件」。
        """
        declared = parse_declared(get_declared_files())
        return check_manifest(declared, strict_extra_files=strict_extra_files)

    @staticmethod
    def _collect_python_files(touched: list[str]) -> list[str]:
        out: list[str] = []
        for item in touched:
            norm = item.replace("\\", "/")
            if not norm.endswith(".py"):
                continue
            if norm not in out:
                out.append(norm)
        return out

    async def run_check(self, touched: list[str]) -> dict[str, Any]:
        """对本次改动的 Python 文件做静态检查。

        返回里的 `status` 是**三态**（`VERIFY-VACUOUS` 建议 4）：
        `passed` / `failed` / `skipped`。「没有可检查的东西」与「检查通过了」
        不是同一件事 —— 只有 `passed` 才是真的查过并通过，
        `checked` 与之配套说明"到底查没查"。这与 `lint` 步骤的三态同一套思路。
        """
        steps: list[dict] = []
        py_files = self._collect_python_files(touched)

        if not py_files:
            return {
                "passed": True,
                "checked": False,
                "status": "skipped",
                "skipped_reason": "本次 cycle 没有产生 .py 文件改动",
                "steps": steps,
                "blocking_file": None,
            }

        for rel in py_files:
            abs_path = os.path.join(WORKSPACE_DIR, rel)
            if not os.path.exists(abs_path):
                steps.append({
                    "tool": "check_syntax",
                    "file": rel,
                    "passed": False,
                    "parsed": {"ok": False, "message": f"文件不存在: {rel}"},
                })
                return {
                    "passed": False,
                    "checked": True,
                    "status": "failed",
                    "skipped_reason": None,
                    "steps": steps,
                    "blocking_file": rel,
                }

            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except OSError as e:
                steps.append({
                    "tool": "check_syntax",
                    "file": rel,
                    "passed": False,
                    "parsed": {"ok": False, "message": f"读取失败: {e}"},
                })
                return {
                    "passed": False,
                    "checked": True,
                    "status": "failed",
                    "skipped_reason": None,
                    "steps": steps,
                    "blocking_file": rel,
                }

            # --- 语法检查（阻塞门） ---
            syn = await self._call("check_syntax", code=code)
            syn_passed = bool((syn["parsed"] or {}).get("ok"))
            steps.append({
                "tool": "check_syntax",
                "file": rel,
                "passed": syn_passed,
                "parsed": syn["parsed"] or {"raw": syn["raw"][:300]},
            })
            if not syn_passed:
                return {
                    "passed": False,
                    "checked": True,
                    "status": "failed",
                    "skipped_reason": None,
                    "steps": steps,
                    "blocking_file": rel,
                }

            # --- lint（非阻塞：ruff 缺失时 ok=None，明确记为「未执行」） ---
            if self.run_lint:
                lint = await self._call("run_lint", code=code)
                parsed = lint["parsed"] or {}
                if parsed.get("skipped"):
                    status = "skipped"
                else:
                    status = "passed" if parsed.get("ok") else "failed"
                steps.append({
                    "tool": "run_lint",
                    "file": rel,
                    "passed": status != "failed",
                    "status": status,
                    "parsed": parsed or {"raw": lint["raw"][:300]},
                })

        return {
            "passed": True,
            "checked": True,
            "status": "passed",
            "skipped_reason": None,
            "steps": steps,
            "blocking_file": None,
        }

    # ---------- verify 阶段 ----------
    async def run_verify(self, command: VerifyCommand) -> dict[str, Any]:
        """执行验证命令，以退出码为唯一判据。

        注意：check_and_run 执行的是 Python 代码，所以 command.command
        应当是一段可直接运行的 Python（例如读入实现文件并 assert）。
        """
        code = (command.command or "").strip()
        if not code:
            return {
                "tool": "check_and_run",
                "passed": False,
                "parsed": None,
                "reason": "verify_command 为空，无法做机器判定",
            }

        # 允许验收标准要求「非零退出」（例如断言脚本本身期望失败）
        res = await self._call(
            "check_and_run", code=code, expect_exit=int(command.expect_exit)
        )
        parsed = res["parsed"] or {}
        passed = bool(parsed.get("ok"))
        if not parsed and is_error_result(res["raw"]):
            passed = False

        return {
            "tool": "check_and_run",
            "passed": passed,
            "command": code,
            "reason": command.reason,
            "expect_exit": command.expect_exit,
            "parsed": parsed or {"raw": res["raw"][:500]},
        }
