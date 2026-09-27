# 变更评估文档 · `ARCH-D7`（含裁决② / D10 / D5）

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 九节填写，自检标准见
> `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
> 契约目录是**只读资产**，本文件写在本仓库。
>
> 本文件按统筹方"或合并为一份"的许可，合并了本轮四项：
> **D7（必修）**、**裁决②（`CONTRACT_VERSION` 升 1.1）**、**D10（建议）**、**D5（建议）**。

---

- **变更编号**：`ARCH-D7`（D7 必修；附带裁决② / D10 / D5）
- **提出方**：统筹（D7/D10/D5 由统筹方实测提出；裁决② 由统筹方裁定）
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**（实现时对应的一版）：`1.0.19`

---

## 1. 变更意图

> 引统筹方原话，不转述。

**D7（必修）**：

> `bridge_gate_steps` 在 HTTP 路径上是**死代码**。… **`main.py` 的 `ContractPeer`**：
> ❌ **没有该字段** → Pydantic **静默丢弃**。
> **后果**：那条分支**永远不可能在 HTTP 上触发**。我实测三种情形
> （给了 `bridge_gate_steps` / 没给 / 阶段是 `ghost`），`action` **逐字相同**。
>
> **这是一类很典型的验证盲区：验证方式与生产路径不一致。**
> 函数级测试全绿，接口层静默失效。

**裁决②**：

> `decision_opened` 的键改名：**你的核实不完整，因此这是 breaking**…
> **因此裁决：`CONTRACT_VERSION` 应升 `1.1`。**
> 理由：契约的价值在于"破坏性改动 = 版本一定变了"这条**无条件**成立；
> 一旦开始按"影响大不大"逐次判断，这条信号就没人敢依赖了。

**D10（建议）**：

> 你新加的门禁查的是"payload 键撞 `_emit` 的位置参数名"…
> **但还有一类没查**：`bridge/runner.py` 把 `**payload` 在后展开，
> 所以 payload 键能**覆盖记录字段** `seq` / `ts` / `kind` / `run_id`。

**D5（建议）**：

> **建议加一条"逐行比对"**：解析 §6.5 规则表的每一行，
> 与 `ISSUE_RULES[code]` 的 `(owner, severity)` 对齐，不一致即 FAIL。
> **为什么值得**：这类漂移**没有症状**。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 D7：同一输入，两条路径结果不同

**现象**：`bridge_gate_steps` 只在 `PEER_FIELDS` 声明与 `contract.py` 的分支里，
`main.py` 的 `ContractPeer` 没有它 → Pydantic 静默丢弃 → HTTP 上那条分支不可达。

**复现命令**（改动前，`cbb3154` @ v1.13）：

```powershell
.venv\Scripts\python.exe -X utf8 -c "import main,sys; print('bridge_gate_steps' in main.ContractPeer.model_fields)"
```

**实际输出**（改动前）：

```
False
```

**改动后**：

```
True
```

**为什么这是问题**：这是**没有症状的失效** —— 字段名对、接口不报错、文档齐全，
只有把"声明 → 请求模型 → 逻辑使用"三层对起来才看得见。
而**生产路径（前端运维机制）走的就是 HTTP**：
进程内直调 `compare()` 一切正常，接口层静默失效。

### 2.2 裁决②：我漏判了"扁平化覆盖"

**现象**：我判定 payload 键 `kind` → `decision_kind` 为**非破坏性**，
依据是"已核实前端未读该键"。**这个核实不完整** —— 只查了显式读取，
漏了 `bridge/runner.py` 的扁平化：`record = {seq, ts, kind, run_id, goal, attempt, **payload}`
（payload **在后展开** ⇒ 能覆盖记录字段）。

**复现**（读前端代码即可判定，是**读代码**而非跑命令的事实）：

```
改名前后 ev.kind 的取值：
  改名前：payload.kind 覆盖记录 kind → ev.kind = 决策种类（repeated_failure）
  改名后：不再覆盖            → ev.kind = 'decision_opened'（事件类型）
