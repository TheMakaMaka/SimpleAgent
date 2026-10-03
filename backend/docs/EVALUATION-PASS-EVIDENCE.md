# 变更评估文档 · `PASS-EVIDENCE`（P17）

- **变更编号**：`PASS-EVIDENCE`（工作单 **P17**，契约 `pass_evidence`）
- **提出方**：用户（2026-10-03 定的这一轮目的：换模型前把边界验证好）
- **执行侧**：backend
- **日期**：2026-10-03
- **契约版本**：`1.0.33`（`pass_evidence`）
- **本轮 round_id**：`R-ecc61d8543` —— **本轮完成 `R-ecc61d8543`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-ecc61d8543` 开工，
> 与仓库里上一轮记录的 `R-8b28b25a1f`（`docs/EVALUATION-OUTPUT-CONTRACT.md`）不同 ⇒ 有新指令。
> 工作单 P14/P15/P13/P11 **上一轮已完成并记录**（同文件 §8），本轮只做 P17 与 D30 复核。
> 所有结论均以仓库里的机器事实为准（测试退出码、探针回显、`git diff --stat`），不是印象。

---

## 1. 变更意图

**统筹方 `DISPATCH.md` 本轮 ⓪（最高优先 · 用户本轮目的），逐字**：

> 实测：**8 个 pass 里 7 个没有执行证据**，而 self_report 11/11 ⇒
> **换模型时，更爱自我宣称的模型会拿到更高的分** —— 那测的是它愿意怎么说话，
> 不是它能不能做 ⇒ **读数不可比，「模型即插即用」在测量层就断了。**
>
> 要做：每次 **pass** 必须带 `checked_by`(tool/model) + `evidence_kind`
> （`executed{command,exit_code}` / `artifacts{path,sha256,size}` /
> `static_declared{reason}`）；**`checked_by==model` 且无 `evidence_kind` ⇒ 不得记 pass**。

**来源（工作单 P17）**：用户 2026-10-03 定的这一轮目的 ——「在**换模型之前**，先把这些
功能开发好，**验证好边界**，模型**即插即用**」。统筹方做了机判标准（`SWAP-READY`，8 条），
跑出来 **6/8**，其中 **S3 = pass 必须有机械证据** 是红的。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（带 `文件:行`）

| # | 缺陷 | 位置 / 机械依据 |
|---|---|---|
| 1 | `pass` 只记 `outcome=pass`，**不记它靠什么** —— 报告/事件里没有 `checked_by` / `evidence_kind` | `core/coding_cycle.py`（HEAD 的成功出口 `_end_cycle(..., "passed", "verified", …)`） |
| 2 | verify 的**执行记录（真实退出码）根本没被留痕**：`set_verify` 的 payload 只有 `passed/detail/command/source/artifact_hashes/cwd/cache_*` | `core/memory.py::set_verify`（HEAD 实测见下） |
| 3 | 于是"**有命令**"与"**真的执行过**"在报告里**同形**；抽掉执行事实也照样记 pass | 同上；`core/orchestrator.py::run` 调用点 |

### 2.2 复现命令与实测输出

**修复前的 `set_verify` payload（`HEAD` 源码，不带 `exit_code`）**：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import subprocess; s=subprocess.run(['git','-c','safe.directory=D:/PythonProject/SimpleAgent2_Cycle','show','HEAD:core/memory.py'],capture_output=True,text=True,encoding='utf-8').stdout; i=s.find('self.verify_state = {'); print(s[i:i+330])"
```

```
self.verify_state = {
            "passed": passed,
            "detail": detail,
            "command": command,
            "source": source or "",
            "artifact_hashes": dict(artifact_hashes or {}),
            "cwd": cwd or "",
            "cache_cleared": int(cache_cleared or 0),
            "cache_warning": cache_w…
```

⇒ **没有 `exit_code` / `expect_exit`**：报告里读不出"判据真的被执行过、退出码是多少"。
这正是统筹方实测「8 个 pass 里 7 个没有执行证据」的机制性缺口 ——
**不是模型不老实，是仪表没记这件事。**

**为什么这是问题**：换模型时若 `pass` 不区分证据，**更爱自我宣称的模型会拿到更高的分**，
读数不可比 ⇒ **「模型即插即用」在测量层就断了**。

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

`git diff --stat`（**不含**未跟踪的新文件）：

