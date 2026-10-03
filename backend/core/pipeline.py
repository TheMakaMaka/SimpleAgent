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

from . import runtime
from .context import get_declared_files
from .cycle import VerifyCommand
from .manifest import Manifest, check_manifest, parse_declared
from .symbol_index import build_index
from tools import TOOLS_MAP, is_error_result

#: 兼容常量（旧引用）；**实际生效的根**由 `runtime.effective_root()` 决定 ——
#: ★ P15：设了任务级目标项目根后，check / verify / 产物对账都要**以它为根**，
#: 否则「被验证的对象必须就是被交付的对象」立刻失效（与 P6 同族）。
WORKSPACE_DIR = os.path.abspath("workspace")


def _abs_of(rel: str) -> str | None:
    """把工具给出的相对标签解析成绝对路径；越界返回 None（不静默落到别处）。"""
    try:
        return runtime.resolve_write(rel)
    except runtime.ScopeError:
        return None


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
    #: 机械层**有否决权**的检查（`TRANSPARENCY2-BACKEND` P2）在这一段接入。
    #: 原来 lint 是**刻意非阻塞**的（下面注释里写着），实测后果是：
    #: **两次运行都带着 lint 错误（含 `F821`）却 `check.passed=True`**。
    #: 现在把"必然崩"的两类提为阻塞：调用了不存在的符号、用了没导入的名字。
    BLOCKING_REUSE_KINDS = frozenset({"undefined-symbol", "undefined-name"})

    #: ★ 架构视图**不得由模型手写**（P4）：架构事实的唯一来源是 AST 派生视图
    #: （`tools/arch.py`）。要人类可读版就从派生视图**渲染** —— 渲染件带这个标记。
    ARCH_VIEW_MARKER = "<!-- derived-from: ast-architecture-view -->"

    @classmethod
    def _arch_doc_violations(cls, touched: list[str]) -> list[dict]:
        """拦住"模型手写的架构文档"（P4 的**会红的检查**）。

        判据是机械的：文件名像架构文档 **且** 内容不含派生视图标记 → 违规。
        为什么用"文件名 + 标记"而不是"内容像不像架构"：后者不可判定；
        前者能同时做到两件事 —— **拦住手写**，并**放行渲染件**（渲染器会写标记）。
        """
        import re

        out: list[dict] = []
        pat = re.compile(r"(架构|architecture|arch)[^/]*\.(md|txt|rst|markdown)$", re.I)
        root = runtime.effective_root()
        for rel in touched:
            norm = str(rel).replace("\\", "/")
            if not pat.search(norm):
                continue
            abs_path = _abs_of(norm) or os.path.join(root, norm)
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    head = f.read(4000)
            except OSError:
                continue
            if cls.ARCH_VIEW_MARKER in head:
                continue
            out.append({
                "kind": "hand-written-architecture-doc",
                "severity": "blocking",
                "message": (
                    f"{norm} 像一份**模型手写的架构文档** —— 架构事实的唯一来源是 "
                    f"AST 派生视图（`get_architecture` / `get_module` / `find_symbol`）。"
                    f"手写版会成为『架构事实的第二份拷贝』（两边都不算错，错在有两份）。"
                    f"要人类可读版请用渲染件（含 `{cls.ARCH_VIEW_MARKER}` 标记）"
                ),
                "where": norm,
            })
        return out

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
        return check_manifest(declared, index=build_index(runtime.effective_root()),
                              strict_extra_files=strict_extra_files,
                              base_dir=runtime.effective_root())

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
        """对本次改动的 Python 文件做静态检查 + **机械复用性检查（阻塞）**。

        返回里的 `status` 是**三态**（`VERIFY-VACUOUS` 建议 4）：
        `passed` / `failed` / `skipped`。「没有可检查的东西」与「检查通过了」
        不是同一件事 —— 只有 `passed` 才是真的查过并通过，
        `checked` 与之配套说明"到底查没查"。这与 `lint` 步骤的三态同一套思路。

        ★ `TRANSPARENCY2-BACKEND` P2：`reuse` 段是**有否决权**的机械层 ——
        "调用了不存在的符号"（实测两次运行都因此失败）在这一段直接判红。
        """
        steps: list[dict] = []
        py_files = self._collect_python_files(touched)

        # ---------- P2 机械复用性（**先于**逐文件语法检查）----------
        # 放在最前面：它抓的是"符号根本不存在"这类**结构性**错误，
        # 报出来的话比后面间接的语法/运行错误更贴近根因。
        from .reuse_checks import check_code, run_ruff_f821

        reuse_blocking: list[dict] = []
        reuse_warnings: list[dict] = []
        for rel in self._collect_python_files(touched):
            abs_path = _abs_of(rel)
            if not abs_path:
                continue
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except OSError:
                continue
            found, _refs = check_code(code, label=rel)
            reuse_blocking += [v for v in found
                               if v.get("kind") in self.BLOCKING_REUSE_KINDS]
            # 用了没导入：优先 ruff 的 F821，没装 ruff 时用 AST 兜底（都算阻塞）
            f821 = run_ruff_f821(code) if code else []
            if not f821 and code:
                from .reuse_checks import check_undefined_names
                f821 = check_undefined_names(code, label=rel)
            reuse_blocking += [
                {**v, "where": rel,
                 "message": f"{rel} {v.get('message', '')}".strip()}
                for v in f821
            ]
        try:
            from .reuse_checks import check_workspace
            ws = check_workspace()
            reuse_warnings += ws.get("warnings") or []
        except Exception:  # noqa: BLE001 —— 机械检查自身出问题不能变成"代码有问题"
            reuse_warnings += [{"kind": "reuse-check-failed", "severity": "warning",
                                "message": "复用性检查自身异常（已忽略）"}]
        # 去重（同一符号可能在多处被引用）
        seen_k: set[tuple] = set()
        dedup: list[dict] = []
        for v in reuse_blocking:
            key = (v.get("kind"), v.get("message"))
            if key in seen_k:
                continue
            seen_k.add(key)
            dedup.append(v)
        reuse_blocking = dedup
        # P4：架构文档不得由模型手写
        arch_blocking = self._arch_doc_violations(touched)
        reuse_blocking += arch_blocking

        reuse = {
            "checked": True,
            "passed": not reuse_blocking,
            "blocking": reuse_blocking[:10],
            "warnings": reuse_warnings[:10],
            "blocking_kinds": sorted({v.get("kind") for v in reuse_blocking}),
        }
        steps.append({
            "tool": "reuse_check",
            "file": "",
            "passed": reuse["passed"],
            "status": "passed" if reuse["passed"] else "failed",
            "parsed": reuse,
        })

        # ★ 复用性违规**直接否决**（不等语法/lint）：它是"符号根本不存在"这类
        # 结构性错误，越早报越好；也避免把两类问题混成一条难读的失败。
        if not reuse["passed"]:
            return {
                "passed": False,
                "checked": True,
                "status": "failed",
                "skipped_reason": None,
                "steps": steps,
                "blocking_file": str(reuse_blocking[0].get("where") or ""),
                "reuse": reuse,
            }

        if not py_files:
            # 没有 `.py` 改动 → 三态里的 **skipped**（"没东西可查" ≠ "查过并通过"）。
            # 注意：复用性检查**已经跑过**（上面，所以 `steps` 里有它的结论）；
            # 这里说的"没查"指的是**逐文件语法/lint**。
            return {
                "passed": True,
                "checked": False,
                "status": "skipped",
                "skipped_reason": "本次 cycle 没有产生 .py 文件改动",
                "steps": steps,
                "blocking_file": None,
                "reuse": reuse,
            }

        for rel in py_files:
            abs_path = _abs_of(rel)
            if not abs_path:
                steps.append({
                    "tool": "check_syntax",
                    "file": rel,
                    "passed": False,
                    "parsed": {"ok": False,
                               "message": f"路径越界（不在目标根/输出根内）: {rel}"},
                })
                return {
                    "passed": False,
                    "checked": True,
                    "status": "failed",
                    "skipped_reason": None,
                    "steps": steps,
                    "blocking_file": rel,
                    "reuse": reuse,
                }
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
                    "reuse": reuse,
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
                    "reuse": reuse,
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
                    "reuse": reuse,
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
            "reuse": reuse,
        }

    # ---------- verify 阶段 ----------
    @staticmethod
    def _purge_pycache() -> tuple[int, str]:
        """清掉**工作区根**下的 `__pycache__`，返回 `(清掉的目录数, 警告)`。

        ★ P6 要求 4：**判词必须描述产物**。若上一版代码留下的 `.pyc` 与
        源码的 (mtime, size) 恰好匹配（回退用 `copy2` 会**保留原 mtime**，
        极容易凑成这种巧合），`import` 就会执行**旧代码** ——
        于是"验证执行的不是被交付的产物"。清掉字节码是唯一可靠的做法。
        清不掉（被占用等）**必须显式声明**，不能假装没这回事。

        ★ P15 边界（**刻意保守**）：只清**工作区根**（agent 的草稿区）。
        设了任务级目标项目根时，那是**别人的仓库** —— 往里面删东西
        违反三方隔离；此时**如实记一条 warning**，而不是偷偷去清。
        """
        import shutil

        cleared = 0
        root = runtime.workspace_root()
        try:
            for dirpath, dirs, _files in os.walk(root):
                if "__pycache__" in dirs:
                    shutil.rmtree(os.path.join(dirpath, "__pycache__"),
                                  ignore_errors=True)
                    cleared += 1
        except OSError as e:
            return cleared, f"清理 __pycache__ 失败: {e}"
        warning = ""
        if os.path.abspath(runtime.effective_root()) != os.path.abspath(root):
            warning = (
                "目标项目根不是工作区根：**只清了工作区根的 __pycache__**，"
                "没有去动目标项目根里的字节码（三方隔离）。"
                "若目标根里有陈旧 .pyc，`-B` + PYTHONDONTWRITEBYTECODE "
                "只阻止写入、不阻止读取"
            )
        return cleared, warning

    @staticmethod
    def artifact_hashes(files: list[str] | None) -> dict[str, str]:
        """被验证产物的**内容哈希**（`{相对路径: sha1[:12]}`）。

        为什么必须是**内容**哈希而不是 mtime：P6 的实测事实是
        "判词不描述产物" —— 只有内容哈希能与**最终产物**逐字对账。
        文件不存在 → 记 `"<missing>"`（**不跳过**：缺失本身就是要对账的事实）。
        """
        import hashlib as _hashlib

        out: dict[str, str] = {}
        for rel in files or []:
            norm = str(rel).replace("\\", "/")
            path = _abs_of(norm)
            if not path:
                out[norm] = "<missing>"
                continue
            try:
                with open(path, "rb") as f:
                    out[norm] = _hashlib.sha1(f.read()).hexdigest()[:12]
            except OSError:
                out[norm] = "<missing>"
        return out

    async def run_verify(
        self, command: VerifyCommand, files: list[str] | None = None
    ) -> dict[str, Any]:
        """执行验证命令，以退出码为唯一判据。

        注意：check_and_run 执行的是 Python 代码，所以 command.command
        应当是一段可直接运行的 Python（例如读入实现文件并 assert）。

        ★ `files` 是**这次验证所针对的产物**（P6）：进来先记它们的**内容哈希**、
        清掉字节码缓存，跑完再记一次。上层据此把"判词"与"最终产物"对账，
        对不上就是 `invalid`（**这次读数无效**），而不是 `fail`（模型不行）。
        """
        code = (command.command or "").strip()
        if not code:
            return {
                "tool": "check_and_run",
                "passed": False,
                "parsed": None,
                "reason": "verify_command 为空，无法做机器判定",
            }

        # ★ P6 要求 1/3/4：验证前记哈希、清缓存、明确工作目录
        before = self.artifact_hashes(files)
        cleared, cache_warning = self._purge_pycache()

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
            # —— P6：这次判词到底验的是哪份产物 ——
            "artifact_hashes": before,
            "artifact_hashes_after": self.artifact_hashes(files),
            "cwd": runtime.effective_root(),
            "cache_cleared": cleared,
            "cache_warning": cache_warning,
        }
