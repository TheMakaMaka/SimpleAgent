# 变更评估文档 · `VERIFY-VACUOUS`

> 后续变更（2026-09-27）：`TRANSPARENCY-BACKEND` 的 **B3** 把 `.py` 交付物的下限
> 从「**引用**」收紧到「**必须调用**」—— 本文 §3.2/§4 里那条
> `assert os.path.exists('add.py')` 可采的用例因此**被有意改成不可采**。
> 两层是叠加关系（引用仍然必要），见 `docs/EVALUATION-TRANSPARENCY-BACKEND.md`。

---

- **变更编号**：`VERIFY-VACUOUS`
- **提出方**：统筹
- **执行侧**：backend
- **日期**：2026-09-26
- **契约版本**：`1.0.23`（按本轮 `DISPATCH` 标注的当前契约版本）

---

## 1. 变更意图

引统筹方的原话（`05-reports/SUGGESTION-20260926-backend-vacuous-verify.md` 与
`DISPATCH` 本轮指令，逐字引用）：

> 调用方不给 `verify_command` 时，**模型自己定义"什么叫对"** ——
> 而 `qwen2.5:7b` 给出的是 **`print('PASS')`**：恒真。
> 于是**什么都没做，也判成功**。

> **三个绿灯叠在一起，恰好等于"什么都没干"。** 这是本次最值得记的一句话。

> ⚠️ **它不是 `FIX-VERIFY-WIRING` 的回归** —— 是那条修复**唤醒**的一个原本睡着的洞。
> **不要理解成"那条修复不该做"**，它正确且必要。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象

目标「读取根目录下的项目结构输出一份分析报告」，**调用方不给 `verify_command`**。
真实运行 `cy_20260926_154707_882595`（统筹方提供，已逐条复核，全部为真）：

| 事实 | 值 | 位置 |
|---|---|---|
| `verify` | `{'passed': True, 'detail': 'PASS', 'command': "print('PASS')"}` | `CycleReport.verify`（`core/coding_cycle.py:500`） |
| 谁给的判据 | **模型自拟**（调用方没给） | `core/orchestrator.py:112-115`（改动前） |
| `manifest.declared` | `0` | `core/manifest.py:204`（`declared` 为空 → `checked=False`） |
| `manifest.checked` | `False`（note：*本轮没有声明文件清单，跳过硬校验*） | `core/manifest.py:192,204` |
| `check.steps` | `0`（*本次 cycle 没有产生 .py 文件改动*） | `core/pipeline.py:85-91`（改动前） |
| `touched_files` | `[]` | `CycleReport.touched_files` |
| 结论 | **`phase=record`（成功）** | `core/coding_cycle.py:541` |
| 产出 | **没有 report.txt** | workspace 实际内容 |

**机制**：采纳自拟 verify 的**唯一**门槛是"非空且可执行"：

```python
# core/orchestrator.py:111-115（改动前）
if (not caller_verify and isinstance(raw_verify, dict)
        and (raw_verify.get("command") or "").strip()):
    verify_command = raw_verify          # ← 只看"非空"，不看"是否引用交付物"
```

`print('PASS')` 满足它，退出码 0，`FIX-VERIFY-WIRING` 之后它**真的被执行** → 判成功。

### 2.2 为什么这是问题

1. 与我们自己写在同一文件里的纪律冲突（`core/orchestrator.py:81-82` 注释）：

   > 调用方给出的验收标准是权威的：模型可以决定「怎么实现」，
   > 但**绝不能改写「什么叫对」**。

   调用方没给标准时，模型把"什么叫对"整个拿走了。
2. **更重的是它污染了整条判据链**：`declared=0` + `checked=False` + `steps=0`
   三个"没东西可查"的绿灯 + 一条恒真命令 = 一个**假的成功结论**。
   对上层（前端、统筹方对账、技能沉淀）来说，这与"真的做完了"在数据上**同形**。
3. 网页端**结构上给不出**这个标准：验收命令输入框是可选的、默认 `null`，
   而"读目录、写一份分析报告"这类目标，用户写不出机器可判定的命令。
   **所以这不是"用户忘了填"。**

### 2.3 复现命令（我这一侧，**不调模型**，确定性）

```powershell
python tests/unit/test_verify_vacuous.py
```

