# 变更评估文档 · `DECOMPOSE-GATE-BLOCK`（P18）

- **变更编号**：`DECOMPOSE-GATE-BLOCK`（工作单 **P18**）
- **提出方**：用户（2026-10-03 裁决：**升到 block**）
- **执行侧**：backend
- **日期**：2026-10-03
- **契约版本**：`1.0.33`
- **本轮 round_id**：`R-58068c34ba` —— **本轮完成 `R-58068c34ba`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-58068c34ba` 开工，
> 与仓库里上一轮记录的 `R-ecc61d8543`（`docs/EVALUATION-PASS-EVIDENCE.md`）不同 ⇒ 有新指令。
> 本轮 **P17（pass 证据）上一轮已交付**（同文件 §8，`core/evidence.py` 等已在 HEAD），
> **不重做**；本轮新增内容只有 `DISPATCH.md` 顶部的 D39 注记与 `WORK-ORDER.md` 新增的
> **P18** —— 即「拆解关卡出厂默认由 `warn` 升到 `block`」。
> 所有结论均以仓库里的机器事实为准（命令回显、测试退出码、`git diff`）。

---

## 1. 变更意图

**统筹方 `DISPATCH.md` 顶部 D39 注记，逐字**：

> **D39 已由用户裁决：拆解关卡默认升到 `block`** —— 若本轮 P17 做完还有余量，
> 请一并做 **P18**（`DECOMPOSE_GATE_DEFAULT` 由 `warn` 改 `block`，
> **拦下时必须写明违反哪条 + 证据**，并保留环境变量以便灰度）。
> 验收要**双向**：不合规拆解必须被拦、合规拆解必须放行。

**来源（工作单 P18），逐字**：

> **用户裁决**：**升到 block。**
>
> | 环节 | 谁在做 | 证据 |
> |---|---|---|
> | 产生拆解 | **模型** | 计划来自 cycle plan |
> | 审查拆解 | **工具** | `core/decompose_review.py`：8 条原则里 6 条完全机械 |
> | 关卡还是辅助 | **辅助** | **`DECOMPOSE_GATE_DEFAULT = "warn"`** ⇒ **违反原则时那一轮照样往下走** |
>
> ⇒ 用户这一轮的目的是「**验证好边界**」；**关卡默认关着，边界就只是建议。**

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（带 `文件:行`）

| # | 事实 | 位置 / 机械依据 |
|---|---|---|
| 1 | 拆解关卡出厂默认是 `warn`：**不合规拆解照样进入写码 / 验证**，只留痕不拦路 | `core/coding_cycle.py::CodingCycle.DECOMPOSE_GATE_DEFAULT`（HEAD v1.28 = `"warn"`，见 §2.2） |
| 2 | 于是"边界"只是建议：违反 P1/P3/P4/P8 的计划不会被拦 | `core/coding_cycle.py::_review_decomposition`（`if not review.get("passed") and mode == "block"` 才否决） |
| 3 | 即便在 `block` 下，拦下理由只写了 `violated` 列表与 summary，**逐条证据没进理由** | 同上，`report.error` 组装处（HEAD v1.28） |

### 2.2 复现命令与实测输出

**修复前（`HEAD` = v1.28 `4bfcce4`）的默认值**：

```powershell
git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle -C D:\PythonProject\SimpleAgent2_Cycle `
  show HEAD:core/coding_cycle.py | Select-String -Pattern 'DECOMPOSE_GATE_DEFAULT = '
```

```
    DECOMPOSE_GATE_DEFAULT = "warn"
```

⇒ 关卡默认关闭：`WORK-ORDER.md` P18 的原话「**违反原则时那一轮照样往下走**」在源码层成立。

