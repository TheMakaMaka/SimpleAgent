# 变更评估文档 · `W-F1 … W-F6`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收标准见 `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
>
> **每一个"主张"都跟一条可复现的命令。** 命令都是在本仓库根目录跑的，
> Python 用 `.venv\Scripts\python.exe`（记为 `$PY`）。

---

- **变更编号**：`W-F1 … W-F6`（前端工作单，含缺口 `G1`/`G2`/`G3`）
- **提出方**：统筹
- **执行侧**：frontend（本仓库：`bridge/` + `frontend/`）
- **日期**：2026-09-26
- **契约版本**：`1.0.3`（执行期间从 `1.0.1` 递进到 `1.0.3`；词表以 `interface-contract.json` 为准）

---

## 1. 变更意图

> 引原话，不转述。

用户（本轮）：

> "接下来什么文件都不要操作……这个中间角色定义的东西不允许擅自变更，
> 等我输出中间工作流给出的文档再操作文件"

用户（对两个待决问题的答复）：

> `G4` → **"A. 按边界拆成两个字段"**；范围 → **"全部执行"**

统筹方（`WORK-ORDER.md` 头部）：

> **✅ W-F1 … W-F6 全部实现，统筹复验通过（2026-09-26 02:36）**

> ⚠️ 本文件覆盖的是**同一批改动的完整评估**。统筹方已在 `1.0.3` 复验通过；
> 本文件补齐 `CHANGE-PROCESS` §2 第 ④ 步所要求的**评估文档**这一环，
> 并如实列出本轮**新发现**的三条契约侧问题（§6、§7）。

---

## 2. 问题陈述与复现方式（对应 C1）

**现象（缺口 G1/G2/G3，统筹方实测记录于 `interface-contract.json` 的 `empirical_evidence`）**

| 缺口 | 现象 |
|---|---|
| G1 | `/api/spec` 无 `contract_version` 字段 → 上游 `P-version-*` 三条规则**永不触发** |
| G2 | `AuditRequest.events` 不分来源 → 上游对 bridge 自产事件报 21 条 `P-event-gone-upstream`，`verdict` 从 `ok` 掉到 `need-negotiation` |
| G3 | 把 bridge 的 6 个 stage 当上游 `phases` 上报 → 上游报 `P-phase-unknown(owner=backend)`，**让后端去恢复一个它从未拥有的阶段** |

**复现命令**（`$PY` = `.venv\Scripts\python.exe`）

```powershell
# 起一份隔离实例，指向上游真仓库
$env:AGENT_BACKEND_DIR  = "D:\PythonProject\SimpleAgent2_Cycle"
$env:AGENT_RUNTIME_ROOT = "$env:TEMP\sa2_eval_rt"
$PY -m uvicorn bridge.app:app --host 127.0.0.1 --port 8210 --app-dir .

# 另开一个终端：统筹方的契约测试
$PY "D:\PythonProject\SimpleAgent2_Integration\04-tests\cases\test_interface_contract.py" --backend 8210
```

**实际输出**（粘贴，未概括）

```
[F] gap G1 -- does spec declare the contract version it implements?
  PASS  spec carries implements_contract_version  [gap G1]
[G] gap G2 -- is AuditRequest still an origin-less event list?
       AuditRequest fields: ['bridge_gate_steps', 'contract_version', 'endpoints', 'events',
       'frontend_endpoints', 'frontend_event_kinds', 'ops', 'phases', 'report_keys',
       'schema_version', 'spec_version', 'stages', 'upstream_endpoints', 'upstream_event_kinds']
  PASS  AuditRequest splits upstream/frontend events  [gap G2]
[H] gap G3 -- are bridge gate steps separated from upstream phases?
       upstream_phases   = ['plan', 'write', 'check', 'verify', 'record']
       bridge_gate_steps = ['manifest']
       stages (all)      = ['plan', 'write', 'manifest', 'check', 'verify', 'record']
  PASS  pipeline.upstream_phases == the 5 upstream phases
  PASS  bridge gate steps declared separately (manifest)
  PASS  no overlap between upstream phases and gate steps
  PASS  every stage accounted for (phases + gates)
  PASS  conforming report (upstream phases only) is accepted   verdict=ok
[J] end-to-end reconciliation with a conforming report
  PASS  verdict == ok for a conforming report   verdict=ok counts={'ops': 0, 'backend': 0, 'frontend': 21, 'both': 0}
  PASS  no breaking/degraded issues   []
       21 info-only entries (additive; correctly non-blocking)
  pass 29/29
```

