# 变更评估文档 · `ARCH-A1A-A4`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收标准：`.interface_contract/ARCHITECTURE-CHECKLIST.md`（A1–A5）+ `CHANGE-PROCESS.md` C1–C8。
>
> **每个"主张"都跟一条可复现的命令。** 命令在仓库根执行，
> `$PY` = `.venv\Scripts\python.exe`。

---

- **变更编号**：`ARCH-A1A-A4`（架构级 A1a + A2 + A3 + A4；A5 是决定无待办）
- **提出方**：用户（"架构级别层面的按照你的想法执行吧，写在清单里，我都批准了"）→ 统筹方拆成清单
- **执行侧**：frontend（本仓库：`bridge/` + `frontend/` + `scripts/`）
- **日期**：2026-09-26
- **契约版本**：`1.0.6`

---

## 1. 变更意图

> 引原话，不转述。

用户：

> 「架构级别层面的按照你的想法执行吧，写在清单里，我都批准了」

统筹方 `DISPATCH.md`（2026-09-26 09:40）：

> **你侧有三项（A1 的一部分 + A2 + A3 + A4）**
> | **A1a** | 两个对账入口**按职责切分**，不合并 | `/api/audit` 自述"本地自检"；**跨侧归属改为引用上游 `code`**，不再自行下结论 |
> | **A2** | `VueWeb\backend\` 过期副本：**启动硬警告 + 探针暴露 + 陈旧检测** | … |
> | **A3** | 两个同名 `core` 包 | **随 A2** —— 指针显式化即消除歧义，不额外做动作 |
> | **A4** | 补 `docs/VERSIONS.md` | 由 `backup.ps1` **自动追加**：标签 / **改了什么** / 验证结果 / 还原命令 |

清单纪律（§执行与验收流程）：

> 「**统筹方不代改代码。** 清单里的"目标形态"是**约束**，不是实现方案 ——
> 具体怎么写由对应工作流决定，只要满足验收标准。
> 若某条验收标准与实现冲突，**回来改清单**（走变更流程），不要悄悄放宽。」

---

## 2. 问题陈述与复现方式（对应 C1）

**现象 A2**（这是本轮最要紧的一条：**不报错的失效**）

```powershell
$PY -c "import os; print(len([f for f in os.listdir('backend/core') if f.endswith('.py')]))"
$PY -c "import os; print(len([f for f in os.listdir(r'D:\PythonProject\SimpleAgent2_Cycle\core') if f.endswith('.py')]))"
$PY -c "import os; print(os.path.isfile('backend/core/contract.py'))"
```

**实际输出**

```
27
29
False
```

再确认差异清单（节选）：

```
上游有、bundled 缺：['contract.py', 'vision.py']
两边都有但内容不同：9 个（__init__ / coding_cycle / compress / config /
                        doc_review / memory / model_profile / orchestrator / worker）
