"""`P19`：推理模型的 `reasoning_content` 协议兼容（**任何推理模型都撞**）。

### 为什么这条测试的方向是"必须回灌"而不是"剥掉"

统筹方 B1-A 的**实测错误原文**（`deepseek-flash`，`https://api.deepseek.com/v1`）：

```
BadRequestError: Error code: 400 - {'error': {'message':
  'The `reasoning_content` in the thinking mode must be passed back to the API.'}}
```

这是"**必须回灌**"（不回灌就 400），不是"禁止回灌"。DeepSeek 官方《Thinking Mode》
也写明：**带 `tools` 的请求**里，上几轮的 `reasoning_content` 必须原样带回。
本仓库旧代码在适配层就把它丢了（`chat()` 返回值里没有这个字段）⇒ 调用点无从补 ⇒ 400。

工单 `P19` 表 1 写的是"剥掉"，与错误原文相反。本测试因此**双向**地把它钉住：
* **带 `tools`**：必须回灌 —— 用一个"缺字段就报 400"的假端点证明（**会红**）；
* **不带 `tools`**：按官方文档无需回灌 ⇒ 剥掉，请求保持干净。

`AGENT_REASONING_REPLAY=never` 可以强制退回工单的字面行为（用于反向验证）。
"""

import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

import core.llm as llm_module  # noqa: E402
from core.llm import (  # noqa: E402
    REASONING_CONTENT,
    REASONING_REPLAY_ENV,
    LLMClient,
    aggregate_usage,
    request_messages,
    strip_reasoning_content,
)
from core.model_profile import ModelProfile  # noqa: E402
from core.task import Task  # noqa: E402
from core.worker import Worker  # noqa: E402

OK = Checker()

#: DeepSeek 官方原文（逐字），本测试用它当"端点判据"。
DEEPSEEK_400 = ("BadRequestError: Error code: 400 - The `reasoning_content` "
                "in the thinking mode must be passed back to the API.")


def _tc(call_id: str, name: str, arguments: str):
    return NS(id=call_id, function=NS(name=name, arguments=arguments))


class FakeCompletions:
    """假端点：**按 DeepSeek 的规则**验收请求，并回放脚本化的响应。

    `_enforce()` 是本测试的"判据"：带 `tools` 的请求里，只要有一个带 `tool_calls`
    的 assistant 消息缺少 `reasoning_content`，就抛**官方原文那个 400**。
    """

    def __init__(self, script: list[dict]):
        self.script = script
        self.requests: list[dict] = []
        self.i = 0

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        self._enforce(kwargs)
        spec = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        msg = NS(content=spec.get("content"),
                 tool_calls=spec.get("tool_calls") or [],
                 reasoning_content=spec.get("reasoning_content"))
        usage = NS(
            prompt_tokens=10,
            completion_tokens=20,
            completion_tokens_details=NS(reasoning_tokens=spec.get("reasoning_tokens", 7)),
        )
        return NS(choices=[NS(message=msg, finish_reason="stop")], usage=usage)

    @staticmethod
    def _enforce(kwargs: dict) -> None:
        if not kwargs.get("tools"):
            return
        for m in kwargs.get("messages") or []:
            if isinstance(m, dict) and m.get("tool_calls") and not m.get(REASONING_CONTENT):
                raise RuntimeError(DEEPSEEK_400)


class FakeClient:
    def __init__(self, script: list[dict]):
        self.completions = FakeCompletions(script)
        self.chat = NS(completions=self.completions)


def _install_fake(script: list[dict]) -> FakeClient:
    fake = FakeClient(script)
    # LLMClient.__init__ 里 `AsyncOpenAI(...)` 取的是模块全局，故在此替换即可。
    llm_module.AsyncOpenAI = lambda **_kw: fake  # type: ignore[assignment]
    return fake


def _worker_script() -> list[dict]:
    """第 1 轮：带 reasoning + 一个无参工具调用；第 2 轮：带 reasoning + 纯文本收尾。"""
    return [
        {"reasoning_content": "先看看系统信息", "content": None,
         "tool_calls": [_tc("c1", "get_system_info", "{}")]},
        {"reasoning_content": "看完了，给结论", "content": "完成", "tool_calls": []},
    ]


async def _run_worker(replay_mode: str):
    os.environ[REASONING_REPLAY_ENV] = replay_mode
    fake = _install_fake(_worker_script())
    client = LLMClient(ModelProfile())
    worker = Worker(client)
    task = Task(id="t1", description="查看系统信息", expected_output="一句话结论")
    return await worker.run(task, context=""), client, fake


