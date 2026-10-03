# 变更评估文档 · `ENVELOPE-WIRING`（P9 追加验收 ③ / D33 后半）

- **变更编号**：`ENVELOPE-WIRING`（工作单里的 **D33 追加验收 ③**，属 P9 家族）
- **提出方**：统筹方（独立复验 `v1.25` 后的追加验收）
- **执行侧**：backend
- **日期**：2026-10-03
- **契约版本**：`1.0.30`（`tool_call_contract` 未变，本轮只接线）
- **本轮 round_id**：`R-4fb8a623b8` —— **本轮完成 `R-4fb8a623b8`**（下一轮据此判断要不要开工）

---

## 1. 变更意图

统筹方 `WORK-ORDER.md` 的 **D33** 在独立复验后追加验收 ③（原话，逐字）：

> **结果校验必须至少接到一个工具上**：`audit().envelope_tools` **非空**；
> 若决定"暂时全部按 legacy 处理"，请在 `docs\EVALUATION-TOOLCALL-NORM.md` 里
> **显式写明这是分阶段决定**及其判据 —— **不要让它停留在"建好了但没人用"**。
>
> （他同时写明：`envelope_tools` 为空 ⇒ 用户要的「**工具生成的东西也要做检验**」
> **尚未交付**；「机制存在」不等于「机制接上了」；他的门禁因此补了不变式 F
> 并**重新变红**。）

本轮 round 由这条追加验收派生（`ROUND.json` 的 `round_id` 与上一轮不同），
另附统筹方低优先级的 **D30**（文档里写死的计数漂移）。

> **交付状态说明（诚实记录）**：本节的代码与文档由上一会话产出。本会话进入时
> `git log` 里**还没有** `v1.26` 提交（工作区改动未提交、`.tmp/` 未清理，`reflog`
> 里也没有），于是**没有重做任何改动**，只做逐条**机械复验**（统筹方门禁 /
> `audit()` / 全量单测 / 探针 / 统筹方独立验收脚本）。复验期间上一会话完成并提交了
> **自包含的 `v1.26` 备份点**（提交信息以 `v1.26:` 开头，`docs/VERSIONS.md` 条目与
> 代码在同一次提交里；本会话对 §3.1 / §3.2 的订正也被它一并带入）。本会话随后确认
> 该提交内容与复验结果一致，并**归并掉一次重复的备份记录提交**（第二次
> `tests/backup.py` 因代码已提交而只追加了第二条 `v1.26` 记录，已 `git reset --hard`
> 撤回），最终 `git log --grep "^v1.26:"` **只有一个**提交。
> 判定依据全部是仓库里的机器事实（`git log` / `docs/VERSIONS.md` / `ROUND.json`），不是印象。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（位置全写）

| 事实 | 位置 / 机械依据 |
|---|---|
| 产出检验的机制**已存在**（`validate_result` / `_envelope_problems` / `audit`） | `tools/tool_contract.py:337`（v1.25 版 `validate_result`）、`:321`（`_envelope_problems`）、`:394`（`audit`） |
| 但**没有任何工具被登记** | `tools/tool_contract.py:105-108`（v1.25 版）：`ENVELOPE_TOOLS: set[str] = set()` —— 空集 |
| 于是 `Worker._invoke` 的产出检验**永远只走 accept 分支** | `core/worker.py:313`（v1.25 版）：`report = validate_result(name, result)`；`reject` 分支不可达（没有工具在登记表里） |
| 结果：用户要的「工具生成的东西也要做检验」**没有交付** | 统筹方复验输出 `audit().envelope_tools == []`；其门禁不变式 F 报红 |

**根因一句话**：**机制建好了，但没有接到任何工具上** ——
"能校验"与"有东西被校验"之间那条缝，正是本项目反复栽的形状。

### 2.2 复现命令与实测输出

**统筹方门禁**（本轮**修复前**我进入时先跑的基线，逐字粘贴）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe `
  D:\PythonProject\SimpleAgent2_Integration\03-scripts\tool-contract-lint.py
```

```
  工具数            : 18（下限 18）
  缺 additionalProperties : 0
  显式允许任意键    : 0
  properties 为空    : 2
  登记结果信封的工具: 0 ← 产出检验没接上

  [FAIL] **结果校验机制没有被接到任何工具上**（audit().envelope_tools 为空）⇒ 「工具生成的东西也要做检验」**尚未交付**：现在没有任何工具的结果会被校验。（机制建好了 ≠ 机制接上了 —— 这正是本门禁要治的那个形状。）
TOOLLINT state=fail problems=1 tools=18
```