```

**为什么这是问题**：缺 `contract.py` → **新契约机制整体静默不可用**，
而**服务照常启动、界面照常显示、没有任何一处报错**。

**现象 A1a**：两个对账入口并存，却对"同一件事该谁改"可能给两个答案 ——
bridge 自造了一套跨侧判定（`frontend.missing_upstream_events` 之类），
与契约的规则名/归属是两套东西。复现：

```powershell
$PY -c "import sys;sys.path.insert(0,'tests');from _bootstrap import ROOT;from bridge.audit import run;from bridge.spec import build_spec;s=build_spec();c={'contract_version':'1.0','upstream_event_kinds':[],'frontend_event_kinds':[],'phases':[],'bridge_gate_steps':[],'frontend_endpoints':[],'upstream_endpoints':[]};print([i.id for i in run(s,c).issues])"
```

改前输出里是 `frontend.missing_upstream_events`、`frontend.contract_version_skew` 等
**自造名字**；改后是 `P-event-unknown-to-frontend`、`P-version-behind` 等**契约 code**。

**现象 A4**：版本只有一个目录名。

```powershell
.\scripts\backup.ps1 -List | Select-Object -First 2
```

改前：只有时间戳 + 标签 + `-Note` 文字，**没有"改了什么 / 验证结果 / 怎么退"**。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 改什么 |
|---|---|---|
| 1 | `bridge/audit.py` | `AUTHORITY`/`AUTHORITY_NOTE` 自述权威范围；`UPSTREAM_RULES`（抄自契约 `upstream_only`）；`DEVIATIONS`（声明偏离）；`_cross()`（跨侧判定统一构造）；`_version_lt()`；`Issue.code`；版本方向拆成 behind/ahead/unparsable；`P-missing-field` 改 info；ops 判定 id 改用契约 code |
| 2 | `bridge/contract_vocab.py` | `load_crosswalk()` 读契约 JSON；`owner_of`/`severity_of` **优先契约**、镜像表降级为回退；`code_of()`；`extract_code()`（取纯 code，去掉契约那一列的限定语） |
| 3 | `bridge/staleness.py` | **新增**：`MARKERS` / `probe()` / `startup_warning()` / `read_contract_version()` / `core_modules()` |
| 4 | `bridge/app.py` | 启动期打陈旧警告；日志加"上游目录（自带/外部）" |
| 5 | `bridge/agent_api.py` | `/api/health` 暴露 `backend_dir` / `backend_is_bundled` / `backend_stale` / `backend_stale_reason` / `backend_core_modules` / `backend_contract_version` |
| 6 | `scripts/doctor.py` | 「路径与隔离」节纳入陈旧结论（bundled→WARN / 外部→FAIL） |
| 7 | `scripts/versions.py` | **新增**：`docs/VERSIONS.md` 的只增不改追加逻辑 + CLI |
| 8 | `scripts/backup.ps1` | `Compare-Snapshot()` 抽出；`Invoke-Preflight()`；`Add-VersionRecord()`；`-SkipVerify` |
| 9 | `docs/VERSIONS.md` | **新增**：头部（纪律/起点）+ v10 起点条目 |
| 10 | `tests/unit/test_staleness.py` | **新增** 34 项 |
| 11 | `tests/unit/test_audit_authority.py` | **新增** 35 项 |
| 12 | `tests/unit/test_versions.py` | **新增** 35 项 |
| 13 | `tests/unit/test_audit.py` | 跟上 id 改名（107 项不变） |
| 14 | `tests/diagnostics/check_contract_report.py` | health 探针（A2）+ **双入口 owner 一致**（A1a 在线形式） |
| 15 | 文档 | `README` / `ARCHITECTURE` §11–12 / `MODULES` §23.1 与 §25 / `DIAGNOSTICS` §7.4–7.5 / `LAYOUT` §7.1 / `OPERATIONS` §11.3 / `CHANGELOG` §27 |

**实际 diff 规模**（本机没有 git，用等价机械核对）

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-093147_v10-warnings-consumer
```

**实际输出**

```
[改动] 17
   ~ bridge\agent_api.py
   ~ bridge\app.py
   ~ bridge\audit.py
   ~ bridge\contract_vocab.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\LAYOUT.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ README.md
   ~ scripts\backup.ps1
   ~ scripts\doctor.py
   ~ tests\diagnostics\check_contract_report.py
   ~ tests\diagnostics\check_webui_stream.py
   ~ tests\unit\test_audit.py
[新增] 7
   + bridge\staleness.py
   + docs\EVALUATION-ARCH-A1A-A4.md
   + docs\VERSIONS.md
   + scripts\versions.py
   + tests\unit\test_audit_authority.py
   + tests\unit\test_staleness.py
   + tests\unit\test_versions.py
改动合计 24 个文件。
```

**与 §3 清单对照**

| §3 清单 | 实测 | 一致？ |
|---|---|---|
| 1–2 `bridge/audit.py`、`bridge/contract_vocab.py` | `[改动]` | ✅ |
| 3 `bridge/staleness.py` | `[新增]` | ✅ |
| 4–5 `bridge/app.py`、`bridge/agent_api.py` | `[改动]` | ✅ |
| 6 `scripts/doctor.py` | `[改动]` | ✅ |
| 7 `scripts/versions.py` | `[新增]` | ✅ |
| 8 `scripts/backup.ps1` | `[改动]` | ✅ |
| 9 `docs/VERSIONS.md` | `[新增]` | ✅ |
| 10–12 三个新测试文件 | `[新增]` | ✅ |
| 13–14 `test_audit.py`、`check_contract_report.py` | `[改动]` | ✅ |
| 15 文档 | `[改动]` 7 个 `.md` | ✅ |
| — | 额外：`tests/diagnostics/check_webui_stream.py` | **§3 未列，补记**：它缺 UTF-8 输出设置，会让备份前验证读成乱码（见下） |

