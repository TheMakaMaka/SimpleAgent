# 变更评估文档 · `OPS-1`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 九节填写，自检标准见
> `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
> 契约目录是**只读资产**，本文件写在本仓库。

---

- **变更编号**：`OPS-1`（契约里记为 `ops_report_constraint`，状态从
  `AWAITING_SIDE_CONFIRMATION` 变为**本侧已确认**）
- **提出方**：统筹（在 2026-09-26 复验 W-B1/W-B2 时实测发现）
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**（实现时对应的一版）：`1.0.4`

---

## 1. 变更意图

> 引统筹方原话，不转述。

工作单 `WORK-ORDER.md`（后端）原文：

> **`ops.service_down` 通过 `POST /contract/check` 上报是自相矛盾的** ——
> 能成功发出这个 POST，就证明上游**可达**。实测它照样返回 `ops-action`：
>
> **为什么这条要紧**：`ops` 优先判定 + 一个可能过期的标志 =
> **一条陈旧的 `service_down` 会把其余全部结论压掉**。而 `ops-action` 的下一步文案是
> "这一条修好之前后面都不成立" —— 于是一个本可修复的后端/前端问题会被它挡住。

DISPATCH 原文：

> **三个选项，请选一个**（选项 1 为统筹倾向）：… **契约里这条语义暂标记
> `AWAITING_SIDE_CONFIRMATION`，等你回复。**

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：随**成功送达**的 `POST /contract/check` 一起上报 `ops.service_down=true` 时，
返回 `verdict=ops-action`，且 `next` 宣称"这一条修好之前后面所有结论都不成立" ——
于是一条**按传输层事实已不可能为当前值**的标志，把后端/前端那些**本可修复**的结论全压掉。

**复现命令**（在**修复前**的提交 `d739c91`（v1.8）上执行；peer 文件内容见下）：

```powershell
# peer.json：8 项规范声明 + ops 里报一个 service_down
'{"contract_version":"1.0","schema_version":"1.0",
  "upstream_event_kinds":["cycle_start","plan","task_result","manifest","syntax","lint",
                          "verify","cycle_end","rollback_denied","decision_opened",
                          "decision_notified","decision_action"],
  "phases":["plan","write","check","verify","record"],
  "upstream_endpoints":["/run","/encode","/profile","/contract/check"],
  "ops":{"service_down":true}}' | Set-Content peer.json -Encoding UTF8

.venv\Scripts\python.exe -X utf8 -m core.contract --peer peer.json `
  --routes "/,/run,/encode,/profile,/contract/check"
```

**实际输出**（在 `d739c91` 上实测，粘贴原文）：

```
verdict = ops-action
counts  = {'ops': 1, 'backend': 0, 'frontend': 0, 'both': 0}
next    = **运维**改：环境/运行态问题（服务没起 / 前端没构建 / 配置坏）。**这一条修好之前，后面所有结论都不成立。**
  [ops] O-service-down | 先把服务起起来；这一条修好之前后面都不成立
```

**为什么这是问题**：`ops` 优先判定的**理由**是"服务不可达时后面一切不成立"。
但请求**成功送达**这个事实本身就把该理由**证伪**了 —— 服务此刻是可达的。
前提不成立却仍按该前提压制结论，报告就不再可行动。

> 补充一点统筹方也点到的：选项 1「只加一条 info、不改 verdict」买到的是**可见性**，
> 危害（陈旧标志压掉全部结论）**仍在**。所以本侧采用的是**选项 2 的语义**
> （标注为"上次已知状态"）**+ 选项 1 的可见性**（`warnings`）**+ 一条判定修正**
> （被传输层证伪的事实不驱动结论）。见 §4 主张 3。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `core/contract.py` | 常量区 | 新增 `OPS_STALE_BY_TRANSPORT = {"O-service-down"}` + 判据注释 |
| 2 | `core/contract.py` | `peer_issues()` | ops 事实若属上述集合，`evidence` 增 `current/semantics/contradicted_by` |
| 3 | `core/contract.py` | `compare()` | 结论驱动集排除被证伪项；新增顶层 `warnings: []`；`ok` 时 `next` 追加提示 |
| 4 | `core/contract.py` | `describe()` | 增 `ops_stale_by_transport` |
| 5 | `core/contract.py` | `_cli()` | peer 文件按 `utf-8-sig` 读（容忍 BOM，实测踩过） |
| 6 | `tests/unit/test_contract_attribution.py` | `test_verdict` | 改两条旧断言（原先期望 `service_down→ops-action`，那正是要改掉的行为）；新增 8 条语义断言 |
| 7 | `tests/unit/test_doc_invariants.py` | 新增第 9 组 | 行尾未被悄悄改动（见下） |
| 8 | `docs/FRONTEND_CONTRACT.md` | §6.2 / §6.5 / §7 | `service_down` 语义、`warnings`、版本轴；契约版本引用 v1.0.0→v1.0.4 |
| 9 | `docs/MODULES.md` | §23 | `OPS_STALE_BY_TRANSPORT` 与 `warnings` 说明 |
| 10 | 本文件 + `README.md` + `docs/CHANGELOG.md`（§25）+ `docs/PENDING_DECISIONS.md` + 版本戳（5 个上游文档）+ `docs/VERSIONS.md` | — | 按本仓库约定登记与升戳（见下"stat 之外"） |

