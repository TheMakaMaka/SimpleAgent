# 上游 → 前端：兼容接口契约

> **谁该看这份文档**：改**上游**（本仓库）代码的人。前端那份 `SPEC.md` 讲的是
> "前端怎么照单渲染"，这份讲的是"**上游必须保证什么，前端才不用改**"。
>
> 一句话：**前端不写死后端事实，所以后端一改就等于在改契约 ——
> 只是前端不会报错，它会静默少显示东西。** 这份文档就是补上那个"没人报错"的缺口。

机器可读入口：

```bash
curl http://127.0.0.1:8000/profile | python -m json.tool   # 看 contract 段
```

```python
from core.contract import describe, audit, capabilities, EVENTS
describe()   # 契约概览（事实源、事件词表、冻结面、能力）
audit()      # 声明 vs 实际扫描，任何不一致都点名
```

---

## 1. 前端扫上游的四处（**这四个名字不能改**）

| 事实 | 上游来源 | 改它会怎样 |
|---|---|---|
| 阶段清单 | `core.cycle.PHASE_ORDER` | 改名/删除 → 流水线节点对不上 |
| 事件词表 | `core/coding_cycle.py` 里 `_emit("<字面量>", ...)` 的调用点（AST 扫） | 改名 → 前端按自动生成的名字显示；删除 → `dead_calibrations` |
| 工具清单 | `tools.registry.TOOLS_MAP`（读 `description` / `profiles`） | 改名 → 工具面板显示原名 |
| 运行报告 | `core.cycle.CycleReport.to_dict()` | 删字段 → 对应那一栏空掉 |

第五处（端点清单）属于 **bridge 自己**，不在本契约范围内。

**两条硬约束**（`test_frontend_contract.py` 守着）：

1. **事件只能从 `CodingCycle._emit` 发出**（`EMIT_SOURCES = ("core/coding_cycle.py",)`）。
   在别处 `append_event` 等于发了个**前端看不见的事件**——它不在扫描范围里。
2. **kind 必须是字面量**。`_emit(kind_var, ...)` 前端 AST 扫不到，
   `audit()["nonliteral_kinds"]` 会把它列出来。

---

## 2. 只增不减（additive-only）

前端对上新增是自动跟上的，对删除/改名只能降级显示。所以：

| 改动 | 安全性 | 要做什么 |
|---|---|---|
| 加一个阶段 | ✅ 安全 | 无（前端自动多一个节点） |
| 加一个事件 | ✅ 安全 | **补 `contract.EVENTS` 声明**（否则测试失败） |
| 加一个 payload 键 | ✅ 安全 | **补进该事件的 `payload` 声明** |
| 加一个工具 | ✅ 安全 | 无（没标定就显示原名） |
| 加一个 `CycleReport` 字段 | ✅ 安全 | 无（可顺手补进 `FROZEN_REPORT_KEYS` 方便后人） |
| 改事件的 payload 键名 | ❌ 破坏 | 见 §3 |
| 删/改事件 kind、阶段名、工具名 | ❌ 破坏 | 见 §3 |
| 删 `CycleReport` / `Snapshot` 字段 | ❌ 破坏 | 见 §3 |
| 改端点路径 | ⚠️ 视情况 | 端点是 bridge 的；改了要通知前端调 `ENDPOINTS` |
| 改 `TOOLS_MAP` 条目的**结构** | ❌ 破坏 | 前端读 `description` / `profiles` |

**"安全"的含义**：前端不需要改一行代码，最差也是显示一个自动生成的名字。

---

## 3. 破坏性改动怎么做（不许悄悄做）

1. **先标废弃，不要直接删**：把事件标成
   ```python
   "old_event": EventSpec("old_event", (...), status="deprecated", note="改用 xxx"),
   ```
   保留**至少一个版本**。这样前端的 `diagnostics.dead_calibrations`
   会提示"标了但后端不发"，人能看见，而不是事后猜。
2. **升 `CONTRACT_VERSION`**（`core/contract.py`）。
   只增不减的改动**不必**升版本；破坏性改动必须升。