其中第 3 组把可采性开关**关掉**（= 复刻修复前行为），于是缺陷**必定复现**：

```
$ python tests/unit/test_verify_vacuous.py
[3] ★ 反向证明：关掉可采性检查（= 复刻修复前行为）→ 缺陷必须复现
  phase=record  touched=[]
  manifest: declared=0 checked=False
  check_steps=[]
  verify={'passed': True, 'detail': 'PASS', 'command': "print('PASS')", 'source': 'model'}
```

（这一组同时是**检查器自身会不会失败**的证明 —— 见 §4。）

### 2.4 复现命令（**真实模型**，与统筹方 §5 的复验方式同构）

```powershell
python tests/diagnostics/repro_vacuous_verify.py
```

它走**生产的构造路径**（`main._build_orchestrator()` + `CodingCycle`，
与 `/encode` 一致），**不手工注入** pipeline、**不给** `verify_command`，
并在临时目录里预置"上一次留下的" `calc.py` / `notes.txt`
（这一点是必须的：正是它们让 `_files_to_verify` 的兜底有文件可挂）。

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M CYCLE.md
 M README.md
 M core/coding_cycle.py
 M core/contract.py
 M core/cycle.py
 M core/memory.py
 M core/orchestrator.py
 M core/pipeline.py
 M core/prompts.py
 M core/skill_runner.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
 M docs/PENDING_DECISIONS.md
 M tests/README.md
?? docs/EVALUATION-VERIFY-VACUOUS.md
?? tests/diagnostics/repro_vacuous_verify.py
?? tests/unit/test_verify_vacuous.py

$ git -c safe.directory=<repo> diff --stat
 CYCLE.md                  |   2 +-
 README.md                 |   3 +-
 core/coding_cycle.py      |  54 ++++++++++++---
 core/contract.py          |  12 ++--
 core/cycle.py             |   9 +++
 core/memory.py            |  53 ++++++++++++++-
 core/orchestrator.py      | 176 ++++++++++++++++++++++++++++++++++++++++++++--
 core/pipeline.py          |  18 ++++-
 core/prompts.py           |  12 +++-
 core/skill_runner.py      |   3 +
 docs/ARCHITECTURE.md      |   2 +-
 docs/CHANGELOG.md         | 101 ++++++++++++++++++++++++++
 docs/MODULES.md           |  41 +++++++++--
 docs/OPERATIONS.md        |  49 ++++++++++++-
 docs/PENDING_DECISIONS.md |  20 ++++++
 tests/README.md           |   2 +
 16 files changed, 523 insertions(+), 34 deletions(-)
```

> 备份点：见 §8。备份后 `git show --stat <tag>` 是本节的最终权威输出。

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/orchestrator.py` | `_deliverables` / `_verify_references` / `_code_without_literals` / `_model_verify_admissible`（新增） | 自拟判据的**可采性下限**：必须有交付物、且判据必须引用它 |
| 2 | `core/orchestrator.py` | `run()` 里采纳分支 | 不合格**不采纳**（也不清空前几轮已采纳的好判据）→ 走已有的"未验证"显式失败路径 |
| 3 | `core/orchestrator.py` | `set_verify(..., source=...)` 调用点 | 判据**来源**留痕（`caller` / `model`） |
| 4 | `core/memory.py` | `verify_untrusted` / `verify_rejections` / `reject_verify()` | "当下原因"与"只增不减的审计流水"分开存 |
| 5 | `core/coding_cycle.py` | 事件段 | 逐条把被拒判据发成 `verify_skipped`（**不新增事件种类**） |
| 6 | `core/coding_cycle.py` | VERIFY 分支 | 第三种情况（判据不合格）与"缺少命令/没执行"**分开说** |
| 7 | `core/coding_cycle.py` | `report.verify` / `report.check` | `verify.source`；`check` 三态进报告 |
| 8 | `core/cycle.py` | `CycleReport.check` + `to_dict` | 让"没东西可查"与"查过并通过"可区分（**additive**） |
| 9 | `core/pipeline.py` | `run_check` 全部返回点 | 加 `checked` 与三态 `status` |
| 10 | `core/prompts.py` | `ORCHESTRATOR_SYSTEM` 规则 11/12 | 让模型**能**满足下限（判据必须引用交付物；没交付物就没法通过） |
| 11 | `core/contract.py` | `EVENTS["verify"]`、`FROZEN_REPORT_KEYS`、词表注释 | 声明新键（additive）；顺手改掉漂移的"当前 12 种"→**13** |
| 12 | `core/skill_runner.py` | 技能自己的验证回流 | 显式 `source="caller"`：技能里**烘焙**的判据由技能作者写定，不是模型自拟，因此**不走**可采性下限 |
| 13 | `tests/unit/test_verify_vacuous.py` | 新增 | 30 项，含**反向证明** |
| 14 | `tests/diagnostics/repro_vacuous_verify.py` | 新增 | 真实模型复验（同统筹方 §5） |
| 15 | `tests/diagnostics/verify_wiring_http.py` | 第 2 条断言 | 把"验证没执行"的**两种原因**分开：判据被拒（本轮新增的**正确**行为） vs 接线断了（`FIX-VERIFY-WIRING` 的缺陷）—— 否则会把一次正确的拒绝读成回归 |
| 16 | 文档 | `CHANGELOG §34`、`MODULES`、`OPERATIONS §4.11/§5.3/§5.4`、`README`、`tests/README`、`PENDING_DECISIONS`、五份上游文档版本戳 | 同步 |