```powershell
$ git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle diff --stat
 CYCLE.md                          |  2 +-
 README.md                         |  3 +-
 core/coding_cycle.py              | 63 ++++++++++++++++++++++++++++++++-
 core/contract.py                  | 22 +++++++++---
 core/cycle.py                     |  9 +++++
 core/memory.py                    |  9 +++++
 core/orchestrator.py              |  5 +++
 core/outcome.py                   |  7 ++++
 core/skill_runner.py              |  3 ++
 docs/ARCHITECTURE.md              |  2 +-
 docs/CHANGELOG.md                 | 73 +++++++++++++++++++++++++++++++++++++++
 docs/MODULES.md                   | 55 +++++++++++++++++++++++++++--
 docs/OPERATIONS.md                | 27 ++++++++++++++-
 main.py                           | 14 ++++++++
 tests/README.md                   |  2 ++
 tests/unit/test_cycle_manifest.py |  4 +++
 tests/unit/test_deliverables.py   |  5 ++-
 17 files changed, 292 insertions(+), 13 deletions(-)
```

新增文件（`git diff --stat` 不含未跟踪文件）：

```
core/evidence.py                              ← pass 证据：build_evidence / pass_allowed / describe
tests/unit/test_pass_evidence.py              ← P17 门禁（30 项）
tests/diagnostics/probe_pass_evidence.py      ← 生产路径机械取证（13 项）
docs/EVALUATION-PASS-EVIDENCE.md              ← 本评估文档
```