3. **记进 `docs/CHANGELOG.md`**，写明：删了什么、替代是什么、前端要做什么。

> `audit()["deprecated_still_emitted"]` 会拦住"标了废弃却还在发"——
> 那种状态最坑：前端同时看到新旧两套。

### 3.1 已发生的一次 payload 改名：`decision_opened.kind` → `decision_kind`

**时间**：2026-09-26（变更记录见 `docs/CHANGELOG.md` §29）。

**为什么改**：`kind` 与 `CodingCycle._emit` 的**参数名**同名，调用点在参数绑定阶段
就抛 `TypeError: _emit() got multiple values for argument 'kind'` ——
**整条人工决策路径 100% 不可用**，且前端装了 bridge 钩子后会把整轮 run 变成
`status=error`。这不是"想改名"，是**必须去掉这个键名**。

**前端影响评估**：
- 前端**没有显式读**这个 payload 键：`agent_api.py` 的 `ev.get("kind")` 读的是**事件记录**的
  `kind` 字段；`d.kind` 读的是 `/decisions` 里的决策记录；
- 按既有纪律，未知 payload 键只会让它"自动挑一个可读字段"，最差是降级显示；
- 若确实读过 `payload.kind`，请改读 `decision_kind`。

> ⚠️ **但"没有显式读"不等于"没有消费方"** —— 这就是 §3.2 要说的那件事：
> 我原先正是拿"显式读取"当结论，**判错了**。

**流程上的一处诚实说明**：按本节第 1 条本应先标废弃保留一版，
但**废弃别名（同时发 `kind`）会立刻重新触发那个 TypeError** ——
所以这次是"先修断链、再登记"，并把原因写进 `EVENTS["decision_opened"].note`。

### 3.2 ★ 这次为什么算**破坏性**（我原先漏判，统筹方纠正）

我原来的结论是"已核实前端未读该键 → 非破坏性"。**这个核实不完整**：
我只查了**显式读取**，漏了**扁平化覆盖**。

| 层 | 事实 |
|---|---|
| `bridge/runner.py` | `record = {seq, ts, kind, run_id, goal, attempt, **payload}` —— **payload 在后展开** |
| 改名**前** | payload 的 `kind` **覆盖**记录的 `kind` → `ev.kind` = **决策种类** |
| 改名**后** | 不再覆盖 → `ev.kind` = **`'decision_opened'`**（事件类型） |
| 前端 `run.ts` | `kind: String(ev.kind \|\| '')` → **决策种类显示成事件名** |

**所以确实有消费方要跟着改**（前端已立 **D8**）。

**因此：`CONTRACT_VERSION` 升 `1.1`**（统筹方裁决，本侧执行）。

**接受这条裁决的理由**（它比我的判断更硬）：契约的价值在于
"**破坏性改动 = 版本一定变了**"这条**无条件**成立；
一旦开始按"影响大不大"逐次判断，这条信号就没人敢依赖了。
我那时的推理恰好是"影响不大 → 不用升"，属于**在削弱信号本身**。

**同时补一条门禁**（统筹方 D10）：payload 键不仅能撞 `_emit` 的参数名（会抛 TypeError），
还能**覆盖前端扁平化后的记录字段**（不报错、静默改语义 —— 本次就是这一类的真实事故）。
`core/contract.py` 现声明 `RECORD_FIELDS`（`seq`/`ts`/`kind`/`run_id`/`goal`/`attempt`）
与 `PAYLOAD_SHARED_KEYS`（故意共用、必须写明理由的 `goal` / `attempt`），
由 `test_frontend_contract.py` 逐条扫。

### 3.3 ⚠️ 钩子包装器改透传 ≠「旧上游也能跑」（统筹方 R5 实测结论）

我此前建议前端把 `bridge/hooks.py` 的包装器改成透传（`*args/**kwargs`）。
**那条建议是对的，但别把它读成"改了之后连旧上游也安全"** —— 统筹方实测：

