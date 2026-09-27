# 变更评估文档 · `ARCH-D1`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 九节填写，自检标准见
> `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
> 契约目录是**只读资产**，本文件写在本仓库。

---

- **变更编号**：`ARCH-D1`
- **提出方**：前端（在 `EVALUATION-ARCH-A1A-A4` §7-1 请求裁决）→ 统筹方裁定
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**（实现时对应的一版）：`1.0.7`

---

## 1. 变更意图

> 引统筹方原话，不转述。

`DISPATCH` 原文：

> **D1 · 把 `ISSUE_RULES` 的 `P-phase-unknown` 改为 `both` / `degraded`**
>
> **背景**：前端在 `EVALUATION-ARCH-A1A-A4` §7-1 请求裁决。**我裁了：他们是对的。**
>
> 『前端自造了一个节点』与『上游删了一个阶段』**现象完全相同**，事实源判不出方向；
> 本契约 `boundary_definition` 明写这种情形归 `both`。
> 且 `empirical_evidence.S2` 已**实证**原判（`backend`/breaking）会把责任推给后端 ——
> 那其实是 bridge 自补的门禁节点。
>
> **真正的"上游删阶段"由 `U-removed-surface`(backend, breaking) 覆盖，不丢检测。**

统筹方转述的前端原话（我认同，且它是本次的**动机**）：

> 「我可以直接照抄 `backend` 让所有测试变绿，但那样就把一个**归因方向**的问题
> 藏进了『验收通过』里。」

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：对端（前端）上报一个本侧没有的阶段时，本侧原来**单方面推定"是上游删了阶段"**，
于是判给 `backend` / breaking —— 也就是**让后端去改一个后端没做错的事**。

**复现命令**（在改动前的 `0b07c55`（v1.11）上执行）：

```powershell
.venv\Scripts\python.exe -X utf8 -c "from core import contract as c; r=c.compare({'phases': c._pipeline_phases()+['manifest']}, ['/run']); print(r['verdict'], r['counts']); print([i['code'] for i in r['backend']])"
```

**实际输出**（`0b07c55` 上实测）：

```
backend-action {'ops': 0, 'backend': 1, 'frontend': 0, 'both': 0}
['P-phase-unknown']
```

**改动后**（同一条命令）：

```
need-negotiation {'ops': 0, 'backend': 0, 'frontend': 0, 'both': 1}
[]
```

**为什么这是问题**：`manifest` 是 bridge 在 `write` 与 `check` 之间**自补的门禁节点**，
上游从来没删过任何阶段。原判把"前端自造节点"说成"后端删阶段"，
**归因方向反了**，而 `backend-action` 的下一步文案会让运维去找后端。
契约 `empirical_evidence.S2` 已在真实服务上打出了这个错误（`verdict=backend-action`）。

> 这也是 `CHANGE-PROCESS` §2 说的那种"自评看不出来"的问题：
> 我上一轮的测试里**恰好把这个错误判据写成了期望值**（`"上游删了阶段 → backend-action"`），
> 于是它一直是绿的 —— **绿的是测试，错的是判据**。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `core/contract.py` | `ISSUE_RULES["P-phase-unknown"]` | `OWNER_BACKEND` → `OWNER_BOTH`；`SEV_BREAKING` → `SEV_DEGRADED`；`why`/`action` 改为"方向判不出来，先确认方向"，并注明删除场景由 `U-removed-surface` 兜底 |
| 2 | `tests/unit/test_contract_attribution.py` | `test_peer_rules` | 该用例的期望 owner 由 `OWNER_BACKEND` 改为 `OWNER_BOTH` |
| 3 | `tests/unit/test_contract_attribution.py` | `test_verdict` | 原断言 `"上游删了阶段 → backend-action"` 改为 `need-negotiation`；**新增两条**：该情形下 backend 栏必须为空、`U-removed-surface` 仍为 backend/breaking |
| 4 | `docs/FRONTEND_CONTRACT.md` | §6.4 提醒 / §6.5 规则表 / §6.6 指纹值 | 同步新判定，并写明这条的历史（原判 `backend`/breaking 是错的） |
| 5 | `docs/MODULES.md` | §23 | 指纹当前值 `740c48d2` → `af6bfe2a` |
| 6 | `docs/EVALUATION-ARCH-A1B.md` | §4 指纹段 | 加注：该值是变更时点快照，`ARCH-D1` 后已变为 `af6bfe2a` |
| 7 | 本文件 + `README.md` + `docs/CHANGELOG.md`（§28）+ 版本戳（5 个上游文档）+ `docs/VERSIONS.md` | — | 文档与登记 |

**实际 diff 规模**（`git diff --stat`，截至本文件**定稿前**实测）：

```
core/contract.py                        |  22 +++++++++++++++---
 docs/EVALUATION-ARCH-A1B.md             |  10 +++++++---
 docs/FRONTEND_CONTRACT.md               |  15 +++++++++++---
 docs/MODULES.md                         |   2 +-
 tests/unit/test_contract_attribution.py |  22 +++++++++++++++++++---
 5 files changed, 61 insertions(+), 10 deletions(-)