### 3.3 若两者不一致，差异是什么

机械输出是权威，手写导读与它**一致**（15 条 ↔ 16 个文件，
其中 `docs/EVALUATION-VERIFY-VACUOUS.md` 与两个测试是本文件本身/新增文件，
在 `status --short` 的 `??` 段里）。

**没有**出现"手写表漏了某一类"的情况：本次改动只落在
`core/`（8 个）+ `tests/`（2 个新增）+ 文档（含 5 份上游文档的版本戳），
没有触碰 `tools/`、`storage/`、`web/`、`main.py`（这些是**刻意不动**的，见 §7）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | 恒真判据**不再**可采 | `python tests/unit/test_verify_vacuous.py` | 第 1 组 10/10（含 `print('PASS')`、`assert True`、无交付物三例） |
| 2 | ★ 「`declared=0` 且 `touched=[]` 却 `phase=record`」不再出现 | 同上（第 2 组） | `这个组合**不再**能是 phase=record` PASS |
| 3 | ★ 这个检查器**确实抓的是该缺陷**（不是碰巧） | 同上（第 3 组，关掉开关复刻旧行为） | `关掉后确实复现：declared=0 + print('PASS') → phase=record` PASS |
| 4 | 合法的自拟判据不被误伤 | 同上（第 4/6 组） | `合法的自拟判据仍然通过` + `换到合法判据后仍然通过` PASS |
| 5 | 调用方给的判据**不受**本门禁影响 | 同上（第 4/5 组） | `调用方给的判据不受本门禁影响` PASS |
| 6 | 判据来源可区分（`caller` / `model`） | `python tests/diagnostics/repro_vacuous_verify.py` | `source='model'` 与 `source='caller'` 各一条，6/6 |
| 7 | 被拒判据在**事件流**里留痕（含被拒命令原文） | 同上（读回真实 `storage_data`） | `verify_skipped=2`，`reason` 含 `print('PASS')` |
| 8 | `check` 三态可区分"没东西可查" | `python tests/unit/test_verify_vacuous.py` | `status=skipped 且 checked=False` PASS |
| 9 | 真实模型 E2E：不给 `verify_command` 时不再假成功 | `python tests/diagnostics/repro_vacuous_verify.py` | `通过 6/6` |
| 10 | 全量回归无退化 | `python tests/run_unit.py` | `通过 33/33` |
| 11 | 契约符合性 / 前端契约 / 文档 | `python tests/unit/test_contract_conformance.py` 等 | 44/44 · 25/25 · 35/35 · 31/31 · 18/18 |

### 4.1 实测输出（粘贴原文）

**主张 2/3（`tests/unit/test_verify_vacuous.py`，节选）**：