| 被包装的 `_emit` 签名 | 透传包装器（内部 `sig.bind(self, *args, **kwargs)`）遇到 `kind=` 调用 |
|---|---|
| 旧上游 `(self, kind, …)` | **TypeError: multiple values for argument 'kind'** |
| 新上游 `(self, event_kind, …)` | OK |

**原因**：`sig.bind` **忠实复现被包装函数的签名** —— 透传只能保证"包装器自身不引入参数名"，
而**旧签名的冲突仍在**。所以：

- 透传的价值是「**上游以后再改也不怕**」；
- 它**不是**「旧上游也能跑」—— 那种情况只能在**调用点/上游侧**修（就是本节做的那件事）。

**写在这里是为了避免下次把"包装器已透传"误当成"陈旧副本无害"。**

### 3.4 `cycle_start` 新增两个键（additive，用于回答"跑的是哪一份"）

| 键 | 含义 |
|---|---|
| `code_dir` | 这份上游代码是从哪个目录 import 的 |
| `code_fingerprint` | **上游代码内容的 8 位指纹**（`core`/`tools`/`storage`/`web` + `main.py`） |

**动机**（实测事故 `docs/CHANGELOG.md` §31）：用户反复失败而修复没生效 ——
前端加载的是它自带的陈旧副本，而当时的运行记录里**没有任何字段**能回答这个问题。
现在每次运行的第一个事件就自报代码身份；`GET /profile` 的 `code` 段同样暴露它。

> ⚠️ `cycle_start` 里原有的 `backend` 是**检查点后端**（git/snapshot），
> **不是**代码来源 —— 两者别混。

---

## 4. 改上游时的检查表

改完跑这一条就够（它是门禁）：

```bash
python tests/unit/test_frontend_contract.py
```

它会告诉你四件事：

| 检查 | 抓什么 |
|---|---|
| 事件词表 声明 == 实际 | 改了词表没说 / 声明了没发（死声明） |
| `_emit` 字面量 + 单一来源 | 发了个前端扫不到的隐身事件 |
| payload 键只增不减 | 键被删/改名（前端"自动挑可读字段"就挑不到了） |
| 冻结面只增不减 | 阶段 / 报告字段 / 快照字段 / 事件字段 / 工具条目结构被删 |

再看一眼这两个数字是否合理：

```bash
curl -s http://127.0.0.1:8000/profile | python -c "import json,sys; a=json.load(sys.stdin)['contract']['audit']; print(a['ok'], a['event_count'], a['undeclared_events'], a['dead_events'])"
```

上游目前是 **13 种事件 / 18 个工具**（前端 `diagnostics.event_count: 33` 里
其余的是 bridge 自己发的，属前端侧）。

---

## 5. 能力声明（`capabilities()`）—— 前端据此隐藏面板

| 能力 | 当前 | 说明 |
|---|---|---|
| `vision` | **否** | `VISION_*` 未配置 → 角色未启用。**推导**自 `role_available("vision")`，不手写 |
| `structured_snapshot` | 是 | 带 `schema_version`，可直接展示 |
| `decisions` | 是 | 机制可用；**通道是否真的通**另看 `/profile` 的 `decision_channel` |
| `skills` / `candidate_packages` / `reflection` | 是 | 对应 `/skills`、`/candidates`、`/reflect` |
| `database_storage` | 否 | 只留 `Storage` Protocol（`describe()` 里写了 why） |
| `parallel_tasks` | 否 | 子任务串行执行 |

纪律：**能推导的一律推导**（如 `vision`），只有"尚未实现"的才显式写 `False`。
前端那份 `DEFAULT_SPEC` 的教训就是这个——手写的兜底值会漂，且没有类型系统帮忙。

---

## 6. 责任划分：对不上时**谁去改**

这份文档前面的内容回答"什么算对不上"，这一节回答**谁来改**。

### 6.1 一条判定原则（其余规则都是它的展开）

> **事实源在哪一侧，责任就在哪一侧。**