> **补记**：`check_webui_stream.py` 不在 §3 清单里 —— 它是我在**真跑一次备份**时
> 被验证环节发现的（不是设计出来的）。清单是动手前写的，这类"跑起来才发现"的
> 修复必然会漏，所以判定依据始终是命令输出。

**结论：C4 满足。**

---

## 4. 主张与验证命令（对应 C2、C3）

### 4.1 A1a

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | `/api/audit` 自述权威范围 | `$PY tests\unit\test_audit_authority.py` | `authority == "local-self-check"` | ✅ |
| 2 | `authority_note` 点名上游是跨侧权威 | 同上 | 含 `/contract/check` | ✅ |
| 3 | 跨侧判定的 id **就是**契约 rule code | 同上 | 无自造 `frontend.*` 名字 | ✅ |
| 4 | 归属**优先读契约 JSON**，镜像表只作回退 | 同上 | 两者逐条一致 | ✅ |
| 5 | 每条判定带 `code`；契约写「无」时为空 | 同上 | — | ✅ |
| 6 | **两个入口 owner 一致（在线）** | `$PY tests\diagnostics\check_contract_report.py` | `本地=frontend 上游=frontend` | ✅ |
| 7 | 声明偏离集合长不大 | 同上（离线） | `{P-phase-unknown}` | ✅ |

### 4.2 A2 / A3

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 8 | `/api/health` 含 `backend_dir` + `backend_is_bundled` | `$PY tests\diagnostics\check_contract_report.py` §[0] | 存在且类型正确 | ✅ |
| 9 | bundled 模式启动输出含醒目警告（**可被测试断言字符串**） | `$PY tests\unit\test_staleness.py` | `startup_warning()` 返回含"仓库自带"的横幅 | ✅ |
| 10 | **负向**：指向缺 contract.py 的目录 → 报落后 | 同上 | `stale is True` 且点名该文件 | ✅ |
| 11 | `doctor.py` 输出该结论 | `python scripts\doctor.py` | 「路径与隔离」节含陈旧项 | ✅ |
| 12 | A3：判据是 `paths.BACKEND_DIR` | `$PY tests\unit\test_staleness.py` | bundled 判据 == 路径相等 | ✅ |

### 4.3 A4

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 13 | `docs/VERSIONS.md` 存在且被 README 登记 | `$PY tests\unit\test_versions.py` | — | ✅ |
| 14 | `backup.ps1` 成功备份后**自动追加**一条（含四字段） | `.\scripts\backup.ps1 -Label <x>` | 多一条 | ✅ 见 §4.4 |
| 15 | 记录**只增不改**（旧条目逐字未变） | `$PY tests\unit\test_versions.py` | — | ✅ |
| 16 | 缺失字段写"未记录"，不编 | 同上 | — | ✅ |
| 17 | 全量无回归 | `$PY tests\run_unit.py` | `32/32` | ✅ |
| 18 | 统筹方契约测试 | `test_interface_contract.py --backend 8230` | `29/29` | ✅ |

### 4.4 第 14 项的实测（真跑一次备份）

见 §8 的回退点小节 —— 本轮最后那次 `backup.ps1` 就是证据，
`docs/VERSIONS.md` 的条目数与内容可直接查看：

```powershell
$PY scripts\versions.py list
```

**未验证的部分**（诚实列出）

- **界面未人眼看**：`/api/health` 新增字段没有对应的前端展示改动
  （本轮没动前端界面），所以不存在"渲染未验"问题；但**顶栏徽标**里
  `auditLabel` 的提示条数仍是上一轮加、**仍未人眼确认**（与既有覆盖缺口同一条）。
- **陈旧检测的判据是"标记文件"，不是"与上游逐模块比对"**：
  不提供 `AGENT_UPSTREAM_DIR` 时只能判"缺不缺关键模块"，判不出"9 个模块里哪个旧"。
  给了参照物才能列出差异（`missing_vs_reference`）。
- **真实上游若也缺 `vision.py`**，本仓库会报落后而其实两边一致 ——
  标记是"应当存在"的假设，不是"与上游一致"的证明。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | — |
| 事件 payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无改动值** | 仍只读上报 |
| `SPEC_VERSION` | **无** | additive |
| 端点路径 | **无新增/无改名** | `ENDPOINTS` 仍 14 条；`/api/audit`、`/api/health` 路径未变 |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 只读资产，一字未改 |