**实际 diff 规模**（`git diff --stat`，截至本文件**定稿前**实测）：

```
CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/contract.py                        |  60 +++++++++++++++++--
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       | 102 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |  38 +++++++++++-
 docs/MODULES.md                         |  26 +++++---
 docs/OPERATIONS.md                      |   2 +-
 docs/PENDING_DECISIONS.md               |  25 +++++++-
 tests/unit/test_contract_attribution.py |  38 +++++++++++-
 tests/unit/test_doc_invariants.py       |  61 +++++++++++++++++++++++++
 11 files changed, 335 insertions(+), 24 deletions(-)

（新增未跟踪）docs/EVALUATION-OPS-1.md   274 行
```

> 上表的 5 个"版本戳"文件里，`CYCLE.md` / `ARCHITECTURE.md` / `OPERATIONS.md` 只改了 1 行
> （`同步至 CHANGELOG §24` → `§25`）；`README.md` 是版本戳 + 登记本文件一行。
> **本文件自身随后被追加这段 stat**，故它的最终行数略大于 274 —— 文件清单不变。
>
> **评审时以备份点的 `git show --stat` 为准。实测 v1.9 备份点是 13 个文件**
> （= 上面 11 个改动 + 本文件新增 + `docs/VERSIONS.md`）。最后那一个由
> `tests/backup.py` 在提交后追加 v1.9 记录带入，属备份机制的固有行为
> （`VERSIONS.md` 里那条记录本身就写着"回退到哪"）。
> 其余 12 个与上表 #1–#10 逐条对应。

### 3.1 过程中发现并顺手修掉的另一个问题（与契约无关，属本侧内部）

第一次 `git diff --stat` 显示 `core/contract.py` **1770 行变更**，而真实改动只有 60 行。
根因：`pathlib.Path.write_text()` 在 Windows 上把 `\n` 翻译成 `\r\n`，
而我用一段 Python 脚本批量替换版本引用，**把该文件的 LF 整体翻成了 CRLF**
（本仓库行尾**本来就是混合的**：`core/*.py` 多为 LF，`README.md`/`CYCLE.md`/`docs/*.md` 多为 CRLF）。

已按字节恢复为与 HEAD 一致，并把它变成机械门禁（`test_doc_invariants.py` 第 9 组）：
**逐文件比对"工作区是否含 CRLF"与"HEAD 是否含 CRLF"**，不一致即 FAIL。
已做**负向测试**确认它会抓（临时翻转 `core/contract.py` → 退出码 1 → 按字节恢复）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | 规则表仍是 23 条，归属/级别**零改判** | `python -c "import core.contract as c; print(len(c.ISSUE_RULES)); print(c.OWNER_ORDER)"` | `23` / `('ops','backend','frontend','both')` |
| 2 | `frontend_not_built` 与可达性不矛盾 → **仍判 `ops-action`** | `python -m core.contract --peer peer_fnb.json --json` | `verdict=ops-action`，`warnings=[]` |
| 3 | `service_down` **不再驱动结论**，但仍出现在 ops 栏且带语义标注 | 同上（peer 带 `service_down`） | `verdict=ok`，`counts.ops=1`，`evidence.semantics=last_known_state` |
| 4 | 陈旧 `service_down` **不再掩盖**真实问题 | peer = `service_down` + `contract_version=0.1` | `verdict=frontend-action`（不是 `ops-action`） |
| 5 | 矛盾对使用方可**看见** | 同主张 3 | `warnings` 非空且含"本请求已成功送达" |
| 6 | 未知运行态事实仍被忽略（additive 安全，原有行为不回退） | peer 带 `ops={"some_future_fact":true}` | `counts.ops=0`，`verdict=ok` |
| 7 | 归因门禁全过 | `python tests/unit/test_contract_attribution.py` | `通过 97/97` |
| 8 | 行尾门禁全过，且它真的会抓 | `python tests/unit/test_doc_invariants.py` | `通过 28/28` |
| 9 | 全量回归无退化 | `python tests/run_unit.py` | `通过 26/26` |
| 10 | 真实正向链路未受影响 | `python tests/bench/run_levels.py 1 1` | `L1 PASS … phase=record` |