前端 run.ts:717 : kind: String(ev.kind || '')  → 决策种类显示成事件名
```

**为什么这是问题**：`CONTRACT_VERSION` 的意义是"**破坏性改动 = 版本一定变了**"这条
无条件信号。我按"影响大不大"判它不用升，**等于在削弱信号本身**。

### 2.3 D10：payload 键能覆盖记录字段

**复现**（改动前无门禁）：AST 扫 `_emit` 调用点，只比对"位置绑定参数名"，
未比对记录字段。实测 payload 键里 `goal`（11 处）与 `attempt` 命中记录字段名，
**目前值相同、无可观测危害**，但结构上与 `decision_opened.kind` 同型。

### 2.4 D5：条数对不代表每一行对

**复现**（改动前的门禁确实抓不到）：

```
文档声称的规则数 == ISSUE_RULES 条数              → PASS（都是 23）
FRONTEND_CONTRACT 列全了 4 个归属值 / 6 个结论值  → PASS（词表都出现过）
但 §6.5 里 P-phase-unknown 那行的 owner/severity 写错 → 无人发现
```

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `main.py` | `ContractPeer` | **补 `bridge_gate_steps: list[str] \| None = None`**（D7 本体）；docstring 里"8 项"改为"10 项"并写明 Pydantic 静默丢弃的风险 |
| 2 | `core/contract.py` | 常量区 | `CONTRACT_VERSION` `1.0` → **`1.1`**（裁决②）；新增 `RECORD_FIELDS` 与 `PAYLOAD_SHARED_KEYS`（D10） |
| 3 | `core/contract.py` | `describe()` | 新增 `event_record_fields` / `payload_shared_keys` |
| 4 | `tests/unit/test_frontend_contract.py` | `[2.5]` | 补**记录字段**门禁（D10）：payload 键不得撞未豁免的记录字段；豁免项必须有理由 |
| 5 | `tests/unit/test_contract_conformance.py` | 新增 `[12]` | **经 HTTP 请求模型**断言 `bridge_gate_steps` 生效（D7） |
| 6 | `tests/unit/test_contract_conformance.py` | `[4]` | 版本轴断言改为**方向感知**：本侧领先 = 台账滞后（打印待更新）；台账领先 = 硬失败 |
| 7 | `tests/unit/test_doc_invariants.py` | 新增 `[8.1]` | **§6.5 规则表逐行比对** `(owner, severity)`（D5） |
| 8 | `docs/FRONTEND_CONTRACT.md` | §3.1/§3.2/§6.2/§6.4/§6.5/§8 | 版本裁决与理由、字段数 10、拆开 `P-schema-*` 合并行 |
| 9 | `docs/MODULES.md` | §23 | `CONTRACT_VERSION = "1.1"`、`RECORD_FIELDS`/`PAYLOAD_SHARED_KEYS` |
| 10 | 本文件 + `README.md` + `docs/CHANGELOG.md`（§30）+ 版本戳（5 个上游文档）+ `docs/VERSIONS.md` | — | 文档与登记 |

**实际 diff 规模**（`git diff --stat`，截至本文件**定稿前**实测）：

```
 core/contract.py                        |  38 +++++++++--
 docs/FRONTEND_CONTRACT.md               |  75 +++++++++++++++----
 docs/MODULES.md                         |  16 +++-
 main.py                                 |  34 +++++++--
 tests/unit/test_contract_conformance.py |  67 ++++++++++++++-
 tests/unit/test_doc_invariants.py       |  48 ++++++++++++
 tests/unit/test_frontend_contract.py    |  36 ++++++++-
 7 files changed, 275 insertions(+), 39 deletions(-)
```

**stat 之外、同一次提交还会带入的**（显式声明）：
本文件（新增）、`README.md`（登记本文件）、`docs/CHANGELOG.md`（§30）、
5 个上游文档的版本戳、`docs/VERSIONS.md`（备份机制追加）。
评审时以备份点的 `git show --stat` 为准。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | `ContractPeer` 收到了 `bridge_gate_steps` | `python -c "import main; print('bridge_gate_steps' in main.ContractPeer.model_fields)"` | `True` |
| 2 | 契约的每个 `canonical_field` 都在请求模型里 | `python tests/unit/test_contract_conformance.py` | `契约有、模型缺: 无` |
| 3 | **经 HTTP** 上报该字段会**改变 action**（D7 的决定性证据） | 同上 `[12]` 组 | `已上报 → action: **方向已定**…` |
| 4 | 方向已定后 owner **仍是 both**（决策树不改归属） | 同上 | `PASS` |
| 5 | `CONTRACT_VERSION` 已升 `1.1` | `python -c "from core import contract as c; print(c.CONTRACT_VERSION)"` | `1.1` |
| 6 | 版本轴断言方向感知（本侧领先=台账滞后，不混为漂移） | `python tests/unit/test_contract_conformance.py` | `→ 契约台账滞后：请更新…observed_value = 1.1` |
| 7 | payload 键不撞记录字段（D10） | `python tests/unit/test_frontend_contract.py` | `未豁免却撞记录字段的 payload 键: 无` |
| 8 | §6.5 规则表**逐行**与代码一致（D5） | `python tests/unit/test_doc_invariants.py` | `从 §6.5 解析到 23 行` / `逐行不一致: 无` |
| 9 | 该逐行门禁**真的会抓**（负向测试） | `python _neg_test_d5.py`（临时脚本） | 退出码 `1`，指出 `owner 文档=backend 代码=both` |
| 10 | 全量回归无退化 | `python tests/run_unit.py` | `通过 31/31` |
| 11 | 真实链路未受影响 | `python tests/bench/run_levels.py 1 1` | `L1 PASS … phase=record` |

**实测输出**（粘贴原文）：

主张 3/4（`[12]` 组）：

```
  ContractPeer 字段: ['bridge_gate_steps', 'contract_version', 'frontend_endpoints',
   'frontend_event_kinds', 'ops', 'phases', 'report_keys', 'schema_version',
   'upstream_endpoints', 'upstream_event_kinds']
  契约有、模型缺: 无
  bridge_gate_steps 是否穿过请求模型: 是
  未上报 bridge_gate_steps → action: 先确认方向：若该阶段是前端自补的门禁节点 → 前端上报时过滤（或另用…
  已上报 bridge_gate_steps → action: **方向已定**：`ghost` 是对端**自己声明的** brid…
  PASS  bridge_gate_steps 能穿过请求模型
  PASS  HTTP 路径上 bridge_gate_steps 改变了 action（分支真的可达）
  PASS  方向已定后 owner 仍是 both（决策树不改归属）
