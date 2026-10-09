# 变更评估文档 · `MODEL-TIERS`

- **变更编号**：`MODEL-TIERS`（工作单 **P22-A**；`DISPATCH.md` ⓪ 点名的「只做 A（解耦）」）
- **提出方**：用户（2026-10-03 提议「类插件结构 / 可启用模式」）+ 统筹（`WORK-ORDER.md`【P22】A）
- **执行侧**：backend
- **日期**：2026-10-06
- **契约版本**：`1.0.34`（`ROUND.json` 随载荷声明；本轮**未改契约**）
- **本轮 round_id**：`R-5f49cfa62f` —— **本轮完成 `R-5f49cfa62f`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-5f49cfa62f` 开工，
> 与仓库里上一轮记录的 `R-d11562e8d6`（`docs/EVALUATION-MEMORY-SCORING.md`）**不同** ⇒ 有新指令。
> §2.1 用**可复现的哈希手术**证明：新增内容**只有**【P22】一节（`DISPATCH.md` 与
> `WORK-ORDER.md` 各一处），删掉它即可逐位复现上一轮的两个哈希 ⇒ 本轮 = **P22-A**，
> **不跳级做 B**（`DISPATCH.md` 逐字「B（思考策略）本轮不动」）。

---

## 1. 变更意图

### 1.1 本轮新增的载荷原文（逐字）

来自 `DISPATCH.md` ⓪：

> ### ⓪【P22】**模型档位 + 可启用模式（类插件结构）** —— 用户提议
>
> **只做 A（解耦）**：把模型差异收进档位 —— 是否推理模型 · 回灌策略 ·
> **思考 token 的预算语义** · 思考长度上限 · 是否支持图像 · 上限默认值。
> **验收**：**加一个推理模型 = 加一份档位、代码零改动**；档位缺失时回落到默认
> （**不得静默变成某个极端**）；每个开关都能关，关掉后与基线一致。
>
> **B（思考策略）本轮不动** —— 它改的是**被测对象的行为**，带四条准入条件。
> **注意与 ① 的分工**：P19/P20 是"把这次的坑填上"，**P22-A 是"以后不再有这类坑"**。

来自 `WORK-ORDER.md`【P22】A：

> | 字段 | 为什么需要 | 实测来源 |
> |---|---|---|
> | **是否推理模型** | 决定走哪条协议路径 | `deepseek-flash` 返回 `reasoning_content` |
> | **回灌策略** | 带 `tools` 必须回灌，否则 400 | P19 的完整错误原文 |
> | **思考 token 的预算语义** | 思考**计入** `max_tokens` ⇒ 预算语义与普通模型不同 | 冒烟测试 `max_tokens=16` 被 `reasoning_tokens:16` 吃光、正文为空 |
> | **思考长度上限** | 可启用的约束 | B2 的前置 |
> | **是否支持图像输入** | 决定 VISION 角色能不能用它 | `/models` 返回 `input_modalities` |
> | **上下文/上限默认值** | 现在能配，但默认来自通用档位 | 1M 上下文需手工 pin |
>
> **验收（机械、双向）**：
> 1. **加一个推理模型**：只加档位、**代码零改动** ⇒ 跑通一道题（不再是 400）；
> 2. **不加档位**时行为**逐字节不变**（档位缺失 ⇒ 回落默认，不得静默变成某个极端）；
> 3. **每个开关都能关**，关掉后与基线一致；
> 4. 新增一份**会红**的测试：档位声明的"必回灌"与实现不符 ⇒ 红。

### 1.2 本轮范围的判定（为什么只做 A）

| 依据 | 原文 | 结论 |
|---|---|---|
| `DISPATCH.md` ⓪ | 「**只做 A（解耦）**」；「**B（思考策略）本轮不动**」 | 只落 A 的六个字段 |
| `WORK-ORDER.md` P22A 验收 1–4 | 加档位即跑通 / 缺失回落不极端 / 开关能关 / 声明-实现会红 | 四条逐条做成机械判据 |
| `WORK-ORDER.md` B1/B2/B3 | B1 预算换算、B2 思考模板、B3 拆解优化 | **本轮不做**（B3 更有前置未满足） |
| `ROLE-BRIEF.md` §0.4 | 「不许改环境」 | 不装任何依赖；不动 `pip` |

⇒ 本轮 = **把模型差异收进档位（数据）**，协议路径统一在适配层按档位裁决。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 本轮新内容是什么 —— 用哈希手术机判（不是猜、不是自述）

`ROUND.json` 声明 `dispatch_sha256 = 0893f4fd33de8b08`、
`work_order_sha256 = b2ad0b7dd48dec95`；上一轮评估文档记录的是
`c2fe1af135a193bf` / `eae6e312c0b12851`。把当前两份文件里的【P22】整节**删掉**，
剩余文本的 sha256 应当逐位等于上一轮的值：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe D:\PythonProject\SimpleAgent2_Cycle\.tmp\find_prev_r5.py
```