`docs/VERSIONS.md` **不在**上面的 `diff --stat` 里 —— 它由 `tests/backup.py` 在提交
**之后**追加 v1.28 记录、再 amend 进同一提交（备份机制的固有行为）。以**备份点**
`git show --stat <v1.28 提交>` 为准，它比 §3.1 多一个 `docs/VERSIONS.md` 与本评估文档。

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/evidence.py`（新） | 全文件 | `build_evidence`（强→弱取三类证据）+ `pass_allowed` 硬判据 + `describe` 契约面 |
| 2 | `core/memory.py` | `set_verify` | **执行记录留痕**：`exit_code` / `expect_exit`（`None` 不冒充 0） |
| 3 | `core/orchestrator.py` | `set_verify` 调用点 | 把 `check_and_run` 的真实退出码传进去 |
| 4 | `core/skill_runner.py` | `set_verify` 调用点 | 技能重放的 pass 同样要带执行记录 |
| 5 | `core/coding_cycle.py` | `report.verify` / `verify` 事件 / **pass 出口** | 报告与事件带 `exit_code`；产物对账后、**打检查点前**执行 `pass_allowed` 门禁 |
| 6 | `core/outcome.py` | `KIND_TO_OUTCOME` | 新种类 `unsubstantiated-pass → invalid`（不默认 fail） |
| 7 | `core/cycle.py` | `CycleReport.evidence` + `to_dict` | 报告回报"这次靠什么"（进 `FROZEN_REPORT_KEYS`） |
| 8 | `core/contract.py` | `cycle_end` / `verify` 事件 + `FROZEN_REPORT_KEYS` | 加性声明新 payload 键与报告字段（`audit()` 的 payload 漂移判据要求声明==实际） |
| 9 | `main.py` | `/profile` / `/encode` | 加性：`pass_evidence` 契约面、`static_reason` 请求字段、`evidence` 响应字段 |
| 10 | `tests/unit/test_deliverables.py` / `test_cycle_manifest.py` | 假编排器的 `set_verify` | 补执行记录 —— 假编排器要**忠实复刻**真实编排器，否则测的不是集成路径 |
| 11 | 文档面 | CHANGELOG §42 / MODULES §33 / OPERATIONS §4.23 / README 文档表 / tests/README / 5 处版本戳 | 声明与实现同步 |

### 3.3 若两者不一致，差异是什么

1. **`docs/VERSIONS.md` 不在 `diff --stat` 里** —— 备份机制在提交后追加再 amend（§3.1）。
2. **统计口径**：§3.1 是 `git diff --stat`（**17 个已跟踪文件**，不含新增文件与本评估文档）；
   备份点 `git show --stat` 会多出 `core/evidence.py`、两个新测试、本评估文档与
   `docs/VERSIONS.md`。**这正是 C4 的意义**：交出去核对的数字必须对，对不上时
   **以机械输出为准**并明写差异。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | ★ 每次 **pass** 带 `checked_by` + `evidence_kind`，按类别给结构 | `tests/unit/test_pass_evidence.py` §[4]–[7] | 30/30，`executed` 带 `{command, exit_code}` |
| 2 | ★ **`checked_by=model` 且无 `evidence_kind` ⇒ 不得记 pass** | 同上 §[1]/[8] | `pass_allowed=False`；cycle 结局 `invalid / unsubstantiated-pass` |
| 3 | ★ **反空洞**：抽掉执行记录（`exit_code`）⇒ 同一个 pass 立刻被拒 | 同上 §[8]；`probe_pass_evidence.py` §[2] | `phase=failed`、`commit` 为空 |
| 4 | ★ **不是一律报红**：正常执行（真实退出码）仍然 pass | 同上 §[7]；探针 §[1] | `phase=record outcome=pass evidence_kind=executed exit_code=0` |
| 5 | `artifacts` 证据路径**必须在输出根内**（与 P14 一致） | 同上 §[5]；探针 §[3] | 输出根内 ⇒ `artifacts`；工作区里 ⇒ `excluded_artifacts[out-of-output-root]` |
| 6 | `static_declared` 必须带**可复核理由** | 同上 §[6]；探针 §[4] | 空理由 ⇒ 不成立；有理由 ⇒ `checked_by=model` |
| 7 | 结局映射不静默：新种类登记为四值之一 | 同上 §[3] | `unsubstantiated-pass → invalid` |
| 8 | `cycle_end` 事件可审计（`checked_by`/`evidence_kind`/`evidence`） | 同上 §[7]；探针 §[1] | payload 三键齐备 |
| 9 | 生产路径（真实子进程 `check_and_run`）也能跑出来 | `tests/diagnostics/probe_pass_evidence.py` | 13/13，末行 ★ |
| 10 | 全量单测无回归（新增测试被 `run_unit.py` 自动收集） | `tests/run_unit.py` | 见 §4.1 |
| 11 | 文档一致性 / 不变量 / 审查 / 契约符合性 / 前端契约 | `test_doc_consistency` / `test_doc_invariants` / `test_doc_review` / `test_contract_conformance` / `test_frontend_contract` | 全 PASS（见 §4.1） |

### 4.1 实测输出（粘贴原文）

**★ 单元门禁（`tests/unit/test_pass_evidence.py`，节选）：**

```
  PASS  ★ 硬规则不成立（这是 P17 要求 2 的原话）
  PASS  executed 缺 exit_code ⇒ 拒绝
  PASS  executed 缺 command ⇒ 拒绝
  PASS  artifacts 为空 ⇒ 拒绝
  PASS  static_declared 缺理由 ⇒ 拒绝
  PASS  没有 exit_code ⇒ 不产生 executed 证据
  PASS  有 exit_code ⇒ executed（checked_by=tool）
  PASS  输出根内的产物 ⇒ artifacts 证据
  PASS  工作区里的产物**不算**交付证据
  PASS  但它被逐条记进 excluded_artifacts（不是静默消失）
  PASS  ★ 仍然 pass（门禁不是一律报红）
  PASS  报告里证据类别 = executed
  PASS  cycle_end 事件也带 checked_by / evidence_kind（可审计）
  PASS  ★ 不再 pass（执行事实缺失）
  PASS  结局 = invalid / unsubstantiated-pass（契约允许的两值之一）
  PASS  phase=failed，且**没有打检查点**（无效读数不落提交）
  PASS  静态交付物 + 可复核理由 ⇒ 允许 pass
  PASS  checked_by 如实标注为 model（不是伪装成 tool）
通过 30/30
```

**★ 生产路径机械取证（`tests/diagnostics/probe_pass_evidence.py`，节选关键行）：**

```
[1] 生产路径：判据真的被执行 ⇒ evidence_kind=executed（带真实退出码）
  [real] phase=record outcome=pass kind=verified
    verify.exit_code=0 verify.passed=True
    evidence.checked_by=tool evidence.evidence_kind=executed
    evidence.executed={'command': 'import mod\nassert mod.f() == 2', 'exit_code': 0,
                       'expect_exit': 0, 'criterion_source': 'model'}
    cycle_end.checked_by=tool cycle_end.evidence_kind=executed
