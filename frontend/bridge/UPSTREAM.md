# 上游适配说明

这份文档回答一个问题：**把最新版后端复制过来之后，要做什么。**

---

## 一句话答案

```powershell
# 1) 覆盖
.\scripts\adopt-backend.ps1 -From D:\path\to\new\backend

# 2) 看自检结果。全绿就完事了；有红项它会告诉你缺什么、影响哪个面板
```

正常情况下**什么都不用改**。下面解释为什么，以及什么情况下需要动手。

---

## 分工

```
backend/     上游代码。**一行都不改**，可以整包替换。
bridge/      我的适配层。上游换新时，原则上不用动。
frontend/    Vue 前端。只跟 bridge 说话。
data/        运行态。
```

`bridge` 对上游的依赖全部是**运行时挂钩**，不是源码修改：

| bridge 做的事 | 手段 | 为什么不用改源码 |
|---|---|---|
| 产出进度事件 | 包装上游的 10 个"汇聚点" | 上游所有事件都从 `_emit` 出去；阶段推进都从 `CycleReport.enter` 出去 |
| 路径落进 `data/` | 启动时把进程 CWD 切到 `data/` | 上游的路径是 CWD 相对的，切了 CWD 它们自动落位 |
| `/api/*` 与 `/app` | 新建 app，把上游 app 的路由接上 | `main.py` 不用动 |
| 契约自检 | 启动时核对 14 个上游接口 | 缺了就报出来，不静默 |

---

## 上游接口清单（bridge 依赖的就是这些）

改动 `bridge/hooks.py` 时必须同步 `bridge/contract.py` 里的 `REQUIREMENTS`。
每一条都写了**缺了会怎样**——这是这份清单的价值所在。

| 上游接口 | 缺了会怎样 |
|---|---|
| `core.coding_cycle.CodingCycle` | 整个流程跑不起来 |
| `core.coding_cycle.CodingCycle._emit` | cycle 级事件（plan/manifest/verify/cycle_end…）全部丢失 |
| `core.coding_cycle.CodingCycle.run` | 无法起一次运行 |
| `core.coding_cycle.CodingCycle._new_file_artifacts` | 前端「产物文件」面板一直为空 |
| `core.cycle.CycleReport.enter` | 阶段流水线不推进（phase 事件丢失） |
| `core.checkpoint.CheckpointManager.commit` | 看不到检查点 |
| `core.checkpoint.CheckpointManager.rollback` | 看不到回退标记 |
| `core.orchestrator.Orchestrator._decide` | 看不到主循环轮次与模型决策原文 |
| `core.worker.Worker.run` | 任务列表为空 |
| `core.worker.Worker._invoke` | 工具调用面板为空 |
| `core.worker.Worker._parse_args` | 工具参数无法预览 |
| `core.llm.LLMClient.chat` | 子循环步数与模型响应看不到 |
| `core.pipeline.CheckPipeline.run_verify` | 「循环内验证回流」看不到 |
| `tools.is_error_result` | 工具成败无法判定 |

**改了签名怎么办**：`.\scripts\adopt-backend.ps1` 会把每个挂钩点的**实际签名**
打出来，与这张表对照即可。

---

## 三种情况

### A. 上游只是修 bug / 换模型 → 什么都不用做

跑一遍验证：

```powershell
python tests/run_unit.py
.\scripts\run.ps1
```

### B. 上游加了新事件

症状：前端时间线上出现标题是**裸 kind**（例如 `review_start`）的一行。

处理：在 `frontend/src/store/run.ts` 的 `switch` 里补一个 `case`。

这件事**有测试把守**——`python tests/unit/test_event_contract.py` 会红，
并指出是哪个 kind、来自哪个文件。它扫三处：

```
backend/ 的 self._emit("kind", ...)     上游自带的事件
bridge/hooks.py 的 emit_progress(...)    挂钩补出来的事件
bridge/runner.py 的 log.append(...)      运行管理器自己的事件
```

### C. 上游改了接口（重命名 / 换签名 / 挪模块）

症状：启动时 `[bridge]` 打出的契约自检报红，或者某个面板一直空着。

处理：

1. 打开 `bridge/contract.py` 的 `REQUIREMENTS`，改对应条目；
2. 打开 `bridge/hooks.py`，改对应的包装；
3. 如果上下游把 `_emit` 之类**汇聚点**拆了，那就得找新的汇聚点——
   找的原则是「上游本来就把所有同类事件从这一个地方发出去」，
   而不是「我方便包哪儿」。

---

## 为什么挂钩选这些点

`_emit` 是最关键的一个：上游**所有** cycle 级事件都从它出去，所以包它一个，
就白拿了 plan / task_result / manifest / syntax / lint / verify / cycle_end /
decision_* / rollback_denied 一大票事件，而且上游以后往里加事件也自动覆盖。

其余各点同理（见 `bridge/hooks.py` 顶部的表）。

**一条纪律**：挂钩内部一律走 `_safe()` 兜异常。进度是旁路，
**坏掉的订阅者绝不能拖垮 cycle**。唯一放行的是 `RunCancelled`
（协作式取消），它继承 `BaseException` 就是为了穿过这些兜底。

---

## 已知的、刻意不做的事

| 不做 | 为什么 |
|---|---|
| 不改上游 `main.py` 的 `/` 返回值 | 那是上游的契约，bridge 只在 `/api/health` 里报自己的路径信息 |
| 不给上游加"暂停/恢复" | 那要改上游的工作流，属于功能需求而不是适配 |
| 不把 `run_id` 与上游 `cycle_id` 对齐 | 上游 `run()` 自己生成 cycle_id。前端按 run_id 订阅，事件里两个 id 都在，按需关联 |
| 不为纯 `uvicorn main:app`（不走 bridge）补事件 | 那条路是上游自己的，没有任何埋点——这是用它就必须接受的取舍 |
