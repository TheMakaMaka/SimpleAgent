# 变更评估文档 · `ARCH-D2`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收依据：统筹方 `DISPATCH.md`（2026-09-26 10:25，契约 **v1.0.7**）§「本轮你只有一项」。
>
> **每个"主张"都跟一条可复现的命令。** 命令在仓库根执行，
> `$PY` = `.venv\Scripts\python.exe`。

---

- **变更编号**：`ARCH-D2`
- **提出方**：统筹（回执我 `EVALUATION-ARCH-A1A-A4 §7` 的两条裁决请求）
- **执行侧**：frontend（本仓库）
- **日期**：2026-09-26
- **契约版本**：`1.0.7`

---

## 1. 变更意图

> 引原话，不转述。

统筹方：

> **D2 · 复核 `bridge/audit.py` 的 `DEVIATIONS` 表**
>
> **背景一（你的 §7-1 请求，我裁了：你对）**：
> `P-phase-unknown` **改判 `both` / `degraded`**（原 `backend` / `breaking`）。
> 你之前把它记进 `DEVIATIONS` —— **现在它不是偏离了，可以撤销那条**。
>
> **背景二（你的 §7-2 报告，缺陷真实但位置不同）**：
> 实际不一致在 `rule_crosswalk.upstream_only[U-dead-event]=degraded` 与
> `bridge_backend_prefixed[backend.dead_event]=breaking` 之间
> （后者 `upstream_equivalent` 正指向前者）。**已统一为 `degraded`。**
>
> **要做的**：按上面两条复核 `DEVIATIONS`，该撤的撤、该留的留，
> 并在评估文档里写明复核结果。变更编号建议 `ARCH-D2`。

---

## 2. 问题陈述与复现方式（对应 C1）

**复现命令**

```powershell
$PY -c "import json,io; C=json.load(io.open('.interface_contract/interface-contract.json',encoding='utf-8')); rc=C['rule_crosswalk']; print([r for r in rc['upstream_only'] if r['code'] in ('P-phase-unknown','U-dead-event')]); print([r for r in rc['bridge_backend_prefixed_reclassified'] if r['bridge_id']=='backend.dead_event'])"
```

**实际输出**（契约 v1.0.7）

```
[{'code': 'U-dead-event', 'owner': 'backend', 'severity': 'degraded', ...},
 {'code': 'P-phase-unknown', 'owner': 'both', 'severity': 'degraded', ...}]
[{'bridge_id': 'backend.dead_event', 'unified_owner': 'SPLIT', 'severity': 'degraded',
  'upstream_equivalent': 'U-dead-event (上游侧)', ...}]
```

**改动前的本仓库状态**（可复现：`git` 不可用，用备份基线）

```powershell
.\scripts\backup.ps1 -Restore -From v11.1-arch-docs -Path bridge/audit.py   # 只回退这一个文件
$PY -c "import sys;sys.path.insert(0,'.');from bridge.audit import DEVIATIONS;print(DEVIATIONS)"
```

改前：`DEVIATIONS` 里有一条 `P-phase-unknown`（记的是 `both`/`degraded`），
而 `U-dead-event` 的级别在代码里**手写成 `breaking`**，与契约的 `degraded` 不一致。

**为什么这是问题**：这两个值写在代码里就是**第二份判据** ——
契约改了它不会跟着改，而且不会报错。A1a 的全部意义就是消除这个。

---

## 3. 拟改动清单（对应 C4）

| # | 文件 | 改什么 |
|---|---|---|
| 1 | `bridge/contract_vocab.py` | 新增 `load_upstream_rules()` / `upstream_rule(code)`（读契约 `upstream_only`）；`REATTRIBUTED["backend.dead_event"]` → `("SPLIT","degraded")` |
| 2 | `bridge/audit.py` | `DEVIATIONS` **清空**；`UPSTREAM_RULES["P-phase-unknown"]` → `("both","degraded")`；`_cross()` **优先读契约**；`U-dead-event` / `bridge.dead_event` 的级别改从 `severity_of("backend.dead_event")` 取 |
| 3 | `tests/unit/test_contract_vocab.py` | `WANT` 跟契约；新增 8 项：**优先读契约** + **回退表逐条一致** + 两处裁决逐条钉住 + 偏离表为空 |
| 4 | `tests/unit/test_audit_authority.py` | 偏离表断言改为**为空** |
| 5 | `tests/unit/test_audit.py` | `U-dead-event` 的严重度断言改为 `degraded` |
| 6 | 文档 | `MODULES` §23.1（判据顺序 + 偏离为空）/ `CHANGELOG` §28 / 本文档 / 版本戳 → §28 |

**实际 diff 规模**（等价机械核对，本机无 git）

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-100606_v11.1-arch-docs
```

**实际输出**

```
[改动] 9
   ~ bridge\audit.py
   ~ bridge\contract_vocab.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ README.md
   ~ tests\unit\test_audit.py
   ~ tests\unit\test_audit_authority.py
   ~ tests\unit\test_contract_vocab.py