```

**stat 之外、同一次提交还会带入的**（显式声明）：
本文件（新增）、`README.md`（登记本文件）、`docs/CHANGELOG.md`（§28）、
5 个上游文档的版本戳、`docs/VERSIONS.md`（备份机制追加）。
评审时以备份点的 `git show --stat` 为准。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | `P-phase-unknown` 已改为 `both` / `degraded` | `python -c "from core import contract as c; r=c.ISSUE_RULES['P-phase-unknown']; print(r.owner, r.severity)"` | `both degraded` |
| 2 | 该情形**不再判给后端** | 见 §2 复现命令 | `verdict=need-negotiation`、`counts.backend=0` |
| 3 | **真正的"上游删阶段"仍有检测**（由 `U-removed-surface` 兜底） | `python -c "from core import contract as c; r=c.ISSUE_RULES['U-removed-surface']; print(r.owner, r.severity)"` | `backend breaking` |
| 4 | 该兜底**不依赖对端上报**（比对的是本侧冻结面） | `python tests/unit/test_contract_attribution.py` | `合成故障 U-removed-surface 被识别` PASS |
| 5 | 归因与新规则表**与契约 v1.0.7 逐条一致** | `python tests/unit/test_contract_conformance.py` | `通过 37/37` |
| 6 | 指纹按设计发生了变化（改归属/级别必变） | `python -c "from core import contract as c; print(c.responsibility_fingerprint())"` | `af6bfe2a`（原 `740c48d2`） |
| 7 | 归因测试整体通过 | `python tests/unit/test_contract_attribution.py` | `通过 99/99` |
| 8 | 全量回归无退化 | `python tests/run_unit.py` | `通过 27/27` |
| 9 | 文档与代码一致（含规则数/词表/版本戳） | `python tests/unit/test_doc_consistency.py` + `test_doc_invariants.py` | `35/35`、`28/28` |
| 10 | 真实正向链路未受影响 | `python tests/bench/run_levels.py 1 1` | `L1 PASS … phase=record` |

**实测输出**（粘贴原文）：

主张 1/3/6：

```
owner   : both
severity: degraded
指纹    : af6bfe2a
```

主张 2：

```
verdict : need-negotiation
counts  : {'ops': 0, 'backend': 0, 'frontend': 2, 'both': 1}
  [both] P-phase-unknown | degraded
