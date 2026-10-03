# 变更评估文档 · `TRANSPARENCY-BACKEND`

- **变更编号**：`TRANSPARENCY-BACKEND`
- **提出方**：统筹（依据用户 2026-09-27 对一次真实运行的审查）
- **执行侧**：backend
- **日期**：2026-09-27
- **契约版本**：`1.0.24`（按本轮 `DISPATCH` 标注的当前契约版本）

---

## 1. 变更意图

引统筹方原话（`REVIEW-20260927-why-it-passed.md` §0 / `REQUIREMENT-20260927-transparency.md` §0）：

> **这次的"通过"不是流程坏了，也不是模型纯自嗨，而是流程给了模型
> "自己出考卷、考不过就换一张"的权力。**

> 用户对"换弱"选的是 **(2) 留痕 + 必须给理由**，**没有**选"直接禁止降级"。

> **关于 B3**：……**如果你们认为 B3 与用户的选择冲突 → 只做 B2 并说明理由。
> 不要默默跳过，也不要默默做掉。**

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象（真实运行 `run_20260927_125647_5a3297`）

目标「以10*10网格为结构……保证起始点和目标点至少可通，写一个基础的蚁群算法，
**并连续测试验证**，**生成对应报告**」→ `status=passed` / `phase=record`。
而机械事实：

| 目标里的要求 | 实际 | 证据位置 |
|---|---|---|
| 连通性保证 | ❌ 只是随机撒点 | `obstacle_generator.py`（统筹方逐行核过） |
| 蚁群算法 | ⚠️ `ant_colony.py:40` 用了 `np.random.choice` 而全文没有 `import numpy` | lint `F821` |
| **连续测试验证** | ❌ `test_ant_colony.py` **一次没被执行** | `tool_call` 汇总无执行类调用 |
| **生成报告** | ❌ 工作区里没有报告文件 | 工作区实际内容 |
| 判据的演化 | **(b) 真跑过、真失败 → (c) 换成 `assert generate_obstacles` → 通过** | 前端 `verify_probe` seq 35 / seq 56 |

同一时刻**上游自己发的**事件里，`orchestrator_decision` 只有 `{"status": "continue"}`
（无 `reasoning`），且"这次换了判据、而上一条是失败的"**读不出来**。

### 2.2 为什么这是问题

判据是「目标是否达成」的**唯一机器判据**。它的变更必须和别的关键事实一样可审计 ——
否则"通过"这个结论可以被**模型自己**在失败后改写，而外部看不出。
这正是统筹方那句"自己出考卷、考不过就换一张"。

### 2.3 复现命令（我这一侧，**不调模型**，确定性）

```powershell
python tests/unit/test_transparency.py     # A1 / B1 / B2 / B3（24 项）
python tests/unit/test_self_report.py      # C1 / C2（19 项，含"撒谎必被抓"）
```

两条都**用真实的生产构造路径**（`CodingCycle.run` → `_setup_orchestrator`
→ 真 `CheckPipeline` / 真 `check_and_run` 子进程），只把 LLM 换成本地脚本。

### 2.4 复现命令（**真实模型**，用统筹方的固定样例）

```powershell
python tests/diagnostics/repro_user_run_20260927.py
```

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M core/coding_cycle.py
 M core/contract.py
 M core/cycle.py
 M core/memory.py
 M core/orchestrator.py
 M core/prompts.py
 M docs/FRONTEND_CONTRACT.md
 M tests/README.md
 M tests/unit/test_verify_vacuous.py
?? core/self_report.py
?? tests/diagnostics/repro_user_run_20260927.py
?? tests/unit/test_self_report.py
?? tests/unit/test_transparency.py

$ git -c safe.directory=<repo> diff --stat
 core/coding_cycle.py              | 170 ++++++++++++++++++++++++++++++++
 core/contract.py                  |  33 ++++++-
 core/cycle.py                     |   8 ++
 core/memory.py                    |  67 +++++++++++++
 core/orchestrator.py              | 197 ++++++++++++++++++++++++++++++++------
 core/prompts.py                   |  54 +++++++++
 docs/FRONTEND_CONTRACT.md         |  13 ++-
 tests/README.md                   |   3 +
 tests/unit/test_verify_vacuous.py |   4 +-
 9 files changed, 514 insertions(+), 35 deletions(-)