| 归属 | 含义 |
|---|---|
| `ops` | 环境/运行态（服务没起、前端没构建、配置坏）—— 与双方契约无关。**判定顺序优先** |
| `backend` | 上游发出/声明的东西与**上游自己的代码**不符 |
| `frontend` | 上游已声明并正常发出，**前端不认识**；或上游删/改了前端在用的东西却没标废弃 |
| `both` | 上游**单方面判不出来**，需人工协商（通常要定契约版本） |

归属词表经**统筹契约（当前 v1.0.19）**统一为这 **4 个值**（本仓库原有 3 个、缺 `ops`）。

> **边界按仓库划**：`frontend` = `SimpleAgent2_Cycle_VueWeb` 仓库里的一切，
> **`bridge/` 与 `frontend/` 同等对待** —— `bridge/spec.py` 里的声明类问题算 frontend。
> 这一条是实测出来的：两侧对"backend"一词的所指不同，
> 是"谁去改"这类协作里最贵的错误。

**为什么把规则声明成表**：前端也在做归因。两边各写一套必然分歧。
规则表在 `core/contract.py` 的 `ISSUE_RULES`，并通过
`GET /profile` 的 `contract.responsibility` 暴露 —— 前端直接用，别自己发明。

### 6.2 怎么调用（前端运维机制）

```bash
# ① 只查后端自己（前端不必提交任何东西）
curl http://127.0.0.1:8000/contract/check

# ② 完整对账：把前端自述一起比，拿到责任划分
curl -X POST http://127.0.0.1:8000/contract/check \
  -H "Content-Type: application/json" \
  -d '{
    "contract_version": "1.0",
    "schema_version": "1.0",
    "upstream_event_kinds": ["cycle_start","plan","task_result","manifest",
                             "syntax","lint","verify","cycle_end",
                             "rollback_denied","decision_opened",
                             "decision_notified","decision_action"],
    "phases": ["plan","write","check","verify","record"],
    "report_keys": ["cycle_id","goal","phase","manifest","verify","commit"],
    "upstream_endpoints": ["/run","/encode","/profile","/contract/check"],
    "frontend_event_kinds": ["bridge_health","bridge_run_started"],
    "frontend_endpoints": ["/api/spec"]
  }'
```

响应（节选）：

```json
{
  "verdict": "multi-action",
  "next": "**两边都有事**：各自看自己那一栏。",
  "counts": { "ops": 0, "backend": 1, "frontend": 2, "both": 1 },
  "ops":      [],
  "backend":  [ { "code": "P-endpoint-missing", "severity": "breaking",
                  "detail": "前端要代理 `/api/spec`，上游没有这个路由",
                  "why": "…", "action": "后端补路由，或确认端点是否在 bridge 自己名下" } ],
  "frontend": [ { "code": "P-version-behind", "severity": "degraded", "…": "…" } ],
  "both":     [ { "code": "P-event-gone-upstream", "…": "…" } ]
}
```

**运行态（ops）怎么报**：`ops` 是**运行态观测**（不是"我按什么写死的"声明），
但在同一个上报体里，所以它**与那 8 项声明并列** —— `PEER_FIELDS` 现共 **10 项**
（8 项声明 + `bridge_gate_steps` + `ops`），
也是契约 `client_report_schema.canonical_fields` 的一项（从 v1.0.2 起）：

```jsonc
{ "…": "…上面 8 项声明…",
  "ops": { "service_down": true, "frontend_not_built": false } }
```

上游在"服务活着"时无法观测"服务不可达"（自己的不可达不可自证），
所以这类事实只能由看得见环境的一侧上报；**code 与归属仍由上游规则表定义**。
未知的事实名会被忽略（additive 安全）。

> **勘误**：本文件早先写"`ops` 不在 `PEER_FIELDS` 的 8 项里"，那是**错的** ——
> 契约早已收它，导致我这边的 `describe().peer_report_fields` 与契约对不上。
> 由 `tests/unit/test_contract_conformance.py` 第一次运行抓出，已改为 9 项。

#### ⚠️ `service_down` 的语义：**上次已知状态**，不是"此刻"

这条通道有一个由**传输层**决定的事实：**`POST /contract/check` 能成功送达，
就已经证明上游可达。** 所以随请求一起报上来的 `service_down=true`
不可能是此刻的状态。