**为什么这是问题**：用户这一轮的目的正是「**验证好边界**」。**关卡默认关着，边界就只是建议** ——
不合规的拆解（并列词、多交付物、无逐叶判据、反复改同一文件）不会被拦，
能力画像里的 `pass` 就分不清「拆得对」与「拆得烂但碰巧过」。这是把尺**默认收起来**。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle -C D:\PythonProject\SimpleAgent2_Cycle status --short
git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle -C D:\PythonProject\SimpleAgent2_Cycle diff --stat
```

```
=== git status --short ===
 M CYCLE.md
 M README.md
 M core/coding_cycle.py
 M core/skill_runner.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
 M docs/PENDING_DECISIONS.md
 M tests/unit/test_artifact_binding.py
 M tests/unit/test_criterion_ownership.py
 M tests/unit/test_cycle_manifest.py
 M tests/unit/test_decompose_review.py
 M tests/unit/test_deliverables.py
 M tests/unit/test_pass_evidence.py
 M tests/unit/test_reuse_scope.py
 M tests/unit/test_transparency.py
 M tests/unit/test_verify_vacuous.py
?? docs/EVALUATION-DECOMPOSE-GATE-BLOCK.md
=== git diff --stat ===
 CYCLE.md                               |  2 +-
 README.md                              |  3 +-
 core/coding_cycle.py                   | 36 ++++++++++----
 core/skill_runner.py                   |  2 +-
 docs/ARCHITECTURE.md                   |  2 +-
 docs/CHANGELOG.md                      | 62 ++++++++++++++++++++++++
 docs/MODULES.md                        | 11 +++--
 docs/OPERATIONS.md                     | 10 ++--
 docs/PENDING_DECISIONS.md              | 23 ++++-----
 tests/unit/test_artifact_binding.py    | 12 ++++-
 tests/unit/test_criterion_ownership.py |  3 +-
 tests/unit/test_cycle_manifest.py      | 10 +++-
 tests/unit/test_decompose_review.py    | 88 ++++++++++++++++++++++++++++++++--
 tests/unit/test_deliverables.py        |  3 +-
 tests/unit/test_pass_evidence.py       |  2 +-
 tests/unit/test_reuse_scope.py         |  6 +++
 tests/unit/test_transparency.py        |  5 +-
 tests/unit/test_verify_vacuous.py      |  4 +-
 18 files changed, 238 insertions(+), 46 deletions(-)
```

> 说明：`git diff --stat` **不含未跟踪的新文件**（本评估文档）。新文件的权威依据是上面的
> `git status --short`（`??` 行）与 §8 的备份点 `git show --stat`。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/coding_cycle.py` | `DECOMPOSE_GATE_DEFAULT` | `"warn" → "block"`（P18 要求 1/3） |
| 2 | `core/coding_cycle.py` | `_review_decomposition` 否决分支 | 拦下理由补**逐条证据**（P18 要求 2） |
| 3 | `core/skill_runner.py` | `render_task_description` | 样板文本「目标**与**参数」撞 P3 并列词 ⇒ 每次技能重放都会被拦；改顿号（见 §4.4） |
| 4 | `tests/unit/test_decompose_review.py` | 新增 `[V4]` | 出厂默认 `block` 的**双向**验收（P18 验收 1/2） |
| 5 | `tests/unit/test_artifact_binding.py` | `[P8]` 组 | 该组改为**显式** `warn`（原依赖默认值，默认改后必须显式） |
| 6 | `tests/unit/test_criterion_ownership.py` | `StubOrch` | 假编排器补 `expected_output`（合规夹具） |
| 7 | `tests/unit/test_pass_evidence.py` | `StubOrch` | 同上 |
| 8 | `tests/unit/test_deliverables.py` | `GateOrch` | 同上 |
| 9 | `tests/unit/test_verify_vacuous.py` | 任务描述 | 「列出工作区内的文件**和**目录」→「列出工作区内容」（P3） |
| 10 | `tests/unit/test_transparency.py` | `ROUND2_TASKS` | 第二轮不再点名 `mod.py`（否则与第一轮构成 P4） |
| 11 | `tests/unit/test_cycle_manifest.py` | 顶部 + `Task` | 夹具本身必须多符号（测 manifest）⇒ **显式** `DECOMPOSE_GATE=off` |
| 12 | `tests/unit/test_reuse_scope.py` | §5 | `app.py` 必须同时交付 `app`/`ping`（测 P7b）⇒ **显式** `DECOMPOSE_GATE=off` |
| 13 | `docs/MODULES.md` | §28 | 默认值、拦下理由、门禁项数（19→33）如实更新 |
| 14 | `docs/OPERATIONS.md` | §4.17 | 默认值如实更新；顺带修两处历史控制字符损坏（`\x0calse`→`false`、`\x08lock`→`block`） |
| 15 | `docs/PENDING_DECISIONS.md` | C11（表 + 详节） | 用户已裁决 ⇒ 标注「已做」 |
| 16 | `docs/CHANGELOG.md` | 新增 §43 | 过程记录（§43.4 如实列出夹具适配） |
| 17 | `README.md` / `CYCLE.md` / `docs/ARCHITECTURE.md` / `docs/MODULES.md` / `docs/OPERATIONS.md` | 顶部版本戳 | `§42 → §43`（文档一致性门禁要求 == CHANGELOG 最新条目） |
| 18 | `README.md` | 文档表 | 登记本评估文档（否则文档不变量第 7 组判红） |
| 19 | `docs/EVALUATION-DECOMPOSE-GATE-BLOCK.md` | 新文件 | 本评估文档 |