```

主张 6：

```
  契约 CONTRACT_VERSION=1.0 本侧=1.1
  → 契约台账滞后：请更新 version_axes.CONTRACT_VERSION.observed_value = 1.1
  PASS  契约台账与本侧一致（滞后期允许，已打印待更新）
```

主张 7：

```
  记录字段（payload 可覆盖）: ['attempt', 'goal', 'kind', 'run_id', 'seq', 'ts']
  显式豁免的公共键: {'goal': '整条链路（Event / 前端记录 / 归因）都要它；值恒等于记录的 goal，覆盖后无差别',
                    'attempt': 'cycle 级尝试序号；前端记录里同名同义，覆盖后无差别'}
  未豁免却撞记录字段的 payload 键: 无
```

主张 8/9：

```
  从 §6.5 解析到 23 行（规则表共 23 条）
  未在表里出现的 code: 无
  逐行不一致: 无
--- 负向测试（把 P-phase-unknown 那行改回 后端/breaking）---
  逐行不一致: ['P-phase-unknown: owner 文档=backend 代码=both',
               'P-phase-unknown: severity 文档=breaking 代码=degraded']
  退出码  : 1 (非 0 = 抓住了)
  结论    : ✅ 门禁有效
```

**未验证的部分**（诚实列出）：

- **没有跑统筹方的 `03-scripts/wiring-audit.py`**：它在统筹工作区，本侧访问不到。
  我用**等价的自建断言**替代（主张 2/3：契约字段集合 ⊆ 请求模型字段集合 + 经 HTTP 生效）。
  若他们的脚本仍有输出，请贴给我 —— 那是更强的交叉验证。
- **未验证前端 D8 的修复**：`run.ts` 是否已改读正确字段是前端的事。
- **未做真实的双入口对拍**（D6 归前端）：本侧只保证"经 HTTP 的自家入口"正确。
- **`PAYLOAD_SHARED_KEYS` 的"无危害"是推理，不是实测**：结论是"值相同 ⇒ 覆盖无差别"；
  没有去构造值不同的场景验证危害（构造它需要让 cycle 的 goal 与 payload 的 goal 不同，
  而那本身就是要修的状态）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 12 种未变 |
| 事件 payload 键 | **无（本轮）** | 上一轮的 `decision_opened.kind → decision_kind` 已登记 |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| **`CONTRACT_VERSION`** | **有：`1.0` → `1.1`** | 裁决② 要求；本侧执行 |
| `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | — |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 规则表 23 条、归属/级别全同 |
| **`/contract/check` 请求体**（新增声明） | **有：additive** | `ContractPeer` 补 `bridge_gate_steps`（此前被静默丢弃） |
| **`/profile` → `contract` 段**（新增声明） | **有：additive** | `event_record_fields` / `payload_shared_keys` |

**additive 还是 breaking**：请求体与 `/profile` 都是 **additive**；
唯一**破坏性**的是 `CONTRACT_VERSION` 本身（升 `1.1`），而它是**裁决要求的动作**。

**需要统筹方登记进契约的三项**（本侧不改契约）：

1. `version_axes.axes.CONTRACT_VERSION.observed_value`：`1.0` → **`1.1`**
   （载体是 `backend: core/contract.py`，我是权威、台账跟着走）；
2. `client_report_schema` 无需改（10 项已齐）—— 但建议记一条
   **"请求模型必须与 canonical_fields 一一对应"** 的接线要求（D7 的教训）；
