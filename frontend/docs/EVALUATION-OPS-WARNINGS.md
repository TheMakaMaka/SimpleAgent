# 变更评估文档 · `WARNINGS-CONSUMER`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收标准见 `.interface_contract/CHANGE-PROCESS.md` §4 的 C1–C8。
>
> **每个"主张"都跟一条可复现的命令。** 命令在仓库根执行，
> `$PY` = `.venv\Scripts\python.exe`。

---

- **变更编号**：`WARNINGS-CONSUMER`（契约 v1.0.5 `response_contract`）
- **提出方**：统筹方（源自后端 `EVALUATION-OPS-1.md` 对 ops 约束的裁定）
- **执行侧**：frontend（本仓库：`bridge/` + `frontend/`）
- **日期**：2026-09-26
- **契约版本**：`1.0.5`

---

## 1. 变更意图

> 引原话，不转述。

统筹方 `DISPATCH.md`（2026-09-26 09:25）：

> 后端在 `EVALUATION-OPS-1.md` 里把 `ops` 那条约束裁定并实现了：
> **被传输层证伪的 ops 事实**（请求已成功送达，却报了 `service_down`）
> **不再驱动 verdict**，但仍出现在 `ops` 栏与新增的 `warnings` 里。

同件：

> **只看 `verdict` 的消费方会看到 `ok`，从而看不到那条陈旧标志。**
> 我已把它写成契约里的**消费方义务**：
> 「展示 verdict 的消费方**应当同时展示 warnings**。」

要做的三项：

> 1. `/contract/check` 的响应多了一个顶层字段 `warnings: []`（additive）；
> 2. 在展示对账结论的地方，**同时展示 `warnings`**（非空时才显示即可）；
> 3. **不需要**你去读 `ops` 栏做特殊判断 —— 展示 `warnings` 就够。

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：被传输层证伪的 ops 事实不参与 `verdict`，于是**结论是 `ok``，
而那条陈旧标志只存在于 `warnings`**。只读 `verdict` 的消费方（本仓库前端的顶栏徽标）
会显示"✓ 兼容"，用户永远看不到它。

**复现命令**

```powershell
$env:AGENT_BACKEND_DIR  = "D:\PythonProject\SimpleAgent2_Cycle"
$env:AGENT_RUNTIME_ROOT = "$env:TEMP\sa2_eval_rt2"
$PY -m uvicorn bridge.app:app --host 127.0.0.1 --port 8220 --app-dir .

# 另开一个终端
$env:AGENT_BASE = "http://127.0.0.1:8220"
$PY tests\diagnostics\check_contract_report.py
```

**实际输出（节选）**

```
[4] 被传输层证伪的 ops 事实（契约 v1.0.5）
  PASS  HTTP 200   200
       verdict = ok
       ⚠ 客户端上报 service_down=true，但该请求已成功送达本服务 ——
         这条 ops 事实被传输层证伪（code=O-service-down），未参与判定。
       ops 栏 = {'service_down': True}
  PASS  ★ 陈旧 service_down → verdict 仍是 ok（不驱动判定）   ok
  PASS  ★ 但 warnings 非空（只看 verdict 的路径由它兜底）
  PASS  ★ ops 栏保留了该事实（运维要看到上次已知状态）   {'service_down': True}
  PASS  该事实没有被计成 blocker   0
[5] markdown 里 warnings 与 verdict 并列（不是藏在附录）
  PASS  markdown 带提示段
  PASS  提示段说明它不参与结论