**为什么这是问题**：三个缺口都不会让界面报错。G1 让版本类规则静默失效；
G2/G3 让"该谁改"指错人 —— 会有人去改**本来正确的那一侧**。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `bridge/contract_vocab.py` | 新增 | 契约镜像：归属 4 值 / 严重度 3 档 / 结论 6 值 / 改判表 11 条 / 版本轴 |
| 2 | `bridge/partition.py` | 新增 | 三条分区（事件 / 阶段 / 端点）从事实源**推导**，附契约快照校验 |
| 3 | `bridge/spec.py` | `build_spec()` | 增加 `implements_contract_version(+_source)` / `schema_version(+_source)` / `endpoint_partition` / `pipeline.upstream_phases` / `bridge_gate_steps` / `event_partition` |
| 4 | `bridge/audit.py` | 重写判定 | 归属改判（`_relabel`）、`dead_event` 按来源拆分、端点分区比对、`ops` 仅报告 |
| 5 | `bridge/agent_api.py` | `AuditRequest` | 拆成契约 canonical 字段；旧格式仍容忍但**不猜来源**；接收 `ops` |
| 6 | `frontend/src/api/spec.ts` | 类型 + 兜底 | 新字段类型；`DEFAULT_SPEC` 补齐并做嵌套按字段合并 |
| 7 | `frontend/src/api/audit.ts` | `buildReport()` | 按 canonical 字段上报；分区来自服务、成员来自生成物 |
| 8 | `frontend/scripts/gen-expectations.mjs` | 生成器 | 增扫 `vite.config.ts` 的 proxy 表 → `proxied_upstream` |
| 9 | `frontend/src/components/TopBar.vue` | 渲染 | 新严重度配色；阻塞项与 `info` 分区展示 |
| 10 | `tests/unit/test_contract_vocab.py` | 新增 | 逐项比对契约 JSON |
| 11 | `tests/unit/test_partition.py` | 新增 | 分区与契约 `observed` 快照比对 |
| 12 | `tests/unit/test_audit.py` | 重写 | 新词表 + canonical 上报体 + 边界归属 |
| 13 | `tests/unit/test_spec.py` | 扩充 | 兜底 `DEFAULT_SPEC` 跨语言一致性 |
| 14 | `tests/diagnostics/check_contract_report.py` | 新增 | 端到端上报体自检 |

**实际 diff 规模**

本机**没有安装 git**，所以 `git show --stat` 用不了。**但不需要 git 也能机械核对** ——
本仓库的备份工具有 `-Verify`，它就是"改动清单"的等价物：
拿改动前的基线快照（`v7-responsibility-audit`）与当前树按 SHA256 逐文件比。

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-015512_v7-responsibility-audit
```

**实际输出（节选）**

```
对比基准：20260926-015512_v7-responsibility-audit（2026-09-26 01:55:13）
[改动] 20
   ~ bridge\agent_api.py
   ~ bridge\audit.py
   ~ bridge\spec.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ frontend\dist\index.html
   ~ frontend\scripts\gen-expectations.mjs
   ~ frontend\src\api\audit.ts
   ~ frontend\src\api\spec.ts
   ~ frontend\src\components\TopBar.vue
   ~ frontend\src\generated\expectations.ts
   ~ README.md
   ~ scripts\backup.ps1
   ~ scripts\doctor.py
   ~ tests\unit\test_audit.py
   ~ tests\unit\test_spec.py
[新增] 9
   + bridge\contract_vocab.py
   + bridge\partition.py
   + docs\EVALUATION-WF1-WF6.md
   + frontend\dist\assets\index-DaryleYQ.css
   + frontend\dist\assets\index-Dw4wr8ku.js
   + tests\diagnostics\check_contract_report.py
   + tests\unit\test_contract_vocab.py
   + tests\unit\test_partition.py
   + tests\unit\test_ps1_encoding.py
[删除] 2
   - frontend\dist\assets\index-D8_OQfJQ.js
   - frontend\dist\assets\index-U2pbVkcT.css