```

（外加 4 个新文件：`core/self_report.py`、两个新单测、一个诊断脚本。
备份后 `git show --stat <tag>` 是本节的最终权威输出。）

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/orchestrator.py` | `run()` 决策处 | 每次 `_decide` 后 `memory.log_decision()` —— **A1**（`reasoning` 进事实源） |
| 2 | `core/orchestrator.py` | 采纳分支 | **B2**：`replacing and not why_reason` → 拒绝采纳；**B3** 走 `_model_verify_admissible` |
| 3 | `core/orchestrator.py` | `_called_modules` / `_module_names_for`（新增） | **B3** 的可判定实现（AST `Call` + import 别名解析） |
| 4 | `core/orchestrator.py` | 验证回流执行处 | `memory.log_criterion("executed", ...)` + `last_failed` 记账 —— **B1** 的数据源 |
| 5 | `core/memory.py` | `criterion_log` / `decision_log` / `log_criterion` / `log_decision` | 判据演化与决策依据的**唯一写入点**；`previous_*` 由此**自动补齐** |
| 6 | `core/coding_cycle.py` | `_emit` 段 | 把上述两个 log 逐条发成 `orchestrator_round` / `verify_criterion` 事件 |
| 7 | `core/coding_cycle.py` | `_finish_self_report` / `_machine_facts`（新增） | **C1 + C2**：自述生成、机械事实、交叉核对、事件与报告字段 |
| 8 | `core/self_report.py`（新） | 归一化 + `fact_check` | **C2** 的全部对照逻辑（只做可判定的相等比较） |
| 9 | `core/prompts.py` | `SELF_REPORT_SYSTEM`（新）+ 规则 11 | 让模型**能**满足新下限（必须调用交付物 / 换判据必须给理由 / 自述字段与证据要求） |
| 10 | `core/cycle.py` | `CycleReport.self_report` | 报告字段（**additive**） |
| 11 | `core/contract.py` | 三个新 `EventSpec` + `FROZEN_REPORT_KEYS` | 声明新事件（additive）；词表 13 → **16** |
| 12 | `tests/unit/test_verify_vacuous.py` | 一条用例 | 上一轮那条 `.py` 只检查存在的用例被 B3 收紧为不可采（**这是有意的收紧，见 §7**） |

### 3.3 若两者不一致，差异是什么

一致。**特别说明一处**：`tests/unit/test_verify_vacuous.py` 出现在改动清单里，
但**不是修 bug** —— 是上一轮矩阵里"`assert os.path.exists('add.py')` 可采"这一格
被 B3 有意改成不可采，用例跟着改。我在 §7 与 CHANGELOG §35 都点了出来。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | **A1**：每轮决策的 `reasoning` 能从事件流读到 | `python tests/unit/test_transparency.py` | `reasoning 非空（A1 的验收点）PASS` |
| 2 | **B1**：判据的采纳/拒绝/执行与**前后关系**直接可读 | 同上 | `previous_command` / `previous_passed` 有值 |
| 3 | **B2**：换掉已执行且失败的判据**没给理由** → 不采纳 | 同上（B2-1） | `B 被拒绝` + `本轮不得通过` PASS |
| 4 | **B2**：给了理由 → 允许（正当替换看得见） | 同上（B2-2） | `B 被采纳` + `B 的理由进了事件` PASS |
| 5 | **B3**：`assert generate_obstacles`（实测反例）**不可采** | 同上 | `B3：实测反例：只 assert 名字（恒真）PASS` |
| 6 | **B3**：真的调用 → 可采 | 同上 | `属性调用` / `import 后调用` / `模块调用` PASS |
| 7 | **C1**：自述七字段齐备、进报告与事件 | `python tests/unit/test_self_report.py` | 7 项 PASS |
| 8 | **C2**：模型谎报 → `fact_check` 必须红 | 同上 | `artifact-missing` / `verify-claim-vs-fact` / `check-claim-vs-fact` / 未提及 各 PASS |
| 9 | **C2**：自述**不改判定** | 同上 | `phase 仍由机械事实决定` PASS |
| 10 | **C1**：拿不到自述 → 显式降级（不静默） | 同上 | `ok=false + error` PASS |
| 11 | 真实模型复跑固定样例 | `python tests/diagnostics/repro_user_run_20260927.py` | `通过 6/6` |
| 12 | 全量回归 | `python tests/run_unit.py` | `通过 35/35` |
| 13 | 契约符合性 / 前端契约 / 文档 | 各 `tests/unit/test_*.py` | 44/44 · 25/25 · 35/35 · 31/31 · 18/18 |

