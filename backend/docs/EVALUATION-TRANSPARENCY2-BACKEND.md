# 变更评估文档 · `TRANSPARENCY2-BACKEND`

- **变更编号**：`TRANSPARENCY2-BACKEND`（按 **P1–P5 一起交**：它们同一条线，
  拆开交会让"结局四值"与"两条否决关卡"的依赖关系说不清 —— 若统筹方要分开，我按 P 拆）
- **提出方**：统筹（依据用户对"能力标准化 / 拆解原则 / 独立审查"的裁决）
- **执行侧**：backend
- **日期**：2026-09-27
- **契约版本**：`1.0.25`（按本轮 `DISPATCH` 标注）

---

## 1. 变更意图

引统筹方原话（`WORK-ORDER.md` §P1 / §P2 / §P3）：

> **为什么最优先**：没有 `invalid`，"任务/判据写错了"会被记成"模型不行"，
> **污染整个能力画像**；没有 `abstain`，用户要的「知道**不能做什么**」**无处安放**。

> 用户原话「代码基本模块能满足要求，但**不具备全局复用属性**，对项目的危害会很大」。

> **一个对所有分解都报"通过"的审查器，等于没有审查器。**

以及用户对 `reviewer` 三职责的解耦裁决（`STANDARD-capability-and-decomposition.md` §6）：
**① 架构＝AST 派生的事实（不是角色）· ② 审查角色（机械层硬否决）· ③ 拆解合规关卡（先机械、有否决权）**。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象（每条都带位置）

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| 1 | 结局只有"通过/失败"两值 | `core/coding_cycle.py` 的 `CyclePhase`（`plan/write/check/verify/record/failed`） | **判据写错**（`AttributeError`/`NameError`）与**模型没做到**在数据上同形 → 能力画像被污染 |
| 2 | 判据来源**不进判定链** | `CycleReport.verify.source` 有值，但 `phase`/`ok` 与来源无关 | 39 条运行里**判据来自调用方的是 0 条**，"仪表"没被真正用过；模型自拟判据的 pass 与调用方判据的 pass **同形** |
| 3 | **lint 非阻塞**（实测两次运行带着 `F821` 却 `check.passed=True`） | `core/pipeline.py:157` 注释「lint（非阻塞）」+ 旧 `:173-180` 无条件 `return {"passed": True, ...}` | 同一个概念模型发明三个名字（`obstacle_generator.generate_obstacles` / `ant_colony.generate_obstacles` / `obstacle_generator.generate_obstacle_grid()`），**两次都因此失败**，而 check 说"通过" |
| 4 | 没有**拆解合规**关卡 | 全仓无 `decompose*` 模块；`reviewer` 声明了没接线（`core/config.py:65`） | 拆解不标准、不原子（Run A 10 个任务里 6 个同义、Run B `t5–t8` 是同一句话的四个变体）**没有任何机制看得见** |
| 5 | 架构视图**没有"唯一来源"的规矩** | `tools/arch.py`（AST 派生，已满足）—— 但**没有任何检查**阻止"模型手写架构文档" | 一旦有人手写，架构事实就有**两份**（本项目原话：「两边都不算错，错在**有两份**」） |

### 2.2 复现命令（我这一侧，**不调模型**）

```powershell
python tests/unit/test_outcome.py            # P1：四值各构造一次（18 项）
python tests/unit/test_reuse_checks.py       # P2 + P4（18 项）
python tests/unit/test_decompose_review.py   # P3（19 项，含"已知错的分解必须被判错"）
```

### 2.3 复现命令（**真实模型**，用统筹方的固定样例）

```powershell
python tests/diagnostics/repro_user_run_20260927.py
```

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M README.md
 M core/coding_cycle.py
 M core/config.py
 M core/contract.py
 M core/cycle.py
 M core/pipeline.py
 M docs/FRONTEND_CONTRACT.md
 M docs/PENDING_DECISIONS.md
 M tests/README.md
 M tools/arch.py