**实测输出**（命令 2/3/4/5/6 合并采集，粘贴原文）：

```
===== ops = {service_down: true} =====
verdict : ok
counts  : {'ops': 1, 'backend': 0, 'frontend': 0, 'both': 0}
warnings: ["`O-service-down` 报了 true，但**本请求已成功送达** —— 该标志只能是「上次已知状态」，不是此刻状态。已按契约语义保留在 ops 栏，**未参与结论判定**（真·服务不可达只可能在前端本地发现：那时它根本发不出这个请求）。"]
next    : 契约一致，无需处理。（注意：ops 栏有一条**上次已知状态**的标志未参与判定，见 warnings）

===== ops = {frontend_not_built: true} =====
verdict : ops-action
counts  : {'ops': 1, 'backend': 0, 'frontend': 0, 'both': 0}
warnings: []
next    : **运维**改：环境/运行态问题（服务没起 / 前端没构建 / 配置坏）。**这一条修好之前，后面所有结论都不成立。**

===== ops = {} =====
verdict : ok
counts  : {'ops': 0, 'backend': 0, 'frontend': 0, 'both': 0}
warnings: []
```

`/profile` → `contract` 段实测：

```
ops_fact_rules        : {'service_down': 'O-service-down', 'frontend_not_built': 'O-frontend-not-built'}
ops_stale_by_transport: ['O-service-down']
owner_values          : ['ops', 'backend', 'frontend', 'both']
verdict_values        : ['ok', 'ops-action', 'backend-action', 'frontend-action', 'need-negotiation', 'multi-action']
rule count            : 23
```

**未验证的部分**（诚实列出）：

- **未测真实前端**：`warnings` 的展示效果在前端那一侧，本侧只保证字段存在且语义正确。
- **未测"外部监视者"场景**：若将来真有一个外部监视者持有带时间戳的观测，
  本侧通道**暂不支持带时间戳**（§7 说明为何不做）。
- **未做长稳测试**：单次请求语义已验，未做并发/重复上报的压力测试。
- 主张 1 的"零改判"是**与我上一轮实现对比**得出的（规则表内容逐条未动），
  不是与契约 JSON 自动比对 —— 自动比对需读 `.interface_contract/`，属只读资产、
  且该目录不在我的测试路径里。

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
| `.interface_contract/` 覆盖的规则与词表 | **规则表内容无改动**（仍 23 条，code/owner/severity 全同） | 但**新增了报告的 `warnings` 字段**与**语义确认**，属对契约的 additive 影响（见下） |
| **报告响应结构**（新增声明） | **有：additive** | `compare()` 返回值新增顶层 `warnings: []` |
| **`/profile` → `contract` 段**（新增声明） | **有：additive** | 新增 `ops_stale_by_transport` |

### 5.1 勘误（2026-09-26 第二轮统筹指令后补，不改上文结论）

统筹方在 `DISPATCH` 里要我重读契约新增的 `response_contract`。照做时发现
**本侧早先的一处声明与契约不符**，与本次 `ops` 语义无关，但属 C5 范畴，如实登记：

| 项 | 我早先以为 | 契约实际 |
|---|---|---|
| `ops` 是否在 `client_report_schema.canonical_fields` 里 | **不在**（8 项）—— 所以我刻意不把它放进 `PEER_FIELDS` | **在**（**9 项**，v1.0.2 起就收了） |

后果不是行为错误（`POST /contract/check` 一项都收），而是
**`describe().peer_report_fields` 只列 8 项，与契约的 9 项对不上** ——
一个拿两者做比对的消费方会看到漂移。

已修：`PEER_FIELDS` 补 `ops`（注明它是"观测"而非"声明"）。
**抓出它的是本侧新增的 `tests/unit/test_contract_conformance.py` 第一次运行**——
那个测试直接读契约原文断言，不依赖我的记忆。

**additive 还是 breaking**：全部为 **additive（新增）**。
没有删除或改名任何字段、规则、词表取值；未知字段的消费方（前端）按既有纪律降级显示。

**需要统筹方做的一件事（我不改契约）**：把 `ops_report_constraint.status`
从 `AWAITING_SIDE_CONFIRMATION` 更新为"后端已确认，采用选项 2 语义 + 选项 1 可见性"，
并把 `warnings` 字段登记进 `client_report_schema`（或相应章节）。
本侧**未也不会**编辑 `.interface_contract/` 下任何文件。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**要，但很小，且不阻断**：
  1. 前端若按 `verdict == "ops-action"` 来显示"环境问题"，需知道
     **`service_down` 现在不会单独触发它** —— 环境横幅应改看 `ops` 栏或 `warnings`；
  2. 建议展示 `warnings`（新增字段，缺失时为 `[]`，可安全忽略）。