3. `response_contract` 可增 `event_record_fields` / `payload_shared_keys`
   （供前端与 wiring-audit 交叉核对）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**D8 是他们的**（`run.ts` 改读正确字段）。
  本侧本轮**不要求前端做任何事**：`bridge_gate_steps` 他们**已经在发**
  （统筹方核过 `buildReport()` 真的发送它，`AuditRequest` 也收），
  断点只在我这一侧。
- **有没有可能"问题被平移到对侧"**？**没有**。D7 的断点经三层核对后
  **唯一落点在我这里**；D10 的门禁在**我产出的 payload**上；
  D5 的门禁在**我的文档**上。
- **前端会静默少显示什么吗**？
  - `bridge_gate_steps` 接上后**只会让 `action` 更具体**（"方向已定"），
    不新增字段、不改 owner/severity —— 对前端是纯收益；
  - **`CONTRACT_VERSION` 从 `1.0` 变 `1.1` 会让前端的版本比对产生一次提示**
    （他们若声明 `implements_contract_version`，会看到"后端领先"）——
    这是**刻意**的：正是这条信号在起作用。

---

## 7. 不做的部分及理由（对应 C7）

- **不去调 `wiring-audit.py`**：它在统筹工作区，本侧访问不到；
  用等价自建断言替代并**在 §4 未验证部分明确写出**。
- **不做真实双入口对拍（D6）**：`/api/audit` 是前端入口，A1a 也是他们的架构项。
- **不构造"值不同的 goal 覆盖"场景**去证明危害：那需要人为制造不一致状态，
  而 `PAYLOAD_SHARED_KEYS` 的结论是"值相同 ⇒ 无差别"，属于**可推理事实**。
- **不做 D5 之外的文档全量语义审查**：逐行比对只覆盖 `(owner, severity)` 两列
  （`why` / `action` 是自然语言，比对它们会引入误报 —— 与 `manifest` 只报结构事实同纪律）。
- **不动 `.interface_contract/`**、**不做架构级 P1–P5**。

---

## 8. 回退点（对应 C8）

- **回退命令**：
  ```powershell
  git log --oneline --grep "^v1.14:"    # 取到备份点 hash
  git reset --hard <该 hash>
  ```
- **上一稳定点**：`v1.13` @ `cbb3154`（`git reset --hard cbb3154`）
- **回退会丢什么**：`ContractPeer.bridge_gate_steps`（D7）、`CONTRACT_VERSION=1.1`、
  两条新门禁（记录字段 / §6.5 逐行）、HTTP 路径断言、本文件与文档同步。
- **回退后的已知后果**：`bridge_gate_steps` 会**重新被静默丢弃**
  —— 而 `docs/FRONTEND_CONTRACT.md` 当时已写明"把自补节点报到它里面"，
  于是**文档会指示一个不生效的行为**（这正是 D7 被升级为必修的原因）。

---

## 9. 自检结论

| 标准 | 结论 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了四条复现（含 D7 的一行命令与改动前后输出） |
| **C2** 每条主张带命令 | **满足** | §4 十一条主张各配一条可独立执行的命令 |
| **C3** 输出支持主张 | **满足** | §4 粘贴了真实输出（含 HTTP 路径的 action 对比、负向测试退出码） |
| **C4** 改动清单与实际一致 | **满足** | §3 表 + `git diff --stat`（7 文件 275/39），并显式列出 stat 之外的登记文件 |
| **C5** 契约影响已声明 | **满足** | §5：`CONTRACT_VERSION` 升 `1.1`、两处 additive、三项待登记 |
| **C6** 对侧影响已评估 | **满足** | §6：D8 归前端、本侧不要求前端改动、版本提示是刻意信号 |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7：不越界访问他人工作区、不做他人的验收项、不构造人为状态 |
| **C8** 回退点明确 | **满足** | §8：v1.14 定位命令 + 回退后的已知后果 |

- **我希望统筹重点验证**：
  1. **主张 3（HTTP 路径）** —— 这是 D7 的决定性证据，也是我上一轮**漏掉的那条路径**。
     请用你们的 `wiring-audit.py` 交叉核一遍：期望从 `1 problems` 变 **0**；
  2. **裁决② 的执行**：`CONTRACT_VERSION=1.1` 已就位，请更新 `version_axes` 台账
     （我的 `[4]` 组会在那一行打印"台账滞后"，直到你们更新，**不会**误判为漂移）；
  3. **D10 的豁免是否认同**：我把 `goal` / `attempt` 列为"故意共用、无覆盖危害"
     并写进 `PAYLOAD_SHARED_KEYS`（附理由）。若你们认为这两个也该禁，
     我可以改调用点，但当前判断是**它们值恒相同、覆盖无差别**。