```

主张 4/7 相关断言：

```
PASS  合成故障 U-removed-surface 被识别
PASS    U-removed-surface 归给 backend
PASS  P-phase-unknown 被识别
PASS    P-phase-unknown 归给 both
PASS  对端报了未知阶段 → need-negotiation（不再推定是后端删的）
PASS  同一情形下 backend 栏必须为空（归因方向已修正）
PASS  真正的删除场景由 U-removed-surface 覆盖（backend/breaking）
```

**未验证的部分**（诚实列出）：

- **未与前端对拍**：前端的 `/api/audit` 是否也把该情形判 `both`/degraded，
  本侧无法验；本侧只保证**与契约 v1.0.7 逐条一致**（主张 5 间接证明）。
- **未验证 `need-negotiation` 在前端界面上如何呈现**：那是前端的事。
  但可预期：它从"指向后端的 breaking"变成"需协商的 degraded"，
  前端若按 verdict 上色，会从"要后端改"变成"要人看"。
- **未做真实删除场景的端到端演练**：主张 3/4 是**规则层面**的覆盖证明
  （`U-removed-surface` 的 owner/severity + 合成故障用例），
  没有真的去删一个阶段再跑一遍对账。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 12 种未变 |
| 事件 payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | 5 个未变（本变更**不改阶段**，只改"看到未知阶段时怪谁"） |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 前者仍 `1.0` |
| 端点路径 | **无** | — |
| **`.interface_contract/` 覆盖的规则与词表** | **有：规则表内容变更** | `P-phase-unknown` 的 owner 与 severity 变了；**这是跟随契约 v1.0.7 已做的改动**，不是本侧单方面改判 |
| `/contract/check` 响应 | **无结构改动** | 该 code 会从 `backend` 栏移到 `both` 栏 —— 属**内容**变化，非字段变化 |
| `/profile` → `contract` 段 | **无结构改动** | `responsibility` 里该项的 owner/severity 变化；`responsibility_fingerprint` 由 `740c48d2` 变 `af6bfe2a` |

**additive 还是 breaking**：
规则的**归属与级别变更**在语义上属**行为变更**（同一输入给出不同的 owner 与 verdict）——
但它**不是本侧发起的**：契约 v1.0.7 已先行改判，本侧是**跟随**。
`CONTRACT_VERSION` 是否该升由统筹方定；本侧**未擅自升**（§7）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**要，且方向比以前更顺**：前端上报 `phases` 时
  仍应过滤自补门禁节点（那是 `gap_G3` 的要求，未变）。
  变化在于：**它若不慎混进来，结论从"指责后端"变成"需协商"** ——
  不再把责任推给后端。
- **有没有可能"问题被平移到对侧"**？**没有，而且这次正是把平移纠回来**。
  原判就是一次平移：前端自造节点 → 判给后端。改判后归 `both`（需协商），
  即**承认本侧判不出方向**，而不是推给任何一侧。
- **前端会静默少显示什么吗**？有一处**降级**需要说明：
  该问题的 severity 由 `breaking` 降为 `degraded`。按既有纪律，
  `breaking` = 前端会真的看不到/画错、必须有人改；`degraded` = 有兜底但仍应修。
  这里降级是对的：前端**已经**为未知阶段做了"运行时补节点 + 通用图标"的兜底
  （其 SPEC §3），所以它**本来就看得见**，只是显示成"未声明"。
  于是它不该再是 breaking。**这不是静默少显示，是 severity 语义归位。**

---

## 7. 不做的部分及理由（对应 C7）

- **不擅自升 `CONTRACT_VERSION`**：本变更的语义由契约 v1.0.7 定义，本侧跟随。
  是否升版本号属统筹方判断（本侧只承诺"指纹变了要能被察觉"，已由指纹机制承担）。
- **不改 `PHASE_ORDER` 或阶段集合**：本变更只改"看到未知阶段时怪谁"，
  阶段清单一个字没动 —— 这条边界必须守住，否则就真成了"改语义"。
- **不改 `P-phase-missing`（前端/degraded）**：方向明确的项不动。
- **不给 `P-phase-unknown` 加"自动判方向"的逻辑**（例如拿事件流里的
  `manifest` 是否由 bridge 自补过来判别）：那是本侧**没有的事实源** ——
  bridge 自补了什么只有前端知道。硬猜等于把幻觉塞进判据，
  违反本项目一贯纪律（判据必须机器可判定）。
  `action` 里因此写的是"**先确认方向**"，而不是自动下结论。
- **不做 A2/A3/A4**（前端侧）；**不做 A5**（决定，无动作）。

---

## 8. 回退点（对应 C8）

- **回退命令**：
  ```powershell
  git log --oneline --grep "^v1.12:"    # 取到备份点 hash
  git reset --hard <该 hash>
  ```
- **上一稳定点**：`v1.11` @ `0b07c55`（`git reset --hard 0b07c55`）
- **回退会丢什么**：`P-phase-unknown` 的 `both`/`degraded` 判定、三条新断言、
  文档同步与指纹更新（回退后指纹回到 `740c48d2`）。
  回退后该情形会**重新判给后端**（即回到 §2 的问题状态），
  且**会与契约 v1.0.7 不符**（符合性测试会红）—— 所以回退等于同时回退契约认知。

---

## 9. 自检结论

| 标准 | 结论 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了同一条命令在改动前后的输出对比（改动前取自 `0b07c55`） |
| **C2** 每条主张带命令 | **满足** | §4 十条主张各配一条可独立执行的命令 |
| **C3** 输出支持主张 | **满足** | §4 粘贴了真实输出（owner/severity、指纹、verdict/counts、断言结果） |
| **C4** 改动清单与实际一致 | **满足** | §3 表 + `git diff --stat`（5 文件 61/10），并显式列出 stat 之外同批提交的文件 |
| **C5** 契约影响已声明 | **满足** | §5：规则内容变更（跟随契约 v1.0.7）、响应无字段变化、指纹变化；阶段集合未动 |
| **C6** 对侧影响已评估 | **满足** | §6：指出 severity 由 breaking→degraded 的**降级**并说明为何正确；明确未平移、反而纠回平移 |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7：不擅自升版本、不改阶段集合、**不硬猜方向**（本侧无该事实源） |
| **C8** 回退点明确 | **满足** | §8：v1.12 定位命令 + 回退会丢什么（含"会与契约不符"） |

- **我希望统筹重点验证**：
  1. **主张 2/3 的配对**：改判后"是否真的没丢检测" ——
     我给的证明是 `U-removed-surface`（backend/breaking）的规则层面覆盖
     + 合成故障用例。请判断这够不够，或需要一次真实的端到端删除演练。
  2. **severity 降级是否会被前端误读为"可以不修"**：
     我按 SPEC §3 的兜底能力论证它该是 `degraded`。
     若前端运维界面把 `degraded` 归入"忽略"，请告诉我 ——
     那说明我该把 `why` 写得更强，而不是改级别。
  3. **`action` 里"先确认方向"这种写法是否可接受**：
     它把一步人工判断写进了机器产出的建议里。我认为这是诚实的
     （本侧确实没有该事实源），但若统筹方要求 action 必须是可执行命令，
     我可以改成"向 bridge 索取 `bridge_gate_steps`"这类具体动作。

---

## 10. 追加：§9 的三个问题已被契约回答，且带出半个新任务

本节在提交前追加。**统筹方没有口头答复，而是把回答写进了契约 v1.0.7** ——
本侧相应补了实现。这也是**符合性门禁先发现的**
（它报 `规范上报字段集合相等` 失败：契约的 `canonical_fields` 由 9 项变 10 项）。

### 10.1 §9(3) 的答案：把"先确认方向"变成**可机械判定**

契约新增 `bridge_gate_steps`（上报字段第 10 项）与
`client_report_schema.phase_unknown_decision_tree`：

| 情形 | 方向 | 效果 |
|---|---|---|
| 1) 未知阶段 ∈ `peer.bridge_gate_steps` | **frontend** | `action` 直接指名前端，不必人猜 |
| 2) ∈ 上游 `FROZEN_PHASES` 且 ∉ 当前 `PHASE_ORDER` | **backend** | 同时被 `U-removed-surface` 抓到 |
| 3) 其余 | **both** | 保持"先确认方向" —— **不伪造方向** |

**关键约束**（契约 `effect_on_owner`）：**owner 不变**（仍 `both`/`degraded`），
树**只用于锐化 `action` 文案**。

### 10.2 本侧的对应实现

| 项 | 做法 |
|---|---|
| 上报字段 | `PEER_FIELDS` 增 `bridge_gate_steps`（第 10 项，与契约 `canonical_fields` 对齐） |
| 方向实现 | 新增 `_phase_unknown_direction(phase, peer) -> (direction, action)`，严格按树的三支 |
| 文案出口 | 新增 `Issue.action_override`（**只改文案**）；`to_dict()` 用 `self.action_override or r.action` |
| 机器可读 | `evidence.direction` ∈ {`bridge_gate_step`, `upstream_removed_frozen_phase`, `undetermined`} |

**为什么 owner 不能逐条覆盖**：`Issue` 的 owner/severity 一向全部来自规则表。
若允许逐条覆盖，就出现"归属有两个来源"，A1 的"两个入口同一 owner"便无从保证。
所以我把"方向"限制在**文案 + evidence** 上，并写成断言：
`action_override 只改 action，owner/severity 仍来自规则表`。

### 10.3 追加的主张与验证（续 §4 编号）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 12 | 三支的方向判定都正确 | `python tests/unit/test_contract_attribution.py` | `情形1 … direction=bridge_gate_step`、`情形3 … direction=undetermined` PASS |
| 13 | 三支的 **owner/severity 完全相同**（树不改归属） | 同上 | `三种情形的 owner/severity 完全相同` PASS |
| 14 | `action_override` 不影响 owner/severity | 同上 | `action_override 只改 action…` PASS |
| 15 | `bridge_gate_steps` 已进 `PEER_FIELDS` | 同上 | `bridge_gate_steps 已进 PEER_FIELDS…` PASS |
| 16 | 与契约 `canonical_fields` 仍相等 | `python tests/unit/test_contract_conformance.py` | `通过 38/38` |

**实测输出**（粘贴原文）：

```
--- 情形1：对端声明 manifest 是自补门禁节点 ---
  owner   : both | severity: degraded
  direction: bridge_gate_step
  action  : **方向已定**：`manifest` 是对端**自己声明的** bridge 自补门禁节点（见 `bridge_gate_steps`）→ **前端**：…