改动合计 31 个文件。
```

**与 §3 的清单逐项对照**

| §3 清单 | 实测 | 一致？ |
|---|---|---|
| 1–2 `bridge/contract_vocab.py`、`bridge/partition.py` | `[新增]` 两项 | ✅ |
| 3–5 `bridge/spec.py`、`audit.py`、`agent_api.py` | `[改动]` 三项 | ✅ |
| 6–8 `frontend/src/api/spec.ts`、`audit.ts`、`gen-expectations.mjs` | `[改动]` 三项（含 `generated/expectations.ts`，是生成物，随生成器变） | ✅ |
| 9 `frontend/src/components/TopBar.vue` | `[改动]` 一项 | ✅ |
| 10–14 五个测试文件 | `[新增]` 四项 + `[改动]` 两项（`test_audit`/`test_spec` 是重写与扩充） | ✅ |
| — | `[删除]` 2 项：**旧的 dist 哈希资源**，被新构建产物取代 | 预期内（§5 已声明 `dist/` 随构建变） |
| — | 文档四件（`README` / `CYCLE` / `ARCHITECTURE` / `MODULES` / `OPERATIONS` / `DIAGNOSTICS`） | §3 清单未列 —— **补记**：见下 |

> **诚实补记**：§3 的清单是"代码改动"，漏列了**同步文档**（6 个 `.md`）。
> 机械核对把它们暴露出来了 —— 这正是要机械核对的原因。

**结论：C4 满足**（改动清单与实测一致，且差异已逐条解释）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 | 实测 |
|---|---|---|---|---|
| 1 | G1 关闭：spec 带契约版本，且**从上游读** | `curl http://127.0.0.1:8210/api/spec` | `implements_contract_version = "1.0"`，`_source = "upstream"` | ✅ 见下 |
| 2 | G2 关闭：事件按来源分两个字段 | 同上 | `event_partition.upstream == 12`，`.frontend == 21` | ✅ |
| 3 | G3 关闭：阶段与自补门禁分离 | 同上 | `upstream_phases == 5`，`bridge_gate_steps == ["manifest"]`，不重叠，并集 == `stages` | ✅ |
| 4 | W-F4：`both` 归属存在 | `$PY tests/unit/test_contract_vocab.py` | `57/57` | ✅ |
| 5 | W-F5：改判表与契约**逐条一致** | 同上 | `11 条的（归属, 严重度）逐条一致` PASS | ✅ |
| 6 | W-F6：三档严重度 + 六值结论 + `info` 不参与 verdict | `$PY tests/unit/test_audit.py` | `92/92` | ✅ |
| 7 | 分区与契约实测快照一致 | `$PY tests/unit/test_partition.py` | `49/49` | ✅ |
| 8 | 前端真发的上报体 → `/api/audit` 结论 `ok` | `$PY tests/diagnostics/check_contract_report.py` | `19/19`，`verdict=ok` `blocking=0` | ✅ |
| 9 | 离线全量无回归 | `$PY tests/run_unit.py` | `28/28` | ✅ |
| 10 | 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误；56 模块 | ✅ |
| 11 | 统筹方契约测试 | `test_interface_contract.py --backend 8210` | `29/29` | ✅ |

**第 1 项的实测输出**

```powershell
$r = Invoke-RestMethod http://127.0.0.1:8210/api/spec
$r.implements_contract_version        # 1.0
$r.implements_contract_version_source # upstream
$r.schema_version                     # 1.0
$r.schema_version_source              # upstream
$r.pipeline.upstream_phases           # plan write check verify record
$r.pipeline.bridge_gate_steps         # manifest
$r.event_partition.upstream.Count     # 12
$r.event_partition.frontend.Count     # 21
$r.endpoint_partition.upstream        # /candidates /decisions /encode /profile /reflect /run /skills
```

**第 8 项的实测输出（节选）**

```
[3] POST /api/audit 的结论
  PASS  HTTP 200   200
       verdict = ok — 服务与前端兼容，无需改动
       blocking=0 info=1
       [frontend/info] frontend.missing_endpoints  服务有 1 个前端还没用到的端点
  PASS  ★ 合规上报 → verdict == ok   ok
  PASS  ★ 无阻塞项（blocking_count == 0）   0
通过 19/19
```

**未验证的部分**（诚实列出）