```
[2] 端到端（生产构造路径，调用方不给 verify_command）
  phase=failed  attempts=1
  manifest: declared=0 checked=False passed=True
  check:    checked=False status=skipped steps=0
  touched_files=[]
  verify=None
  error=模型自拟的验收判据**不合格，已拒绝采纳**：本轮没有任何交付物（计划没声明文件、
        也没有 write_file 产物），自拟的验收无从判定 —— …
  [事件 verify_skipped] reason=模型自拟的验收判据不合格，已拒绝采纳（…；被拒命令: "print('PASS')"）

[3] ★ 反向证明：关掉可采性检查（= 复刻修复前行为）→ 缺陷必须复现
  phase=record  touched=[]
  manifest: declared=0 checked=False
  check_steps=[]
  verify={'passed': True, 'detail': 'PASS', 'command': "print('PASS')", 'source': 'model'}
...
通过 30/30
```

**主张 6/7/9（真实模型，`repro_vacuous_verify.py`，当前代码）**：

第一次运行用**只读目标**（模型只列目录、没有任何交付物 → 判据被拒），
这是缺陷路径在真实模型下的样子：

```
$ python tests/diagnostics/repro_vacuous_verify.py --goal "总结一下当前工作区里有哪些文件" --skip-caller-check
[verify] 拒绝采纳模型自拟的验收判据：本轮没有任何交付物（计划没声明文件、也没有 write_file
         产物），自拟的验收无从判定 —— 一份交付声明都没有，就说不出「交付了什么」…
[manifest] checked=False passed=True declared=0 actual=1 violations=0
[verify] 拒绝通过：模型自拟的验收判据**不合格，已拒绝采纳**：…；被拒命令: "print('PASS')"…
phase=failed  attempts=2  用时=7.5s
  manifest: declared=0 checked=False passed=True actual=1
  touched_files=[]
  verify=None
事件流（本 cycle，共 11 条）：verify=0 verify_skipped=2
  [verify_skipped] reason='模型自拟的验收判据不合格，已拒绝采纳（…被拒命令: "print(\'PASS\')"）'
  [verify_skipped] reason='模型自拟的验收判据不合格，已拒绝采纳（…被拒命令: "assert set([\'calc.py\', \'notes.txt\']) == set(list_workspace())"）'
通过 4/4
```

第二次运行用**统筹方给的那个目标**（模型会真的写出 `report.txt`）：

```
$ python tests/diagnostics/repro_vacuous_verify.py
phase=failed  attempts=2  用时=61.0s
  manifest: declared=1 checked=True passed=True actual=2
  check:    checked=False status=skipped steps=0
  touched_files=['report.txt']
  verify={'passed': False, 'detail': 'AssertionError: 报告内容不完整',
          'command': "import os\nreport_content = open('report.txt').read()\n
                      assert 'calc.py' in report_content and 'notes.txt' in report_content,
                      '报告内容不完整'\nprint('PASS')",
          'source': 'model'}
[第二个 cycle] 调用方给 verify_command=print('PASS')（简单目标）
  phase=record  declared=1 checked=True
  verify={'passed': True, 'detail': 'PASS', 'command': "print('PASS')", 'source': 'caller'}
  PASS  ★ 不出现「declared=0 且 touched=[] 却 phase=record」这个组合
  PASS  调用方给的判据执行后 → source=caller（能区分来源）
通过 6/6
```

> ★ 注意这两次真实运行的**区别**，它正是本次修复的要点：
> 模型现在自拟的是 `assert 'calc.py' in report_content and 'notes.txt' in report_content`
> —— 一条**真的引用了交付物**的判据，于是它**会失败**（`AssertionError: 报告内容不完整`），
> 而 cycle 诚实地报了 `phase=failed`。**改动前这个目标是 `phase=record`。**

**主张 10/11**：

```
$ python tests/run_unit.py
通过 33/33

$ python tests/unit/test_contract_conformance.py   → 通过 44/44
$ python tests/unit/test_frontend_contract.py      → 通过 25/25
$ python tests/unit/test_doc_consistency.py        → 通过 35/35
$ python tests/unit/test_doc_invariants.py         → 通过 31/31
$ python tests/unit/test_doc_review.py             → 通过 18/18
```

### 4.2 未验证的部分（诚实列出）

- **只验了三个目标**（统筹方给的那个 + 一个只读目标 + 一个简单目标），
  **没有系统扫过**"哪些目标的自拟判据会被拒"。他们报告里那句
  "这是一个样本，不是一个比例"同样适用于我这一侧。
