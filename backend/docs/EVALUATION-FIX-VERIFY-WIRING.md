# 变更评估文档 · `FIX-VERIFY-WIRING`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 九节填写，自检标准见
> `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
> 缺陷报告来源：`SimpleAgent2_Integration/05-reports/SUGGESTION-20260926-backend-verify-never-runs.md`。
> 契约目录是**只读资产**，本文件写在本仓库。

---

- **变更编号**：`FIX-VERIFY-WIRING`
- **提出方**：统筹方（缺陷报告，含 `文件:行` 级定位与 14 条运行史穷举）
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**（实现时对应的一版）：`1.0.22`

---

## 1. 变更意图

> 引统筹方原话，不转述。

> **`main.py:119` 构造 `Orchestrator` 时没注入 `pipeline`**，
> 而唯一会注入它的 `_setup_orchestrator` 只在
> `coding_cycle.py:306` / `:338` 的 `if verify_command is not None:` 成立时才被调用
> （= **只有调用方自己给了 `verify_command`**）。
>
> 于是**不带 `verify_command` 的真实目标永远不执行验证**，
> 随后 `coding_cycle.py:456` 报「**缺少**可机器判定的验证命令」——
> **而模型已经把它拟好了**。**这个诊断是错的。**

他们的复验方式（我按它自检）：

> **打接口，不看你们文档**：`demo=False` + 空 `verify_command` 端到端跑一次，
> 断言 `report.verify` **非空**且 `status=passed`。**这条过了才算修好。**

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 我逐条复核了他们的证据（全部为真）

| 他们的论断 | 我核到的 |
|---|---|
| `main.py:119` 没传 `pipeline` | ✅ `return Orchestrator(orch_llm, worker)` |
| `coding_cycle.py:306/:338` 被 `if verify_command is not None:` 包住 | ✅ 两处都在 |
| `orchestrator.py:151` 因此整块跳过 | ✅ `if verify_command and self.pipeline is not None:` |
| `coding_cycle.py:458` 报「缺少…」是错误诊断 | ✅ 命令在 `orch_result.verify_command` 里 |
| `repro_user_goal.py` 手工传了 `pipeline` → 抓不到 | ✅ 第 47 行 `pipeline=CheckPipeline()` |

### 2.2 复现（改动前）

```powershell
# 关键：**经生产构造路径**、且 verify_command 留空
.venv\Scripts\python.exe -X utf8 tests\diagnostics\repro_user_goal.py
```

**改动前**：`phase=failed`、`report.verify = None`、
`error = "缺少可机器判定的验证命令（verify_command）…"` —— 而计划事件里命令就在。

**改动后**：

```
[构造] 经 main._build_orchestrator()（与 /encode 同一条路径）
[构造] orchestrator.pipeline = CheckPipeline
[构造] orchestrator.context_provider = 已注入
phase=record  attempts=1  用时=12.7s
report.verify = {'passed': True, 'command': "with open('file_list.txt', 'r') as f:\n    lines = f.readlines()\nassert len(lines) > 0\nprint('PASS')"}
```

### 2.3 ★ 同一个 `if` 还连带杀掉了第二个能力（他们没提，我核出来的）

`_setup_orchestrator` 注入的是**三样**东西：

| 注入物 | 作用 | 被那个 `if` 影响 |
|---|---|---|
| `pipeline` | 循环内验证回流 | **生产路径上全灭** |
| `verify_command` | 调用方权威 | 只在"调用方给了"时才需要设 |
| **`context_provider`** | **结构化上下文回流**（v1.12/§19 的能力） | **同样全灭** |

也就是说：**用户那几次运行里，结构化上下文回流也从未生效过**。
这不是"顺手发现"，而是同一个结构性缺陷的第二个受害者 ——
**一个 `if` 决定了两个能力是否存在**。修法必须治结构（见 §3）。
（实测补记：`context_provider` 未注入时，`SharedMemory.structured_context`
恒为空串，渲染层整段不输出。）

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `core/coding_cycle.py` | `run()` 循环前 | **去掉 `if verify_command is not None:`**，无条件 `_setup_orchestrator(verify_command)`（结构性修复） |
| 2 | `core/coding_cycle.py` | `run()` 每次尝试前 | 同上（第二处） |
| 3 | `core/coding_cycle.py` | `_setup_orchestrator` | `verify_command is None` 时**保留原值**而非清成 `None`（否则会抹掉 `SkillRunner` 烘焙的命令 —— 见 §4 主张 7 的回归） |
| 4 | `main.py` | `_build_orchestrator` | `Orchestrator(orch_llm, worker, pipeline=CheckPipeline())`（让 `/run` 那条无 cycle 的路径也具备回流） |
| 5 | `core/orchestrator.py` | `OrchestratorResult` | 新增 `verify_skipped: str` —— 把"跳过验证"变成显式事实（附 1） |
| 6 | `core/orchestrator.py` | 验证回流处 | 有命令但 `pipeline is None` 时**打印并记录原因**（原来完全静默） |
| 7 | `core/orchestrator.py` | `_files_to_verify` | **语义修正**（附 4）：`声明 > 产物 > prior`，不再"prior 优先" |
| 8 | `core/orchestrator.py` | `run()` | `cycle_files` → 更名 `prior_files`/`prior_set`（它回答的是"哪些是历史文件"，不是"验什么"） |
| 9 | `core/coding_cycle.py` | 拿到 `orch_result` 后 | `verify_skipped` 非空时记 `verify_skipped` 事件（**单一事件出口**不变） |
| 10 | `core/coding_cycle.py` | 失败文案 | **把「缺少」与「没跑」分开**（附 2） |
| 11 | `core/contract.py` | `EVENTS` | 新增事件 `verify_skipped`（additive；词表 12 → 13） |
| 12 | `tests/unit/test_verify_wiring.py`（新增） | — | 把本缺陷钉死的 17 项离线断言 |
| 13 | `tests/diagnostics/verify_wiring_http.py`（新增） | — | **经 HTTP** 的同构自检（附 3，需真实模型） |
| 14 | `tests/diagnostics/repro_user_goal.py` | — | **改走 `main._build_orchestrator()`**，不再手工注入 pipeline（否则永远复现不出本缺陷）；并把 `report.verify` 非空列为验收断言 |
| 15 | 文档 | — | 本文件 + `README.md` + `CHANGELOG.md`（§33）+ `FRONTEND_CONTRACT.md`（新事件）+ `MODULES.md` + `OPERATIONS.md` + `tests/README.md` + 版本戳 + `docs/VERSIONS.md` |

**实际 diff 规模**（`git diff --stat`，截至本文件**定稿前**实测）：

```
 core/coding_cycle.py                    |  56 ++++++++++++++++---
 core/contract.py                        |   8 +++
 core/orchestrator.py                    |  72 ++++++++++++++++------
 main.py                                 |   8 +-
 tests/diagnostics/repro_user_goal.py    |  31 ++++++--
 docs/FRONTEND_CONTRACT.md               |   4 +-
 docs/MODULES.md                         |   4 +-
 docs/PENDING_DECISIONS.md               |   2 +-
 8 files changed, 154 insertions(+), 31 deletions(-)