[2] ★ 反空洞：抽掉 exit_code（模拟执行记录缺失）⇒ 同一个 pass 被拒
  [no-exit-code] phase=failed outcome=invalid kind=unsubstantiated-pass
    verify.exit_code=None verify.passed=True
    evidence.checked_by=model evidence.evidence_kind=
    evidence.problems=['verify 通过，但**执行记录里没有退出码**（exit_code 缺失）
                       —— 无法证明它真的被执行过']
[3] artifacts 证据：输出根内算数；工作区里的逐条记原因（不静默）
  输出根内 ⇒ kind=artifacts artifacts=[{'path': 'outputs/_p17_probe.txt',
              'sha256': '52f979fdc5b55dce…', 'size': 13}]
  工作区里 ⇒ kind='' excluded=[{'path': '_p17_probe/draft.txt', …,
              'reason': 'out-of-output-root', …}]
[4] static_declared：空理由 ⇒ 不成立；有理由 ⇒ checked_by=model
[5] /profile.pass_evidence 契约面（加性、可读）
  required_on_pass = ['checked_by', 'evidence_kind']
  evidence_kinds   = ['artifacts', 'executed', 'static_declared']
  gate             = checked_by==model 且无 evidence_kind ⇒ 不得记 pass（记 invalid/unsubstantiated-pass）
通过 13/13
```

**★ 全量单测（本轮实跑，`tests/run_unit.py`）：**

```
通过 47/47          （上一轮基线 46/46 + 新增 test_pass_evidence.py）
包含：test_pass_evidence.py PASS · test_deliverables.py PASS · test_cycle_manifest.py PASS
      test_outcome.py PASS · test_criterion_ownership.py PASS · test_artifact_binding.py PASS
      test_doc_consistency.py PASS · test_doc_invariants.py PASS · test_doc_review.py PASS
      test_contract_conformance.py PASS · test_frontend_contract.py PASS · test_tool_envelope.py PASS
```

（全量单测的官方数字见 `docs/VERSIONS.md` 的 v1.28 备份记录。）

### 4.2 未验证的部分（诚实列出）

- **没有做真实模型 E2E**（需要模型配额）。本轮做的是**确定性**证据：
  生产构造路径（`Orchestrator` + `CodingCycle` + `CheckPipeline`）+ **真实
  `check_and_run` 子进程**的退出码，以及假编排器级/纯函数级的两向对照。
- **`checked_by=model` 但**有** `evidence_kind=static_declared` 仍然允许 pass** ——
  这是契约 P17 要求 2 的原话（只禁止"model 且**无**类别"）。它靠"理由可复核 +
  如实标注 model"约束，**不是**被当作强证据；稳态下主流程的 pass 都走 `executed`。
- **历史读数的影响面**：本仓库 `storage_data/events.jsonl` 的旧事件里没有
  `checked_by`/`evidence_kind` 字段（字段是本轮才加的），**旧读数不会被自动补证据**；
  统筹方那批 `batch_20261003-153501` 的 7 个"无执行证据"的 pass，需要他们按新字段重算。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 18 种） | 本轮不发新事件 |
| 事件 payload 键 | **加性** | `cycle_end` 加 `checked_by`/`evidence_kind`/`evidence`；`verify` 加 `exit_code` |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **加性** | `CycleReport.evidence`（已进 `FROZEN_REPORT_KEYS`，只增不减） |
| `TOOLS_MAP` 条目结构 | **无**（顶层键仍 4 个） | 未新增工具（仍 18 个） |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无**（仍 `1.1` / `1.0` / `1.0`） | 加性实现；契约规则"只增不减的改动不必升版本" |
| 端点路径 | **无** | 只有 `/encode` 请求/响应**字段**加性扩展 |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 未改规则表/词表；契约目录只读未动 |

**结论**：**additive**（新增，安全）。前端不读新字段则行为**逐字不变**；
`audit()` 的 payload 漂移判据要求"声明了就必须实际发出"，本轮的声明与发出同步
（`cycle_end` / `verify` 的 `_emit` 已带全部新键）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不需要**。所有新字段都是可选的；旧前端不读即降级显示。
  若前端想显示"这个 pass 靠什么"，读 `/encode` 响应的 `evidence.evidence_kind`
  或 `cycle_end` 事件的 `evidence_kind` 即可（`/profile.pass_evidence` 是契约说明）。
- **有没有可能"问题被平移到对侧"**：没有。证据判定全部在**上游内部**
  （`core/evidence.py` + `CodingCycle`），判据与实现同侧；前端不承担新义务。
- **前端会静默少显示什么吗**：不会（纯加性）。仍保留统筹方记的 **D32**
  （bridge `/api/spec` 的 `tools[]` 不含 `parameters`）—— 前端侧可选增强，与本轮无关。

---

## 7. 不做的部分及理由（对应 C7）

- **不做 D39「拆解关卡默认关闭」**：`ROUND.json` 把它列为阻塞项，但**本轮
  `DISPATCH.md` 未指派**，且该项自述「**需用户批准后才改默认**」⇒ 不动
  `DECOMPOSE_GATE_DEFAULT = "warn"`。**这不是漏做，是没有用户批准就不改默认**。
- **不做 D37 / P16（多语言）**：`DISPATCH.md` 明写「**现在别动**，用户裁决随后再上」。
- **不做 P12（子模型细读）**：用户裁决"等地图可信再上"，本轮不在指令内。
- **不重跑 P14/P15/P13/P11**：上一轮已交付并记录（`R-8b28b25a1f`），本轮只做加性的
  P17 接线；未改它们的语义（`test_deliverables.py` / `test_project_root.py` /
  `test_arch_map.py` / `test_criterion_ownership.py` 全部仍绿）。
- **不改工具名/参数语义、不新增工具**（仍 18 个）、**不新增事件种类**（仍 18 种）、
  **不引新依赖**（不用向量库/RAG）。
- **不靠放宽门禁变绿**：本轮是**收紧** —— 新增一条能拒绝 pass 的门禁；
  两个假编排器的测试夹具补 `exit_code` 是"让夹具忠实"，**不是**放宽判据
  （真正的负向用例由 `test_pass_evidence.py` §[8] 构造）。
- **不动 `.interface_contract/`**（只读权威源）；**不动对侧仓库与集成工作区**。

---

## 8. 回退点（C8）

- **回退命令**：见 `docs/VERSIONS.md` 的 `v1.28` 条目，
  `git log --oneline --grep "^v1.28:"` 定位提交，`git reset --hard <该提交>`。
- **回退会丢什么**：
  1. `core/evidence.py`（三类证据 + `pass_allowed` 门禁 + 契约面）；
  2. 执行记录留痕（`set_verify(exit_code=…)`、`CycleReport.verify.exit_code`、
     `verify` 事件的 `exit_code`）；
  3. pass 出口的 `unsubstantiated-pass` 门禁（退回"有命令即 pass"）；
  4. `CycleReport.evidence`、`cycle_end` 的三个新 payload 键、
     `/encode` 的 `static_reason`/`evidence`、`/profile.pass_evidence`；
  5. 两个新测试 + 探针 + 本评估文档 + 文档面同步。
- **回退不会丢什么**：v1.27 及以前的全部改动（P14/P15/P13/P11、P9、P7b、P6、
  P1 四值、P2/P3 机械关卡等）。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 逐条给 `文件:行`；§2.2 给 `HEAD` 源码机械回显（`set_verify` 无 `exit_code`） |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 11 条，全部离线可跑 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘单元门禁 / 生产路径探针 / 全量单测原文 |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明 `VERSIONS.md`（备份带入）与统计口径差异 |
| **C5** 对接口契约的影响已声明 | **满足**。§5 逐面声明；唯一"改动"是加性 payload 键与报告字段，事件/阶段/端点/版本轴/工具结构均未动 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：前端不需改；不读新字段则行为逐字不变；D32 仍是前端可选增强 |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 明确边界：D39 无用户批准不动、P16/P12 不动、不重写既有模块、不靠放宽门禁 |
| **C8** 回退点明确 | **满足**。§8 给出 `v1.28` 定位命令与丢失项清单 |

**我希望统筹重点验证哪两条**：

1. **门禁真的有牙齿，且不是把检查关掉**：请**抽掉执行记录**（让 `verify.exit_code`
   为 `None`，或摘掉 `core/evidence.py` 的 `pass_allowed` 调用）——
   同一个 pass **必须**从 `pass` 翻成 `invalid/unsubstantiated-pass`，且**不打检查点**；
   恢复后必须回到 `pass`。`tests/diagnostics/probe_pass_evidence.py` §[1]/§[2]
   就是这两向（前者在跑真实子进程）。
2. **`checked_by` 的如实性**：`static_declared` 路径**必须**标成 `checked_by=model`
   （不得伪装成 tool），且**理由为空时不得成立** —— 请构造一条空 `static_reason`
   的静态交付物，它**不得**记 pass（`tests/unit/test_pass_evidence.py` §[6]/§[9]）。