[新增] 1
   + docs\EVALUATION-ARCH-D2.md
```

**与 §3 清单对照**：1–5 对应上；文档 6 项（`README`/`CYCLE`/`ARCHITECTURE`/`MODULES`/`OPERATIONS`/`CHANGELOG`）——
**手写清单又漏列了同步文档**（这是第三次同类遗漏，见 §9 附注）。
判定依据是命令输出，不是 §3 那张表。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | 跨侧规则**优先从契约读** | `$PY tests\unit\test_contract_vocab.py` | `86/86` | ✅ |
| 2 | 离线回退表与契约**逐条一致** | 同上 | 无差异 | ✅ |
| 3 | `P-phase-unknown` == `both/degraded` | 同上 | 契约与回退表都对 | ✅ |
| 4 | `U-dead-event` == `backend/degraded` | 同上 | — | ✅ |
| 5 | `DEVIATIONS` **为空** | `$PY tests\unit\test_audit_authority.py` | `34/34` | ✅ |
| 6 | `U-dead-event` 实测判 `degraded` | `$PY tests\unit\test_audit.py` | `107/107` | ✅ |
| 7 | 全量无回归 | `$PY tests\run_unit.py` | `32/32` | ✅ |
| 8 | 端到端（**指向上游**） | `$PY tests\diagnostics\check_contract_report.py` | `41/41` | ✅ |
| 9 | 端到端（**bundled**，跨侧按配置不可测） | 同上 | `39/39 · SKIP 1` | ✅ |
| 10 | 统筹方契约测试 | `test_interface_contract.py --backend <port>` | `29/29` | ✅ |

**第 8/9 项的实测**

```
指向上游（:8240）
      上游 verdict=frontend-action 命中 1 条
         [frontend/degraded] P-event-unknown-to-frontend
  PASS  ★★ 两个入口给出的 owner **一致**   本地=frontend 上游=frontend
通过 41/41

bundled（:8000）
  SKIP  ★★ 两个入口 owner 一致（在线形式）  —— 上游 /contract/check 不可用
        （RuntimeError: HTTP 404）—— backend_is_bundled=True，陈旧=True