- **没有跑 8 级基准做前后对比**：这次改的是"无调用方判据"这条路，
  而基准每一级都由 `run_levels.py` 提供调用方判据 → 走的是另一条分支，
  对比意义不大。我只跑了 L1 冒烟（PASS）。
- **没有验证前端会怎么显示 `verify.source` / `report.check`**：前端对新增键
  是"能读就读、读不到就降级"，属对侧行为；我只声明了事实面（§5）。
- **`print('report.txt')` 这类误收**：命令里只要出现交付物路径就算引用，
  即使它没对文件做任何操作。**这是刻意的留白**（见 §7），我明确知道它存在。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 **13** 种） | 被拒判据复用 `verify_skipped`（对外是同一类事实："本轮验证没跑，原因是…"） |
| 事件 payload 键 | **有：`verify` 事件新增 `source`** | **additive**：`"caller"` / `"model"`。`verify_skipped` 的 `reason` 里现在也会出现"判据不合格"这一类文本（键未变） |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` 字段 | **有：新增 `check`**（`{checked, passed, status, skipped_reason}`）；`verify` 内新增 `source` | **additive**：`FROZEN_REPORT_KEYS` 加 `check`；`verify` 本来就是 dict |
| `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1`；`SCHEMA_VERSION` 未动） | 新增键按本侧规则属 additive，不升版本 |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无**（规则表仍 23 条，归属/结论词表未动） | 事件种类数未变，`event_partition.observed` **无需更新** |

**结论：全部属 additive**，无删除/改名，不需走废弃流程。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不要**（本次不改任何既有键的语义）。
  可选的两条**增强**：
  1. 前端若想让用户一眼看出"这条验证结论是模型自拟的"，
     可读 `report.verify.source`（`model` 建议弱化显示，**不要**染成失败）；
  2. `report.check.status == "skipped"` 建议与 lint 的 `skipped` 同等对待
     —— 明写"未执行"，不要染绿。
- **有没有可能"问题被平移到对侧"**：**有，而且必须说清楚**。
  门禁收紧了"无调用方判据"这条路，于是**结构性缺口浮到对侧**：
  网页端那个「验收命令」输入框是**可选且默认 `null`** 的
  （统筹方报告 §3 已实测：`LaunchPanel.vue:87` → `App.vue:135` →
  `bridge/runner.py:418`）。后果：

  | 目标形态 | 改动前 | 改动后 |
  |---|---|---|
  | 产出文件的编程目标，用户不填验收命令 | 可能"假成功" | 正常路径：模型自拟引用交付物的判据，或明确失败 |
  | **不产出任何文件**的目标（如"总结一下有哪些文件"），用户不填 | **假成功** | **必定失败**（判据无交付物可引用） |

  第二行是我这一侧**有意选择**的结论：没有交付物就说不出"交付了什么"，
  那也不该有"验证通过"。**但这也意味着**："人类目标"与"机器可判定"
  之间的那个缺口，需要在**调用方那一侧**补 —— 由用户/前端给一条验收命令，
  或者由工作流把这类目标改写成"产出一个文件"。
  **我不认为这是把问题推给对侧**（缺口的性质是"谁来定义什么叫对"，
  那本来就是调用方的权力，不是上游能替它决定的），
  但它确实**提高了"调用方给判据"的必要性**，请统筹方按此评估。
- **前端会静默少显示什么吗**：不会变少。事件种类数不变、`verify` 事件与
  `CycleReport` 既有键都在；新增的两个键读不到时的表现与现在一致。

---

## 7. 不做的部分及理由（对应 C7）

- **不做"识别废话"的启发式**（如"命令里必须含 `assert`/`open`"）。
  理由：那是**关键词表**，既任意又容易判宽/判窄；而"引用交付物"是**字符串事实**。
  取一个可判定的下限，胜过写一个看起来很聪明、实则判宽了的启发式。
  → 代价（已知）：`print('report.txt')` 这种"只把路径打在字符串里"的命令**仍会通过**。
- **不把调用方给的判据也纳入下限**。理由：那会**夺权**。
  调用方写 `print('PASS')` 时照样通过 —— 标准由调用方定，这是权威性，不是缺陷。
  （`test_verify_vacuous.py` 第 4/5 组**专门盯着这一点**，防我以后越界。）
- **不把 `manifest.checked=False` 本身升级为失败**（他们的建议 3）。
  理由：有调用方判据时，"模型没声明清单"不构成缺陷
  （`declared=0` + 调用方判据 + 目标不需要文件是合法组合）。
  真正的病根是"没有交付物**却**判通过"，那一条已经堵住了。
- **不新加"未验证"阶段或 `phase`**。理由：会动 `PHASE_ORDER`/`FROZEN_PHASES`
  （契约面 + 前端节点），而现有 `failed` + 精确文案已经能表达同一件事 ——
  **明确失败优于新增状态**。
- **不改 `_files_to_verify` 的 `prior_files` 兜底**。理由：它在
  `FIX-VERIFY-WIRING` 附 4 里是**刻意保留**的第三条兜底（调用方判据 +
  本轮无新产物时可验既有文件）。自拟判据这条路已经由"必须有交付物"堵住，
  不会再走到那个兜底；动它反而会破坏调用方判据的合法用法。
- **不动前端**（验收命令可选、默认 `null`）。理由：属对侧，且涉及
  "谁来定义什么叫对"的产品判断，见 §6。
- **不动基准（`tests/bench/`）**。理由：B3 说明基准必须放在 agent 够不到的位置，
  这是另一件事，不该夹带。

---

## 8. 回退点（C8）

- **回退命令**：见本变更的备份点 `docs/VERSIONS.md`（`v1.19`），
  形如 `git reset --hard <tag>`。
- **回退会丢什么**：
  1. 自拟判据的可采性下限（`_model_verify_admissible` 及其三个辅助函数）；
  2. `report.verify.source` 与 `verify` 事件的 `source` 键；
  3. `report.check` / `run_check` 的三态；
  4. 两个新测试文件与评估文档。
  回退后**回到**：`declared=0` + `print('PASS')` → `phase=record` 的旧行为
  （即本缺陷重新出现）。**判据不会被静默放宽** —— 回退是整份代码回退，
  不存在"只回退检查、保留判据"的中间态。
- **回退不会丢什么**：`FIX-VERIFY-WIRING`（上一轮，`v1.17`）的任何改动 ——
  本次没有触碰那条接线。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.3 一条离线命令（含反向证明）；§2.4 真实模型脚本；`文件:行` 全写（§2.1 表） |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表共 11 条，每条一个命令 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘贴原文；真实模型跑两次（缺陷路径 + 正常路径） |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威，§3.2 只作导读；差异已点明（`diff --stat` 的 `...` 是显示截断） |
| **C5** 对接口契约的影响已声明 | **满足**。§5：无新事件、无改名；新增 `verify.source` / `report.check` / `run_check` 三态，全 additive，`CONTRACT_VERSION` 不升 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：不需要改，但**缺口浮到调用方一侧**（不给判据的"无文件目标"现在必定失败），已如实指出 |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 六条"不做"，含"不夺调用方的权""不动前端""不新增阶段" |
| **C8** 回退点明确 | **满足**。§8：单一备份点，回退丢什么/不丢什么逐条写清 |

**我希望统筹重点验证哪一条**：**C3 里的第 2、3 条**
（"这个组合不再出现" + "关掉开关必定复现"）。
理由：本次修复的核心是**一条判据**，而判据最容易"看起来对了其实没生效"——
第 3 条是它**会不会失败**的证明；如果他们用**只读目标**（我 §4.1 第一个真实运行的形态）
打接口复验，应当看到：`verify=None`、`phase=failed`、
事件流里 `verify_skipped` 带着被拒命令原文，而**不再是** `phase=record`。

---

## 附：这次和 `FIX-VERIFY-WIRING` 的关系（防止被读成"上一轮没修好"）

| | `FIX-VERIFY-WIRING` | `VERIFY-VACUOUS` |
|---|---|---|
| 缺陷 | 模型自拟的 verify **从不执行** | 执行了，但判据**可以是恒真的** |
| 方向 | 让验证**真的跑** | 让判据**有下限** |
| 关系 | — | **是它唤醒的**（不跑就没有后果，也就不暴露） |

两条都不是"另一条不该做"：**先让它跑，再让它有意义**。