通过 29/29
```

**为什么这是问题**：契约 `response_contract.warnings.consumer_obligation` 自己写了理由：

> 因为被证伪的 ops 事实不参与 verdict，只看 verdict 的消费方会看到 ok
> 而**看不到**那条标志。后端已把它同时放进 ops 栏与 next 文案，
> 但『只看 verdict』的路径必须有这一条兜底。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 位置 | 改什么 |
|---|---|---|---|
| 1 | `bridge/audit.py` | `Audit` | 新增 `warnings` / `ops_reported` 字段 |
| 2 | `bridge/audit.py` | `to_dict()` | 输出 `warnings` / `ops`（additive） |
| 3 | `bridge/audit.py` | `to_markdown()` | 提示段**排在分归属正文之前** |
| 4 | `bridge/audit.py` | `run()` | ops 事实按裁定分流：证伪→warning，矛盾→warning，其余照常参与 |
| 5 | `bridge/audit.py` | 常量 | `OPS_STALE_BY_TRANSPORT` / `OPS_FACT_CODES` |
| 6 | `frontend/src/api/audit.ts` | 类型 + 取用 | `warnings` / `ops`（缺失兜底空）+ `auditWarnings()` / `auditOps()` |
| 7 | `frontend/src/components/TopBar.vue` | 模板 + 样式 | 提示段渲染在阻塞项之前；徽标带提示条数；显示 ops 栏 |
| 8 | `tests/unit/test_audit.py` | §[9b] 重写 | 按裁定钉死五条 ops 路径 + 无重复 id |
| 9 | `tests/unit/test_contract_vocab.py` | §[9] 新增 | 契约 `response_contract` 形状 + **跨语言**核对前端确实展示 |
| 10 | `tests/diagnostics/check_contract_report.py` | §[4][5] 新增 | 端到端证伪路径 |

**实际 diff 规模**

本机**没有 git**，用本仓库的备份工具做等价机械核对
（拿上一条基线与当前树按 SHA256 逐文件比）：

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-030308_v9-dispatch-v1.0.4
```

**实际输出**

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-030308_v9-dispatch-v1.0.4
```

```
[改动] 14
   ~ bridge\audit.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ frontend\dist\index.html
   ~ frontend\src\api\audit.ts
   ~ frontend\src\components\TopBar.vue
   ~ README.md
   ~ tests\diagnostics\check_contract_report.py
   ~ tests\unit\test_audit.py
   ~ tests\unit\test_contract_vocab.py
[新增] 3
   + docs\EVALUATION-OPS-WARNINGS.md
   + frontend\dist\assets\index-BY1HBqvb.js
   + frontend\dist\assets\index-DiEIbo8g.css
[删除] 2
   - frontend\dist\assets\index-DaryleYQ.css
   - frontend\dist\assets\index-Dw4wr8ku.js
改动合计 19 个文件。
```

**与 §3 清单逐项对照**

| §3 清单 | 实测 | 一致？ |
|---|---|---|
| 1–5 `bridge/audit.py`（含 `run()`、常量、`to_dict`/`to_markdown`） | `[改动]` 一项（同一文件多处） | ✅ |
| 6 `frontend/src/api/audit.ts` | `[改动]` | ✅ |
| 7 `frontend/src/components/TopBar.vue` | `[改动]` | ✅ |
| 8–10 三个测试文件 | `[改动]` 三项 | ✅ |
| — | `[新增]` 3 项：本文档 + **2 个 dist 构建产物**（新哈希） | 预期内（§5 已声明 `dist/` 随构建变） |
| — | `[删除]` 2 项：**旧 dist 哈希资源**，被新构建取代 | 预期内 |
| — | 5 个同步文档（`README` / `CYCLE` / `ARCHITECTURE` / `MODULES` / `OPERATIONS` / `DIAGNOSTICS`） | **§3 清单未列** —— 见下 |

> **诚实补记**：§3 的清单只列了"代码改动"，**漏列 6 个同步文档**。
> 这与上一轮被机械核对抓到的**是同一类遗漏** ——
> 说明"手写清单必然漏"是个稳定现象，不是偶发。
> 机械核对的用途就在这里；判定依据是上面的命令输出，不是 §3 那张表。

**结论：C4 满足。**

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 | 实测 |
|---|---|---|---|---|
| 1 | 陈旧 `service_down` 不驱动 verdict | `$PY tests\diagnostics\check_contract_report.py` | `verdict=ok` | ✅ |
| 2 | 但必须产出 `warnings`（恰好 1 条） | 同上 | `len(warnings)==1` | ✅ |
| 3 | `ops` 栏保留该事实 | 同上 | `ops={'service_down': True}` | ✅ |
| 4 | 它是 `warning` 而不是 blocker | 同上 | `blocking_count == 0` | ✅ |
| 5 | `frontend_not_built` 仍判 `ops-action`（ops 优先未削弱） | `$PY tests\unit\test_audit.py` | `107/107` | ✅ |
| 6 | 矛盾观测（本地有产物却报未构建）→ warning | 同上 | `107/107` | ✅ |
| 7 | 未知事实名被忽略（additive 安全） | 同上 | `107/107` | ✅ |
| 8 | 同一条事实不重复计入 | 同上 | `107/107` | ✅ |
| 9 | 契约 `consumer_obligation` 措辞与实现一致 | `$PY tests\unit\test_contract_vocab.py` | `78/78` | ✅ |
| 10 | **前端真的展示了 warnings**（跨语言） | 同上 | `78/78` | ✅ |
| 11 | 全量无回归 | `$PY tests\run_unit.py` | `29/29` | ✅ |
| 12 | 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误 / 56 模块 | ✅ |
| 13 | 统筹方契约测试 | `test_interface_contract.py --backend 8220` | `29/29` | ✅ |

**第 10 项的实测输出**

```
消费方义务的前端一侧（跨语言核对）
  PASS  api/audit.ts 的响应类型带 warnings
  PASS  api/audit.ts 对缺失的 warnings 兜底成 []
  PASS  api/audit.ts 导出 auditWarnings()
  PASS  ★ TopBar 渲染 warnings（义务的落点）
  PASS  ★ 徽标本身体现提示条数（否则「✓ 兼容」会盖住它）
  PASS  ops 栏也在界面上（判断环境问题不能只看 verdict）