**同一判据直接读 `audit()`**（也是统筹方复验时用的那条）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c `
  "from tools.tool_contract import audit; print(audit())"
```

```
{'tool_count': 18, 'not_closed': [], 'bad_type': [], 'required_not_in_properties': [],
 'bad_alias_targets': [], 'envelope_tools': [], 'unknown_envelope_tools': [],
 'alias_tool_count': 16, 'ok': True}
                    ^^^^^^^^^^^^^^^^^^ 空 ⇒ 「工具产出检验」这半边没交付
```

**为什么这是问题**：用户 2026-10-03 的原话是「**工具生成的东西也要做检验**」。
`envelope_tools` 为空时，18 个工具的产出**没有任何一条经过形状校验** ——
模型拿到的仍是各工具自报的形状，"每次生成的东西不一样"在**产出侧没有判据**。

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

`git diff --stat`（**不含**未跟踪的新文件，故单列；数字为最终值）：

```powershell
$ git -c safe.directory=<repo> diff --stat
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/prompts.py                          |   5 +-
 core/worker.py                           |  34 +++++-
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  85 +++++++++++++
 docs/MODULES.md                          |  43 +++++--
 docs/OPERATIONS.md                       |  29 ++++-
 docs/PENDING_DECISIONS.md                |   5 +-
 tests/README.md                          |   3 +-
 tests/diagnostics/probe_tool_contract.py |  74 ++++++++++-
 tests/unit/test_doc_invariants.py        |  61 ++++++----
 tests/unit/test_tool_contract.py         |   8 +-
 tools/__init__.py                        |  10 +-
 tools/tool_contract.py                   | 203 +++++++++++++++++++++++++++++--
 15 files changed, 505 insertions(+), 62 deletions(-)
```

新增文件（`git diff --stat` 不含未跟踪文件）：

```
docs/EVALUATION-ENVELOPE-WIRING.md          ← 本评估文档
tests/unit/test_tool_envelope.py            ← 35 项门禁（登记面 + 端到端 + 反空洞）
```

`docs/VERSIONS.md` **不在**上面的 `diff --stat` 里 —— 它由 `tests/backup.py` 在提交
**之后**追加 v1.26 记录、再 amend 进同一提交（备份机制的固有行为）。
所以以**备份点** `git show --stat <v1.26 提交>` 为准，它比 §3.1 多一个 `docs/VERSIONS.md`。

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `tools/tool_contract.py` | `ENVELOPE_TOOLS` | 空集合 → **登记表**（工具 → `kind`），非空：`check_and_run → verification` |
| 2 | 同上 | 新增 `build_envelope()` / `_error_object()` / `_parse_payload()` | **唯一一处**把工具产出装配成信封；错误信封的 `code/message` 从 `error`/`parsed_error`/`message` **抽出真实失败** |
| 3 | 同上 | 新增 `envelope_of()` / `unwrap_payload()` | 兼容旁路：读产出内容时取回 `data`（同一份事实，不是第二套读法） |
| 4 | 同上 | 新增 `STAGED_OUT_OF_ENVELOPE` / `envelope_policy()` | **分阶段迁移的判据公开声明**（其余 17 个工具各有理由） |
| 5 | 同上 | `audit()` / `describe_contract()` | 增加 `envelope_tool_count` / `bad_envelope_kinds`；`/profile` 公开登记面与 `built_by`/`staged` |
| 6 | `core/worker.py` | `_invoke` | **先套信封、再检验信封本体**（顺序反了会把工具中间形状判成不合规）；`_maybe_artifact` 用 `envelope_of()` 取回产出 |
| 7 | `tools/__init__.py` | 导出 | 公开 `build_envelope` / `envelope_of` / `unwrap_payload` / `envelope_policy` |
| 8 | `core/prompts.py` | `WORKER_SYSTEM` 第 7 条 | `check_and_run` 的内容在 `data` 里（`data.parsed_error` / `data.output`） |
| 9 | `tests/unit/test_tool_envelope.py`（新） | — | 35 项：登记面非空 + 端到端信封 + **摘掉登记立刻变红** |
| 10 | `tests/unit/test_tool_contract.py` | 登记面适配 | `ENVELOPE_TOOLS` 由 set 改 dict 的两处跟进（`tests/unit/test_tool_contract.py:190`、`:214`） |
| 11 | `tests/diagnostics/probe_tool_contract.py` | 新增第 [5] 段 | 统筹方要的机械输出：`envelope_tools` 非空 + `Worker._invoke` 的真实信封 + 反空洞 |
| 12 | `tests/unit/test_doc_invariants.py` | 第 10 组 | **D30**：扫 `upstream_event_kinds（当前 N 个）` 写法、纳入 `PENDING_DECISIONS.md`、新增"判据有牙齿"反向 |
| 13 | `docs/PENDING_DECISIONS.md` | 原行 118 | `upstream_event_kinds` 写「当前 13 个」→ 实测 18，改正（**D30 的另一处同族漂移**） |
| 14 | 文档面 | `CHANGELOG §40` / `MODULES §31` / `OPERATIONS §8.2` 第 13 项 + `§4.21` / `README` 文档表（含本评估文档） / `tests/README` 登记新测试 / 5 处版本戳 | 声明与实现同步 |