### 4.1 实测输出（粘贴原文）

**主张 3（B2-1：不给理由就换 → 不采纳）**：

```
[B2-1] 判据 A 执行失败 → 换成 B 但**不给理由** → 不得静默采纳
  [adopted] passed=None cmd='import mod\nassert mod.f() == 1' reason='断言返回 1'
  [executed] passed=False cmd='import mod\nassert mod.f() == 1'
  [rejected] passed=False cmd='import mod\nassert mod.f() == 2'
             reason='要替换一条**已执行且失败**的判据（上一条：...），但 verify.reason 是空的
                     —— 换判据必须给理由，否则无法区分「修正了判据自身的问题」
                     与「把考卷换成一张必过的」'
  PASS  A 被判据采纳并**真的执行且失败**
  PASS  B 被拒绝（没给理由就不采纳）
  PASS  → 本轮不得通过（不静默采纳）
```

**主张 4 + 2（B2-2 / B1：给了理由 → 采纳，且四样都能读到）**：

```
[B2-2] 同样替换，但**给了理由** → 允许（正当替换要看得见）
  [adopted]  cmd='import mod\nassert mod.f() == 1' reason='断言返回 1'
  [executed] passed=False
  [adopted]  cmd='import mod\nassert mod.f() == 2'
             reason='上一条断言写错了期望值（实现返回 2），修正为 2'
             prev='import mod\nassert mod.f() == 1' prev_passed=False
  [executed] passed=True
  PASS  事件里带上了**前后关系**（previous_command / previous_passed）
  PASS  → 四样都能读到（A 的命令 + A 失败 + B 的命令 + B 的理由）
```

**主张 11（真实模型，统筹方的固定样例）**：

```
$ python tests/diagnostics/repro_user_run_20260927.py
[决策] status=continue reasoning=首先需要设计障碍物生成规则
[verify] 拒绝采纳模型自拟的验收判据：本轮没有任何交付物（…）
[决策] status=continue reasoning=下一步是编写蚁群算法并进行测试
[verify] 拒绝采纳模型自拟的验收判据：自拟的验收命令引用了 ['ant_colony.py']
         却**没有调用**它：只写 `assert 名字`…（B3 生效 —— 这正是那次被采纳的形态）
...
phase=failed attempts=2 用时=287.5s
  manifest: declared=1 passed=False
  check: {'checked': True, 'passed': True, 'status': 'passed'}
  verify: {'passed': False, 'detail': "NameError: name 'random' is not defined",
           'command': "import ant_colony; import obstacle_generator;
                       assert ant_colony.AntColony(obstacle_generator.generate_obstacles(10,10,10,1),
                       10, 1.0, 2.0, 0.5, 0.5, 10).run() == True; print('PASS')",
           'source': 'model'}
  touched_files: ['obstacle_generator.py', 'ant_colony.py', 'test_ant_colony.py']
事件流（本 cycle 共 100 条）：orchestrator_round=20 verify_criterion=31 self_report=1
...
收尾自述（C1）+ 交叉核对（C2）
  ok=True
  done       = ['obstacle_generator.py', 'ant_colony.py', 'test_ant_colony.py']
  not_done   = ['generate_ants 方法']
  why        = ['未实现 generate_ants 方法导致蚁群算法无法运行']
  reflections= ['应更早识别并实现 generate_ants 方法，以确保蚁群算法完整']
  confidence = {'level': 'low', 'basis': '缺少关键方法导致验证失败'}
  requirements = [('设计一个随机障碍物生成规则…', 'done'),
                  ('写一个基础的蚁群算法', 'not_done'),
                  ('连续测试验证', 'unknown')]
  fact_check: 矛盾 0 条 / 未提及 1 条
    [未提及] 要求 3（连续测试验证）：既没写成 done 也没写成 not_done
通过 6/6
```