因此上游这样处理它（契约  `ops_report_constraint`，由本侧确认，
过程见 `docs/EVALUATION-OPS-1.md`）：

| 行为 | 说明 |
|---|---|
| **照常出现在 `ops` 栏** | 信息不丢；`evidence` 带 `semantics: "last_known_state"`、`current: false`、`contradicted_by: "request_succeeded"` |
| **不驱动 `verdict`** | `ops` 优先的前提是"服务不可达时后面一切不成立"，而请求成功把这个前提**证伪**了 —— 此时后面那些结论**是成立的** |
| **写进 `warnings`** | 报告新增顶层 `warnings: []`（additive），明说"该标志与本请求可达性矛盾" |

> **为什么排除它不会漏掉真实故障**：真·服务不可达时，前端**根本发不出这个请求** ——
> 那种情况由 bridge 自己的本地自检（`ops.service_down`）负责，不依赖这条通道。
>
> **`frontend_not_built` 不受影响**：它与"请求可达"不矛盾（服务活着但前端没构建
> 完全可能），所以它**照旧驱动 `ops-action`**。

响应里的 `warnings` 示例：

```json
{ "verdict": "frontend-action",
  "counts": { "ops": 1, "backend": 0, "frontend": 2, "both": 0 },
  "warnings": ["`O-service-down` 报了 true，但**本请求已成功送达** —— 该标志只能是「上次已知状态」，不是此刻状态。已按契约语义保留在 ops 栏，**未参与结论判定**…"],
  "next": "**前端**改：见 frontend 列表（上游已声明，前端落后）。（注意：ops 栏有一条**上次已知状态**的标志未参与判定，见 warnings）" }
```

其他调用方式：

| 方式 | 用途 |
|---|---|
| `GET /contract/check` | 后端自检（前端不需要参与） |
| `POST /contract/check` | 完整对账（**前端运维机制用这个**） |
| `python -m core.contract` | 服务没起来时也能查（读 `--peer peer.json`） |
| `GET /profile` → `contract.responsibility` | 前端想**离线**自己归因时用这张规则表 |

`verdict` 取值（**6 个**，取自统筹契约 `verdict_vocabulary`）：
`ok` / `ops-action` / `backend-action` / `frontend-action` /
`need-negotiation` / `multi-action`。

**判定顺序：先判 `ops`** —— 服务不可达 / 前端没构建时，后面一切结论都不成立。

### 6.3 严重程度（severity）—— 决定要不要拦

| 级别 | 含义 | 前端该怎么办 |
|---|---|---|
| `breaking` | 前端会**真的看不到 / 画错** | 必须有人改；建议界面显式提示 |
| `degraded` | 前端有兜底（降级显示），但应当修 | 记进运维日志，不阻断 |
| `info` | 只是提醒（多为 additive 新增） | 可以不处理 |

**`info` 不参与 `verdict`** —— 上游新增端点这类 additive 变更不该被当成"有事要改",
否则"低定制"就又退化成"每次加东西都要两边同步改"。

### 6.4 前端提交什么（`PEER_FIELDS`）

字段全部可选；**少给只会降低归因精度，不会报错**（会降级成 `P-missing-field` 的 info）。

| 字段 | 说明 | 少了会怎样 |
|---|---|---|
| `contract_version` | 前端支持的契约版本 | 无法判定谁落后 |
| `schema_version` | 前端能解析的快照版本 | 无法判定快照兼容性 |
| `upstream_event_kinds` | 前端认得的**上游**事件（**不含** bridge 自己发的） | 无法判定前端是否漏了事件 |
| `phases` | 前端画的阶段 | 无法判定阶段是否对上 |
| `report_keys` | 前端会读的 `CycleReport` 字段 | 少一项检查 |
| `upstream_endpoints` | 前端要代理的**上游**端点 | 无法判定端点是否对上 |
| `frontend_event_kinds` | （仅信息）前端自己发的事件 | 无 |
| `frontend_endpoints` | （仅信息）前端自己的端点 | 无 |
| `ops` | （**观测**，非声明）运行态事实：`service_down` / `frontend_not_built` | 无法判定 ops 类问题 |
| `bridge_gate_steps` | （可选，**建议提供**）bridge 自补的门禁节点，如 `["manifest"]` | 未知阶段的 `action` 只能写"先确认方向"（判不出方向） |