**若两者不一致**：机械输出里 `git diff --stat` 不含新文件（第 19 项）与 `docs/VERSIONS.md`
（由 `tests/backup.py` 在提交后追加）；这两项的权威依据是 §8 的备份点 `git show --stat`。

---

## 4. 主张与验证命令（对应 C2、C3）

### 4.1 出厂默认值已改（P18 验收 2）

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import os,sys; sys.path.insert(0,r'D:\PythonProject\SimpleAgent2_Cycle'); os.chdir(r'D:\PythonProject\SimpleAgent2_Cycle'); from core import CodingCycle; os.environ.pop('DECOMPOSE_GATE',None); c=CodingCycle(orchestrator=None,worker=None); print('DECOMPOSE_GATE_DEFAULT =', CodingCycle.DECOMPOSE_GATE_DEFAULT); print('_decompose_gate_mode() =', c._decompose_gate_mode()); print('env DECOMPOSE_GATE =', repr(os.environ.get('DECOMPOSE_GATE')))"
```

```
DECOMPOSE_GATE_DEFAULT = block
_decompose_gate_mode() = block
env DECOMPOSE_GATE = None
```

⇒ **不设任何环境变量**时默认就是 `block`（环境变量确实没设）。

### 4.2 双向验收：不合规被拦 + 合规放行（P18 验收 1）

```powershell
& "D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe" tests\unit\test_decompose_review.py
```

`[V4] P18：不设 DECOMPOSE_GATE ⇒ 出厂默认 block（双向验收）` 段回显：

```
  默认 + 不合规：phase=failed outcome=fail kind=decomposition-violation
    error=拆解合规审查**否决**（机械层，mode=block）：违反 ['P3'] —— 机械层：5 条通过 / 1 条违反 ['P3'] / 2 条判不了 ['P2', 'P5']；**且 L3 判断类审查未启用**（REVIEW 未配置）。逐条证据：P3（mechanical）：t1「写 add.py 并测试它」含并列词 ['并']。要求：
    事件：mode='block' applied=True violated=['P3']
  默认 + 合规：phase=record outcome=pass kind=verified
    事件：mode='block' applied=True passed=True violated=[]