**这一次和用户那次的关键差别**（同一个目标）：

| | 用户那次（改动前） | 本次重跑（改动后） |
|---|---|---|
| 最终判据 | `assert generate_obstacles`（不调用） | `ant_colony.AntColony(...).run() == True`（**真调用**） |
| 结论 | `phase=record` **passed** | **`phase=failed`**，detail `NameError: name 'random' is not defined` |
| 判据演化 | 事件流里读不出"上一条失败了" | `verify_criterion=31` 条，每条带 `previous_passed` |
| 决策依据 | 事件里只有 `{"status":"continue"}` | `orchestrator_round=20` 条，`reasoning` 全非空 |
| 收尾自述 | **没有** | 有，且 `fact_check` 把"连续测试验证"标成**未提及** |

> 注意最后一行：**报告里的 bug 也从 `np` 变成了 `random`** ——
> 说明"真调用"这条规则确实让判据摸到了真实代码，而不是名字。

**主张 12/13**：

```
$ python tests/run_unit.py                     → 通过 35/35
$ python tests/unit/test_contract_conformance.py → 44/44
$ python tests/unit/test_frontend_contract.py    → 25/25
$ python tests/unit/test_doc_consistency.py      → 35/35
$ python tests/unit/test_doc_invariants.py       → 31/31
$ python tests/unit/test_doc_review.py           → 18/18
```

### 4.2 未验证的部分（诚实列出）

- **A1 的实时性**：上游的 `orchestrator_round` 是**该 attempt 结束时按轮次顺序补发**的
  （事件只能由 `CodingCycle._emit` 发出，而 cycle 拿不到循环中间的时刻）。
  **实时显示仍由前端 bridge 的 `orchestrator_decision` 负责** —— 两者数据同源。
  我没有验证前端把两条一起显示时的观感（那是对侧）。
- **`not_done` 的质量依赖模型**：我只保证"自述被核对、矛盾被抓"，
  **不保证模型一定会把该写的写进 `not_done`**。本次真实运行里它写了
  `generate_ants 方法`，但把"连续测试验证"留成了 `unknown`（被标未提及）。
  **这是模型能力问题，不是这一层的保证范围。**
- **没有跑 8 级基准做前后对比**：B2/B3 是收紧，可能让某些级别从"侥幸通过"变回失败
  —— 那正是预期方向，但我没测通过率的变化（超出本轮范围，且基准属 B3 待排期项）。
- **B3 的误伤面没有穷举**：已知一类（`.py` 交付物只做存在性检查）会在 §7 写明。
  我没有系统扫描"哪些真实目标会因此只能判 failed"。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **有：13 → 16** | 新增 `orchestrator_round` / `verify_criterion` / `self_report`。**additive** |
| 事件 payload 键 | **有** | 三个新事件各自的键；既有事件**一律未改** |
| 上游 `PHASE_ORDER` 阶段 | **无** | 自述**不是**新阶段（在 `record`/`failed` 之后作为报告追加） |
| `CycleReport` 字段 | **有：新增 `self_report`** | **additive**；`FROZEN_REPORT_KEYS` 同步加 |
| `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1`） | 新增事件/字段按本侧规则属 additive |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无**（规则表仍 23 条） | 事件**种类数**变了 → 台账 `event_partition.observed` 需 **13 → 16** |