```

**stat 之外、同一次提交还会带入的**（显式声明）：
本文件（新增）、`tests/unit/test_verify_wiring.py`（新增）、
`tests/diagnostics/verify_wiring_http.py`（新增）、`README.md`、`docs/CHANGELOG.md`、
`docs/OPERATIONS.md`、`tests/README.md`、5 个上游文档的版本戳、`docs/VERSIONS.md`。
评审时以备份点的 `git show --stat` 为准。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | `main` 的构造路径注入了 `pipeline`（**抓原缺陷**） | `python -c "import main; print(main._build_orchestrator().pipeline)"` | 非 `None` |
| 2 | 两处 `_setup_orchestrator` 不再被 `if verify_command…` 包住 | `python tests/unit/test_verify_wiring.py` | `受 if 保护的调用点: 无` |
| 3 | 调用方没给命令时**不覆盖**编排器自带命令 | 同上 | `调用方没给时不覆盖编排器自带的命令` PASS |
| 4 | 端到端（离线）：空 `verify_command` 时主循环仍拿到 pipeline 与 `context_provider` | 同上 | 两项 PASS |
| 5 | 有命令却跑不了验证时 **`verify_skipped` 事件可见** | 同上 | `发出了 verify_skipped` PASS |
| 6 | 「验什么」= 声明 > 产物 > prior，且指纹随交付物变化 | 同上 | 四条 PASS |
| 7 | **经 HTTP**：`demo=False` + 空 `verify_command` → `verify` 非空 | `python tests/diagnostics/verify_wiring_http.py` | `通过 3/3`（需真实模型） |
| 8 | 生产构造路径的真实需求跑通 | `python tests/diagnostics/repro_user_goal.py` | `phase=record`、`report.verify` 非空、exit 0 |
| 9 | 全量回归无退化 | `python tests/run_unit.py` | `通过 32/32` |
| 10 | 契约符合性（新事件按 additive 处理） | `python tests/unit/test_contract_conformance.py` | `通过 44/44` |
| 11 | 真实 E2E 基准 | `python tests/bench/run_levels.py 1 1` | `L1 PASS … phase=record` |

**实测输出**（粘贴原文）：

主张 1/2/4：

```
[构造] 经 main._build_orchestrator()（与 /encode 同一条路径）
[构造] orchestrator.pipeline = CheckPipeline
[构造] orchestrator.context_provider = 已注入
  受 `if verify_command …` 保护的调用点: 无
  PASS  没有任何 _setup_orchestrator 调用被该条件包住
  主循环被调用时 pipeline = CheckPipeline
  主循环被调用时 context_provider = True
