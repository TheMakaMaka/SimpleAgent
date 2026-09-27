import json
import os
import re
import sys

from .llm import LLMClient
from .model_profile import DEFAULT_COUPLING, ModelCoupling, ModelLimits
from .prompts import WORKER_SYSTEM, build_worker_user_message
from .task import Artifact, Task, TaskResult
from tools import TOOLS_MAP, tool_schemas, is_error_result
from tools.registry import PROFILE_CODING, hidden_names


# 计划句式识别与错误前缀嗅探属于「模型耦合」，已移入 ModelCoupling。
# 工作流层只做结构化判断（is_error_result），不再内置任何模型的措辞习惯。

_DEBUG_DIR = "workspace/_debug"
os.makedirs(_DEBUG_DIR, exist_ok=True)


def _normalize_code(code: str) -> str:
    """归一化后再做「是否重复提交」的判断。

    模型常把代码当字面量传来（\\n 而非真换行），或每次只改一点空白，
    导致逐字符比较失效、同一错误反复刷满错误预算。
    这里去掉行尾空白与空行差异，让语义相同的代码能被判为重复。
    """
    text = (code or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _code_hash(code: str) -> int:
    return hash(_normalize_code(code))


def _clip(text: str, limit: int) -> str:
    """按预算截断回灌内容。截断长度来自 ModelLimits，不是魔法数字。"""
    if len(text) <= limit:
        return text
    return text[:limit] + f"...（已截断，共 {len(text)} 字符）"


def _extract_code_block(text: str) -> str | None:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return m.group(1) if m else None


def _dbg(path_suffix: str, content: str) -> None:
    try:
        with open(os.path.join(_DEBUG_DIR, path_suffix), "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


class Worker:
    """子循环：用工具完成单个任务。

    所有预算（max_steps / max_errors / 回灌截断长度）来自 ModelLimits，
    不再使用模块级魔法数字。
    """

    def __init__(
        self,
        llm: LLMClient,
        limits: ModelLimits | None = None,
        coupling: ModelCoupling | None = None,
        profile: str | None = None,
    ):
        self.llm = llm
        # 默认从模型档位取预算，保证「预算只有一个来源」
        profile_obj = getattr(llm, "profile", None)
        self.limits = limits or (profile_obj.limits if profile_obj else ModelLimits())
        self.coupling = coupling or (profile_obj.coupling if profile_obj else DEFAULT_COUPLING)

        # 工具按 profile 过滤：种子工具（天气/计算/抓网页）在编码 profile 下**不下发**。
        # 这比 `tool_hint` 提示更硬——模型根本看不到它们，就不存在"选错"。
        # 注意工具本身没删，只是不在这个 profile 暴露（见 tools/registry.py）。
        self.profile = profile or PROFILE_CODING
        self.tools = tool_schemas(self.profile)
        self.hidden_tools = hidden_names(self.profile)
        if self.hidden_tools:
            print(
                f"  [W] profile={self.profile}：已隐藏种子工具 "
                f"{', '.join(self.hidden_tools)}",
                flush=True,
            )

    async def run(self, task: Task, context: str) -> TaskResult:
        messages = [
            {"role": "system", "content": WORKER_SYSTEM},
            {"role": "user", "content": build_worker_user_message(task, context)},
        ]

        max_steps = task.max_steps or self.limits.max_steps
        max_errors = self.limits.max_errors
        clip = self.limits.tool_result_chars

        error_count = 0
        empty_count = 0
        artifacts: list[Artifact] = []
        last_code_hash = None
        for step in range(max_steps):
            _dbg(
                f"{task.id}_step{step + 1}_input.json",
                json.dumps(messages, ensure_ascii=False, indent=2),
            )

            reply = await self.llm.chat(messages, tools=self.tools)
            content = reply.get("content")
            tool_calls = reply.get("tool_calls") or []

            print(f"  [W:{task.id}:{step + 1}] tool_calls={len(tool_calls)} content_len={len(content or '')}", flush=True)

            # ============ 情况 1：标准 tool_calls ============
            if tool_calls:
                empty_count = 0
                messages.append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                })

                step_had_error = False
                fallback_code = _extract_code_block(content) if content else None
                for tc in tool_calls:
                    name = tc.function.name
                    raw_args = tc.function.arguments or ""
                    # arguments 无效时用 content 里的代码块兜底

                    if name == "run_python":
                        args = self._parse_args(tc.function.arguments) or {}
                        code = args.get("code", "")
                        h = _code_hash(code)
                        if h == last_code_hash:
                            # 归一化后相同的代码，结果不会改变
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": (
                                    "Error: 你刚刚提交了与上一次实质相同的代码（仅空白/换行差异），"
                                    "结果不会改变。请修改代码逻辑后再试。"
                                ),
                            })
                            step_had_error = True
                            continue
                        last_code_hash = h
                    if name == "run_python" and fallback_code:
                        parsed = self._parse_args(raw_args) or {}
                        if not parsed.get("code"):
                            print(f"  [W] arguments 无效，使用 content 代码块兜底", flush=True)
                            raw_args = json.dumps({"code": fallback_code}, ensure_ascii=False)

                    result_text = await self._invoke(name, raw_args)  # ← 用 raw_args
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _clip(result_text, clip),
                    })
                    artifact = self._maybe_artifact(name, raw_args, result_text, task.id)
                    if artifact:
                        artifacts.append(artifact)
                    if is_error_result(result_text):
                        step_had_error = True

                if step_had_error:
                    error_count += 1
                    if error_count > max_errors:
                        return TaskResult(
                            task_id=task.id, ok=False,
                            output=f"连续 {max_errors} 次工具报错",
                            error="工具连续报错，已放弃",
                            artifacts=artifacts, steps_used=step + 1,
                        )
                    messages.append({
                        "role": "user",
                        "content": "上一步出错。请阅读错误信息，修正后重新调用工具。",
                    })
                else:
                    error_count = 0
                continue

            # ============ 情况 2：没 tool_calls，但 content 里有代码块 ============
            if content:
                empty_count = 0
                code = _extract_code_block(content)
                if code:
                    fake_id = f"auto_{task.id}_{step}"
                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": fake_id,
                            "type": "function",
                            "function": {
                                "name": "run_python",
                                "arguments": json.dumps({"code": code}, ensure_ascii=False),
                            },
                        }],
                    })
                    result_text = await self._invoke(
                        "run_python", json.dumps({"code": code}, ensure_ascii=False)
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": fake_id,
                        "content": _clip(result_text, clip),
                    })
                    artifacts.append(Artifact(
                        key=f"{task.id}_code_{step + 1}",
                        kind="code",
                        content=code,
                    ))
                    if is_error_result(result_text):
                        error_count += 1
                        if error_count > max_errors:
                            return TaskResult(
                                task_id=task.id, ok=False,
                                output="代码反复出错",
                                error=f"代码执行连续失败，最后错误: {result_text[:200]}",
                                artifacts=artifacts, steps_used=step + 1,
                            )
                    else:
                        error_count = 0
                    continue

                # 情况 3：纯文本总结
                # 「像不像计划」由耦合层判断；默认耦合不识别任何句式
                if self.coupling.looks_like_plan(content) and step < max_steps - 1:
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": "不要写计划，直接调用工具。"})
                    continue

                return TaskResult(
                    task_id=task.id, ok=True,
                    output=content.strip(),
                    artifacts=artifacts, steps_used=step + 1,
                )

            # 情况 4：空响应
            empty_count += 1
            if empty_count >= 3:
                return TaskResult(
                    task_id=task.id, ok=False,
                    output="模型连续空响应，可能是生成被截断",
                    error=f"连续 {empty_count} 次空响应，max_tokens 可能不足",
                    artifacts=artifacts, steps_used=step + 1,
                )
            messages.append({
                "role": "user",
                "content": "你上一条响应为空。请直接调用工具，不要输出空内容。",
            })

        return TaskResult(
            task_id=task.id, ok=False,
            output="达到子任务步数上限",
            error=f"max_steps={max_steps}",
            artifacts=artifacts, steps_used=max_steps,
        )

    # ---------- 内部 ----------
    async def _invoke(self, name: str, arguments_json: str) -> str:
        if name not in TOOLS_MAP:
            print(f"  [W:_invoke] 未知工具 {name}", flush=True)
            return f"Error: 未知工具 {name}"

        args = self._parse_args(arguments_json)
        if args is None:
            print(f"  [W:_invoke] JSON 解析失败 raw={arguments_json[:200]!r}", flush=True)
            return f"Error: 工具参数不是合法 JSON: {arguments_json[:120]}"

        print(f"  [W:_invoke] {name} keys={list(args.keys())}", flush=True)
        try:
            fn = TOOLS_MAP[name]["function"]
            result = await fn(**args)
            print(f"  [W:_invoke] {name} len={len(result)} head={result[:200]!r}", flush=True)
            return result
        except Exception as e:
            print(f"  [W:_invoke] {name} EXC {e!r}", flush=True)
            return f"Error: 工具执行异常: {e}"

    @staticmethod
    def _maybe_artifact(tool_name: str, arguments_json: str, result: str, task_id: str = "") -> Artifact | None:
        args = Worker._parse_args(arguments_json) or {}

        # --- run_python 成功 → 存代码 ---
        if tool_name == "run_python" and not is_error_result(result):
            code = args.get("code", "")
            if code:
                key = f"{task_id}_code" if task_id else "code_snippet"
                return Artifact(key=key, kind="code", content=code)

        # --- write_file 成功 → 存文件引用 ---
        if tool_name == "write_file" and result.startswith("OK:FILE|"):
            parts = result.split("|", 3)
            if len(parts) >= 4:
                filename = parts[1]
                key = f"{task_id}_file_{filename}" if task_id else f"file_{filename}"
                return Artifact(
                    key=key,
                    kind="file",
                    content=None,
                    path=filename,
                    meta={"filename": filename, "size": parts[2]},
                )

        return None

    @staticmethod
    def _parse_args(arguments_json: str) -> dict | None:
        if not arguments_json or not arguments_json.strip():
            return {}
        try:
            v = json.loads(arguments_json)
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            pass
        try:
            import ast
            v = ast.literal_eval(arguments_json)
            return v if isinstance(v, dict) else None
        except Exception:
            return None