?? core/decompose_review.py
?? core/outcome.py
?? core/reuse_checks.py
?? tests/unit/test_decompose_review.py
?? tests/unit/test_outcome.py
?? tests/unit/test_reuse_checks.py

$ git -c safe.directory=<repo> diff --stat
 README.md                 |   1 +
 core/coding_cycle.py      | 173 ++++++++++++++++++++++++++++++++++++++++++----
 core/config.py            |  11 ++-
 core/contract.py          |  63 ++++++++++++++++-
 core/cycle.py             |  21 ++++++
 core/pipeline.py          | 136 +++++++++++++++++++++++++++++++++++++++-
 docs/FRONTEND_CONTRACT.md |  13 +++-
 docs/PENDING_DECISIONS.md |  22 ++++++
 tests/README.md           |   3 +
 tools/arch.py             |  43 ++++++++++++
 10 files changed, 464 insertions(+), 22 deletions(-)
```

（外加 3 个新模块 + 3 个新单测；文档面在本节之后补齐，最终以备份点的
`git show --stat <tag>` 为准。）

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/outcome.py`（新） | — | **P1**：原因种类 → 四值；`classify_verify_detail`（判据自身语法错/缺依赖 → invalid）；`build_verdict`（判据来源 + 可信档位） |
| 2 | `core/coding_cycle.py` | `_end_cycle`（新） | **P1**：所有出口统一落实结局；`cycle_end` 事件加 `outcome`/`outcome_reason`；**终局也发 `cycle_end`**（原来跑满尝试次数一个结束事件都没有） |
| 3 | `core/coding_cycle.py` | verify 失败分支 | **P1**：先做**判据自身**的符号反查 → `criterion-broken`（invalid）区别于 `verify-failed`（fail） |
| 4 | `core/reuse_checks.py`（新） | — | **P2**：五类复用性缺陷；阻塞只留"必然崩"的三类；**同一份判据**也用于判据自检（P1 的 invalid 靠它） |
| 5 | `core/pipeline.py` | `run_check` + `_arch_doc_violations` | **P2**（复用性进入 check，**阻塞**）+ **P4**（手写架构文档被拦、渲染件放行）；顺带修回"没 `.py` 改动 = `skipped`"三态 |
| 6 | `core/decompose_review.py`（新） | — | **P3**：八条原则；机械层有否决权；`checked_by/independent/undecidable` 如实 |
| 7 | `core/contract.py` | `DECOMPOSE_PRINCIPLES` + `OUTCOMES` + 3 个新事件 | **L1**：原则是**契约载荷**（执行方不得改写）；结局四值进契约 |
| 8 | `tools/arch.py` | `render_architecture_view` | **P4** 的**唯一允许路径**：从派生视图渲染，带 `derived-from` 标记 |
| 9 | `core/config.py` | `reviewer.purpose` | **P5**：定位写死"建议性、无自由否决权"，并指明**否决权在机械关卡** |
| 10 | `core/cycle.py` | `CycleReport` | 加 `outcome`/`outcome_reason`/`verdict`/`reuse_checks`/`decompose_review`（**additive**） |

### 3.3 若两者不一致，差异是什么