**★ 一个必须显式声明的取舍**：`orchestrator_decision` 这个 kind **归前端 bridge**
（`bridge/hooks.py` 的 `Orchestrator._decide` 挂钩），**上游不复用它** ——
两个生产者发同一个 kind 会让审计无法判断哪条权威。
上游新增的是**独立名字** `orchestrator_round`。两者数据同源（同一个 `_decide` 返回值），
但**上游这条在没有 bridge 时也在**。若统筹方要求统一成一个 kind，
请先让前端侧停发，我再改过来 —— **我不会在两侧都发的情况下抢这个名字**。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **必须跟着改吗**：**不必须**。三个新事件对前端是 additive（认不出就降级显示），
  `CycleReport.self_report` 同理。前端的三块视图（A2/A3、B4、C3）可以照做，数据已齐：
  * 决策依据 → `orchestrator_round.reasoning` **或** bridge 自己的 `orchestrator_decision.reasoning`；
  * 判据演化 → `verify_criterion`（含 `previous_command` / `previous_passed`），
    `verify_probe` 仍然可用；
  * 收尾自述 → `self_report`，其中 `fact_check.contradictions` **建议放最显眼处**。
- **有没有可能"问题被平移到对侧"**：**有一处，且我要说清**。
  用户那次运行里的 `orchestrator_decision` **事件只有 `{"status":"continue"}`** ——
  我核了他们的**现行源码**：`bridge/hooks.py:306-313` **已经**带 `reasoning`、
  `round`、`task_count`、`final_answer`。也就是说那次运行跑的是**比现行源码更旧的
  bridge**（与 §31 的"陈旧副本"同一个病根，只是这次在前端侧的 bridge）。
  证据（原始事件，来自统筹方自己的 probe）：

  ```
  {"seq": 8,  "ts": "...", "kind": "orchestrator_decision", "status": "continue"}
  {"seq": 18, ...} {"seq": 37, ...}          ← 三条都只有 status
  ```
  **所以 A1 的"前端看不到为什么"里，有一半是部署问题**（旧 bridge），
  不是缺字段。我这一侧仍然把 `reasoning` 做成了**上游事件**，这样
  **无论 bridge 新旧，事件流里都能读到决策依据**。请统筹方按此评估：
  前端需要的是"升级 bridge 副本"，而不是"改 hooks 去拿 reasoning"。
- **前端会静默少显示什么吗**：不会少，只会**多**三个 kind。
  但请注意 `self_report` 的 `fact_check` 是**结论性的负面信息**，
  前端若把它折叠起来，这个机制的价值就丢掉了一半。

---

## 7. 不做的部分及理由（对应 C7）

- **不做"禁止降级"（统筹方列的强度 3 / 4）**。用户的裁决是 **(2) 留痕 + 必须给理由**。
  B2 严格按这个来：换判据**允许**，但必须给理由、必须看得见。
  **我没有把"换弱"本身判为失败** —— 那会越权改用户的选择。
- **B3 我做了，并说明为什么它不与该裁决冲突**（这是统筹方点名要求"不要默默处理"的那条）：
  * 用户裁决的是**"换判据这件事怎么处理"**（留痕 + 理由）；
  * B3 管的是**"什么样的判据才算合格"** —— 与"换不换"正交；
  * 而且它是**本次唯一能拦住 (c) 的规则**：只做 B2 的话，模型只要写一句
    "我改判据了"，`assert generate_obstacles` 照样被采纳、照样 `passed`。
  * 代价我如实列在这里：**`.py` 交付物只做存在性/内容检查的判据会被拒**
    （例：`assert os.path.exists('add.py')`）。处置仍是**显式失败**并给出改法，
    调用方给的判据**不受影响**。
  * 若统筹方判定它与用户选择冲突，**删掉 B3 只需回退 `_model_verify_admissible`
    里的第三层**（一处），`test_transparency.py` 会同时红 —— 是可控的回退。