```

主张 7（**经 HTTP**）：

```
  orchestrator.pipeline          = CheckPipeline
  orchestrator.context_provider  = 已注入
  请求: {'goal': '在 workspace 下创建 note.txt，写入一行文本 hello', 'max_attempts': 2}
  HTTP 200
  ok               = True
  phase            = record
  verify_passed    = True
  manifest_passed  = True
  PASS  构造路径注入了 pipeline
  PASS  verify_passed 非空（= 验证真的执行过）
  通过 3/3
```

主张 8（生产构造路径 + 用户原话）：

```
phase=record  attempts=1  用时=12.7s
report.verify = {'passed': True, 'command': "with open('file_list.txt', 'r') as f:\n …"}
运行记录里的代码身份: code_dir=D:\PythonProject\SimpleAgent2_Cycle code_fingerprint=…
  自报完整 = True | 与当前加载的代码一致 = True
```

### 4.1 我在修的过程中**引入并修掉了一个回归**（如实记录）

无条件调用 `_setup_orchestrator` 后，它会把 `orchestrator.verify_command`
**清成 `None`** —— 而 `SkillRunner` 把技能里烘焙的 `verify_command` 放在**同一个属性**上。
`test_skills.py` 当场报 `'NoneType' object has no attribute 'get'`（`skill_runner.py:165`）。

**这正是统筹方在报告里提醒过的那一点**（"`None` 时它会把 `orchestrator.verify_command`
置 None，需要一并调整以免覆盖模型自拟的那份"）——他们预判对了。

修法：`verify_command is None` 时**保留原值**。并把这条**写进断言**
（否则我自己的门禁标签还是旧的、会误报通过）：

```
自带命令在 `_setup_orchestrator(None)` 之后 = {'command': "print('skill')", …}
PASS  调用方没给时不覆盖编排器自带的命令（SkillRunner 依赖这条）
PASS  调用方给了命令时覆盖为调用方的（权威性不变）
```

**未验证的部分**（诚实列出）：

- **没有用他们那条"完整实例"复验**：我跑的是 FastAPI `TestClient`（经请求模型与
  `/encode` 处理器，与生产同一条构造路径），**没有**起真实 uvicorn + 前端 bridge。
  真实部署形态的复验仍以他们为准。
- **没有验证"结构化上下文回流复活"的效果**：我只断言了 `context_provider` 被注入
  （§4 主张 4），**没有**断言 prompt 里真的出现了「结构化上下文」段 ——
  那需要抓取发给模型的 messages，属另一件事。
- **`/run` 路径**（无 cycle 层）只做了代码层注入，未端到端跑过。
- **附 5（workspace 跨运行不重置）未处理**：那是前端运行根的行为，不在本侧；
  只确认它会让 manifest 报 `unexpected-file` 警告（非阻塞）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| **事件 `kind` 名** | **有：新增 `verify_skipped`**（12 → 13） | **additive**：新增事件前端会"自动生成可读名字"降级显示，不破坏 |
| 事件 payload 键 | **有：新事件的 `reason` / `command`** | 新事件自带，不影响既有事件 |
| `cycle_start` 的 payload | 上一轮已加 `code_dir`/`code_fingerprint`（本轮无新增） | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **CycleReport 无改动**（`verify` 字段本就存在，只是以前恒为 `None`） | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1`） | 新增事件属 additive，按本侧规则不升版本 |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无**（规则表 23 条未变） | — |

**需要统筹方登记进契约的两项**（本侧不改契约）：

1. `event_partition.observed`：上游事件 12 → **13**，补 `verify_skipped`；
   `union_count` 33 → 34（若他们仍统计 union）。**本侧符合性测试会打印这条待更新**，
   且**不再判失败**（新增是 additive；只有"契约有、本侧已无"才硬失败）。
