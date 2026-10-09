# 变更评估文档 · `REASONING-PROTOCOL`（P19 + P20 + D43）

- **变更编号**：`REASONING-PROTOCOL`（工作单 **P19** / **P20** / 未决 **D43**）
- **提出方**：统筹（`DISPATCH.md` 顶部 P19/P20）+ 未决 D41/D43
- **执行侧**：backend
- **日期**：2026-10-04
- **契约版本**：`1.0.34`
- **本轮 round_id**：`R-5bfd0ff2e5` —— **本轮完成 `R-5bfd0ff2e5`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-5bfd0ff2e5` 开工，
> 与仓库里上一轮记录的 `R-58068c34ba`（`docs/EVALUATION-DECOMPOSE-GATE-BLOCK.md`）不同 ⇒ 有新指令。
> 本轮新增内容 = `DISPATCH.md` 顶部的 **P19 + P20** 与未决 **D43**；`P14/P15/P13/P11/P17/P18`
> 均已在前几轮交付（见各自评估文档），**不重做**。

---

> ## ★ 必须先看：本轮有一处**方向性分歧**，需要统筹方裁决
>
> **工单 `P19` 表 1** 写：「组装后续请求的消息历史时，**剥掉 `reasoning_content`**」，
> 并给验收 ①「带 `reasoning_content` 的响应 ⇒ 后续请求体里没有该字段」。
>
> **但统筹方自己的实测错误原文是"必须回灌"**（`04-tests/capability/records.jsonl`，逐字）：
>
> ```
> BadRequestError: Error code: 400 - {'error': {'message':
>   'The `reasoning_content` in the thinking mode must be passed back to the API.'}}
> ```
>
> **这是"不回灌就 400"，不是"回灌才 400"。** DeepSeek 官方《Thinking Mode》逐字：
> 「If the request **carries the `tools` parameter**: the `reasoning_content` of all previous
> turns **should be passed back to the API** and will be concatenated into the context.」
> 本仓库旧代码在适配层就把该字段丢了（`core/llm.py::LLMClient.chat` 的返回值里没有它）
> ⇒ 子循环 `core/worker.py` 组装 assistant 消息时**无从补** ⇒ 下一个带 `tools` 的请求 400。
>
> **因此本轮按"协议正确"实现**（带 `tools` 必须回灌、不带才剥掉），并保留
> `AGENT_REASONING_REPLAY=never` 一键退回工单的字面行为。**请统筹方裁决**：
> 若确认要一律剥掉，把默认改成 `never` 即可（一处常量）；但那会让真实推理端点继续 400。
> 机械证据见 §2.1 / §4.1 / §4.2。

---

## 1. 变更意图

**统筹方 `DISPATCH.md` 顶部，逐字**：

> ### ⓪【P19 + P20】**换模型路上实测炸出来的两件**（最高优先）
>
> - **P19 `reasoning_content` 协议兼容**：实测 400 —— 推理模型返回的 `reasoning_content`
>   **被回灌进消息历史**，API 拒绝。**任何推理模型都撞**。
> - **P20 修正 P18（我派错了）**：关卡 `block` 正在**误否决** —— 实测通报写着
>   『2 条判不了 [P2, P5]』而任务被拦。**先止血：默认退回 `warn`**；再**分档**
>   （`undecidable` ≠ 不通过）。

**工作单 P19 表（逐字）**：① 组装后续请求时剥掉 `reasoning_content`；② 模型返回的
`reasoning_content` 可留在事件/报告里供诊断，但不得回灌；③ `max_tokens` 语义要与推理模型
一致（`reasoning_tokens` 先吃预算 ⇒ 报告里要能看到 reasoning 用量）；④ 加**会红**的测试。

**工作单 P20 表（逐字）**：① 止血：默认退回 `warn`；② 分档：`undecidable` 不得等同于
不通过（只要没有 `violated` 就不否决）；③ 通报里如实写出三项计数；④ 分档落地后再决定是否升
`block`；⑤ 加**会红**的测试：只有 `undecidable`、没有 `violated` 的拆解必须放行。

**未决 D43（逐字）**：「加一条「**假换**」冒烟 —— 用同一个模型换个名字走通『换模型』这条路径。
**我该做而没做的正是这个**：验了配置，没验路径。」

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 P19 · `reasoning_content`：旧代码把"必须回灌的字段"丢了

**实测错误原文**（统筹方 B1-A，`deepseek-flash`，`base_url=https://api.deepseek.com/v1`）：