- **不做"goal 要求自动抽取"**：C2 第 4 行要求"目标里明确要求、但既不 done 也不 not_done
  的要标未提及"。**从自然语言目标里机械抽取要求是不可判定的**，所以我改成：
  让模型自己列 `requirements[]`（每条一个状态），**核对由程序做**（缺状态 → 未提及）。
  这样"未提及"是**机械判定**，不是又一层模型判断。
- **不改 `verify_probe`（前端事件）**：那是对侧的东西；B1 的数据我用自己的事件补齐。
- **不动前端任何代码**，也没有替前端决定 UI 该长什么样。
- **不做 8 级基准的通过率对比**（见 §4.2）。

---

## 8. 回退点（C8）

- **回退命令**：见本变更的备份点 `docs/VERSIONS.md`（`v1.21`），
  形如 `git reset --hard <tag>`。
- **回退会丢什么**：
  1. A1 的 `orchestrator_round`（决策依据重新只在日志/前端 bridge 里）；
  2. B1 的 `verify_criterion`（判据演化重新只能靠 `verify_probe` + seq 拼）；
  3. **B2 的"换判据必须给理由"**（模型可以再次静默换弱 → **缺陷复现**）；
  4. **B3 的"必须调用交付物"**（`assert generate_obstacles` 重新可采 → **缺陷复现**）；
  5. C1/C2 的 `self_report` / `fact_check`。
- **回退不会丢什么**：`FIX-VERIFY-WIRING`（v1.17）与 `VERIFY-VACUOUS`（v1.19/v1.20）的
  全部改动 —— 本次是在它们之上加层，没有改它们的判据。
  **另外：B3 若单独回退（删第三层），`VERIFY-VACUOUS` 的"引用交付物"下限仍然在。**
- 回退后**不会**出现"判据被静默放宽"的中间态：回退是整份代码回退。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.3 两条离线命令；§2.4 真实模型脚本；每条事实都带 `文件:行` 或事件 `seq` |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 13 条，每条一个命令 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘贴原文（含真实模型跑统筹方固定样例） |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；并点出 `test_verify_vacuous.py` 那条**不是修 bug 而是有意收紧** |
| **C5** 对接口契约的影响已声明 | **满足**。§5：13 → 16 个事件、`self_report` 字段，全 additive；并显式声明 `orchestrator_decision` 归前端 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：不需要改，但**指出用户那次的 `orchestrator_decision` 缺 reasoning 是旧 bridge 造成的**（附原始事件） |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 七条"不做"，含 B3 的取舍与可回退说明、以及"不替前端做 UI 决定" |
| **C8** 回退点明确 | **满足**。§8：单一备份点；并单独说明"B3 可单独回退" |

**我希望统筹重点验证哪一条**：**B3 的边界**（§4 主张 5/6）与 **C2 的"撒谎必被抓"**（主张 8）。
理由：这两条都是"**判据/自述本身会不会被骗**"的问题 ——
而我这一侧的判据越强，越容易在一个没人测的角落**判宽或判窄**。
B3 我已知的判窄面写在 §7（`.py` 只做存在性检查会被拒）；
C2 我只做**可判定的相等比较**，任何"语义上像但结构上没填"的谎报**抓不到** ——
这一点我宁愿他们先知道。

---

## 附：与上一轮的关系（避免被读成"上一轮没修好"）

| | `VERIFY-VACUOUS`（v1.19/v1.20） | 本次 `TRANSPARENCY-BACKEND` |
|---|---|---|
| 下限 | 自拟判据必须**引用**交付物 | 引用了 `.py` 就必须**调用**它（B3） |
| 判据的**变更** | 未管 | 换掉已失败的判据**必须给理由**（B2） |
| 可见性 | 只有最终 `verify` + 被拒留痕 | 判据**演化**、决策**依据**、收尾**自述** |
| 关系 | 统筹方原话：上一轮的下限"是**必要**的，但**远不充分**" | 本次把"不充分"补上 |

上一轮的评估文档里那条 `.py` 只做存在性检查的用例，**本次被有意收紧**；
`docs/EVALUATION-VERIFY-VACUOUS.md` 顶部已加一行指针，避免两份文档看起来互相矛盾。