一致。**一处需要点明的"我没照单全做"**：P2 的五类里，我只把三类做成**阻塞**
（调用了不存在的符号 / 用了没导入 / 按旧签名传参），另两类（重复符号、命名不一致）
是**警告**。理由与代价写在 §7，并且**提升只需改一行**（`BLOCKING_KINDS`）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | **P1-a** 应 `abstain` 的目标 → `abstain`（不是 fail/pass） | `python tests/unit/test_outcome.py` | `★ 结局是 abstain` PASS |
| 2 | **P1-a** 判据写错 → `invalid`（不是 fail） | 同上 | `★ 结局是 invalid` + `kind=criterion-broken` PASS |
| 3 | **P1-a** 判据真跑过、真失败 → `fail` | 同上 | `★ 结局是 fail` PASS |
| 4 | **P1-b** 判据来源可辨、**不同形** | 同上 | `model-self-authored` vs `caller-authoritative` PASS |
| 5 | **P1-c** 报告字段只增不改 | 同上 | `outcome/outcome_reason/verdict` 在 `to_dict()` 里 PASS |
| 6 | **P2** 实测那两条判据**必须被抓住** | `python tests/unit/test_reuse_checks.py` | `Run A / Run B` PASS + `正确的判据不误伤` PASS |
| 7 | **P2** check **必须红**（不再带着错误放行） | 同上 | `★ check 判红` + `outcome=fail` PASS |
| 8 | **P2** 用了没导入 / 按旧签名传参 → 阻塞 | 同上 | 两条 PASS |
| 9 | **P3** 真实运行的分解**必须判不通过** | `python tests/unit/test_decompose_review.py` | `★ 判不通过` + `P3` PASS |
| 10 | **P3** Run A 型分解违反 P3/P4/P6/P7 | 同上 | 四条 PASS |
| 11 | **P3** 合规分解**必须通过** | 同上 | `★ 八条原则没有一条 violated` PASS |
| 12 | **P3** `independent=false` 且 L3 未启用如实标注 | 同上 | PASS |
| 13 | **P3** 否决权**真的生效** | 同上（`DECOMPOSE_GATE=block`） | `★ block 模式：否决` PASS |
| 14 | **P4** 手写架构文档被拦、渲染件放行 | `python tests/unit/test_reuse_checks.py` | 两条 `★` PASS |
| 15 | 真实模型复跑固定样例 | `python tests/diagnostics/repro_user_run_20260927.py` | `通过 6/6` |
| 16 | 全量回归 | `python tests/run_unit.py` | `通过 38/38` |
| 17 | 契约符合性 / 前端契约 / 文档 | 各 `tests/unit/test_*.py` | 44/44 · 25/25 · 35/35 · 31/31 · 18/18 |

### 4.1 实测输出（粘贴原文）

**主张 1–5（P1 四值 + 判据来源）**：

```
[1] 没有可用判据（自拟判据被拒）→ abstain
  phase=failed outcome=abstain kind=no-admissible-criterion
[2] 判据引用了不存在的符号 → invalid
  phase=failed outcome=invalid kind=criterion-broken
  error=验证未通过: AttributeError: …（判据/环境自身有问题 → 本次读数 invalid：…）
[3] 判据真跑过、真断言失败 → fail
  phase=failed outcome=fail kind=verify-failed
[4] 判据通过 → pass，来源可辨
  phase=record outcome=pass source=model trust=model-self-authored independent=False
[5] 调用方给判据并通过
  phase=record outcome=pass source=caller trust=caller-authoritative
（[4] 与 [5] 同为 pass，但 trust/independent 不同 → **不同形**）
通过 18/18
```

**主张 6–8 + 14（P2 复用性 + P4 架构事实层）**：

```
[1] 实测反例：判据引用了不存在的符号
  →  引用了不存在的符号 `ant_colony.generate_obstacles` —— `ant_colony` 里只有 ['AntColony']
  →  引用了不存在的符号 `obstacle_generator.generate_obstacle_grid` —— 它只有 ['generate_obstacles']
  正确的判据：未被误伤
[2] BLOCKING_KINDS = ['symbol-arity-mismatch', 'undefined-name', 'undefined-symbol']
  参数个数不符 → ['symbol-arity-mismatch']（实测那条 `generate_obstacles(10)`）
  参数个数正确时不误报
[3] 端到端：交付物里调了不存在的符号
  phase=failed outcome=fail kind=reuse-violation
  check={'checked': True, 'passed': False, 'status': 'failed'}
    [阻塞] undefined-symbol: a.py 引用了不存在的符号 `b.missing_fn`
[4] P4：手写件 → ['hand-written-architecture-doc']；渲染件 → []（放行）
  端到端：手写架构文档作为交付物 → check 红、结局 fail
通过 18/18
```