```

断言：

```
通过 33/33
```

关键断言（逐条）：`★ 类默认值 == block` · `★ 不设环境变量 ⇒ _decompose_gate_mode() == 'block'` ·
`环境变量 off/warn/block 仍可覆盖（保留灰度）` · `非法值回落到默认 block（不是静默放行）` ·
`★ 默认拦下不合规拆解（phase=failed / decomposition-violation）` · `★ 结局是 fail（不是 pass，也不是 invalid）` ·
`拦下理由写明违反了 P3` · `★ 拦下理由带逐条证据（不是只说『违反了』）` ·
`事件：mode=block / applied=True / violated 含 P3` · `事件 principles 里 P3 带 evidence（留痕可复核）` ·
`★ 默认放行合规拆解（双向，不是一律拦死）` · `合规拆解：passed=True 且 applied=True（默认真的在把关）`。

> **反空洞**：`[V4]` 不设任何环境变量（`os.environ.pop("DECOMPOSE_GATE", None)`），
> 因此它证明的是**出厂行为**，不是"测试里手动打开关卡"。

### 4.3 其他门禁

| # | 主张 | 验证命令 | 结果 |
|---|---|---|---|
| 1 | 全量单测通过 | `python tests\run_unit.py` | **47/47**（见 §4.5，通过数以脚本回显为准） |
| 2 | 文档一致性通过 | `python tests\unit\test_doc_consistency.py` | **35/35** |
| 3 | 文档不变量通过 | `python tests\unit\test_doc_invariants.py` | **35/35** |
| 4 | 文档审查通过 | `python tests\unit\test_doc_review.py` | **18/18** |
| 5 | 契约符合性通过 | `python tests\unit\test_contract_conformance.py` | **44/44** |
| 6 | 前端契约通过 | `python tests\unit\test_frontend_contract.py` | **25/25** |
| 7 | 套件卫生通过 | `python tests\unit\test_suite_hygiene.py` | **4/4** |

```powershell
& "D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe" tests\run_unit.py
```

```
通过 47/47
```

### 4.4 `block` 默认暴露并修掉的一处交互（技能重放）

**现象**：`core/skill_runner.py::render_task_description` 的样板文本写着
「必须按上面的目标**与**参数重新实现」；P3 的判据是"描述里出现并列词即疑似两件事"。
默认升到 `block` 后，**每次技能重放都会被自己的样板文案拦下**（实跑 `test_skills.py` 时红）。

**修法**：改为「必须按上面的目标、参数重新实现」（顿号，语义不变）。

**验证**：

```powershell
python -c "from core.decompose_review import CONJUNCTIONS; from core.skill_runner import render_task_description; ...; print([c for c in CONJUNCTIONS if c in d])"
```

```
conjunctions hit: []
```

### 4.5 D30（可选项）：文档里写死的版本号 / 计数再复查

| 声称 | 机械真值 | 结论 |
|---|---|---|
| 上游事件种类数 | `len(core.contract.EVENTS) == 18` | `test_doc_invariants` 第 10 组机判（含反向：合成「999 种」必被判不一致） |
| 责任划分规则数 | `len(core.contract.ISSUE_RULES) == 23` | `test_doc_invariants` 第 8 组机判 |
| 工具数 | `len(tools.TOOLS_MAP) == 18` | `test_doc_consistency` 第 1 组机判 |
| `VERSIONS.md` 的「事件 16 → 19」 | 已在 `v1.24` 勘误为 `16 → 18`；历史评估文档只加勘误注（不重排） | 本轮复查无新的「声明 vs 实现」漂移；§3 顺手修 `MODULES.md` §28 的门禁项数 `19 → 33` |

**未验证的部分**（诚实列出）：

- **没有跑真实模型**。本轮的验收全在离线门禁 + 生产构造路径（`CodingCycle.run`）上取；
  `P18` 的"真实 7B 分解会被拦"没有实跑（那需要模型端点，且会修改 `workspace/`）。
- **没有改 `.interface_contract/`**（只读），也没有跑统筹方的门禁脚本（不触碰对侧仓库 / 集成工作区）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 仍 18 种 |
| 事件 payload 键 | **无** | `decompose_review` 的键未增（`violated` / `principles` 本就有） |
| 上游 `PHASE_ORDER` 阶段 | **无** | 仍 `plan/write/check/verify/record` |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | 未增删；`decompose_review` 是既有字段，内部 dict 键未增 |
| `TOOLS_MAP` 条目结构 | **无** | 仍 18 个工具 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 仍 `1.1` / `1.0` / `1.0`（纯内部默认值变更） |
| 端点路径 | **无** | 未动 |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 只读未动 |

**结论**：本次是**纯后端内部默认值 + 一处样板措辞**的变更，**对接口契约零影响**
（无 additive、无 breaking）。前端不需要跟改。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不要**。默认值不是接口面：`/profile` 未暴露该默认值，
  事件 payload 未变，前端读到的 `decompose_review.mode` 只会从 `warn` 变成 `block`
  （该字段本就有，语义已在契约里写明）。
- **有没有可能"问题被平移到对侧"**？**没有**。这是本侧内部的门禁强度，
  不依赖对端上报；把关卡升到 `block` 只会让本侧更早失败，不会把责任推给前端。
- **前端会静默少显示什么吗**？不会。`mode` / `applied` / `violated` / `principles`
  这些键一个没少，只是取值变化。

---

## 7. 不做的部分及理由（对应 C7）

- **不做真实模型实跑**：那会写 `workspace/`、需要模型端点；本轮的判据是"默认值 + 双向拦截"，
  离线测试已能机判（§4.1 / §4.2）。
- **不动 `P16`（多语言）**：`DISPATCH.md` 明写「**现在别动**，用户裁决随后再上」。
- **不动 `P12`（子模型细节读取）**：等 P11 地图可信后再上（工作单原话）。
- **不重做 P14/P15/P13/P11/P17**：前四项在 `R-8b28b25a1f` 交付，P17 在 `R-ecc61d8543` 交付，
  均有独立评估文档（见 §8）。
- **不重写 `core/decompose_review.py` 的判据**：八条原则本体在 `core/contract.py::DECOMPOSE_PRINCIPLES`
  （L1 契约载荷），执行方只读；本次只改"默认用不用否决权"与"拦下时写不写证据"。
- **不改 `render_task_description` 的语义**：只把并列词换成顿号（§4.4）。
- **不手工重排 `VERSIONS.md` 历史条目**：由 `tests/backup.py` 追加。

---

## 8. 回退点（对应 C8）

- **回退命令**：`git reset --hard <v1.29 备份点>`（本条目所在提交，提交信息以 `v1.29:` 开头；
  定位：`git log --oneline --grep "^v1.29:"`）。
- **回退会丢什么**：`DECOMPOSE_GATE_DEFAULT` 回到 `warn`（关卡重新只留痕不拦路）、
  拦下理由的逐条证据、技能样板措辞修正、`[V4]` 双向验收与本评估文档。
  **不会**丢 `core/evidence.py` 等 P17 成果（上一轮 `R-ecc61d8543` 已提交）。
- **更细粒度的回退**：只改一行 `DECOMPOSE_GATE_DEFAULT = "warn"` 即可恢复灰度默认，
  其余（证据、测试）都不依赖它。

---

## 9. 自检结论

- **C1 问题陈述可复现**：满足。§2.2 给出 `git show HEAD:core/coding_cycle.py` 的原文与回显
  （`DECOMPOSE_GATE_DEFAULT = "warn"`），并写明 `文件:行`。
- **C2 每条主张带可复现验证命令**：满足。§4.1–§4.5 每条都有完整命令。
- **C3 命令实测输出支持该主张**：满足。§4 的输出均为本轮实跑回显（含 `[V4]` 双向、47/47）。
- **C4 改动清单与实际一致**：满足。§3 先贴 `git status --short` + `git diff --stat`；
  并显式点出机械输出**不含**未跟踪的评估文档与 `VERSIONS.md`（以备份点为准）。
- **C5 对接口契约的影响已声明**：满足。§5 逐项写"无"，并说明本次是纯内部默认值变更。
- **C6 对另一侧的影响已评估**：满足。§6 结论是"不需要跟改、不平移、不静默少显示"。
- **C7 未把接口级问题当内部问题处理**：满足。§7 明确划出未做范围（P16/P12、真实模型实跑）。
- **C8 回退点明确**：满足。§8 给出 `git reset --hard` 的定位命令与回退会丢什么。
- **契约目录只读**：满足。`.interface_contract/` 未被写入（见 §3 机械输出）。
- **对侧仓库 / 集成工作区未写入**：满足。本轮所有命令都在 `D:\PythonProject\SimpleAgent2_Cycle`
  内执行；未对 `SimpleAgent2_Cycle_VueWeb` 或 `SimpleAgent2_Integration` 做任何写操作。

**希望统筹重点验证哪一条**：
**§4.2 的"双向"**（不合规被拦、且合规放行）与**§4.4 的交互修正** ——
后者是 `block` 默认暴露出来的真实产品问题（技能样板的并列词），
不是为了让测试变绿而放宽门禁；请对照 `docs/CHANGELOG.md` §43.4 的三类夹具适配逐条复核。