```
BadRequestError: Error code: 400 - {'error': {'message':
  'The `reasoning_content` in the thinking mode must be passed back to the API.'}}
```

**根因（带 `文件:行`）**：

| # | 事实 | 位置（本轮改动前 = v1.29） |
|---|---|---|
| 1 | 适配层从响应里**只取** `content` / `tool_calls` / `finish_reason`，`reasoning_content` 被丢弃 | `core/llm.py::LLMClient.chat` 返回 dict（旧版无该键） |
| 2 | 子循环组装的 assistant 消息只有 `role/content/tool_calls`，**没有** `reasoning_content` | `core/worker.py::Worker.run` 情况 1（旧版 `messages.append({...})`） |
| 3 | 于是下一个带 `tools` 的请求里"上轮 assistant 有 `tool_calls` 却没有 `reasoning_content`" ⇒ API 400 | 同上；DeepSeek 官方《Thinking Mode》Tool Calls 节 |

**为什么"任何推理模型都撞"**：只要模型返回 `reasoning_content` 且后续请求带 `tools`
（子循环**总是**带），就必撞；7 个历史批次全是 `qwen2.5:7b`（不返回该字段）⇒ 这条路径从未被走过。

### 2.2 P20 · 拆解关卡 `block` 误否决

**实测（统筹方 B1-A）**：

```
T9  invalid —— 拆解合规审查**否决**（机械层，mode=block）：违反 ['P3']
    机械层：5 条通过 / 1 条违反 ['P3'] / **2 条判不了 ['P2', 'P5']**
T11 fail · V2 fail（上一轮它是 pass）· V4 fail · V6 fail —— 同一类否决
```

**根因**：`P18` 把出厂默认从 `warn` 升到 `block`，而统筹方自己在拆解数据分析里已写明
「P2/P5 在现有数据形态下 11/11 得不出结论 ⇒ 直接升 `block` 会拦下大部分题且主要是假阳性」。
**分档这件事没有写进 P18 工单** —— 报告 ≠ 工单 ≠ 判据。

**当前代码事实（机械输出）**：`core/coding_cycle.py::CodingCycle.DECOMPOSE_GATE_DEFAULT`
在 v1.29 = `"block"`；`review_decomposition()` 的 `passed = not violated`（P2/P5 的
`undecidable` 本就不参与 `passed`），**但默认值是 `block`，于是 P3 的假阳性会直接拦下整轮**。

### 2.3 复现命令与输出（默认值）

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import os,sys; sys.path.insert(0,r'D:\PythonProject\SimpleAgent2_Cycle'); os.chdir(r'D:\PythonProject\SimpleAgent2_Cycle'); from core import CodingCycle; os.environ.pop('DECOMPOSE_GATE',None); c=CodingCycle(orchestrator=None,worker=None); print('DECOMPOSE_GATE_DEFAULT =', CodingCycle.DECOMPOSE_GATE_DEFAULT); print('_decompose_gate_mode() =', c._decompose_gate_mode()); print('env DECOMPOSE_GATE =', repr(os.environ.get('DECOMPOSE_GATE')))"
```

```
DECOMPOSE_GATE_DEFAULT = warn
_decompose_gate_mode() = warn
env DECOMPOSE_GATE = None
```

⇒ **不设任何环境变量**时默认就是 `warn`（环境变量确实没设）—— `P20` 要求 1 的止血已生效。

### 2.4 D43 · "换模型"路径从未被走过

统筹方自陈：换模型冒烟只验了**配置**（`/profile` 回显模型名与 limits），**没验路径**。
⇒ 需要一个"**同一个模型换个名字**"的冒烟：能力不变，任何失败都只能归因于**路径**。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle -C D:\PythonProject\SimpleAgent2_Cycle status --short
git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle -C D:\PythonProject\SimpleAgent2_Cycle diff --stat
```