2. `fact_sources` / 无其它改动。

**我要如实说明一处**：他们的 `PHASE_ORDER` 与 `CyclePhase` 我一个字节没动 ——
本缺陷是**接线**问题，不是契约定义问题。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不需要**（本轮全是本侧接线与文案）。
  但**新增了一个事件 `verify_skipped`**，前端会在下次对账里看到
  `P-event-unknown-to-frontend`（`degraded`，自动降级显示）——
  **这是预期的**，他们可据此补标定。
- **有没有可能"问题被平移到对侧"**？**没有**。缺陷完全在本侧装配；
  修法也在本侧。前端唯一相关的是"用哪一份后端"（已于 §31 定位，属部署配置）。
- **前端会静默少显示什么吗**？本轮**不会**（只新增事件）。
  反而**多了一条可见信号**：以前"验证被跳过"是**完全静默**的，
  现在会出现在事件流里。这是**修掉一处静默失效**，不是新增静默。

---

## 7. 不做的部分及理由（对应 C7）

- **不动 `PHASE_ORDER` / `CyclePhase`**：本缺陷与阶段定义无关。
- **不改 `bridge/`（前端）的任何东西**：包括他们建议里可能涉及前端的部分（无）。
- **不引入新的配置项**：修法是"让它总是注入"，而不是"加个开关让调用方记得开"。
- **不做附 5（workspace 跨运行重置）**：那是**前端运行根**的行为
  （`data/workspace` 在两次 run 之间不清理）。本侧只确认它会产生
  `unexpected-file` 警告。是否要清理属部署策略，需用户/前端定。
- **不把"验证没跑"升级为硬失败**：`verify_skipped` 只是事件。
  理由：那会让"手工构造的 Orchestrator"（测试里常见）直接崩，
  而它本身不是错误用法。当前选择是**让它可见**，不是让它致命。

---

## 8. 回退点（对应 C8）

- **回退命令**：
  ```powershell
  git log --oneline --grep "^v1.17:"    # 取到备份点 hash
  git reset --hard <该 hash>
  ```
- **上一稳定点**：`v1.16` @ `a567828`（`git reset --hard a567828`）
- **回退会丢什么**：无条件注入（两处）、`main` 的 `pipeline=`、
  `verify_skipped` 事件、`_files_to_verify` 语义修正、文案分开、两个新诊断脚本、
  本文件。**回退后的已知后果**：不带 `verify_command` 的真实目标**重新变成：
  验证从不执行、却报「缺少验证命令」**，且结构化上下文回流再次静默失效。

---

## 9. 自检结论

| 标准 | 结论 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了生产构造路径的复现命令与改动前后输出；并逐条复核了他们的 `文件:行` |
| **C2** 每条主张带命令 | **满足** | §4 十一条主张各配一条可独立执行的命令 |
| **C3** 输出支持主张 | **满足** | §4 粘贴真实输出（含**经 HTTP** 的 `通过 3/3` 与生产路径的 `report.verify`） |
| **C4** 改动清单与实际一致 | **满足** | §3 表 + `git diff --stat`（8 文件 154/31），并显式列出 stat 之外的新增文件 |
| **C5** 契约影响已声明 | **满足** | §5：新增事件（additive，已声明）+ 两项待登记；阶段/规则表未动 |
| **C6** 对侧影响已评估 | **满足** | §6：不需前端改动；新事件会导致一次预期的 `P-event-unknown-to-frontend` |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7：不动阶段定义、不加配置开关、不越界改前端 |
| **C8** 回退点明确 | **满足** | §8：v1.17 定位命令 + 回退后的已知后果 |

- **我希望统筹重点验证**：
  1. **§4 主张 7（经 HTTP）** —— 这是他们复验时会打的那一条；
     我的实现用 FastAPI `TestClient`（经请求模型与处理器），**未起真实 uvicorn**，
     请以真实实例为准；
  2. **§4.1 那个回归**：无条件注入会让 `verify_command=None` 覆盖
     **编排器自带**的命令（`SkillRunner` 依赖它）。我已改成"保留原值"并写了断言，
     请确认这个语义与你们对 `verify_command` 的理解一致；
  3. **附 4 的判定**：我的结论是**他们的读法正确**（`prior_files` 被当成"验什么"，
   导致指纹键在旧文件集上、同命令的后续轮次会跳过重验）。修法是
   `声明 > 产物 > prior`。若设计原意是"整体验一遍 workspace"，请指出 ——
   那我改回去并补文档。