> **`ops` 与上面 8 项的类别不同**，但同属这套上报字段（契约 `canonical_fields`）。
> 未知的运行态事实名会被忽略（additive 安全）。
> `bridge_gate_steps` 属**声明**类；缺省不影响判定，**只降低精度** —— 与其它字段同纪律。

> **`upstream_event_kinds` 只写上游的**：前端自己的 21 个事件（bridge 发的）
> 写进 `frontend_event_kinds`。混在一起会让 `P-event-gone-upstream` 产生误报 ——
> 上游不认识 bridge 自己的事件，那是正常的。
> **实测代价**：33 个混着报，会回**恰好 21 条** `P-event-gone-upstream`，
> 结论从 `ok` 掉到 `need-negotiation`，全是噪声。
>
> **`phases` 只写上游的 5 个流水线阶段**（`plan` `write` `check` `verify` `record`）。
> bridge 自补的门禁节点（如 `manifest`）**不要混进来** ——
> 混进来会命中 `P-phase-unknown`，**结果是 `need-negotiation`**（`both` / degraded）。
>
> **把自补节点报到 `bridge_gate_steps` 里**（第 9 个上报字段）：
> 这样上游就能**机械判定方向**并把 `action` 直接指名前端，而不是让人去猜。
> 判定树见下方 §6.5.1。
>
> **注意这条的历史**（变更 `ARCH-D1`，契约 v1.0.7）：它原本判 `backend` / breaking，
> 即"推定上游删了阶段"—— 而实测里那个 `manifest` 是 bridge 自补的节点，
> **后端并没有删过任何阶段**。现在改成"**方向判不出来，需协商**"，
> 因为「前端自造节点」与「上游删阶段」现象完全相同。

### 6.5 规则表全表（共 23 条）

上游侧（`U-` 前缀，上游自查就能发现，**全部归后端**）：

| code | 级别 | 触发 |
|---|---|---|
| `U-emit-nonliteral` | breaking | `_emit(<非字面量>)` → 前端 AST 扫不到 |
| `U-emit-source` | breaking | 在 `EMIT_SOURCES` 之外发事件 |
| `U-undeclared-event` | degraded | 发了但没写进 `EVENTS` 声明 |
| `U-dead-event` | degraded | 声明 active 但已不再发 |
| `U-deprecated-emitted` | breaking | 标了废弃却还在发 |
| `U-payload-drift` | breaking | 声明过的 payload 键被删/改名 |
| `U-removed-surface` | breaking | 冻结面里的阶段/字段消失 |

对账侧（`P-` 前缀，需要前端自述）：

| code | 归谁 | 级别 | 触发 |
|---|---|---|---|
| `P-version-behind` | 前端 | degraded | 前端契约版本落后 |
| `P-version-ahead` | 后端 | breaking | 前端版本领先（后端没跟上） |
| `P-version-unparsable` | 协商 | degraded | 版本号无法比较 |
| `P-schema-behind` | 前端 | degraded | 快照版本落后 |
| `P-schema-ahead` | 后端 | breaking | 快照版本领先 |
| `P-schema-mismatch` | 协商 | degraded | 快照版本无法比较 |
| `P-event-unknown-to-frontend` | 前端 | degraded | 上游已声明并会发，前端不认识 |
| `P-event-gone-upstream` | 协商 | degraded | 前端把它当上游事件，上游没这声明 |
| `P-phase-missing` | 前端 | degraded | 上游流水线有该阶段，前端没画 |
| `P-phase-unknown` | **协商** | **degraded** | 前端在画一个上游没有的阶段 —— **方向判不出来**（前端自造 / 上游删改） |
| `P-report-key-missing` | 前端 | degraded | 前端读一个上游从未承诺的报告字段 |
| `P-endpoint-missing` | 后端 | breaking | 前端要代理的上游端点不存在 |
| `P-endpoint-added` | 前端 | info | 上游新增端点（additive，可忽略） |
| `P-missing-field` | 前端 | info | 前端少提交了某字段 |