```
=== git status --short ===
 M CYCLE.md
 M README.md
 M core/coding_cycle.py
 M core/contract.py
 M core/cycle.py
 M core/llm.py
 M core/worker.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
 M docs/PENDING_DECISIONS.md
 M tests/unit/test_artifact_binding.py
 M tests/unit/test_cycle_manifest.py
 M tests/unit/test_decompose_review.py
 M tests/unit/test_reuse_scope.py
 M tests/unit/test_transparency.py
?? docs/EVALUATION-REASONING-PROTOCOL.md
?? tests/unit/test_model_swap.py
?? tests/unit/test_reasoning_protocol.py
=== git diff --stat ===
 CYCLE.md                            |   2 +-
 README.md                           |   5 +-
 core/coding_cycle.py                |  56 +++++++++++----
 core/contract.py                    |   2 +
 core/cycle.py                       |   9 +++
 core/llm.py                         | 139 +++++++++++++++++++++++++++++++++++-
 core/worker.py                      |  40 ++++++++---
 docs/ARCHITECTURE.md                |   2 +-
 docs/CHANGELOG.md                   |  64 +++++++++++++++++
 docs/MODULES.md                     |  24 ++++---
 docs/OPERATIONS.md                  |  12 ++--
 docs/PENDING_DECISIONS.md           |  25 ++++---
 tests/unit/test_artifact_binding.py |   9 +--
 tests/unit/test_cycle_manifest.py   |   6 +-
 tests/unit/test_decompose_review.py |  98 +++++++++++++++----------
 tests/unit/test_reuse_scope.py      |   4 +-
 tests/unit/test_transparency.py     |   6 +-
 17 files changed, 398 insertions(+), 105 deletions(-)
```