### 3.3 若两者不一致，差异是什么

两处需要说明：

1. **`docs/VERSIONS.md` 不在 `diff --stat` 里** —— 备份机制在提交后追加再 amend
   （见 §3.1）。
2. **`.tmp/` 是本轮临时件**（smoke 脚本与 `patch_docs.py`），**不进提交、已删除**
   （它在 `.gitignore` 里，属临时产物而非交付物）。

**行尾说明（本轮真踩了一次）**：`docs/MODULES.md` 与 `docs/OPERATIONS.md` 是
git 的 `-text` 文件（历史行尾混合被固化）。我第一版用编辑器直接改，**新插入的块
被写成另一种行尾**，`git diff --numstat` 从真实的 `34/7`、`27/0` 膨胀到
`113/86`、`73/46`（每行都像被重写）——**看起来像大改，实际只加了 40 行**。
已 `git checkout` 还原，改用**字节级替换**（先读原始字节、用该文件的行尾构造新旧串、
字节替换写回），两份文件现在 `bare LF = 0`，`numstat` 与真实改动一致（§3.1）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | ★ 验收：统筹方门禁**由红转绿** | 绝对路径 `python 03-scripts/tool-contract-lint.py`（§2.2） | `登记结果信封的工具: 1（check_and_run）`、`TOOLLINT state=ok problems=0 tools=18`，退出码 0 |
| 2 | ★ `audit().envelope_tools` **非空**（他追加验收的原话判据） | `python -c "from tools.tool_contract import audit; print(audit())"` | `'envelope_tools': ['check_and_run'], 'envelope_tool_count': 1` |
| 3 | ★ **端到端**：模型看到的就是信封本体 | `python tests/unit/test_tool_envelope.py` §[2] | `{"tool": "check_and_run", "ok": true, "kind": "verification", "data": {...}}` |
| 4 | ★ 反空洞：**摘掉登记 ⇒ 判据立刻变红** | 同上 §[3] | `envelope_tools == []`，且 `Worker` 返回退回旧形状 |
| 5 | 产出检验**有牙齿**：半成品信封 reject | 同上 §[4] | `action=reject` + `tool-result-invalid` |
| 6 | 错误信封的 `error` 描述**真实失败** | 同上 §[2] | `{"code": "AssertionError", "message": "boom", "category": "assertion_error"}`（不是占位文案） |
| 7 | 旧字符串结果仍可读（回退路径未改） | 同上 §[5] | 四条旧样例判定不变；未登记工具仍 `accept` / `legacy-json` |
| 8 | 未登记的工具产出**原样返回** | 同上 §[6] | `'OK:FILE|a.py|5|已写入 a.py'` 原样 |
| 9 | 探针机械输出（含反空洞） | `python tests/diagnostics/probe_tool_contract.py` | 全部 PASS，末行 `★ 全部通过：…信封真的接到工具上`，退出码 0 |
| 10 | 全量单测无回归 | `python tests/run_unit.py` | 通过数 ≥ 基线（41），退回 0 |
| 11 | **D30**：`PENDING_DECISIONS` 的事件数已对齐 | `python tests/unit/test_doc_invariants.py` | `PENDING_DECISIONS.md: 声明 18 / 实际 18  OK` |
| 12 | **D30**：判据有牙齿（不是恒真） | 同上 | `反向：合成声明 [999, 999] ⇒ 判据抓到` PASS |
| 13 | 文档面一致 / 契约符合性 / 前端契约 / 文档审查 | `test_doc_consistency` / `test_contract_conformance` / `test_frontend_contract` / `test_doc_review` | 全部 PASS（数字见 §4.1） |
| 14 | 统筹方**独立验收脚本**仍通过 | 绝对路径 `python 04-tests/cases/test_tool_norm_acceptance.py` | 11/11 通过 |