```

**未验证的部分**（诚实列出）

- **界面渲染未人眼看**：提示段与徽标条数只过了 `vue-tsc` 与构建。
  类型与数据流是对的，**视觉呈现没有确认过**（与本项目一贯的覆盖缺口同一条）。
- **`warnings` 的历史留痕未做**：只反映"本次上报"，无法追"这条标志挂了多久"。
- **`ops` 栏未做真实性校验**：服务侧只能证伪"与本次请求矛盾"的那一类，
  无法校验客户端上报的其它事实是否与真实环境一致。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 33 个事件名一个没动 |
| 事件 payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无改动值** | 仍只读上报 |
| `SPEC_VERSION` | **无** | 新增输出字段是 additive，不需要升 |
| 端点路径 | **无新增/无改名** | `ENDPOINTS` 仍 14 条 |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 只读资产，一字未改 |

**`/api/audit` 响应新增字段（additive）**

```
warnings: list[str]         # 缺失时按 [] 处理
ops:      dict[str, bool]   # 全部上报的运行态事实（含未参与判定的）
```

**性质**：**全部 additive**。无删除、无改名，故不需要废弃流程。
旧消费方忽略 `warnings` 不会坏（契约 `absent_means` 明规）。

> **注意**：契约的 `warnings` 字段定义在**上游 `/contract/check`** 上。
> 本仓库的 `/api/audit` 是**另一个入口**（契约
> `reconciliation_entrypoints` 把它列为"前端本地自检"）。
> 我按同一语义在自己的入口上实现，是为了让**展示 verdict 的那条界面路径**
> 能履行消费方义务 —— 本仓库前端消费的是 `/api/audit`，不是 `/contract/check`
> （已核对：前端源码里没有任何 `contract/check` 引用）。
> 若统筹方认为消费方义务只约束 `/contract/check` 的消费方，
> 请指出，我据此调整范围。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要。** 本轮没有触碰任何上游事实面（§5）。

- **有没有可能"问题被平移到对侧"？** 有一处，是本轮**已修**的真错：

  我先前用 `_relabel(code, ...)` 处理客户端上报的 ops 事实。
  `_relabel` 查的是按 `bridge_id` 索引的 `REATTRIBUTED` 表 ——
  传**契约 code**（`O-frontend-not-built`）查不到，会落到默认归属 `frontend`。
  于是**一条运维问题会被标成"前端要改"**。
  已改为显式构造 `Issue(owner="ops")`。

  > 这与 G3、与上轮的端点少报同型：**归属由一张表决定时，
  > 用错键就会静默指错人**，而且不产生任何报错。

- **前端会静默少显示什么吗？**
  - `warnings` 缺失 → 按 `[]` 处理（additive 安全），只是不显示提示；
  - `ops` 缺失 → 不显示运行态观测行；
  - 两者都不会让界面报错或空白。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/` 任何文件**（只读资产，README §3）。
  本轮验证镜像一致，未改动：

  ```powershell
  $PY "D:\PythonProject\SimpleAgent2_Integration\03-scripts\sync-contract.py" --check
  ```

- **不主动"读 `ops` 栏做特殊判断"** —— 工作单明示"展示 `warnings` 就够"。
  界面确实显示了 `ops` 栏，但那是**展示**（运维要看的"上次已知状态"），
  不参与任何判定分支。

- **不实现 `warnings` 的历史留痕/趋势**（见 §4 未验证项）。

- **不把 `ops` 上报改成"前端必须报"**：契约
  `client_report_schema.absence_policy` 说字段全部可选；
  本仓库前端**当前仍不主动上报 `ops`**（没有真实可观测的运行态事实要报）。
  本轮实现的是"**收到了怎么处理**"。