> `git diff --stat` **不含未跟踪的新文件**（本评估文档 + 两个新测试）。新文件的权威依据是
> 上面的 `git status --short`（`??` 行）与 §8 的备份点 `git show --stat`。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/llm.py` | 新增 `request_messages()` / `strip_reasoning_content()` / `response_usage()` / `aggregate_usage()` + `REASONING_CONTENT` 常量 | **唯一判定点**：带 `tools` ⇒ 回灌，不带 ⇒ 剥掉；`AGENT_REASONING_REPLAY` 可灰度 |
| 2 | `core/llm.py` | `LLMClient.chat()` | 把 `reasoning_content` 作为**事实**带回；累计用量（含 `reasoning_tokens`） |
| 3 | `core/worker.py` | 新增 `_assistant_message()` + 三个分支 | 上一轮的 `reasoning_content` **原样回灌**（P19 的真实修复点） |
| 4 | `core/cycle.py` | `CycleReport.model_usage` + `to_dict()` | 报告要能看到 reasoning 用量（要求 3） |
| 5 | `core/contract.py` | `FROZEN_REPORT_KEYS` | 加 `model_usage`（**加性**） |
| 6 | `core/coding_cycle.py` | `_attach_model_usage()` | 把 `orchestrator` / `worker` 的用量汇总进报告 |
| 7 | `core/coding_cycle.py` | `DECOMPOSE_GATE_DEFAULT: "block" → "warn"` | **P20 要求 1**：止血 |
| 8 | `core/coding_cycle.py` | `_review_decomposition()` 否决条件 `not passed` → **`violated`** | **P20 要求 2**：分档，`undecidable` 不否决 |
| 9 | `tests/unit/test_reasoning_protocol.py` | 新文件 | P19 的**会红**双向判据（假端点按 DeepSeek 规则验收） |
| 10 | `tests/unit/test_model_swap.py` | 新文件 | D43 假换冒烟（配置层 + 路径层 + 反空洞） |
| 11 | `tests/unit/test_decompose_review.py` | `[V4]` 重写 + 新增 `[V5]` + `ScriptedLLM.usage` | P20 默认值与分档双向；P19 报告用量 |
| 12 | `tests/unit/test_artifact_binding.py` / `test_cycle_manifest.py` / `test_reuse_scope.py` / `test_transparency.py` | 注释 | 把"P18 起默认 block"的**陈旧声明**改成与实现一致（这本身就是本项目在治的 U- 类） |
| 13 | `docs/CHANGELOG.md` | 新增 §44 | 过程记录 |
| 14 | `docs/MODULES.md` §28 / `docs/OPERATIONS.md` §4.17 / `docs/PENDING_DECISIONS.md` C11 | 默认值与分档 | 文档与实现一致 |
| 15 | `README.md` / `CYCLE.md` / `docs/ARCHITECTURE.md` / `docs/MODULES.md` / `docs/OPERATIONS.md` | 顶部版本戳 | `§43 → §44`（文档一致性门禁要求 == CHANGELOG 最新条目） |
| 16 | `README.md` | 文档表 | 登记本评估文档；并把 P18 那行标注"已由 P20 修正" |
| 17 | `docs/EVALUATION-REASONING-PROTOCOL.md` | 新文件 | 本评估文档 |

**若两者不一致**：机械输出里 `git diff --stat` 不含第 9/10/17 项（未跟踪新文件）
与 `docs/VERSIONS.md`（由 `tests/backup.py` 在提交后追加）；这几项的权威依据是
§8 的备份点 `git show --stat`。

---

## 4. 主张与验证命令（对应 C2、C3）

### 4.1 P19 · 会红：不回灌 ⇒ 复现官方 400；回灌 ⇒ 走通（验收 ① 的**正确版本**）

```powershell
& "D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe" tests\unit\test_reasoning_protocol.py
```

`[1]` 段（假端点：带 `tools` 且 assistant 缺 `reasoning_content` ⇒ 抛官方 400 原文）：

```
  worker: ok=True steps=2 requests=2
  ★ 第 2 次请求里那个 assistant 消息带回了 reasoning_content
    回灌字段 = '先看看系统信息'
```

`[2]` 段（**反空洞**：把回灌关掉 = 复刻旧代码行为）：

```
  实测异常: BadRequestError: Error code: 400 - The `reasoning_content` in the thinking mode must be passed back to the API.
  PASS  ★ 不回灌 ⇒ 假端点抛出官方 400 原文（说明这条判据不是空转）
  PASS  ★ 这也证明：工单表 1 的‘剥掉’正是旧代码 400 的成因（方向相反）
```

`[3]` 段（不带 `tools` ⇒ 剥掉）：

```
  PASS  ★ 不带 tools 的请求体里没有 reasoning_content
  PASS  请求体仍然完好（只剥这一个字段，不动 role/content）
```

`[1]–[5]` 合计：**通过 16/16**。

> **对照统筹方验收 ①**：工单要求"带 `reasoning_content` 的响应 ⇒ 后续请求体里**没有**该字段"。
> **本侧不满足这条字面验收**，因为它与错误原文相反。本侧满足的是"**带 `tools` ⇒ 有**、
> **不带 `tools` ⇒ 没有**"，并给出 `AGENT_REASONING_REPLAY=never` 一键退回字面行为。
> **请统筹方裁决**（见顶部横幅与 §9）。

### 4.2 P19 · 用量（要求 3）

同上测试 `[4]` 段：

```
  usage = {'calls': 2, 'prompt_tokens': 20, 'completion_tokens': 40, 'reasoning_tokens': 14}
  aggregate = {'calls': 2, 'prompt_tokens': 20, 'completion_tokens': 40, 'reasoning_tokens': 14, 'reasoning_share': 0.35}
  PASS  ★ client.usage 记到 reasoning_tokens（= 7 × 2 次调用）
  PASS  ★ aggregate_usage 汇总 reasoning_tokens（报告可读）
