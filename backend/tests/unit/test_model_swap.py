"""`D43`：一条「**假换**」冒烟 —— 用同一个模型换个名字，把「换模型」这条**路径**走通。

### 为什么要有它（统筹方自陈，逐字）

> 「我该做而没做的正是这个：**验了配置**（`/profile` 回显了模型名与 limits），
> **没验路径** ⇒ 路径上的缺陷测不出来。」
> 「该做而没做的是『假换』冒烟：用同一个模型换个名字走一遍换模型路径。」

所以这条测试**刻意分两层**，缺一不可：

1. **配置层**：换名字后 `/profile` 的数据源（`main.resolve_profiles()`）真的变了；
2. **路径层**：用这个"换了名字"的档位**真的跑一次子循环**（`Worker.run`），
   并且请求体里带的就是新名字 —— 配置改了但路径没走，等于没换。

「假换」= **同一个端点、同一个模型，只换名字**：能力不变，因此任何失败都只能
归因于**路径**，不会与"新模型能力不行"混在一起。
"""

import asyncio
import os
import sys
from types import SimpleNamespace as NS

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

import core.llm as llm_module  # noqa: E402
from core.llm import REASONING_REPLAY_ENV, LLMClient  # noqa: E402
from core.task import Task  # noqa: E402
from core.worker import Worker  # noqa: E402

OK = Checker()

#: 假换后的名字（同一个模型，只换名字 —— 能力不变，失败只能归因于路径）。
ALIAS = "qwen2.5:7b-fake-swap"
BASE = "http://fake.local/v1"
DEEPSEEK_400 = ("BadRequestError: Error code: 400 - The `reasoning_content` "
                "in the thinking mode must be passed back to the API.")


def _tc(call_id, name, arguments):
    return NS(id=call_id, function=NS(name=name, arguments=arguments))


class FakeCompletions:
    def __init__(self):
        self.requests: list[dict] = []
        self.i = 0

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        # 假端点按 DeepSeek 规则验收：带 tools 的请求必须回灌 reasoning_content。
        if kwargs.get("tools"):
            for m in kwargs.get("messages") or []:
                if isinstance(m, dict) and m.get("tool_calls") and not m.get("reasoning_content"):
                    raise RuntimeError(DEEPSEEK_400)
        self.i += 1
        if self.i == 1:
            msg = NS(content=None,
                     tool_calls=[_tc("c1", "get_system_info", "{}")],
                     reasoning_content="假换后第一轮思考")
        else:
            msg = NS(content="完成", tool_calls=[], reasoning_content="假换后收尾")
        usage = NS(prompt_tokens=1, completion_tokens=2,
                   completion_tokens_details=NS(reasoning_tokens=3))
        return NS(choices=[NS(message=msg, finish_reason="stop")], usage=usage)


class FakeClient:
    def __init__(self):
        self.completions = FakeCompletions()
        self.chat = NS(completions=self.completions)


def _install_fake() -> FakeClient:
    fake = FakeClient()
    llm_module.AsyncOpenAI = lambda **_kw: fake  # type: ignore[assignment]
    return fake


async def main() -> int:
    keys = ("ORCH_MODEL", "ORCH_BASE_URL", "ORCH_API_KEY", "ORCH_PROFILE",
            "WORKER_MODEL", "WORKER_BASE_URL", "WORKER_API_KEY", "WORKER_PROFILE",
            REASONING_REPLAY_ENV)
    saved = {k: os.environ.get(k) for k in keys}
    try:
        # ================= [1] 配置层：/profile 的数据源真的换了名字 =================
        print("=" * 74)
        print("[1] 假换（配置层）：resolve_profiles() —— 就是 `/profile` 用的那个函数")
        print("=" * 74)
        for k in keys:
            os.environ.pop(k, None)
        os.environ.update({
            "ORCH_MODEL": ALIAS,
            "ORCH_BASE_URL": BASE,
            "ORCH_API_KEY": "fake-key",
            "ORCH_PROFILE": "default",
        })
        from main import resolve_profiles  # noqa: E402  在 env 之后 import，避免副作用

        profs = resolve_profiles()
        orch, worker = profs["ORCH"], profs["WORKER"]
        print(f"  ORCH   : {orch.name} / {orch.model} @ {orch.base_url}")
        print(f"  WORKER : {worker.name} / {worker.model} @ {worker.base_url}")
        OK.check("★ 编排器档位读到假换后的模型名", orch.model == ALIAS)
        OK.check("★ 编排器 base_url 也来自本次假换配置", orch.base_url == BASE)
        OK.check("★ 子模型未单独配置 ⇒ 按角色表继承编排器（同一个假换档位）",
                 worker.model == ALIAS)
        OK.check("档位可用（validate 无问题）", orch.validate(role="ORCH") == [])

        # ================= [2] 路径层：用假换档位真的跑一次子循环 =================
        print("\n" + "=" * 74)
        print("[2] 假换（路径层）：Worker 真的跑一次 —— 请求体里带的就是新名字")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "auto"
        fake = _install_fake()
        client = LLMClient(orch)
        worker_obj = Worker(client)
        task = Task(id="t1", description="查看系统信息", expected_output="结论")
        res = await worker_obj.run(task, context="")
        reqs = fake.completions.requests
        print(f"  worker: ok={res.ok} requests={len(reqs)}")
        OK.check("★ 假换路径走通（没有因为换名字而报错）",
                 res.ok is True and len(reqs) >= 2)
        OK.check("★ 每一次请求都用了假换后的模型名（配置真的进了请求体）",
                 all(r.get("model") == ALIAS for r in reqs))
        OK.check("★ 请求仍受工具契约约束（tools 照常下发）",
                 all(bool(r.get("tools")) for r in reqs))

        # ================= [3] 反空洞：路径必须真的被走 =================
        print("\n" + "=" * 74)
        print("[3] 反空洞：把回灌关掉 ⇒ 同一个假换路径必须复现 400")
        print("=" * 74)
        os.environ[REASONING_REPLAY_ENV] = "never"
        _install_fake()
        raised = ""
        try:
            await Worker(LLMClient(orch)).run(task, context="")
        except RuntimeError as e:  # noqa: PERF203
            raised = str(e)
        print(f"  实测异常: {raised[:110]}")
        OK.check("★ 假换路径真的执行到了模型调用（不回灌就 400，判据不是空转）",
                 "must be passed back" in raised)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return OK.report()


raise SystemExit(asyncio.run(main()))