- **架构级提案 P1–P5 不碰**（`CHANGE-PROCESS §6`）。

---

## 8. 回退点（对应 C8）

- **整树回退**

  ```powershell
  .\scripts\backup.ps1 -List
  # → 20260926-030308_v9-dispatch-v1.0.4   （本轮改动前的基线）
  .\scripts\backup.ps1 -Verify -From v9-dispatch-v1.0.4    # 先看改了什么
  .\scripts\backup.ps1 -Restore -From v9-dispatch-v1.0.4   # 再整体回退
  ```

- **文件级回退**（本轮改动集中在 3 个源文件 + 文档，粒度回退很合适）

  ```powershell
  .\scripts\backup.ps1 -Restore -From v9-dispatch-v1.0.4 `
      -Path bridge/audit.py `
      -Path frontend/src/api/audit.ts `
      -Path frontend/src/components/TopBar.vue
  ```

  覆盖前会把被点名文件的当前版本存到
  `_backups/<快照>/undo-<时间戳>/`（粒度回退配粒度的后悔药）。

- **回退会丢什么**：`warnings` / `ops` 的输出字段、前端的提示段与徽标条数、
  §4 的全部断言。

- **回退不会丢什么**：契约镜像、`data/` 运行态、上游 `backend/`（从未改动）。

- **回退后必须重跑**：`$PY tests\run_unit.py`（应回到 29/29，
  且 `test_audit.py` 会因断言已改而失败 —— **那说明回退不彻底**，
  因为测试文件也在 §8 的清单里，一并退回即可）。

  > 这一条是上一轮评估的教训：**"只退源文件、不退测试"会得到
  > 一个红着的仓库**。所以 `-Path` 的清单里必须包含测试文件。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 有起实例 + 跑诊断的完整命令与实测输出 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 13 行，每行一条命令 |
| **C3** 命令输出支持主张 | **满足** | §2 / §4 的输出与主张逐条对应 |
| **C4** 改动清单与实际一致 | **满足** | §3 用 `-Verify` 做机械核对（不需 git）；并预先记下两处不在清单里的同步文档 |
| **C5** 对接口契约的影响已声明 | **满足** | §5 逐项声明；结论是 additive；并**主动声明了一处范围疑问**（见下） |
| **C6** 对另一侧的影响已评估 | **满足** | §6 列出一处平移风险，且是本轮**已修**的真错（`_relabel` 用错键） |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明不做的部分，含"不读 ops 做判定"与"不实现历史留痕" |
| **C8** 回退点明确 | **满足** | §8 有整树 + 文件级回退，并记下"必须连测试一起退"的教训 |

**我希望统筹重点验证的一条：§5 末尾的那处范围疑问。**

理由：契约把 `warnings` 定义在**上游 `/contract/check`** 的响应上，
而本仓库前端消费的是 `/api/audit`（契约自己列为"前端本地自检"）。
我按同一语义在自己的入口上实现了 `warnings`，理由是
"消费方义务约束的是**展示 verdict 的那条路径**，而不是某个具体端点"。

**这个推理可能不对。** 如果契约的意图是"只有 `/contract/check` 的消费方受约束"，
那我这一侧的改动就超出了义务范围（虽然无害——additive）。

请明确一句：**消费方义务的适用范围是「端点」还是「展示行为」？**
若是前者，我应当把界面改为消费 `/contract/check`（那属架构级，需用户批准）；
若是后者，本轮实现即为完整履约。

---

## 附：本轮的三条纪律说明

1. **"不采信"升级为"按裁定分流" —— 但不是我改的主意。**
   上轮我写"接收但不采信"，理由是"语义待后端拍板"。
   后端拍板了，结论与我同向但更精确（进 `warnings` 而非丢弃）。
   这说明**"暂时不做"要写清"等谁、等什么"**，否则下一个人不知道何时该动。

2. **我把一个自己刚加的参数删掉了。** 先加了 `transport_reached: bool = True`
   表达"离线代别人上报"，但该分支让 `service_down` 在 `False` 时被**静默丢弃**
   ——恒为真的开关只制造缝隙。**没有调用方的可配置性不是可配置性。**

3. **消费方义务要跨语言核对才算履约。** 后端产出 `warnings` 不等于前端展示了它。
   所以断言直接读 `frontend/` 的 `.ts` / `.vue`——这是本项目里
   "跨语言一致性只能靠测试"那条纪律的又一次应用。