async def main() -> int:
    original = os.environ.get(REASONING_REPLAY_ENV)
    try:
        # ================= [1] 带 tools ⇒ 必须回灌（会红的判据） =================
        print("=" * 74)
        print("[1] P19：带 tools 的后续请求**必须回灌** reasoning_content（真实 400 的成因）")
        print("=" * 74)
        res, client, fake = await _run_worker("auto")
        reqs = fake.completions.requests
        print(f"  worker: ok={res.ok} steps={res.steps_used} requests={len(reqs)}")
        OK.check("worker 走通（不再 400）", res.ok is True)
        OK.check("发了不止一次请求（确实走了‘后续请求’那条路）",
                 len(reqs) >= 2)
        second = reqs[1]
        asst = [m for m in second["messages"]
                if isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls")]
        OK.check("★ 第 2 次请求带 tools", bool(second.get("tools")))
        OK.check("★ 第 2 次请求里那个 assistant 消息带回了 reasoning_content",
                 bool(asst) and asst[0].get(REASONING_CONTENT) == "先看看系统信息")
        print(f"    回灌字段 = {asst[0].get(REASONING_CONTENT)!r}")

        # ================= [2] 反空洞：抽掉回灌 ⇒ 同一个假端点必须 400 =================
        print("\n" + "=" * 74)
        print("[2] 反空洞：`AGENT_REASONING_REPLAY=never`（工单字面行为）⇒ 必须复现 400")
        print("=" * 74)
        raised = ""
        try:
            await _run_worker("never")
        except RuntimeError as e:  # noqa: PERF203
            raised = str(e)
        print(f"  实测异常: {raised[:120]}")
        OK.check("★ 不回灌 ⇒ 假端点抛出官方 400 原文（说明这条判据不是空转）",
                 "must be passed back" in raised)
        OK.check("★ 这也证明：工单表 1 的‘剥掉’正是旧代码 400 的成因（方向相反）",
                 "reasoning_content" in raised)

        # ================= [3] 不带 tools ⇒ 剥掉（按官方文档无需回灌） =================
        print("\n" + "=" * 74)
        print("[3] 不带 tools ⇒ 剥掉（官方：无需回灌，传了也会被忽略）")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "auto"
        fake = _install_fake([{"content": '{"ok": 1}', "reasoning_content": "思考"}])
        client = LLMClient(ModelProfile())
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "a", REASONING_CONTENT: "不该回灌的思考"},
        ]
        await client.chat_json(msgs)
        sent = fake.completions.requests[-1]
        leaked = [m for m in sent["messages"]
                  if isinstance(m, dict) and REASONING_CONTENT in m]
        OK.check("★ 不带 tools 的请求体里没有 reasoning_content",
                 not sent.get("tools") and not leaked)
        OK.check("请求体仍然完好（只剥这一个字段，不动 role/content）",
                 sent["messages"][0]["role"] == "user"
                 and sent["messages"][1]["content"] == "a")

        # ================= [4] 用量（reasoning_tokens 先吃掉 max_tokens） =================
        print("\n" + "=" * 74)
        print("[4] 用量：reasoning_tokens 必须进 client.usage 并能汇总进报告")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "auto"
        _res, client2, _fake2 = await _run_worker("auto")
        print(f"  usage = {client2.usage}")
        OK.check("★ client.usage 记到 reasoning_tokens（= 7 × 2 次调用）",
                 client2.usage["reasoning_tokens"] == 14)
        agg = aggregate_usage([("worker", client2)])
        print(f"  aggregate = {agg['total']}")
        OK.check("★ aggregate_usage 汇总 reasoning_tokens（报告可读）",
                 agg["total"]["reasoning_tokens"] == 14
                 and agg["by_role"]["worker"]["calls"] == 2)

        # ================= [5] 纯函数面：request_messages 的三档策略 =================
        print("\n" + "=" * 74)
        print("[5] `request_messages` 的三档策略（唯一判定点）")
        print("=" * 74)
        sample = [{"role": "assistant", "content": "x", REASONING_CONTENT: "t"}]
        os.environ[REASONING_REPLAY_ENV] = "auto"
        OK.check("auto + tools ⇒ 保留", REASONING_CONTENT in request_messages(sample, [{}])[0])
        OK.check("auto + 无 tools ⇒ 剥掉",
                 REASONING_CONTENT not in request_messages(sample, None)[0])
        os.environ[REASONING_REPLAY_ENV] = "never"
        OK.check("never ⇒ 一律剥掉",
                 REASONING_CONTENT not in request_messages(sample, [{}])[0])
        os.environ[REASONING_REPLAY_ENV] = "always"
        OK.check("always ⇒ 一律保留",
                 REASONING_CONTENT in request_messages(sample, None)[0])
        os.environ[REASONING_REPLAY_ENV] = "bogus"
        OK.check("非法值回落 auto",
                 REASONING_CONTENT not in request_messages(sample, None)[0])
        OK.check("strip_reasoning_content 不改调用方的列表（纯函数）",
                 REASONING_CONTENT in sample[0])
    finally:
        if original is None:
            os.environ.pop(REASONING_REPLAY_ENV, None)
        else:
            os.environ[REASONING_REPLAY_ENV] = original
    return OK.report()


raise SystemExit(asyncio.run(main()))