**主张 9–13（P3 拆解合规）**：

```
[V1] 用户那次真实运行的 plan（逐字复刻）
  passed=False violated=['P3'] undecidable=['P2','P5']
      [violated] P3: t1「设计并实现障碍物生成规则」含并列词 ['并'] …
[V1-b] Run A 型分解
  passed=False violated=['P3','P4','P6','P7']
[V2] 符合全部原则的分解
  passed=True；六条机械原则全 ok；P5 undecidable；coverage_complete=False
[V3] 否决权
  warn 模式：phase=record（留痕但不拦）
  block 模式：phase=failed kind=decomposition-violation
    error=拆解合规审查**否决**（机械层）：违反 ['P3'] …
通过 19/19
```

**主张 15（真实模型，统筹方固定样例 —— 同一次运行里的四条新事实）**：

```
[decompose] 机械层：3 条通过 / 3 条违反 ['P3','P4','P6'] / 2 条判不了 ['P2','P5']；
            **且 L3 判断类审查未启用**（REVIEW 未配置）
verify: {'passed': False, 'detail': "NameError: name 'List' is not defined…", 'source': 'model'}
cycle_end: failed | outcome=fail | 验证未通过: TypeError: generate_obstacles()
           missing 1 required positional argument: 'num_obstacles'
decompose_review 事件: passed=False violated=['P3','P4','P6'] independent=False
reuse 事件: passed=True blocking=0 warnings=0
self_report.fact_check: 矛盾 1 条 → [lint-failed-not-disclosed] 自述给人以「检查通过」的印象
           ←→ lint 有 1 处 failed：obstacle_generator.py: UP035 `typing.List` is deprecated
```

> 注意最后两行：**真实模型那次运行的分解确实违反 P3/P4/P6**（与统考方实测一致），
> 而且 C2 的交叉核对**又抓到一次"自述说通过、而 lint 有 failed"**。
> ★ 另外那两条 `TypeError`/`NameError` 现在会被 `symbol-arity-mismatch` /
> 符号反查在 **check 阶段**就抓住（该 run 的最终文件已修好 import，故 check 放行；
> 这正是"判据自己写错 → invalid"与"交付物坏了 → fail"的分界）。

**主张 16/17**：

```
$ python tests/run_unit.py                       → 通过 38/38
$ python tests/unit/test_contract_conformance.py → 44/44
$ python tests/unit/test_frontend_contract.py    → 25/25
$ python tests/unit/test_doc_consistency.py      → 35/35
$ python tests/unit/test_doc_invariants.py       → 31/31
$ python tests/unit/test_doc_review.py           → 18/18
```

### 4.2 未验证的部分（诚实列出）

- **P1 的"能力画像"效果没验**：四值本身是可判定的，但"跑一批后画像是否更干净"
  要等统筹方的测量仪跑基线 —— 那不是这一侧能自证的。
- **P3 的阈值没校准**：`MAX_TASKS=12`、`SYNONYM_JACCARD=0.6`、并列词表都是**我定的初值**，
  只保证"实测那两个样例判对、合规样例判过"。**统筹方说过阈值等基线校准** —— 现在定了，
  改起来是一处常量（`core/decompose_review.py` 顶部）。
- **P3 的 P2/P5 是 `undecidable` 而不是判定**：不是偷懒，是这两种信息当前形态里没有
  （逐叶判据、目标要求清单）。给它们补上字段就能真判 —— 需要契约侧先定字段。
- **P4 的检查只覆盖"文件名像架构文档"**：一个叫 `notes.md` 的手写架构说明**拦不住**。
  判据是"文件名 + 派生标记"，因为"内容像不像架构"不可判定。代价已写明在 OPERATIONS。