```

`CycleReport` 侧（`tests/unit/test_decompose_review.py` `[V4]` 段）：

```
  P19 报告用量：{'calls': 2, 'prompt_tokens': 0, 'completion_tokens': 20, 'reasoning_tokens': 14, 'reasoning_share': 0.7}
  PASS  ★ P19：报告带模型用量（含 reasoning_tokens，且进了 to_dict）
```

### 4.3 P20 · 默认值 + 分档双向（验收 ①/②）

```powershell
& "D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe" tests\unit\test_decompose_review.py
```

`[V4]` 段（默认值，不设任何环境变量）：

```
  PASS  ★ 类默认值 == warn（P20 要求 1：退回 warn 止血）
  PASS  ★ 不设环境变量 ⇒ _decompose_gate_mode() == 'warn'
  PASS  环境变量 off/warn/block 仍可覆盖（保留灰度）
  PASS  非法值回落到默认 warn（不是静默放行）
  PASS  ★ 默认 warn：不合规拆解**只留痕、不拦路**（这正是止血）
  PASS  留痕仍在：事件带 violated（含 P3）与 mode=warn
```

`[V5]` 段（**分档双向**：只有 `undecidable` ⇒ 放行；有 `violated` ⇒ 拦下）：

```
  block + 只有 undecidable：phase=record outcome=pass kind=verified
    事件：passed=True violated=[] undecidable=['P2', 'P5']
  PASS  ★ 只有 undecidable、没有 violated ⇒ **放行**（不被否决）
  PASS  ★ 事件如实分档：violated 为空、undecidable 非空、passed=True
  block + 有 violated：phase=failed outcome=fail kind=decomposition-violation
    事件：violated=['P3']
  PASS  ★ 有 violated ⇒ **拦下**（双向，不是一律放行）
  PASS  拦下理由写明违反了 P3 + 逐条证据
```

`[V1]–[V5]` 合计：**通过 32/32**。

> **反空洞**：`[V5]` 走的是**生产构造路径**（`CodingCycle.run`），不是直接调
> `review_decomposition`；"有 `violated` ⇒ 拦下"证明分档**不是把否决权关掉**，
> 只是把"判不了"从"不合格"里分出来。

### 4.4 D43 · 假换冒烟（配置层 + 路径层 + 反空洞）

```powershell
& "D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe" tests\unit\test_model_swap.py
```

```
  ORCH   : default / qwen2.5:7b-fake-swap @ http://fake.local/v1
  WORKER : default / qwen2.5:7b-fake-swap @ http://fake.local/v1
  worker: ok=True requests=2
  实测异常: BadRequestError: Error code: 400 - The `reasoning_content` ... must be passed back ...
  PASS  ★ 编排器档位读到假换后的模型名
  PASS  ★ 子模型未单独配置 ⇒ 按角色表继承编排器（同一个假换档位）
  PASS  ★ 假换路径走通（没有因为换名字而报错）
  PASS  ★ 每一次请求都用了假换后的模型名（配置真的进了请求体）
  PASS  ★ 假换路径真的执行到了模型调用（不回灌就 400，判据不是空转）