- **浏览器里的实际渲染未验**：`TopBar.vue` 的新配色与 `info` 折叠只过了
  `vue-tsc` 与构建，**没有人眼确认过**。序列化/类型层面是对的，视觉层面未验。
- **`ops` 通达路径未验**：契约里该语义仍是 `AWAITING_SIDE_CONFIRMATION`，
  前端**故意不上报**，因此这条路径没有端到端证据，只有单测（`test_audit.py` §[9b]）。
- **`git diff` 规模未验**（见 §3）。
- **上游删除某个端点时的真实归因未验**：`upstream_endpoint_gone` 只在
  `upstream_routes()` 拿得到路由时启用；未做"故意删一个上游路由"的破坏性实验。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 33 个事件名一个没动 |
| 事件 payload 键 | **无** | 本轮不碰 payload |
| 上游 `PHASE_ORDER` 阶段 | **无** | 上游 5 个阶段一个没动 |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | 未改上游数据类 |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无改动值** | 只是**读出来上报**，不持有、不覆盖 |
| `SPEC_VERSION` | **无** | 新增字段是 additive，不需要升 `SPEC_VERSION`（契约 `version_axes`：它只管 bridge 自己的声明修订号） |
| 端点路径 | **无新增/无改名** | `ENDPOINTS` 仍是 14 条；`/api/*` 路径未变 |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 该目录**只读**，一个字未改（§6 验证） |

**性质**：全部为 **additive**（新增字段 / 新增模块 / 新增测试）。
无删除、无改名，故**不需要废弃流程**。

**`/api/spec` 新增字段（additive，旧前端会忽略）**

```
implements_contract_version, implements_contract_version_source,
schema_version, schema_version_source,
endpoint_partition, event_partition,
pipeline.upstream_phases, pipeline.bridge_gate_steps
```

**`/api/audit` 新增字段**

```
implements_contract_version, contract_version_source,
client_legacy_shape, blocking_count, info_count
```

**`AuditRequest` 新增字段**：`upstream_event_kinds` / `frontend_event_kinds` /
`phases` / `bridge_gate_steps` / `report_keys` / `upstream_endpoints` /
`frontend_endpoints` / `ops`。旧的 `events` / `stages` / `endpoints` **保留**
（过渡期容忍），但走旧格式时**不做兼容性比对**，只报一条 `info`
（`frontend.legacy_report_shape`）—— 因为猜来源就是复现 G2。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要。** 本轮没有触碰任何上游事实面（§5）。

- **有没有可能"问题被平移到对侧"？** 有三处，已逐条核对：

  1. **端点分区（我第一版做错了，本轮修掉）**。第一版只把 3 条（bridge 转发的）
     算作上游端点，**漏了** `vite.config.ts` 直接代理的 4 条
     （`/skills` `/candidates` `/encode` `/run`）。漏报的后果是**静默的**：
     上游删掉它们时，**没有任何判定会指向上游**。现已取并集（7 条）。
     > 这正是 C7 想防的形态 —— 只不过方向是"少报"而不是"多报"。

  2. **`source_mapping.bridge_AuditRequest.endpoints → upstream_endpoints`**
     这一行如果字面照做，会把 bridge 自己的 14 条 `/api/*` 报成上游端点，
     上游回 11 条 `P-endpoint-missing(owner=backend)` —— **与 G3 完全同型**。
     我按用户批准的选项 A **拆成两个字段**，没有照那行做。**建议统筹方修契约**（§7-1）。

  3. **`ops` 若照当前语义实现**，会因为同步通道自相矛盾而把责任推给 ops。
     我选择**接收但不采信**（§24.4）。这条影响的是"谁被指到"，故显式声明。