实际输出（原始回显）：

```
WO  bytes 56873 sha b2ad0b7dd48dec95 want b2ad0b7dd48dec95
DI  bytes 14148 sha 0893f4fd33de8b08 want 0893f4fd33de8b08

--- WORK-ORDER surgery (remove P22 block) ---
  P22 -> next H1: start@51592 end@55839
    remove 4247 bytes -> 52626 sha=eae6e312c0b12851
    MATCH prev_wo: True
  P22 -> sep+H1: start@51592 end@55834
    remove 4242 bytes -> 52631 sha=97c8d6bc35e17e24
    MATCH prev_wo: False

--- DISPATCH surgery (remove P22 block) ---
  P22 -> P21: start@613 end@1746
    remove 1133 bytes -> 13015 sha=c2fe1af135a193bf
    MATCH prev_di: True
```

⇒ **只有**删掉【P22】整节才复现上一轮的哈希（另一种切法 `MATCH=False`）
⇒ 本轮新增内容**就是 P22**，且 DISPATCH 逐字限定为 **A**。

### 2.2 缺口（改动前的机械取证）

改动前，模型差异**散在代码里**、且与"声明"分离：

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle show f1c7a23:core/model_profile.py | Select-String -Pattern 'reasoning|is_reasoning'
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle show f1c7a23:core/llm.py | Select-String -Pattern 'def request_messages|def reasoning_replay_mode|def effective_replay'
```

实际输出：

```
（第一条：空 —— 改动前 ModelProfile 里没有 reasoning 相关字段）
（第二条：只有 def reasoning_replay_mode / def request_messages；
  没有 effective_replay_policy、没有 replay_contract_problems）
```

| P22-A 的字段 | 改动前的事实 | 缺口 |
|---|---|---|
| 是否推理模型 | `ModelProfile` 里**没有**该字段 | **不可声明** |
| 回灌策略 | 只由**进程级** `AGENT_REASONING_REPLAY` 决定 | **不能按模型给** |
| 思考 token 的预算语义 | 无字段（只在 `aggregate_usage` 的 note 里提一句） | **不可声明** |
| 思考长度上限 | 无字段、无实现 | **不可启用** |
| 是否支持图像 | 已有 `capabilities.supports_image_input`（本次只并入档位视图，不重复状态） | 已有 |
| 上限默认值 | `from_env` 一律按 `CONTEXT_WINDOW` 重推 ⇒ 档位声明的 `limits` 被丢弃 | **丢了** |
| 加模型的方式 | `_guess_profile_name` 里**硬编码 `"qwen"`** | 加模型 = 改代码 |

### 2.3 为什么这是问题

「模型即插即用」的前提是**加模型不动代码**。改动前：换一个推理模型要碰
`llm.py`（改回灌策略的来源）；加一个模型名要碰 `model_profile.py`（改猜测函数）；
档位里写了 `max_tokens=8192` 也会被 `from_env` 静默丢掉 ——
这正是本项目反复在治的形状：**声明与实现分家**。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle -c core.quotepath=false status --short
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle -c core.quotepath=false diff --stat
```