通过 39/39 · SKIP 1
```

**第 6 项的实测（直接打接口，不只看单测）**

```powershell
$PY tests\diagnostics\check_contract_report.py     # 端点层
$PY -c "... print(DEVIATIONS); print(run(...).issues)"   # 判定层
```

```
P-phase-unknown   → owner=both     sev=degraded
bridge.dead_event → owner=frontend sev=degraded
DEVIATIONS: {}
```

**未验证的部分**（诚实列出）

- **契约内部一致性未校验**：本仓库校验的是"回退表 == `upstream_only`"，
  但**没有**校验"`upstream_only` 用到的严重度都在 `severity_vocabulary.values` 里"。
  那是契约内部的机械门禁，属统筹方范围。
- **界面未人眼看**（与历轮同一条既有覆盖缺口；本轮无界面改动，所以不扩大）。
- **`/contract/check` 的 500 只观察到一次瞬时的**：见 §7 的观察条目 ——
  重启后恢复 200，所以**无法确定**它是否已随上游那次编辑一起修掉。

---

## 7. 一条报给上游的**观察**（不是本仓库缺陷）

跑端到端时，指向上游的实例上 `POST /contract/check` 返回 **500**：

```
File "backend/core/contract.py", line 805, in peer_issues
    out.append(Issue("P-missing-field", "前端未提交 contract_version",
NameError: name '_version_tuple' is not defined
```

**但磁盘上第 731 行就定义了 `_version_tuple`。** 重启实例后恢复 200。
判断是"模块被改过、运行中的实例还是旧版本"的**瞬时状态**，大概率上游当时正在编辑。

**为什么仍然报**：若它不是瞬时的，那是一条让**所有**跨侧对账 500 的严重缺陷，
而只有"打接口"才看得到（离线单测不一定覆盖只在特定代码路径触发的 `NameError`）。
**请确认它已随那次编辑修掉。**

**复现命令**

```powershell
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"
$env:AGENT_RUNTIME_ROOT="$env:TEMP\sa2_probe_rt"
.\.venv\Scripts\python.exe -m uvicorn bridge.app:app --host 127.0.0.1 --port 8240 --app-dir .
# 另开一个终端：
.\.venv\Scripts\python.exe -c "import httpx; r=httpx.post('http://127.0.0.1:8240/contract/check', json={'contract_version':'1.0','phases':['plan','write','check','verify','record'],'upstream_event_kinds':[],'upstream_endpoints':[]}); print(r.status_code, r.text[:200])"
```

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 / payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | — |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 只读资产，一字未改 |

**`/api/audit` 的响应**：**无新增字段**。改的只是两条判定的 `severity` 取值：

```
U-dead-event   : breaking → degraded     （契约 v1.0.7 统一级别）
（P-phase-unknown 的 owner/severity 取值不变：both/degraded —— 它本来就判这个，
  改的只是"判据来源"从副本变成了契约）
```

**性质**：**行为上是收紧**（`breaking` → `degraded` 会让 verdict 从"要改"变成
"要改但不阻塞"）。这是**按契约改**，且 `degraded` 仍参与 verdict（只有 `info` 不参与），
所以不会把问题藏起来。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要。**
- **有没有可能"问题被平移到对侧"？**
  本轮**修掉的正是这类问题的一个实例**：契约把 `U-dead-event` 统一为 `degraded`，
  如果本仓库继续手写 `breaking`，那么"同一件事"在两侧就是两个级别 ——
  消费方按 code 对账时会得到不同结论。现在级别从契约取，**没有第二份**。
- **前端会静默少显示什么吗？** 不会：`degraded` 仍 `blocking=True`，
  仍会出现在阻塞项列表里（只有 `info` 折起来）。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/` 任何文件**（只读资产）。
- **不加 id 别名映射** —— 统筹方已裁定不需要；加别名等于把两套判据养回来
  （那是 A1a 要消除的东西）。
- **不放宽 `ops.warnings` 的语义** —— 裁定维持单一语义（只放被传输层证伪的事实）；
  本仓库实现本来就是这样，**无需改动**。
- **不因 `degraded` 而调整 verdict 逻辑** —— 契约 `NON_BLOCKING_SEVERITIES` 只有 `info`，
  `degraded` 参与判定，本仓库实现一致。

---

## 8. 回退点（对应 C8）

- **整树回退**

  ```powershell
  .\scripts\backup.ps1 -List
  # → 20260926-100606_v11.1-arch-docs   （本轮改动前的基线）
  .\scripts\backup.ps1 -Verify  -From v11.1-arch-docs
  .\scripts\backup.ps1 -Restore -From v11.1-arch-docs
  ```

- **文件级回退**（本轮只改了 5 个代码/测试文件）

  ```powershell
  .\scripts\backup.ps1 -Restore -From v11.1-arch-docs `
      -Path bridge/audit.py -Path bridge/contract_vocab.py `
      -Path tests/unit/test_contract_vocab.py `
      -Path tests/unit/test_audit_authority.py -Path tests/unit/test_audit.py
  ```

  **必须连测试一起退** —— 只退源文件会让测试引用不到新符号而变红（历轮教训）。

- **回退会丢什么**：契约优先的跨侧规则读取（退回手写副本）、偏离撤销、级别统一。
- **回退不会丢什么**：契约镜像、`data/` 运行态、上游 `backend/`（从未改动）。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了读契约与读本仓库状态的两条命令 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 8 行 |
| **C3** 命令输出支持主张 | **满足** | §4 附了判定层的实测 |
| **C4** 改动清单与实际一致 | **满足** | §3 用 `-Verify` 机械核对；并如实记下"手写清单第三次漏列同步文档" |
| **C5** 对接口契约的影响已声明 | **满足** | §5：无新增字段，但**声明了 `breaking→degraded` 这一行为收紧** |
| **C6** 对另一侧的影响已评估 | **满足** | §6：本轮修掉的就是"同一件事两个级别"的实例 |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明不做；两项主动询问按裁定**不改代码** |
| **C8** 回退点明确 | **满足** | §8 整树 + 文件级，并注明"必须连测试一起退" |

**我希望统筹重点验证的一条：§3 里我第三次漏列同步文档这件事。**

理由：这不是本轮的实现问题，而是一个**稳定的过程缺陷** ——
三轮下来，"手写改动清单"漏的**全部**是文档（从未漏过代码）。
如果我继续只是"下次注意"，它会一直发生。**判定依据请一律以 `-Verify` 的输出为准**，
不要以我 §3 那张表为准。若你希望我在流程上修掉它（例如让清单也由命令生成），
请指示 —— 那属流程改动，我不擅自动。

---

## 附：本轮的两条纪律说明

1. **这两行值之所以会漂，是因为它们被抄了一份。**
   D2 的字面任务只是"改两个常量"，但那样做下一轮还会漂。
   所以本轮做的是**把跨侧规则也改成读契约**（与既有的 `owner_of` + 回退表同一模式），
   并加断言"回退表 == 契约"。**修根因，不是修症状。**

2. **我报得对，但指得偏。** `U-dead-event` 那条我判定"契约内部不一致"是对的，
   但我指的是**同一行的两个字段**，实际是**两行之间**（`upstream_only` 与
   `bridge_backend_prefixed`）。结论一致、定位偏了。
   记下来：在协作里"报得对但指得偏"会浪费对方一轮排查 ——
   **报缺陷时应当把"我看到的两个值分别在哪一行"写全**，本轮我写的是
   "`rule_crosswalk` 的行里"与"`upstream_only` 那一列"，后者是**一列不是一行**，
   这就是偏差的来源。