### 4.1 实测输出（粘贴原文）

**★ 验收①：门禁由红转绿**（同一命令，修复后）：

```
  工具数            : 18（下限 18）
  缺 additionalProperties : 0
  显式允许任意键    : 0
  properties 为空    : 2
  登记结果信封的工具: 1（check_and_run）


  ★ 全部工具的实参形状都是**封闭**的：传错键会被拒，而不是被静默忽略。
TOOLLINT state=ok problems=0 tools=18 item=D33
```

**★ 端到端信封 + 反空洞**（探针第 [5] 段，逐字节选）：

```
[5] ★ 产出检验**真的接上了**（统筹方追加验收 ③：机制存在 ≠ 机制接上）
==============================================================================
  audit().envelope_tools      : ['check_and_run']
  audit().envelope_tool_count : 1
  audit().unknown/bad_kinds   : [] / []
  未登记的工具（分阶段）       : 17 个
  PASS  ★ envelope_tools **非空**（v1.25 正是红在这里）
  PASS  登记面自洽（工具存在 + 类别名有效）
  Worker._invoke('check_and_run') 成功 → {"tool": "check_and_run", "ok": true, "kind": "verification", "data": {"ok": true, "syntax_passed": true, "run_ok": true, "exit_code": 0, "expected_exit": 0, "output": "2"}}
  PASS  ★ 模型看到的就是信封本体（ok/kind/data/error，不是旧形状）
  PASS  工具原产出原样在 data 里（没有丢信息）
  Worker._invoke('check_and_run') 失败 → ok=False error={"code": "AssertionError", "message": "boom", "category": "assertion_error"}
  PASS  ★ 失败信封的 error 描述**真实失败**（不是占位文案）
  PASS  失败细节没丢（data.parsed_error 仍可读，模型能定位）
  PASS  信封与旧判据兼容：错误信封 is_error_result=True

  ★ 反空洞：摘掉登记 ⇒ 门禁判据**立刻变红**（证明 [5] 不是摆设）
  摘掉后 envelope_tools = [] ⇒ 门禁 F 判据 bool(...) = False
  摘掉后 Worker 的返回: {"ok": true, "syntax_passed": true, "run_ok": true, "exit_code": 0, "expected_exit": 0, "output": "1"}
  PASS  摘掉登记 ⇒ envelope_tools 变空（回到 v1.25 的被退回状态）
  PASS  摘掉登记 ⇒ Worker 不再套信封（机制与声明同源）
  PASS  恢复登记 ⇒ 回到非空且自洽

★ 全部通过：形状封闭 · 未知键结构化拒绝 · 产出检验有牙齿 · 旧结果仍可读 · 信封真的接到工具上
```

**★ 新增门禁**（`tests/unit/test_tool_envelope.py`，35 项，节选关键三行）：

```
  PASS  ★ envelope_tools **非空**（v1.25 的门禁红点就是这里）
  PASS  ★ 模型看到的就是信封本体（ok/kind/data/error，不是旧形状）
  PASS  ★ 反空洞：摘掉登记 ⇒ Worker 不再套信封（回到旧形状 {ok,syntax_passed,...}）
通过 35/35
```

**★ D30：文档计数判据（扩面 + 反向）**：

```
[10] 文档声明的事件种类数 == 代码里的 18
  docs/FRONTEND_CONTRACT.md: 声明 18 / 实际 18  [上游 N 种事件]  OK
  docs/PENDING_DECISIONS.md: 声明 18 / 实际 18  [upstream_event_kinds 当前 N 个]  OK
  反向：合成声明 [999, 999] ⇒ 判据抓到
  PASS  ★ 事件数判据有牙齿（合成的陈旧声明必须被判不一致）
（并进主汇总：通过 35/35）
```

