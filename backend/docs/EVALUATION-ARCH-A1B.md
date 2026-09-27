# 变更评估文档 · `ARCH-A1B`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 九节填写，自检标准见
> `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
> 依据：`ARCHITECTURE-CHECKLIST.md` 的 **A1**（用户已批准）。
> 契约目录是**只读资产**，本文件写在本仓库。

---

- **变更编号**：`ARCH-A1B`（架构清单 A1 的 backend 子项）
- **提出方**：用户（原话见 §1）→ 统筹方拆解为 A1–A5
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**（实现时对应的一版）：`1.0.6`

---

## 1. 变更意图

> 引用户/统筹的原话，不转述。

用户原话（`ARCHITECTURE-CHECKLIST.md` 开头）：

> 「架构级别层面的按照你的想法执行吧，写在清单里，我都批准了」

统筹方 `DISPATCH` 给我这一项的原话：

> **A1b —— 让 `/contract/check` 自述权威范围**
> A1 的决定是"**按职责切分**两个对账入口，而不是合并"：
> `GET/POST /contract/check`（上游）→ **跨侧对账**：归属、严重度、结论、`both` 协商项
> `GET/POST /api/audit`（bridge）→ **本地自检**：bridge 自身声明 vs 实现 vs 环境
> **要你做的**：`/contract/check` 的响应里加一个**自述权威范围**的字段
> （名字你定，例如 `authority` / `scope`），说明它是**跨侧归属的权威**。
> 属 **additive**，不破坏消费方。

同一条 A1 的验收标准里与我有关的两条（清单原文）：

> - 一个测试：对同一跨侧不一致，两个入口给出的 **owner 归属一致**
> - 文档（两边）说明各自权威范围

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：两个对账入口（上游 `/contract/check`、bridge `/api/audit`）都能对**同一件**
跨侧不一致给结论，而**入口自己不说自己有权对哪些事下结论**。
消费方（前端运维界面）拿到两份结论时无从判断该信谁，
于是"两套入口"就退化成"两个答案"。

**复现命令**（与本侧改动**前**的 `d5062ba`（v1.10）对比；当下跑则是改后）：

```powershell
# 改动前：响应里没有任何自述权威范围的字段
.venv\Scripts\python.exe -X utf8 -m core.contract --json | python -c "import json,sys; print(sorted(json.load(sys.stdin).keys()))"
```

**实际输出**（`d5062ba` 上实测）：

```
['backend', 'both', 'contract_version', 'counts', 'frontend', 'issues', 'next',
 'note', 'ops', 'schema_version', 'upstream_facts', 'upstream_ok', 'verdict']
```

**改动后**（同一条命令）：

```
['authority', 'backend', 'both', 'contract_version', 'counts', 'frontend', 'issues',
 'next', 'note', 'ops', 'schema_version', 'upstream_facts', 'upstream_ok', 'verdict']
```

**为什么这是问题**：A1 的决定是"**按职责切分而不是合并**"（理由：`/api/audit`
看得见上游看不见的东西）。切分要成立，前提是**两侧各自声明自己管什么** ——
否则切分只把"一个模糊的答案"变成了"两个模糊的答案"。
本项补的就是本侧那一半声明。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `core/contract.py` | 常量区 | 新增 `AUTHORITY_SCOPE`（本入口权威范围自述：covers / not_covers / rule_source / counterpart / policy） |
| 2 | `core/contract.py` | 新增函数 | `responsibility_fingerprint()`：规则表内容指纹（只覆盖 `code\|owner\|severity`） |
| 3 | `core/contract.py` | `compare()` | 响应新增 `authority`（**A1b 本体**） |
| 4 | `core/contract.py` | `describe()` | 新增 `authority` / `responsibility_count` / `responsibility_fingerprint` |
| 5 | `tests/unit/test_contract_conformance.py` | 新增第 [10] 组 | **A1 验收**：crosswalk ↔ 本侧规则表的 owner 一致性 |
| 6 | `tests/unit/test_contract_conformance.py` | 新增第 [11] 组 | **A1b 验收**：`authority` 字段内容 + 完整性与稳定性凭据 |
| 7 | 本文件 + `README.md` + `docs/FRONTEND_CONTRACT.md` + `docs/MODULES.md` + `docs/CHANGELOG.md`（§27）+ 版本戳（5 个上游文档）+ `docs/VERSIONS.md` | — | 文档与登记（见下） |

**实际 diff 规模**（`git diff --stat`，截至本文件**定稿前**实测，仅代码与测试）：

```
core/contract.py                        |  57 ++++++++++++++++
 tests/unit/test_contract_conformance.py | 111 +++++++++++++++++++++++++++++++-
 2 files changed, 166 insertions(+), 2 deletions(-)