**`/api/audit` 响应新增字段（additive）**

```
authority       : "local-self-check"
authority_note  : 跨侧归属以上游 /contract/check 为准的说明
（每条 issue 新增 code 字段 = 契约 upstream_equivalent；空 = 契约写「无」）
```

**`/api/health` 响应新增字段（additive）**

```
backend_dir / backend_is_bundled / backend_stale / backend_stale_reason
backend_core_modules / backend_contract_version
```

**改动的 id（对消费方可见，但只影响字符串）**

跨侧判定的 id 从自造名字改成契约 code。影响面已核对：
- 前端只用 `i.id` 当 `:key`，无逻辑依赖（`TopBar.vue`）；
- 契约测试 29/29 仍通过（它不比对 bridge 自己的 id）；
- 本仓库的测试与文档已同步。

> ⚠️ **这算不算 breaking？** 对"把 `/api/audit` 的 id 当接口用"的消费方算。
> 我判定为**可接受的接口收紧**：A1a 的决定就是"同一件事只有一个判据"，
> 而名字统一是它的直接后果。**若统筹方认为需要兼容期，请说明，我可以加别名映射。**

**性质**：结构上 **additive**；id 改名是**内部标识收紧**，已在上面显式声明。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要。** 本轮没有触碰任何上游事实面（§5）。
  上游 `/contract/check` 不需要知道 bridge 的 id 变了。

- **有没有可能"问题被平移到对侧"？** 本轮有**两处**，一处已修、一处**显式声明**：

  1. **已修：契约版本方向没分。** 我原来把版本不一致一律判 `frontend/degraded`。
     契约有两条方向相反的规则 —— 前端**领先**时归属 **`backend`/breaking**
     （后端没跟上）。不分方向会把"后端落后"判成"前端要改"，
     **正是把问题平移到了对侧**。已拆成 behind / ahead / unparsable 三条。

  2. **声明：`P-phase-unknown` 判 `both` 而非契约的 `backend`。**
     理由已写进 `audit.DEVIATIONS`（见 §7）。

- **前端会静默少显示什么吗？**
  `authority` / `authority_note` / `code` 都是 additive，前端不读也不影响；
  `backend_*` 是 `/api/health` 的 additive 字段。**不会静默少显示。**

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/` 任何文件**（只读资产）。
- **不删除 `backend/` 副本**（A2 的决定明确是"保留开箱可跑，但让它无法被静默使用"）。
- **A3 不额外做动作**（清单原话：指针显式化即消除歧义）——
  只补文档，说明判据是 `paths.BACKEND_DIR`。
- **不追溯补写 `v1`…`v9` 的版本记录**：凭记忆补出来的记录不是记录。
- **A4 不做"验证不过拒绝备份"**：清单没要求；上游是那么做的，但本仓库**刻意不同** ——
  最需要备份的时候恰恰是东西坏掉的时候。这个偏离写在 `docs/VERSIONS.md` 头部。
- **不改 `ops` 通道的 `warnings` 适用范围**（上一轮 §26 的疑问未获答复，本轮保持）。

### 请统筹方裁决的两处

1. **`P-phase-unknown` 的归属。** 契约 `rule_crosswalk.upstream_only` 判
   `backend`/breaking。但"前端新画了一个阶段"与"上游删了一个前端还在画的阶段"
   **现象完全一样**，事实源判不出方向 —— 按 `boundary_definition` 应判 `both`。
   契约 `empirical_evidence.S2` 自己把这条的归因称为
   "让后端去恢复一个它从未拥有的东西"。
   我判 `both`/`degraded` 并记进 `DEVIATIONS`。**请裁决。**
   若维持 `backend`，请说明两者如何区分；若改判 `both`，我删一条即可。

2. **`U-dead-event` 的级别在契约内部不一致。** `rule_crosswalk` 的行里写 `breaking`，
   而 `upstream_only` 那一列写 `degraded`。按 code 对账的消费方会因此对不上。
   本模块取行里的值。**建议契约统一。**

---

## 8. 回退点（对应 C8）

- **整树回退**

  ```powershell
  .\scripts\backup.ps1 -List
  # → 20260926-093147_v10-warnings-consumer   （本轮改动前的基线）
  .\scripts\backup.ps1 -Verify  -From v10-warnings-consumer
  .\scripts\backup.ps1 -Restore -From v10-warnings-consumer
  ```

- **文件级回退**（本轮新增了 3 个模块 + 改了 4 个源文件 + 8 个文档）

  ```powershell
  .\scripts\backup.ps1 -Restore -From v10-warnings-consumer `
      -Path bridge/audit.py -Path bridge/contract_vocab.py `
      -Path bridge/app.py -Path bridge/agent_api.py `
      -Path scripts/backup.ps1 -Path scripts/doctor.py
  ```

  覆盖前会把被点名文件的当前版本存到 `_backups/<快照>/undo-<时间戳>/`。