**★ 统筹方独立验收脚本**（我不改它，只跑）：

```
  11/11 通过
  [PASS] **产出检验有牙齿**：坏信封被判为有问题   check_and_run → {'action': 'reject', ...}
  audit() = {..., 'envelope_tools': ['check_and_run'], 'envelope_tool_count': 1, ...}
```

**套件汇总**（本轮实跑）：

```
tests/unit/test_tool_envelope.py             通过 35/35（新增）
tests/unit/test_tool_contract.py             通过 40/40
tests/diagnostics/probe_tool_contract.py     全部 PASS（扩到五段）
全量单测                                      通过 42/42
契约符合性 / 前端契约 / 文档一致性 / 文档不变量 44/44 · 25/25 · 35/35 · 35/35
文档审查                                      18/18
```

（全量单测的官方数字见 `docs/VERSIONS.md` 的 v1.26 备份记录。）

### 4.2 未验证的部分（诚实列出）

- **没有把 18 个工具全部登记**。本轮只登记 `check_and_run`（1/18），
  其余 17 个**分阶段迁移**，判据与逐条理由写在
  `tools/tool_contract.py::STAGED_OUT_OF_ENVELOPE` 并经
  `/profile.contract.tool_call_contract.result_envelope.staged` 公开。
  这是**刻意的分阶段决定**（不是遗漏）：登记 = 该工具的产出会被硬校验，
  而 `run_lint` / `check_syntax` 的产出正被 `pipeline.run_check` 直接读
  （`core/pipeline.py:43` 的 `_call` 直调工具函数，**不经** `Worker._invoke`），
  先动读法再登记更安全。**新增工具从本轮起必须直接登记。**
- **没有做真实模型 E2E**验证"模型读 `data.parsed_error` 后表现更好"——
  那需要 `simple-agent` 实例与模型配额，且读数应归统筹方的能力基线。
  本轮只做确定性证据（门禁 + 探针 + 单测）。
- **`check_and_run` 成功产出的 `kind` 取了新词 `verification`**。
  契约只把 `kind` 定义成"结果类别（string）"，没有封闭词表；
  若统筹方要求统一词表，改 `ENVELOPE_TOOLS` 的 value 一处即可（`audit()` 会跟着变）。
- **`docs/PENDING_DECISIONS.md` 的 13→18 是"同族漂移的第二处"**，
  但我**只扫了声明了事件数的文档**；其它数字（如前端 `event_count: 33`）
  不在本侧职责内，未做核对。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 18 种） | 本轮不发新事件；`verify` 事件 payload 本来就不含工具原始产出 |
| 事件 payload 键 | **无** | 同上 |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无**（顶层键仍 `description`/`function`/`parameters`/`profiles`） | 本轮**没有改任何工具的 schema**；只改了产出的装配层 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无**（仍 `1.1` / `1.0` / `1.0`） | 加性接线，不升版本 |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 未改规则表/词表/事件分区 |
| `/profile` 的 `contract.tool_call_contract.result_envelope` | **加性**：多 `envelope_tool_count` / `built_by` / `staged` | 前端只增不减，认不出就忽略 |
| **工具产出的形状**（模型可见的 tool message） | **改变**：登记工具现在是信封 | 契约 `result_envelope` 的**本来就是**这个要求（"新工具结果符合 result_envelope"）；未登记工具**产出不变** |

**结论**：**additive**（新增/接线，安全）。没有删除或改名任何前端依赖的事实面。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不需要**。工具名、参数语义、`TOOLS_MAP` 顶层结构、
  事件、端点、版本轴都没动；`/profile.contract` 只多了几个键。
- **有没有可能"问题被平移到对侧"**：没有。产出装配在**上游工具层内部**
  （`tools/tool_contract.py` + `core/worker.py`），判据与实现同侧；
  前端不承担任何新义务。前端的 `tool_result` 事件来自 bridge 钩子，
  本轮不涉及。
- **前端会静默少显示什么吗**：不会（纯加性）。
  仍保留统筹方记的 **D32**（bridge `/api/spec` 的 `tools[]` 不含 `parameters`）——
  那是前端侧可选增强，与本轮无关。

---

## 7. 不做的部分及理由（对应 C7）