```

**stat 之外、同一次提交还会带入的**（显式声明，避免被判"改动清单与实际不一致"）：
本文件（新增）、`README.md`（登记本文件）、`docs/FRONTEND_CONTRACT.md`（权威范围一节）、
`docs/MODULES.md`（§23）、`docs/CHANGELOG.md`（§27）、
5 个上游文档的版本戳、`docs/VERSIONS.md`（备份机制追加）。
评审时以备份点的 `git show --stat` 为准。
（上一轮我在这里漏了 `VERSIONS.md`，被自己的 C4 口径纠正过，这次先写上。）

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | 响应含自述权威范围的字段 | `python -m core.contract --json` → 看 `authority` | `authority.id == "cross-side"` |
| 2 | 它说明了**不**负责什么（划清边界，不只说管什么） | 同上 | `not_covers` 非空且点名 `/api/audit` |
| 3 | `/profile` 也带同一份 authority（前端离线可读） | `python tests/unit/test_contract_conformance.py` | `authority` 一致 |
| 4 | 规则表**完整**（23 条全在，无遗漏） | `python tests/unit/test_contract_conformance.py` | 契约规则全集 == 本侧集合 |
| 5 | 规则表**稳定**（有内容指纹，前端可判断变没变） | `python -c "from core import contract as c; print(c.responsibility_fingerprint())"` | 8 位十六进制 |
| 6 | 指纹**只覆盖 code/owner/severity**：改文案不变、改归属必变 | 见 §4 下方实测 | 文案变→指纹同；owner 变→指纹不同 |
| 7 | **A1 验收：跨侧归属只有一个判据** | `python tests/unit/test_contract_conformance.py` → [10] 组 | `owner 不一致: 无`、`severity 不一致: 无` |
| 8 | 该一致性检查**不是空转** | 同上 | `完整比对的: 8 行`（≥5） |
| 9 | 全量回归无退化 | `python tests/run_unit.py` | `通过 27/27` |
| 10 | 契约符合性整体仍成立 | `python tests/unit/test_contract_conformance.py` | `通过 37/37` |
| 11 | 真实正向链路未受影响 | `python tests/bench/run_levels.py 1 1` | `L1 PASS … phase=record` |

**实测输出**（粘贴原文）：

`GET /contract/check` 的 `authority` 块：

```json
{
  "id": "cross-side",
  "role": "authoritative-for-cross-side-attribution",
  "covers": [
    "归属（owner：ops / backend / frontend / both）",
    "严重度（severity：breaking / degraded / info）",
    "结论（verdict：6 个取值）",
    "`both` 协商项",
    "运行态 ops 事实的 code 与归属"
  ],
  "not_covers": [
    "本地环境细节：前端是否构建、钩子是否装上、bridge 自身声明是否自洽 —— 那是 `/api/audit` 的权威范围"
  ],
  "rule_source": "/profile → contract.responsibility（机器可读的完整规则表，23 条，随本入口一起发布）",
  "counterpart": {
    "entry": "/api/audit",
    "authority": "local-self-check",
    "cross_side_attribution": "以本入口为准（bridge 应引用本入口的 code 与 owner）"
  },
  "policy": "同一件跨侧不一致只有一个判据；两个入口给出同一 owner。"
}
```

`/profile` → `contract`：

```
responsibility_count      = 23
responsibility_fingerprint= 740c48d2
authority.id              = cross-side
responsibility 条目数      = 23
```

指纹覆盖范围（主张 6）：

```
改 why/action 后指纹: 740c48d2 （应与上面相同）
改 owner 后指纹    : 4ff7e560 （应不同）
原指纹              : 740c48d2
恢复后指纹          : 740c48d2 （应回到原值）
```

> **注**：上面是**本次变更时点的快照**。之后 `ARCH-D1`（契约 v1.0.7）
> 把 `P-phase-unknown` 由 `backend/breaking` 改判为 `both/degraded`，
> 指纹随之从 `740c48d2` 变为 **`af6bfe2a`** —— 这正是本指纹的设计意图：
> **改归属/级别一定变**。当前值以 `/profile` 的
> `contract.responsibility_fingerprint` 为准（见 `docs/CHANGELOG.md` §28）。

A1 一致性（主张 7/8）：

```
crosswalk 共 17 行；无上游等价（bridge 本地项）8 行
完整比对的: 8 行；部分等价（只比 owner）: 2 行
SPLIT（无可单判 owner）: ['backend.dead_event -> U-dead-event']
映射到本侧不存在的 code: 无
owner 不一致: 无
severity 不一致: 无
```

**未验证的部分**（诚实列出）：

- **没有真的调用 `/api/audit`**：它在另一个仓库。主张 7 是拿**契约里的
  `rule_crosswalk`（两侧商定的统一映射）**当锚点做的**静态一致性**验证，
  不是一次真实的双入口对拍。真正的端到端对拍需要前端实现完 A1 的
  "bridge 引用上游 code"那一半之后才能做。
- **`/api/audit` 是否真的加了 `authority` 字段**：那是前端的事，本侧无法验。
- **指纹的跨版本稳定性**：本侧只保证"改了就变"；"变了要升 `CONTRACT_VERSION`"
  是纪律，靠契约对账与人工评审，本侧没有自动拦阻（也不该由本侧单方面拦）。
- **未压测**：`responsibility_fingerprint()` 每次调用重算 23 条，开销可忽略（未实测）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 12 种未变 |
| 事件 payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | 5 个未变 |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 前者仍 `1.0`（本改动是 additive） |
| 端点路径 | **无** | 未增删路由 |
| `.interface_contract/` 覆盖的规则与词表 | **规则内容无改动**（23 条，code/owner/severity 全同，指纹 `740c48d2`） | 见下两条新增声明 |
| **`/contract/check` 响应**（新增声明） | **有：additive** | 新增 `authority` |
| **`/profile` → `contract` 段**（新增声明） | **有：additive** | 新增 `authority` / `responsibility_count` / `responsibility_fingerprint` |

**additive 还是 breaking**：全部 **additive（新增）**。没有删改任何字段、规则、
词表取值、端点。旧消费方按既有纪律忽略不认识的键即可。

**需要统筹方登记进契约的两项**（本侧不改契约）：

1. `response_contract` 增 `authority`（A1b 的产出，与 `warnings` 同类：响应新增字段）；
2. `profile_additions` 增 `responsibility_count` / `responsibility_fingerprint`
   （"机器可读的权威 code 列表"的完整性与稳定性凭据）；
3. A1 的状态列可勾选"一个测试：两个入口 owner 归属一致"——
   本侧已提供该测试（§4 主张 7），但**它是静态锚定版**，见 §4 未验证部分。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不需要为本项改动**，但 A1 整体需要前端做两件事
  （清单里已列，不是本项引入的）：
  1. `/api/audit` 响应加自述权威范围字段（对称声明）；
  2. bridge 的跨侧判定改为**引用本入口的 code 与 owner**，不再自下结论。
  本项为第 2 件事提供了**可引用的稳定凭据**：`/profile` →
  `contract.responsibility`（23 条完整规则表）+ `responsibility_fingerprint`
  （变没变一眼可判）+ `authority.counterpart`（明确"跨侧以本入口为准"）。
- **有没有可能"问题被平移到对侧"**？**没有**。本项只**声明本侧的权威范围**，
  不含任何"把职责推给前端"的动作；反而在 `not_covers` 里**主动划出**
  本侧不该管的范围（本地环境细节），交给 `/api/audit`。
- **前端会静默少显示什么吗**？**不会**（本次全是新增字段）。
  但有一个**能力性提示**：前端若仍以 `/api/audit` 作为跨侧结论来源，
  会与 A1 的决定不一致 —— 这不是"静默少显示"，而是需要前端按清单改；
  本侧已在 `authority.counterpart.cross_side_attribution` 里写明"以本入口为准"。

---

## 7. 不做的部分及理由（对应 C7）

> 明确划出没碰的范围。

- **不去调用/修改 `/api/audit`**：它在另一个仓库，属前端；本侧只声明自己那一半。
- **不合并两个入口**：A1 的决定就是"切分而不是合并"，理由（观测能力）本侧接受。
- **不改任何规则内容**：本项与规则表内容无关；指纹在改动前后都是 `740c48d2`。
- **不为 `authority` 造"机器可读的机器判据"**：它是**声明性文本 + 结构化字段**，
  本侧只做"字段存在且内容自洽"的断言（§4 主张 2/3）。
  内容是否贴切仍需人判断 —— 与既有 `responsibility` 规则表的 why/action 同性质。
- **不做 A2/A3/A4**：全在前端（适配层与部署形态）。
- **不做 A5**：它是决定，无动作。

---

## 8. 回退点（对应 C8）

- **回退命令**：
  ```powershell
  git log --oneline --grep "^v1.11:"     # 取到备份点 hash
  git reset --hard <该 hash>
  ```
- **上一稳定点**：`v1.10` @ `d5062ba`（`git reset --hard d5062ba`）
- **回退会丢什么**：`authority` 自述字段、规则表指纹与条数、A1 一致性测试
  （第 [10] 组）与 A1b 验收测试（第 [11] 组）、本评估文档与相应文档段落。
  回退后 `/contract/check` 会**重新变成"不自述权威范围"**（即回到 §2 的问题状态）。

---

## 9. 自检结论

| 标准 | 结论 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了同一条命令在改动前后的键列表对比（改动前输出取自 `d5062ba`） |
| **C2** 每条主张带命令 | **满足** | §4 十一条主张各配一条可独立执行的命令 |
| **C3** 输出支持主张 | **满足** | §4 粘贴了真实输出（authority 块、凭据、指纹三态、A1 一致性计数） |
| **C4** 改动清单与实际一致 | **满足** | §3 表 + `git diff --stat`（2 文件 166/2），并**显式列出** stat 之外同批提交的文件（含 `VERSIONS.md`） |
| **C5** 契约影响已声明 | **满足** | §5：规则内容零改动；两处 additive 新增已声明；并列出需统筹方登记的三项 |
| **C6** 对侧影响已评估 | **满足** | §6：本项不需前端改动；A1 整体需前端两件事（非本项引入）；未平移问题 |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7：只声明本侧范围，主动划出 `not_covers`，未合并入口、未碰前端 |
| **C8** 回退点明确 | **满足** | §8：v1.11 定位命令 + 回退会丢什么 |

- **我希望统筹重点验证**：
  1. **A1 验收第 2 条的形式**：我做的是**静态锚定版**
     （拿契约 `rule_crosswalk` 当两侧商定的映射，断言本侧 owner 与 `unified_owner` 一致），
     **不是真实的双入口对拍**。请判断这算不算满足"两个入口 owner 归属一致"；
     若要求真实对拍，需等前端 A1 前半部分落地后由统筹方组织端到端验证
     ——**我会配合提供 fixture 与预期 owner**。
  2. **`authority` 的字段设计**是否与前端即将加的同名字段对称
     （我用了 `id` / `role` / `covers` / `not_covers` / `rule_source` /
     `counterpart` / `policy`）。若前端已定形状，**请以他们的为准告诉我**，
     我改我这侧去对齐 —— 这类"声明形状"应当两侧一致，不该各写各的。
  3. **是否需要把 `responsibility_fingerprint` 写进契约**：它是"权威 code 列表
     稳定"这一条的凭据；若统筹方认可，建议登记进 `response_contract` 或
     `profile_additions`，让前端有据可依。