- **回退会丢什么**：A1a 的权威自述与 id 统一、A2 的陈旧检测、
  A4 的 `docs/VERSIONS.md` 与自动追加、8 个新测试文件。

- **回退不会丢什么**：契约镜像、`data/` 运行态、上游 `backend/`（从未改动）。

- **⚠️ 回退**必须**把测试一起退**：新增的 `test_staleness.py` /
  `test_audit_authority.py` / `test_versions.py` 会引用回退后不存在的符号。
  这是上一轮评估记下的教训（"只退源文件、不退测试会得到红着的仓库"）的第二次应用。
  `-Path` 的清单里**必须**包含它们：

  ```powershell
  .\scripts\backup.ps1 -Restore -From v10-warnings-consumer -Path tests/unit/test_staleness.py -Path tests/unit/test_audit_authority.py -Path tests/unit/test_versions.py
  ```

  > 注意：这三个文件在 v10 快照里**不存在**，`-Path` 会明确列出并跳过它们，
  > 所以整树回退是更省事的选择。这一条如实记下。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了三段可跑的命令与实测输出 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 18 行 |
| **C3** 命令输出支持主张 | **满足** | 逐条对应 |
| **C4** 改动清单与实际一致 | **满足** | §3 用 `-Verify` 机械核对；`[删除]` 2 项已解释 |
| **C5** 对接口契约的影响已声明 | **满足** | §5 逐项；并**主动声明了 id 改名对消费方的影响**，询问是否需要兼容期 |
| **C6** 对另一侧的影响已评估 | **满足** | §6 列出两处平移风险：一处**已修**（版本方向），一处**显式声明** |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明不做的部分 + **两处请统筹裁决** |
| **C8** 回退点明确 | **满足** | §8 有整树 + 文件级；并记下"必须连测试一起退" |

**我希望统筹重点验证的一条：§7 的第一处裁决请求（`P-phase-unknown` 归属）。**

理由：这是本轮**唯一一处我没有照契约做**的地方。我可以直接照抄 `backend`
让所有测试变绿，但那样就把一个**归因方向**的问题藏进了"验收通过"里 ——
而这一轮的全部工作（A1a）恰恰是关于"归因只有一个判据"的。
**把它显式列出来、请裁决，比悄悄合规更有价值。**

具体验证动作：

```powershell
$PY -c "import sys;sys.path.insert(0,'.');from bridge.audit import DEVIATIONS,UPSTREAM_RULES;print('契约:',UPSTREAM_RULES.get('P-phase-unknown'));print('本仓库:',DEVIATIONS.get('P-phase-unknown'))"
```

---

## 附：本轮的三条纪律说明

1. **测试先红后绿，抓到了三处我自己判错的地方**（版本方向、`P-missing-field` 级别、
   `_relabel` 用错键）。都不是"没想到"，而是**新测试/对账逼出来的** ——
   这与前几轮同型，说明"改完就跑"这条纪律是有效的。

2. **没有把 A2 写成 FAIL。** 直觉上"缺 core/contract.py"该是 FAIL，
   但默认用自带副本是**设计的一部分**；判 FAIL 会让默认配置永远红着，
   而"永远红着"的检查等于没有检查。改成 bundled→WARN / 外部→FAIL 之后，
   **两档都还能被测到**。这是"严重度要反映真实处境"的一次应用。

3. **把追加逻辑从 PowerShell 挪进 Python，只为可测。**
   `docs/VERSIONS.md` 的纪律是"只增不改"，而一个会静默改写历史的 bug
   比没有记录更糟。PowerShell 里的字符串拼接没法离线断言
   "旧条目逐字未变"，所以逻辑住进了 `scripts/versions.py`。