```
=== git status --short ===
 M CYCLE.md
 M README.md
 M core/__init__.py
 M core/coding_cycle.py
 M core/config.py
 M core/llm.py
 M core/model_profile.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
 M main.py
?? tests/diagnostics/probe_model_tiers.py
?? tests/unit/test_model_tiers.py

=== git diff --stat ===
 CYCLE.md              |   2 +-
 README.md             |   3 +-
 core/__init__.py      |   6 ++
 core/coding_cycle.py  |  10 ++-
 core/config.py        |   8 ++
 core/llm.py           | 159 ++++++++++++++++++++++++++++++++++++++-----
 core/model_profile.py | 238 ++++++++++++++++++++++++++++++++++++++++++++++++--
 docs/ARCHITECTURE.md  |   7 +-
 docs/CHANGELOG.md     |  55 ++++++++++++
 docs/MODULES.md       | 115 ++++++++++++++++++++++--
 docs/OPERATIONS.md    |  64 +++++++++++++-
 main.py               |  17 ++++
 12 files changed, 642 insertions(+), 42 deletions(-)
```

> `git diff --stat` **不含未跟踪的新文件**（两个新测试）与
> `docs/EVALUATION-MODEL-TIERS.md`、`docs/VERSIONS.md` 的 v1.33 条目。
> 它们的权威依据是上面的 `??` 行与 §8 的备份点。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/model_profile.py` | `ModelReasoning` 新类 | P22-A 的四个推理字段 + `problems()` + `modes()` |
| 2 | 同上 | `ModelProfile.reasoning/match/fallback/fallback_to` | 档位 = 数据；回落可见 |
| 3 | 同上 | `effective_reasoning_replay()` / `tier()` | 生效策略与全字段可机读 |
| 4 | 同上 | `from_env` | 推理字段的逐项环境覆盖；未给窗口时用档位 `limits`；未登记档位可见回落 |
| 5 | 同上 | `_guess_profile_name` / `_BUILTIN_PROFILES` / `register_profile` | 选档数据驱动（`match`）；内置新增 `reasoner` |
| 6 | `core/llm.py` | `effective_replay_policy` / `request_messages(profile=)` | 判定点收进档位，`profile=None` 时与 P19 逐字节一致 |
| 7 | 同上 | `replay_contract_problems()` | ★ 声明 vs 实现（会红） |
| 8 | 同上 | `aggregate_usage(profile=)` / `LLMClient.chat` | 读数带档位归因；请求走档位 |
| 9 | `core/coding_cycle.py` | `_attach_model_usage` | 把生效档位带进 `model_usage` |
| 10 | `core/config.py` / `core/__init__.py` | 导出 `ModelReasoning` / `profile_names` / `profile_source` | 对外入口 |
| 11 | `main.py` | `/profile` 的 `model_tiers` + `models[*].tier` + `replay_contract_problems` | 档位面可见、可机判 |
| 12 | `tests/unit/test_model_tiers.py` | 新文件 | 四条验收的判据（33 项） |
| 13 | `tests/diagnostics/probe_model_tiers.py` | 新文件 | 六段机械取证（本文 §4 的原始回显都来自它） |
| 14 | `docs/CHANGELOG.md` | 新增 §47 | 过程记录 |
| 15 | `docs/MODULES.md` | §1/§2 更新 + 新增 §36 | 档位与开关参考 |
| 16 | `docs/OPERATIONS.md` | §2.3 / §2.5 / §2.6 / §3 / §4.24 | 环境变量、注册示例、读法、排障 |
| 17 | `docs/ARCHITECTURE.md` / `CYCLE.md` / `README.md` | 版本戳 §46→§47；README 登记本文件 | 文档一致性门禁要求 |
| 18 | `docs/VERSIONS.md` | 追加 v1.33 条目 | 版本记录 |

**本轮刻意没碰的**：`tools/`、`core/contract.py`、`core/cycle.py`、`core/worker.py`、
`core/pipeline.py`、`core/context_store/*`、`.interface_contract/`、对侧仓库、集成工作区。

**若两者不一致**：以 §3 的机械输出为准；第 12/13 项与 `docs/EVALUATION-MODEL-TIERS.md`
在快照时尚未被跟踪（`??` 行即依据）。

---

## 4. 主张与验证命令（对应 C2、C3）

> 以下回显全部来自 `tests/diagnostics/probe_model_tiers.py`（六段）与
> `tests/unit/test_model_tiers.py`。**先贴机械输出，再给结论。**

### 4.1 验收 1：加一个推理模型 = 加一份档位、代码零改动

**主张**：运行时 `register_profile()` 注册一份带 `match` 的推理档位即可，
`from_env` 自动选中，并且**用假 DeepSeek 端点**（缺回灌就抛官方 400）真的跑通一道题。

**命令**：

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe tests\diagnostics\probe_model_tiers.py
```

**实际输出（节选，原文）**：

```
==========================================================================
[2] ★ 加一个推理模型：运行时注册一份档位（不改代码）⇒ 跑通一道题
==========================================================================
{
  "profile": "acme-reasoner",
  "model": "acme-r1",
  ...
  "is_reasoning_model": true,
  "reasoning_replay": "auto",
  "reasoning_replay_declared": "auto",
  "reasoning_replay_env": null,
  "thinking_counts_in_max_tokens": true,
  "max_thinking_chars": 0,
  "supports_image_input": false,
  ...
  "context_window": 65536,
  "limits": {
    "max_tokens": 4096,
    ...
  },
  "modes": {
    "reasoning_model": true,
    "reasoning_replay": true,
    "thinking_cap": false
  },
  "problems": []
}
  _guess_profile_name('acme-r1') = acme-reasoner
  选档函数里有具体模型名吗: qwen=False deepseek=False acme=False
  [W:t1:1] tool_calls=1 content_len=0
  [W:t1:2] tool_calls=0 content_len=2
  worker: ok=True requests=2 回灌='先看看系统信息'
```

**结论**：`ok=True` + 第二次请求带回 `reasoning_content` ⇒ 只加档位就跑通；
选档函数源码里**没有任何具体模型名**（`qwen=False deepseek=False acme=False`）
⇒ 这是「代码零改动」的机械证据，不是自述。

### 4.2 验收 2：档位缺失 ⇒ 回落默认、**不是极端**

**主张**：未登记的 `{ROLE}_PROFILE` 与未知模型名都回落到 `default` + `auto`，
且回落**可见**（`fallback` / `fallback_to`）。

**实际输出（单元测 [3]，原文）**：

```
[3] 档位缺失：回落 `default` + `fallback=True`，策略是 auto（不是极端）
  fallback=True profile=no-such-tier replay=auto (declared=auto)
  未知模型名 -> profile=default replay=auto
  PASS  ★ 未登记档位 ⇒ fallback=True 且写明回落到谁（回落**可见**）
  PASS  ★ 回落策略 == auto（既不是 never 也不是 always）
  PASS  ★ 未知模型名也回落 default/auto（不静默变成极端）
```

（stderr 同时打印 `[配置] ACME_PROFILE='no-such-tier' 未登记，回落 'default' 档位
（回灌策略取 default，不是 never/always）`——回落既不静默，也不取极端值。）

### 4.3 验收 3：每个开关都能关，关掉后与基线一致（**同哈希**）

**主张**：把同一个模型/预算固定，只变档位 ⇒ 关掉开关后请求体 sha256
**回到基线**；打开必须**改变**哈希（证明开关不是死的）。

**实际输出（探针 [3]，原文）**：

```
[3] ★ 关掉开关 == 基线；打开 ⇒ 哈希必变（同一个模型/预算，只变档位）
  基线（全关：False / auto / cap=0）        sha256=c1b86b4b0565c787 kept=True == 基线
  推理模式=True                          sha256=c1b86b4b0565c787 kept=True == 基线
  推理模式=False（关）                      sha256=c1b86b4b0565c787 kept=True == 基线
  覆盖 replay=never（非推理档位）             sha256=5264bf0a28c4d401 kept=False != 基线
  覆盖 replay=always（非推理档位）            sha256=c1b86b4b0565c787 kept=True == 基线
  thinking_cap=2（开）                  sha256=46a1fd715bd696f2 kept=True != 基线
  thinking_cap=0（关）                  sha256=c1b86b4b0565c787 kept=True == 基线
  AGENT_REASONING_REPLAY=never       sha256=5264bf0a28c4d401 (== replay=never 的哈希: True)
```

**结论**：
* 「推理模式」开/关、`cap=0`、取消进程级覆盖 ⇒ 全部回到**同一个**基线哈希
  `c1b86b4b0565c787`（关掉 = 基线，不是"约等于"）；
* `replay=never`、`cap=2`、`AGENT_REASONING_REPLAY=never` ⇒ 哈希必变；
* `replay=always` 在**带 tools** 时与 `auto` 同哈希是**协议正确**的表现
  （两者都回灌）；单元测另有一条**不带 tools** 的判据证明它有效
  （`PASS ★ 覆盖值 replay=always 有效：不带 tools 时也保留（与 auto 不同）`）。

> **口径说明（不藏）**：「基线」= 改动前的出厂行为：非推理档位、策略 `auto`、
> 无思考上限。`replay=never`/`always` 是**覆盖值**（P19 之前/官方文档的两种极端），
> 它们**不等于基线**，正因如此才能被上面这张表观测到。

### 4.4 验收 4：档位声明的"必回灌"与实现不符 ⇒ **红**

**主张**：`replay_contract_problems()` 把"档位声明"与"实现实际做的"对照；
真实实现下为空，把实现换成"一律剥掉"的坏实现 ⇒ **立刻非空**，换回 ⇒ 又为空。

**实际输出（探针 [4]，原文）**：

```
[4] ★ 声明 vs 实现：真实实现 == 空；坏实现 ⇒ 立刻非空
  真实实现: []
  坏实现（一律剥掉）: ["档位声明是推理模型（replay='auto'），但带 tools 的请求没有回灌 reasoning_content ⇒ 实测会 400（P19）", "声明 replay='auto' 时带 tools 应 kept=True，实现 kept=False"]
  恢复后: []
```

并且这条判据**不只在测试里活着**：`/profile` 直接转发它（`models[*].replay_contract_problems`），
`ModelProfile.validate()` 也把自相矛盾的档位（推理模型 + `never`）并入启动自检：

```
  冲突档位的 validate(): ["[ORCH] reasoning.is_reasoning_model=True 与 reasoning.replay='never' 冲突：带 tools 的后续请求必须回灌 reasoning_content，否则 API 400"]
```

### 4.5 反空洞：一键关回灌 ⇒ 同一个假端点必须复现官方 400

```
[6] 反空洞：AGENT_REASONING_REPLAY=never ⇒ 同一个假端点复现 400
  实测异常: BadRequestError: Error code: 400 - The `reasoning_content` in the thinking mode must be passed back to the API.
  PASS  关掉回灌 ⇒ 假端点抛官方 400 原文
```

⇒ 4.1 的"跑通"是**真的走了回灌那条路**，不是假端点没判。

### 4.6 档位字段面与 `/profile`

```
[1] 档位面：registry + 每份档位的 P22-A 字段
  profile_names() = ['default', 'qwen', 'reasoner']
  [default] reasoning=False replay=auto thinking_in_maxtok=True cap=0 image=False ctx=8192 max_tokens=4096
  [qwen] reasoning=False replay=auto thinking_in_maxtok=True cap=0 image=False ctx=8192 max_tokens=4096
  [reasoner] reasoning=True replay=auto thinking_in_maxtok=True cap=0 image=False ctx=65536 max_tokens=8192

[5] /profile：model_tiers + models[*].tier + replay_contract_problems
  model_tiers = {"registry": ["default", "qwen", "reasoner", "acme-reasoner"], "sources": {"default": "builtin", "qwen": "builtin", "reasoner": "builtin", "acme-reasoner": "registered"}, "env_override": null, "fallback_policy": "档位缺失 ⇒ default 档（replay=auto），并置 tier.fallback=true 使其可见"}
  models[ORCH].tier = profile=qwen reasoning=False replay=auto fallback=False modes={'reasoning_model': False, 'reasoning_replay': True, 'thinking_cap': False}
  models[ORCH].replay_contract_problems = []
```

### 4.7 各门禁汇总（命令 + 结果）

| # | 命令 | 期望 | 实测 |
|---|---|---|---|
| 1 | `python tests/unit/test_model_tiers.py` | 全 PASS | **33/33**，exit 0 |
| 2 | `python tests/diagnostics/probe_model_tiers.py` | 全 PASS | **31/31**，exit 0 |
| 3 | `python tests/run_unit.py` | 全 PASS | **52/52** |
| 4 | `python tests/unit/test_doc_consistency.py` | 全 PASS | **35/35** |
| 5 | `python tests/unit/test_doc_invariants.py` | 全 PASS | **35/35** |
| 6 | `python tests/unit/test_doc_review.py` | 全 PASS | **18/18** |
| 7 | `python tests/unit/test_contract_conformance.py` | 全 PASS | **44/44** |
| 8 | `python tests/unit/test_frontend_contract.py` | 全 PASS | **25/25** |
| 9 | `python tests/unit/test_suite_hygiene.py` | 全 PASS | **4/4** |

**未验证的部分**（诚实列出你没验的，比假装验过有价值）：

- **没有真实推理端点实跑**（无端点/密钥，且真跑会写 `workspace/`）。验收 1 的
  "跑通一道题"是在**假端点**上做的，该端点**按 DeepSeek 官方规则验收**请求
  （带 `tools` 的 assistant 消息缺 `reasoning_content` 就抛官方 400 原文）——
  方向与原文都对齐，但**没有对真实 `api.deepseek.com` 发过一次请求**。
- **思考长度上限（`max_thinking_chars`）只做了"截断后请求体变了"的机械判据**，
  没有验证真实推理端点是否接受被截断的 `reasoning_content`。默认 `0`（关闭），
  即**出厂行为不含该约束**；B2 启用前应先在真实端点确认。
- **预算换算规则（B1）没有实现**：本轮只把"思考是否计入 `max_tokens`"作为
  **档位声明**（`tier.thinking_counts_in_max_tokens`）与读数归因
  （`model_usage.thinking_counts_in_max_tokens`）落地；换算公式按工单属于 B1。
- **`/models` 的 `input_modalities` 未做在线探测**：`supports_image_input`
  仍由配置声明（本轮只是把它并入档位视图，未新增探测）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | 否 | 仍 18 种 |
| 事件 payload 键 | 否 | 未新增/改名 |
| 上游 `PHASE_ORDER` 阶段 | 否 | 未动 |
| `CycleReport` / `Snapshot` / `Event` 字段 | **加性** | `model_usage` 新增 `policy_declared` / `model` / `thinking_counts_in_max_tokens`；`total` / `by_role` / `policy` / `note` 未动（`model_usage` 本就在 `FROZEN_REPORT_KEYS` 里，本次只加键） |
| `TOOLS_MAP` 条目结构 | 否 | 仍 18 个工具，未动 schema |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | 否 | 未升 |
| 端点路径 | 否 | `/profile` 的**响应**加键（`model_tiers`、`models[*].tier`、`models[*].replay_contract_problems`），路径未动 |
| `.interface_contract/` 覆盖的规则与词表 | 否 | 只读未动 |

**属 additive（新增，安全）**。前端对认不出的键是降级显示，不会报错。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不要**。本轮全部是后端内部适配层的档位化；
  前端读 `/profile` 的既有键（`models[*].profile` / `model` / `limits` 等）**语义未变**。
- **有没有可能"问题被平移到对侧"**？没有。这与跨侧归属无关：档位只影响
  **上游自己怎么跟模型说话**，不改变任何事件/payload 的语义。
- **前端会静默少显示什么吗**？不会少显示；只是多了三个可读键。若前端将来想让
  "换档位"在界面上可见，可直接读 `model_tiers` 与 `models[*].tier`（本轮不要求）。

---

## 7. 不做的部分及理由（对应 C7）

- **B1 / B2 / B3（思考策略）不做**：`DISPATCH.md` 逐字「B（思考策略）本轮不动」，
  且它改的是**被测对象的行为**，带四条准入条件（外锚 / 可关且逐字节回退 /
  A/B 可比 / 不许改判据）。本轮只把 B1 要用的**声明位**（预算语义）放进档位。
- **不实现真实端点探测**：无端点/密钥；按纪律不 `pip install`、不写环境。
- **不改 `core/worker.py`**：回灌字段的组装本就在那里（P19），本轮把**裁决**留在
  `core/llm.py::request_messages` 一处，避免"机制在多处各写一遍"。
- **不改工具契约 / 事件 / 阶段**：与 P22-A 无关。
- **不给所有内置档位加满字段**：`default` / `qwen` 保持非推理；
  只新增 `reasoner` 一份作为"加档位即接入推理模型"的现成样例。
- **P16 多语言、P12 子模型**：DISPATCH 未指派且明写别动。

---

## 8. 回退点（对应 C8）

- **回退点（改动前）**：`f1c7a23`
- **回退命令**：

  ```powershell
  cd D:\PythonProject\SimpleAgent2_Cycle
  git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle reset --hard f1c7a23
  ```

- **回退会丢什么**：`P22-A` 的档位化（`ModelReasoning` / `tier()` /
  `_guess_profile_name` 数据驱动 / `reasoner` 内置档位 / `replay_contract_problems` /
  `/profile.model_tiers`）与两个新测试文件；**不丢** P17–P21 的任何成果
  （它们都在 `f1c7a23` 及更早的提交里）。
- 本轮的提交点记在 `docs/VERSIONS.md` 的 v1.33 条目（含 `git show --stat` 与回退命令）。
- **本轮提交点**：`34a4deb`（提交信息以 `v1.33:` 开头；定位命令
  `git log --oneline --grep "^v1.33:"`）。

---

## 9. 自检结论

- **C1 问题陈述可复现**：**满足**。§2.1 的哈希手术脚本与原始回显可直接复跑；
  §2.2 用 `git show f1c7a23:...` 给出"改动前没有这些字段"的机械输出。
- **C2 每条主张带可复现验证命令**：**满足**。§4.1–§4.6 每条主张都给了命令与回显；
  §4.7 汇总九条门禁。
- **C3 命令实测输出支持主张**：**满足**。所有回显来自本轮的探针/单测，未做二次概括；
  §4.3 的"关掉 = 同哈希"是逐字节 sha256，不是"看起来一样"。
- **C4 改动清单与实际一致**：**满足**。§3 先贴 `git status --short` 与
  `git diff --stat`；未跟踪文件单列（`??` 行）。
- **C5 对接口契约的影响已声明**：**满足**。§5 逐面写"否/加性"，
  明确 `/profile` 加键、`model_usage` 加键、版本轴与事件未动。
- **C6 对另一侧的影响已评估**：**满足**。§6 结论是"不需要改"，并逐条回答
  "会不会平移 / 前端会不会少显示"。
- **C7 未把接口级问题当内部问题处理**：**满足**。§7 明确本轮不碰事件/端点语义，
  不给前端派活；`/profile` 的新键是加性的。
- **C8 回退点明确**：**满足**。§8 给出 `f1c7a23` 与 `reset --hard` 命令，
  并写明会丢什么、不会丢什么。

**我希望统筹重点验证的两条**：

1. **§4.1 的"代码零改动"**：请用你那一侧的假换冒烟（或另造一个模型名）验证
   —— 只要 `register_profile()` 一份带 `match` 的档位就能选到，
   而 `_guess_profile_name` 的源码里确实没有任何模型名。
2. **§4.3 的"关掉 = 同哈希"**：请独立算一遍基线请求体的 sha256，
   确认 `replay=never` 是**唯一**会改变"带 tools 报文"的档位项
   （`reasoning_replay` 语义由此可机判，而不是靠读注释）。