- **不把 18 个工具一次性全登记**：登记即承诺产出受硬校验，而部分工具产出形状
  被别的读法依赖（`pipeline.run_check` 直调 `run_lint`/`check_syntax`）——
  一次性改会变成**破坏性变更**。故分阶段，判据与理由**公开声明**（§4.2）。
- **不改 `is_error_result()` 语义**：它是老读数的唯一判据，兼容纪律要求回退路径
  原样保留（§4.1 的旧结果判定表）。
- **不靠"把 `envelope_tools` 手工塞一个名字"来让门禁变绿**：登记的工具必须
  **真的经过 `build_envelope`** 且产出合规 —— 反空洞（§4.1）就是这条的分界线：
  摘掉登记后 `Worker` 也不再套信封（机制与声明同源）。
- **不动 `.interface_contract/`**：契约是统筹方权威源，只读。
- **不动对侧仓库与集成工作区**：只**只读地运行**了统筹方的门禁与验收脚本
  （§2.2、§4），未写入任何文件。
- **不做"顺手把其它文档数字全刷一遍"**：D30 只收口**本侧、可机械判定**的
  事件数声明；其它数字各有其所有者。

---

## 8. 回退点（C8）

- **回退命令**：见 `docs/VERSIONS.md` 的 `v1.26` 条目，
  `git log --oneline --grep "^v1.26:"` 定位提交，`git reset --hard <该提交>`。
- **回退会丢什么**：
  1. `ENVELOPE_TOOLS` 的登记（`check_and_run`）⇒ 统筹方门禁的**不变式 F 重新变红**，
     回到"机制建好了但没人用"；
  2. `build_envelope` / `_error_object` / `envelope_of` / `unwrap_payload` /
     `envelope_policy` 与 `Worker._invoke` 的接线 ⇒ 产出不再被校验；
  3. `STAGED_OUT_OF_ENVELOPE`（分阶段判据）与 `/profile` 的
     `envelope_tool_count` / `built_by` / `staged`；
  4. `tests/unit/test_tool_envelope.py`（回退点之后的东西全丢）、探针第 [5] 段、
     `WORKER_SYSTEM` 第 7 条的读法、`MODULES §31` / `OPERATIONS §4.21`、
     D30 的文档修正与第 10 组扩面。
- **回退不会丢什么**：v1.25 及以前的全部改动（18/18 封闭、别名归一、
  未知键结构化拒绝、`is_error_result` 回退路径仍在）。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 给出 `文件:行` 级根因（`tools/tool_contract.py:105-108`、`core/worker.py:313`）；§2.2 给出统筹方门禁**修复前**的机械输出与 `audit()` 原文 |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 14 条，逐条给命令（含统筹方两份脚本的绝对路径） |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘贴门禁红→绿、探针第 [5] 段、新增门禁、D30 反向、他侧验收 11/11 |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明 `VERSIONS.md`（备份机制带入）、`.tmp/`（临时件已删）与**行尾事故的真实 numstat 对照** |
| **C5** 对接口契约的影响已声明 | **满足**。§5 逐面声明；唯一"改变"的是登记工具的产出形状（契约本就要求的信封），未登记工具产出不变；`/profile` 新增键属加性 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：前端不需改；D32 仍是前端可选增强，本轮不产生义务 |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 明确"不一次性全登记（那会变成破坏性变更）、不改老判据语义、不手工塞名字骗门禁、不动对侧与契约" |
| **C8** 回退点明确 | **满足**。§8 给出 `v1.26` 定位命令与丢失项清单 |

**我希望统筹重点验证哪两条**：

1. **`envelope_tools` 非空且**真的接到工具上**：请重跑
   `03-scripts/tool-contract-lint.py`（应 `state=ok problems=0 tools=18`，
   且打印 `登记结果信封的工具: 1（check_and_run）`），并对照 §3.1 确认
   这不是"往登记表里塞了个名字"—— 摘掉它，`Worker._invoke` 的返回会**同时**
   退回旧形状（`tests/unit/test_tool_envelope.py` §[3] 的机械输出）。
2. **失败信封不丢信息**：`check_and_run` 失败时顶层 `error.code=AssertionError`、
   `error.message=boom`，而 `data.parsed_error`（frames/category/exit_code）
   仍完整可读 —— 信封是**分类**，不是把工具算出来的事实丢掉。