--- 情形3：对端没提供 bridge_gate_steps ---
  owner   : both | severity: degraded
  direction: undetermined
  action  : 先确认方向：若该阶段是前端自补的门禁节点 → 前端上报时过滤…
```

### 10.4 一个我核过的边界（写进断言，避免后人误判）

`failed` 在 `FROZEN_PHASES` 里但不在 `PHASE_ORDER`，**看似**会命中情形 2。
实际不会：本规则的触发条件是"对端报的阶段 ∉ 全部 `CyclePhase` 值"，
而 `failed` 是 `CyclePhase` 的成员，所以它**根本不触发本条规则**。
情形 2 只有在上游真把某阶段从 `CyclePhase` 删掉时才可达。
已写成**一对**断言（助手判情形 2 **且** peer 报 `failed` 不触发规则）。

### 10.5 §9(1)(2) 也已被回答

- **§9(2)**（severity 降级会不会被误读为"可以不修"）→ 契约新增
  `response_contract.severity_consumer_obligation`：**"`degraded` 必须被呈现，
  不得被静默丢弃"**，并明确"**生产方不要因为担心被忽略而把 degraded 抬回 breaking**"。
  我保持 `degraded` 的判断得到契约背书。
- **§9(1)**（主张 2/3 的"不丢检测"证明够不够）→ 契约在
  `rule_crosswalk.upstream_only` 的 `P-phase-unknown` note 里自己写了
  "真正的『上游删阶段』由 `U-removed-surface`(backend,breaking) 覆盖，
  不因此丢失检测"，与我的论证一致。

### 10.6 追加后的验证总览

| 测试 | 项数 |
|---|---|
| `tests/unit/test_contract_attribution.py` | **113** |
| `tests/unit/test_contract_conformance.py` | **38** |
| 全量单测 | **27/27** |
| 文档一致性 / 不变量 / 审查 | 35/35 · 28/28 · 18/18 |
| 真实 E2E | `L1 PASS … phase=record` |

**追加后未验证的部分**（诚实补充）：

- **未验证前端真的会上报 `bridge_gate_steps`**：那是前端的事；
  本侧只保证"给了就能判、没给就诚实说判不出"。
- **未验证前端界面如何呈现 `degraded`**：契约已把它写成消费方义务
  （不得静默丢弃），但落实在界面上，本侧无法验。

### 10.7 给统筹方的一处**契约内不一致**（我只报不改）

`interface-contract.json` 的 `phases_partition.consequence` 仍写着：

> "上游会对 `manifest` 报 P-phase-unknown(**breaking, owner=backend**)"

而 `rule_crosswalk.upstream_only` 里该条**已改为 `both` / `degraded`**。
同一份契约里两处不一致 —— 建议同步（**我没有、也不会改契约目录**）。

另：`open_items.awaiting_side_confirmation` 仍列着 `ops_report_constraint`
（"待后端选择"），但该约束已由 `resolution` 结清（本侧 `OPS-1` 已答复），
`awaiting_user_approval` 里也仍写着"当前 v1.0.2"而契约已是 v1.0.7。
两条都属**契约内部台账过期**，一并报上。