```

合计：**通过 8/8**。`resolve_profiles()` 就是 `GET /profile` 用的那个函数（`main.py:596`）。

### 4.5 其他门禁

| # | 主张 | 验证命令 | 结果 |
|---|---|---|---|
| 1 | 全量单测通过 | `python tests\run_unit.py` | **49/49** |
| 2 | 文档一致性通过 | `python tests\unit\test_doc_consistency.py` | **35/35** |
| 3 | 文档不变量通过 | `python tests\unit\test_doc_invariants.py` | **35/35** |
| 4 | 文档审查通过 | `python tests\unit\test_doc_review.py` | **18/18** |
| 5 | 契约符合性通过 | `python tests\unit\test_contract_conformance.py` | **44/44** |
| 6 | 前端契约通过 | `python tests\unit\test_frontend_contract.py` | **25/25** |
| 7 | 套件卫生通过 | `python tests\unit\test_suite_hygiene.py` | **4/4** |

**未验证的部分**（诚实列出）：

- **没有用真实推理模型端点跑通一道题**（统筹方验收 ② 的后半）。本侧离线环境没有可用的
  `deepseek-flash` 端点与密钥；本轮用**假端点按官方规则验收**代替（§4.1 的会红判据）。
  真实端点那一跑需要统筹方在 :8000 或 :8100 上做，且会写 `workspace/`。
- **没有改 `.interface_contract/`**（只读），也没有跑统筹方的门禁脚本（不触碰对侧仓库 / 集成工作区）。
- **没有改 P3 的并列词启发式**：P20 只要求分档 + 退默认，没有要求修 P3 的假阳性来源。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 仍 18 种 |
| 事件 payload 键 | **无** | `decompose_review` 的键未增（`violated`/`undecidable`/`passed` 本就有） |
| 上游 `PHASE_ORDER` 阶段 | **无** | 仍 `plan/write/check/verify/record` |
| `CycleReport` / `Snapshot` / `Event` 字段 | **加性**：`CycleReport` 加 `model_usage` | 同步进 `FROZEN_REPORT_KEYS`（只增不减）；`Snapshot` / `Event` 未动 |
| `TOOLS_MAP` 条目结构 | **无** | 仍 18 个工具 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 仍 `1.1` / `1.0` / `1.0` |
| 端点路径 | **无** | 未动 |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 只读未动 |

**结论**：本次对接口契约**零破坏**，只有一处**加性**字段（`CycleReport.model_usage`）。
前端**不需要跟改**。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不要**。`model_usage` 是加性字段；前端认不出时按它的既有
  降级显示处理，不会报错。`decompose_review.mode` 的取值只会从 `block` 变回 `warn`
  （该字段本就有，语义已在契约里写明）。
- **有没有可能"问题被平移到对侧"**？**没有**。P19 是**本侧与被测模型之间**的协议适配，
  P20 是本侧内部的门禁强度；两者都不依赖对端上报。
- **前端会静默少显示什么吗**？不会。`passed`/`violated`/`undecidable`/`principles`/
  `summary` 一个没少，只是 `DECOMPOSE_GATE_DEFAULT` 的取值变化；`model_usage` 是新增可读项。
- **需要统筹方裁决的一处**（P19 方向）：见顶部横幅 —— 若改为"一律剥掉"，
  **真实推理端点会继续 400**；本侧认为应按官方协议"带 `tools` 回灌"。

---

## 7. 不做的部分及理由（对应 C7）

- **不按工单字面"一律剥掉" `reasoning_content`**：与实测错误原文（`must be passed back`）
  及 DeepSeek 官方文档相反；按字面做会让 400 继续。已实现协议正确行为 + `never` 开关，
  **把裁决权交回统筹方**（`docs/CHANGELOG.md` §44.1、本文 §2.1）。
- **不做真实推理模型实跑**：需要端点/密钥，且会写 `workspace/`；判据已能离线机判（§4.1）。
- **不动 `P16`（多语言）**：`DISPATCH.md` 明写"用户裁决随后再上"。
- **不动 `P12`（子模型细节读取）**：等 P11 地图可信后再上（工作单原话）。
- **不重做 P14/P15/P13/P11/P17/P18**：前五项在前几轮交付，P18 在上一轮交付；
  P20 是对 P18 的**修正**（退默认 + 分档），不是重做。
- **不改 `core/decompose_review.py` 的八条原则**：原则本体是契约载荷
  （`core/contract.py::DECOMPOSE_PRINCIPLES`），执行方只读；本次只改"默认用不用否决权"
  与"判不了算不算不合格"。
- **不修 P3 的假阳性来源**：P20 未要求；若要把默认升回 `block`，那才是前置条件（已记 C11）。
- **不手工重排 `VERSIONS.md` 历史条目**：由 `tests/backup.py` 追加。

---

## 8. 回退点（对应 C8）

- **回退命令**：`git reset --hard <v1.30 备份点>`（本条目所在提交，提交信息以 `v1.30:` 开头；
  定位：`git log --oneline --grep "^v1.30:"`）。
- **回退会丢什么**：`reasoning_content` 的协议回灌、`model_usage` 报告字段、P20 的默认值
  与分档、两个新测试与本文档。
- **更细粒度的回退**（不用回退整个提交）：
  - P19 退回工单字面行为：`AGENT_REASONING_REPLAY=never`（环境变量，一处，无需改码）；
  - P20 灰度：`DECOMPOSE_GATE=warn|off` 或直接把 `DECOMPOSE_GATE_DEFAULT` 改回 `"block"`；
  - 只想要报告用量：`model_usage` 加性，去掉不影响其它任何键。

---

## 9. 自检结论

> **★ 需要统筹方裁决一条**：工单 `P19` 验收 ①（后续请求体里**没有** `reasoning_content`）
> 与实测错误原文（`must be passed back`）**互相矛盾**。本侧选择"协议正确"（带 `tools` 回灌），
> 并证明按字面剥掉会复现 400（§4.1 `[2]`）。**请裁决**：维持协议正确，还是改默认
> `AGENT_REASONING_REPLAY=never`（代价：真实推理端点继续 400）。

- **C1 问题陈述可复现**：满足。§2.1 贴官方 400 原文 + `文件:行`；§2.2 贴 B1-A 否决原文；
  §2.3 贴默认值机械输出；§2.4 引 D43 原话。
- **C2 每条主张带可复现验证命令**：满足。§4.1–§4.5 每条都有完整命令。
- **C3 命令实测输出支持该主张**：满足。§4 输出均为本轮实跑回显（含会红对照）。
- **C4 改动清单与实际一致**：满足。§3 先贴 `git status --short` + `git diff --stat`；
  并显式点出机械输出**不含**未跟踪的评估文档与两个新测试（以备份点为准）。
- **C5 对接口契约的影响已声明**：满足。§5 逐项写"无/加性"，并点明 `model_usage` 进冻结面。
- **C6 对另一侧的影响已评估**：满足。§6 结论是"不需要跟改、不平移、不静默少显示"。
- **C7 未把接口级问题当内部问题处理**：满足。§7 明确划出未做范围（P16/P12、真实端点、P3 启发式），
  且把 P19 的**方向性分歧**显式上报而不是自行按字面实现。
- **C8 回退点明确**：满足。§8 给出 `git reset --hard` 的定位命令、回退会丢什么，以及两条
  更细粒度的回退（环境变量级）。
- **契约目录只读**：满足。`.interface_contract/` 未被写入（见 §3 机械输出）。
- **对侧仓库 / 集成工作区未写入**：满足。本轮所有写操作都在
  `D:\PythonProject\SimpleAgent2_Cycle` 内；只**只读**查看了 `SimpleAgent2_Integration`
  的错误原文与工作单生成脚本（未写入任何文件）。

**希望统筹重点验证哪一条**：
**§4.1 的 `[1]`/`[2]` 对照**（回灌 ⇒ 走通；不灌 ⇒ 复现官方 400）——
它同时是"P19 真修好了"的证据，也是"工单方向写反了"的证据。请对照
`D:\PythonProject\SimpleAgent2_Integration\04-tests\capability\records.jsonl` 里
T3/T7/V3 三条的 `error` 字段逐字复核。