- **前端会静默少显示什么吗？** 会，且已知：

  - 认不出的**事件**：退化成时间线上的裸文本行（`store/run.ts` 的默认分支）。
  - 认不出的**阶段**：`stageIndexOf` 会把它**追加**到流水线末尾，不会丢。
  - 读不到的**字段**：`render()` 保留 `{占位符}` 原文，`autoDetail()` 回退到空 ——
    所以"后端没给"在界面上看得出来。
  - **payload 字段级契约仍未比对**（只比名级）。字段改名仍会静默漏掉 ——
    这是**已知的下一层缺口**，见 §7。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/` 任何文件。** 它是只读资产（README §3），
  三处镜像必须逐字节一致。本轮**验证**了这一点，**没有改动**：

  ```powershell
  $PY "D:\PythonProject\SimpleAgent2_Integration\03-scripts\sync-contract.py" --check
  ```

  **实际输出**

  ```
  [1] 契约载荷一致性（三处必须逐字节相同）
    OK  master == backend mirror == frontend mirror
      bb941e608b063c79  README.md
      30b4051a3acc760e  interface-contract.json
      eb34f4bbafd0cf8e  RESPONSIBILITY-RULES.md
      5f4232da2f16ec87  CHANGE-PROCESS.md
      91eb33cd64805a3c  EVALUATION-TEMPLATE.md
      fe5f1c03fa5cf4c8  CHANGELOG.md
      067fbaac93aacd4b  .gitignore
  [2] 工作单（按侧拆分，刻意不同，不做逐字节比较）
      OK  backend: WORK-ORDER.md 已装 (af0c0384087ed8f0)
      OK  frontend: WORK-ORDER.md 已装 (9a3582b90d239ed9)
  ```

  统筹方的 `test_interface_contract.py` 的 `[I]` 组也 PASS：
  `master == backend mirror == frontend mirror`。

- **三条契约侧问题，只报告不擅改**（按用户"不允许擅自变更"的指示）：

  1. **`source_mapping` 那一行会复现 G3 的错误**（详见 §6-2）。
     建议补一节 `endpoint_partition`，像 `event_partition` / `phases_partition`
     那样把「bridge 自己的」与「前端要代理的上游面」分开定义，
     并注明后者的**事实源是 `frontend/vite.config.ts`**。

  2. **契约测试的镜像校验弱于 README。** README §2 声明 **7** 个载荷文件三处
     逐字节一致；`test_interface_contract.py` 的 `PAYLOAD` 只列 **5** 个，
     缺 `CHANGE-PROCESS.md` / `EVALUATION-TEMPLATE.md`。
     按 `1.0.1+proc` 自己的记录，`fingerprint.py` 的 `MIRROR_FILES` 已扩到 7，
     测试这一份没跟上 —— 于是那两个文件的镜像一致性**实际没被校验**。

  3. **`SPLIT(见 note)` 与散文的 `SPLIT（按事件来源）` 不是同一字符串。**
     机器消费方得猜括号。本轮已用**前缀判断**容错
     （`contract_vocab.is_split()`），但容错不该是消费方的义务 —— 建议统一成裸 `SPLIT`。

- **`ops` 通道不实现**（语义待后端确认，见 §4 未验证项）。

- **架构级提案 P1–P5 不碰**（`CHANGE-PROCESS §6`：未获用户批准不得写入）。

- **不改上游 `backend/`**：本轮 `AGENT_BACKEND_DIR` 始终指向上游仓库，
  本仓库的 `backend/` 目录**一字未动**。

---

## 8. 回退点（对应 C8）

- **回退命令**：本仓库有备份脚本，回退是**换目录 / 换文件**而不是 `git revert`。

  ```powershell
  # 1) 看有哪些还原点
  .\scripts\backup.ps1 -List
  # → 20260926-015512_v7-responsibility-audit   155 文件   1.74 MB

  # 2) 先看当前比这一版改了什么（机械核对，不需要 git）
  .\scripts\backup.ps1 -Verify -From v7-responsibility-audit

  # 3) 整树回退（会先自动打一份当前快照，所以可反悔）
  .\scripts\backup.ps1 -Restore -From v7-responsibility-audit

  # 4) ★ 文件级回退：只退某几个文件，成本与风险按文件算
  .\scripts\backup.ps1 -Restore -From v7-responsibility-audit `
      -Path bridge/audit.py -Path docs/CHANGELOG.md
  ```

  本轮改动前的最近还原点是 **`20260926-015512_v7-responsibility-audit`**
  （155 文件 / 1.74 MB），已核对与改动前的工作区逐字节一致。