- **没有跑 8 级基准做前后对比**：P2 是收紧（lint 从非阻塞变部分阻塞），
  很可能让某些级别从"侥幸通过"变回失败 —— 那是预期方向，但**通过率的变化我没测**。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **有：16 → 19** | `reuse`（P2）、`decompose_review`（P3）为新增；`cycle_end` 为**加键** |
| 事件 payload 键 | **有** | `cycle_end` 加 `outcome`/`outcome_reason`；两个新事件各自的键。既有事件其余键**未动** |
| 上游 `PHASE_ORDER` 阶段 | **无** | 结局四值是**报告/事件字段**，不是新阶段（`phase` 语义不变） |
| `CycleReport` 字段 | **有：+5** | `outcome` / `outcome_reason` / `verdict` / `reuse_checks` / `decompose_review`，全 **additive**，`FROZEN_REPORT_KEYS` 同步 |
| `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无**（`tools/arch.py` 只**加**了一个不注册为工具的渲染函数） | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1` / `1.0`） | 按本侧规则属 additive |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无**（规则表仍 23 条） | 事件**种类数** → 台账需 **16 → 19**；另外 `DECOMPOSE_PRINCIPLES` 是**上游新加的契约载荷**（原则归统筹方，本侧只读） |

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不必**（都 additive）。建议前端做三件事：
  1. `cycle_end.outcome` 用**四值**显示，且 **`invalid` 不要染成"失败"**
     （它是"这次读数无效"）。`verdict.criterion_trust` 建议在通过时也显示出来 ——
     否则"模型自拟判据的通过"与"调用方判据的通过"看起来一样（这正是 P1-b 要治的）；
  2. `reuse` 事件里 `blocking` 是**有否决权**的结论，`warnings` 只是提示 —— 别同色；
  3. `decompose_review.passed` **不等于"审查通过"**：`independent=false` 表示
     独立模型层未启用，`undecidable` 非空表示覆盖不全。
- **有没有可能"问题被平移到对侧"**：**有一处，必须说清**。
  P2/P3 是**收紧**，实战里最常见的后果是"以前能过、现在过不了"：
  * P2：`F821`（用了没导入）与"按旧签名传参"从**放行**变**阻塞**。
    实测那两次运行**都是**因为这类错误失败（`np` / `random` 未定义、
    `generate_obstacles` 签名改了三版）—— 也就是说**这些运行本来就不该通过**。
    代价是"通过了但有小毛病"的历史运行会变成失败，**这正是用户要的**（要能区分）。
  * P3：默认 `warn`，**不动行为**（见 §7 的 C11）。
- **前端会静默少显示什么吗**：不会。多三个 kind、多五个报告字段。

---

## 7. 不做的部分及理由（对应 C7）

- **P2 的五类里，两类没做成阻塞**（重复符号、命名不一致）→ 只做**警告**。
  理由：`main()`/`run()`/`test_*` 同名是**常见且合法**的结构，
  把它们阻塞会让几乎每次运行都红；而"是不是同一概念"要模型判（属 ② 的模型层）。
  与统筹方 P2 章节"五类都要阻塞"的差异**在此显式声明**，
  提升只需改 `BLOCKING_KINDS` 一行（已留 `PENDING C12`）。
- **P3 默认 `warn` 而不是 `block`**。理由：统筹方自己说"P3 的阈值可能等能力基线再校准"，
  而 7B 现阶段的分解**几乎必然违反** P3/P6（实测两次运行都判不通过）——
  默认拦会让每次运行都 abstain。**否决权已实现且有用例**，
  一行环境变量（`DECOMPOSE_GATE=block`）开启（已留 `PENDING C11`）。
  这不是"悄悄放宽"：结论照样算、照样进事件与报告，只是不拦路。
- **不做 P5/P6 的模型层**：REVIEW 未配置 → `independent=false` 如实标注。
  按 `STANDARD §3.1 L3`，判断类审查要用**独立档位**的模型；
  现在没有第二个端点，**不能拿同一个模型冒充独立审查**（这是纪律 7 的老账）。