运行态侧（`O-` 前缀，**两侧原先都没有**，来源 bridge 的 `ops.*`）：

| code | 归谁 | 级别 | 触发 | action |
|---|---|---|---|---|
| `O-service-down` | `ops` | breaking | 服务不可达 | 先把服务起起来；这一条修好之前后面都不成立 |
| `O-frontend-not-built` | `ops` | breaking | 无前端构建产物（`/app` 不注册） | `npm run build` |

> **`O-service-down` 在同步通道上不驱动结论**（它只能是"上次已知状态"，
> 见上面 §6.2 的小节）。规则本身的 code / 归属 / 级别都没变 ——
> 变的只是"什么条件下算当前值"。它在 `ops` 栏照常出现。
>
> **`O-` 两条为什么必须有**：没有 `ops` 这一栏时，"服务没起来"只能被塞进
> backend 或 frontend —— **归错人**。它跟双方契约都无关。

> **三条"协商"项是刻意的**：`P-event-gone-upstream`、`P-version-unparsable`、
> `P-schema-mismatch` 上游**单方面判不出来**（第一项不知道那事件历史上属不属于自己，
> 后两项本来就无法比较），硬归给某一侧会把人带偏，所以标成"需协商"。

> 本表共 **23 条**（`U-` 7 + `P-` 14 + `O-` 2）。
> 21 条既有规则的归属与级别经统筹契约**原样采纳，零改判**
> （例外：`P-phase-unknown` 于 v1.0.7 改判，见 §6.5.1）。

#### 6.5.1 `P-phase-unknown` 的方向判定树（契约 v1.0.7）

`P-phase-unknown` 判 `both` / `degraded` 是**默认**。但当对端提供了
`bridge_gate_steps` 时，第一种情形其实是**可机械判定**的 —— 于是契约定义了一棵树，
**只用来锐化 `action` 文案，不改 owner**（`effect_on_owner`：避免来回改判）：

| 情形 | 方向 | `action` 指向 |
|---|---|---|
| 未知阶段 ∈ `peer.bridge_gate_steps` | **frontend** | 上报 `phases` 时过滤掉，自补节点只在 `bridge_gate_steps` 里报 |
| 未知阶段 ∈ 上游 `FROZEN_PHASES` 且 ∉ `PHASE_ORDER` | **backend** | 恢复该阶段（同时会被 `U-removed-surface` 抓到） |
| 其余 | **both** | 保持"先确认方向"的人工表述 —— **不伪造方向** |

**实现细节（本侧）**：方向体现在 `evidence.direction`
（`bridge_gate_step` / `upstream_removed_frozen_phase` / `undetermined`）
与逐条锐化的 `action` 上；**owner / severity 永远来自规则表，不可逐条覆盖**
（`Issue.action_override` 只能改文案）。

> **`failed` 的边界（我核过）**：它在 `FROZEN_PHASES` 里但不在 `PHASE_ORDER`，
> 看似会命中情形 2。实际上**不会** —— 本规则的触发条件是"对端报的阶段 ∉ 全部
> `CyclePhase` 值"，而 `failed` 是 `CyclePhase` 成员，所以它根本不触发本条。
> 情形 2 只有在上游**真把某阶段从 `CyclePhase` 删掉**时才可达。

### 6.6 本入口的**权威范围**（A1b）—— 两侧按职责切分

架构清单 **A1**（用户已批准）的决定是：**按职责切分两个对账入口，而不是合并**。
于是两侧都必须**自述权威范围**，否则切分只把"一个模糊的答案"变成"两个模糊的答案"。

`/contract/check` 与 `/profile` 的 `contract.authority` 都带这份自述：