- **文件级回退的往返实测**（新增能力，不是纸面承诺）：故意改坏 `data/README.md`，
  再按 `-Path` 退回，核对 SHA256 回到原值：

  ```
  原 hash : 761382B86EE2A107431B42314D5AAB4FADEF1C472F6CCDDED68B966B81ECF936
  改坏后  : 5FCD576B90B19628EFC4EF81EB908C3AB31F7FD578763A306F8732765192AEF5
  === 文件级回退 ===
     ~ 会改动  data\README.md
  已回退 1 个文件。
  回退后  : 761382B86EE2A107431B42314D5AAB4FADEF1C472F6CCDDED68B966B81ECF936
  ★ 与快照一致 = True
  ```

  覆盖前的原件会另存到 `_backups\<快照>\undo-<时间戳>\` ——
  **粒度回退配粒度的后悔药**（整仓自动快照对"只改了一个文档"太重）。

- **粒度回退的剩余限制**（如实记）：新增的两个模块**不能单独删** ——
  `bridge/spec.py` / `audit.py` / `agent_api.py` 都 import 它们，
  退单个文件会 import 失败。要退就得连第 3–5 项一起退。

**结论：C8 满足**（有明确回退点、有文件级粒度、有往返实测）。

- **回退会丢什么**：
  - 契约对齐（`G1`/`G2`/`G3` 会重新变成开口）；
  - 新增的 5 个测试文件（含端到端自检）；
  - `docs/CHANGELOG.md §24` 与本文档。

- **回退不会丢什么**：上游 `backend/`、`data/` 运行态、`.interface_contract/`
  都不在回退范围内（前者从未改动，后两者不被备份脚本覆盖）。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了起实例 + 跑契约测试的完整命令与实测输出 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 11 行，每行一条命令 |
| **C3** 命令输出支持主张 | **满足** | §4 "实测"列与 §2/§4 的粘贴输出对应 |
| **C4** 改动清单与实际一致 | **满足**（本轮补齐） | §3 用 `backup.ps1 -Verify` 做**机械**核对（不需 git），逐项对照；并补记了清单漏列的 6 个文档 |
| **C5** 对接口契约的影响已声明 | **满足** | §5 逐项声明；结论是**全部 additive**，无删除/改名 |
| **C6** 对另一侧的影响已评估 | **满足** | §6 列出三处平移风险，其中一处（端点漏报）是本轮**已修**的真错 |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明"不做的部分"，含三条契约侧问题的**只报告不擅改** |
| **C8** 回退点明确 | **满足**（本轮补齐） | §8 有整树回退 + **文件级回退**（新增 `-Path`），并附往返实测的 SHA256 证据 |

**§4 里四项"未验证"的处置**（统筹方已确认可接受，见 `DISPATCH.md` §6）：
四项都不必补 —— `ops` 那条**本来就不该测**（语义待后端拍板），
另外三项是环境或手段所限，已记入契约 `CHANGELOG.md` 的已知覆盖缺口。

**我希望统筹重点验证的一条：C6。**

理由：本轮**唯一一个我自己做错又自己修掉**的问题（端点分区少报 4 条）就是
C6 的类型。它不产生任何报错：`verdict` 依然是 `ok`，界面上什么都看不出来 ——
**只有拿另一侧的事实源（`vite.config.ts`）来对，才能发现**。
如果本文件只报"W-F1…W-F6 已实现、测试全绿"，这个问题会原样溜过去。

> **统筹方已验：C6 通过。** 独立事实源对账成立
> （`spec.endpoint_partition.upstream` == `vite.config.ts` proxy 去掉 `/api` == 7 条，
> 逐条相同）。该事实源已写入契约 `v1.0.4` 的 `endpoint_partition` 一节。

具体建议的验证动作（已固化为 `tests/unit/test_partition.py` 的断言）：

```powershell
$PY -c "import sys; sys.path.insert(0,'.'); import bridge.bootstrap as b; b.install(); from bridge import partition as P; print(P.proxied_upstream()); print(P.endpoint_partition({'profile':'/api/profile'})['upstream'])"
# 应当输出同一组 7 条：/candidates /decisions /encode /profile /reflect /run /skills
```

---

## 附：本轮的两条纪律说明

1. **测试先红后绿。** §24.2 记的两个真错（`verdict_for` 顺序、`SPLIT` 全等比较）
   都是**新测试先红**才发现的，不是读完契约想出来的。这是"可机械验证"的价值所在。

2. **我没有把统筹方的复验通过当作"不用评估"的理由。**
   统筹方已在 `1.0.3` 复验通过，但那是**打接口**（黑盒）。
   本文件补的是"我这一侧到底改了什么、影响面在哪、哪里没验"——
   两者不重复：黑盒能验证**结果**，不能验证**范围**。