- **不动 `reviewer` 的语义**（P5）：只把 purpose 写清楚并指明否决权在机械层。
  给模型审查**否决权**需要新增角色（如 `ARCHITECT`）—— 架构级，等用户裁决。
- **不新建架构机制**（P4）：`tools/arch.py` 已经满足"AST 派生、按需查询"，
  所以只做"立规矩 + 会红的检查 + 一条渲染路径"，**不重写**。
- **不动前端**；也没替前端决定 UI 长什么样（四值怎么显示是他们的活）。

---

## 8. 回退点（C8）

- **回退命令**：见本变更的备份点 `docs/VERSIONS.md`（`v1.22`），`git reset --hard <tag>`。
- **回退会丢什么**：
  1. 结局四值（退回"通过/失败"两值 → **"判据写错"重新被记成"模型不行"**）；
  2. 判据来源进判定链（模型自拟与调用方判据重新同形）；
  3. P2 的阻塞复用性检查（`F821` 重新放行 → 那两次运行的失败形态回归）；
  4. P3 的拆解合规关卡（拆解质量重新不可见）；
  5. P4 的架构文档检查与渲染路径。
- **回退不会丢什么**：`FIX-VERIFY-WIRING`(v1.17)、`VERIFY-VACUOUS`(v1.19/20)、
  `TRANSPARENCY-BACKEND`(v1.21) 的全部改动 —— 本次是在它们之上加层。
- **P3 可单独软化**：`DECOMPOSE_GATE=warn` 就是它的软模式（无需回退）；
  **P2 可单独放松**：改 `BLOCKING_KINDS` 一行。两者都不影响其它改动。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 五条缺陷每条带 `文件:行`；§2.2/2.3 给出命令 |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 17 条 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘原文（含真实模型跑固定样例的四条新事实） |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明"五类里只有三类做成阻塞"这处差异 |
| **C5** 对接口契约的影响已声明 | **满足**。§5：事件 16 → 19、报告 +5 字段，全 additive；原则进契约（L1） |

> **勘误（`v1.27` / D30 追加，2026-10-03）**：上表 **C5** 里的「事件 16 → 19」
> 是**当时的笔误** —— 把 `cycle_end` 新增的两个 *payload 键* 当成了一个新事件。
> 实测 `len(core.contract.EVENTS)` = **18**（`CONTRACT_VERSION 1.1`），
> 也是 `/profile` 的 `event_kinds` 实测值。**历史条目只加勘误注、不重排，**
> 故此处保留原文并加此注；机械门禁见 `tests/unit/test_doc_invariants.py` 第 10 组
> （它会抓「上游 N 种事件 / `upstream_event_kinds` 当前 N 个」两种写法，且带反向证明）。
> 详见 `docs/CHANGELOG.md` §41.4。
| **C6** 对另一侧的影响已评估 | **满足**。§6：三条前端建议 + **"收紧会让历史运行变失败，而那正是要区分的"** |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 六条"不做"，含 P2/P3 两处**与工作单的差异**及可一行切换的开关 |
| **C8** 回退点明确 | **满足**。§8：单一备份点 + 两条可单独软化的开关 |

**我希望统筹重点验证哪两条**：
1. **P3 的 V1/V2**（"已知错的分解必须判错、合规的必须判过"）——
   我用的"真实 plan"是**从你 probe 的原始事件里逐字抄的**，
   而 Run A 型分解是**按你工作单的症状描述重建的**（我没有那两份原始 plan）。
   若你能给原始 plan，我立刻加进用例（那才是真正的"已知答案"）。
2. **P2 的阻塞边界**：我只阻塞三类。若你认为"重复符号/命名不一致"也必须拦，
   请回 C12 —— 代价是 `main()` 同名这类合法结构会红。