- **有没有可能"问题被平移到对侧"**？**没有，且这正是本变更要防的**。
  修正发生在**判定语义**上（本侧拥有该通道的语义定义），不涉及把职责推给前端：
  规则 `O-service-down` 的 `owner=ops` 未变，"服务不可达归运维"这一归属**未改**；
  改的只是"它在同步通道上算不算当前值"。
- **前端会静默少显示什么吗**？
  **有一处，已明确告知**：只读 `verdict` 的消费方会看到 `ok`，
  从而**看不到**那条陈旧标志。这是刻意的（它已非当前事实），
  并且**不是静默的** —— 它同时出现在 `ops` 栏与 `warnings` 里，
  `next` 也会追加一句"ops 栏有一条上次已知状态的标志未参与判定"。
  这是本变更**最需要前端注意**的一点。

---

## 7. 不做的部分及理由（对应 C7）

- **不做带时间戳的观测**（选项 2 的另一半）：那要改 `ops` 的载荷形状，
  而 `ops` 已进契约 `client_report_schema` —— 属**接口级变更**，
  必须走统筹方的变更流程，不能由本侧顺手改。**若统筹方决定要，我可以实现。**
- **不改 `O-service-down` 的 code / owner / severity**：那是契约已固化的部分
  （统筹方明确"原样采纳、零改判"），我只动"何时算当前值"这个契约留待确认的空白。
- **不改 `frontend_not_built` 的任何行为**：它与可达性不矛盾，无需处理。
- **不动 `.interface_contract/`**：只读资产，改动只能由统筹方改主本再同步。
- **不做架构级 5 条提案**（P1–P5）：未获用户批准。
- **不顺手统一全仓行尾**：本仓库行尾是混合的（且**混合本身是我历轮脚本累积的产物**，不是原始设计）。
  统一属独立变更（会让本次 diff 膨胀到无法评审）；我只把"别悄悄改行尾"变成门禁。
  因此**本文件（新增）是 LF**，而它旁边的 `docs/*.md` 多为 CRLF —— 这一处不一致
  留给待办 `C8`（`docs/PENDING_DECISIONS.md`）的一次性统一动作。

---

## 8. 回退点（对应 C8）

- **回退命令**：
  ```powershell
  git log --oneline --grep "^v1.9:"     # 取到备份点 hash
  git reset --hard <该 hash>
  ```
- **上一稳定点**：`v1.8` @ `d739c91`（`git reset --hard d739c91`）
- **回退会丢什么**：`service_down` 语义修正、`warnings` 字段、
  `ops_stale_by_transport` 暴露、行尾门禁、本评估文档；
  回退后 `service_down` 会**重新**把结论压成 `ops-action`（即回到本文件 §2 的问题状态）。

---

## 9. 自检结论

| 标准 | 结论 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | 复现命令 + `d739c91` 上的实测输出已粘贴（§2）。注：该输出需在**修复前**的提交上复现 |
| **C2** 每条主张带命令 | **满足** | §4 十条主张各配一条可独立执行的命令 |
| **C3** 输出支持主张 | **满足** | §4 粘贴了真实输出；主张 7/8/9/10 为测试退出码与通过数 |
| **C4** 改动清单与实际一致 | **满足** | §3 表 + `git diff --stat`（5 文件 203/18），并显式列出 stat 之外同批提交的文件 |
| **C5** 契约影响已声明 | **满足** | §5：规则表零改判；两处 additive 新增（`warnings`、`ops_stale_by_transport`）已显式声明 |
| **C6** 对侧影响已评估 | **满足** | §6：需改两点（都小）、未平移问题、并明确指出"只读 verdict 的消费方会看不到该标志" |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7：语义修正留在本侧；**没有**把责任推给前端；未获批的架构项一律未动 |
| **C8** 回退点明确 | **满足** | §8：v1.9 定位命令 + 回退会丢什么 |

- **我希望统筹重点验证**：
  1. **主张 3/4**（`service_down` 不再驱动结论、也不掩盖真实问题）——
     这是本次的核心语义，也是最可能与契约 `verdict_vocabulary.priority` 产生**表面冲突**的地方
     （我保留了"ops 优先"，但收窄了"什么算当前 ops 事实"）；
  2. **§6 的第三点**（只读 `verdict` 的消费方会看不到该标志）——
     请判断这是否需要在前端那一侧补一条展示要求；
  3. **是否接受"选项 2 语义 + 选项 1 可见性"作为该约束的最终结论**，
     若倾向严格选项 1（保留 `ops-action`），这是一行改动，我立刻照办。