| 字段 | 内容 |
|---|---|
| `id` / `role` | `cross-side` / `authoritative-for-cross-side-attribution` |
| `covers` | **本入口权威**：归属（owner）、严重度、结论（verdict）、`both` 协商项、运行态 ops 事实的 code 与归属 |
| `not_covers` | **不管**：本地环境细节（前端是否构建、钩子是否装上、bridge 自身声明是否自洽）—— 那是 `/api/audit` 的权威范围 |
| `rule_source` | 规则表在哪：`/profile` → `contract.responsibility`（23 条） |
| `counterpart` | 对应入口 `/api/audit`（`local-self-check`），且**跨侧归属以本入口为准** |
| `policy` | 同一件跨侧不一致只有一个判据；两个入口给出同一 owner |

**为什么切分比合并正确**：`/api/audit` 看得见本入口**看不见**的东西
（前端是否构建、钩子是否装上）—— 那些事实本来就无法由上游观测
（后端在 `docs/EVALUATION-OPS-1.md` 论证过，已被契约采纳）。
硬合并会丢掉这些观测能力。

**规则表的完整性与稳定性凭据**（前端要引用本入口的 code，就需要能判断"表变了没有"）：

| 字段 | 含义 |
|---|---|
| `contract.responsibility_count` | 规则表条数（当前 **23**） |
| `contract.responsibility_fingerprint` | 内容指纹（当前 **`af6bfe2a`**），只覆盖 `code`/`owner`/`severity` |

指纹的语义：**改 `why`/`action` 文案不变；增删规则或改归属/级别一定变**。
指纹变化 = 契约变化，应同步升 `CONTRACT_VERSION`（实测见
`docs/EVALUATION-ARCH-A1B.md` §4）。

**两侧一致性怎么保证**：`tests/unit/test_contract_conformance.py` 第 [10] 组拿契约
`rule_crosswalk`（两侧商定的统一映射）当锚点，逐行断言本侧 owner == `unified_owner`。
实测：17 行中 8 行无上游等价（属 bridge 本地自检）、8 行完整比对、2 行部分等价、
1 行 `SPLIT`，**owner / severity 零不一致**。

---

## 7. 版本号

| 版本号 | 位置 | 含义 |
|---|---|---|
| `CONTRACT_VERSION` | `core/contract.py` | 上游对前端的**接口兼容性**版本。破坏性改动才升 |
| `SCHEMA_VERSION` | `core/compress.py` | 压缩快照结构版本。前端据此判"能不能解析" |
| `SPEC_VERSION` | bridge `bridge/spec.py` | **前端自己的修订号**，与接口兼容性无关（别与本契约版本相减） |
| `同步至 CHANGELOG §N` | 各上游文档 | 文档与代码的同步戳（与本契约无关，但同样靠检查器守） |

> **三条版本轴不许合并、不许相减**（统筹契约 §3）。现在两侧都报 `1.0`
> **纯属巧合**，不是同一个刻度。

---

## 8. 尚未做 / 待前端确认

| 项 | 状态 |
|---|---|
| **前端也带 `CONTRACT_VERSION`** | 带上才能判定"谁落后"。**需要前端确认**（带上即可，不需要额外维护逻辑） |
| **payload 键的类型未冻结** | 现在只冻结"键名存在"。类型变了前端可能渲染异常（如 `violations` 从数组变字符串）。**这是目前最大的未覆盖面** |
| **事件时序未冻结** | 前端不假设顺序（按 `seq` 排）。所以上游调整发出顺序是安全的，也意味着**顺序语义不在契约内** |
| **多模态事实未接入快照** | `vision` 接口就绪但未启用；将来接上后要给快照加新 fact 类型（属新增，安全） |
| **字段级废弃标记** | 事件有 `status="deprecated"`，payload 键没有。要废弃单个键目前只能靠 CHANGELOG 说明 |
| **`/contract/check` 是新端点** | 属 additive 新增。前端的端点检查可能会报 `P-endpoint-added`（info，不阻断）——**前端可选**：登记它并按提示改进，或忽略 |
| **`ops` 字段的类别** | 它是**观测**而非声明，但**已进契约的 `canonical_fields`**（9 项之一）。本仓库按"类别不同、字段同一套"处理 |
