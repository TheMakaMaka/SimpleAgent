# 体检与失败归因

**一句话**：出问题时跑一条命令，它自己采集、自己判断、自己给结论。

```powershell
python scripts\doctor.py              # 人读：分节报告 + 结论
python scripts\doctor.py --json       # 机器读（Agent 用的就是它）
python scripts\doctor.py --triage     # 归因最近一次失败
python scripts\doctor.py --triage <run_id>
python scripts\doctor.py --e2e        # 额外真跑一次演示运行
```

---

## 1. 为什么要有它

出问题时，人的自然反应是：**收集信息 → 整理成报告 → 交给别人判断**。

这个来回本身就是瓶颈，而且整理过程会丢信息（"我看到报错里有 ModuleNotFound"，
但没说清是哪一步、哪个文件）。所以把它做成命令：**采集与判断都归程序，
人只看结论。**

两条设计原则：

| 原则 | 原因 |
|---|---|
| **服务挂了也要能跑** | 体检最需要它的时候，恰恰是服务起不来的时候。所以除"服务"一节外全部离线自检 |
| **每条结论都带证据** | 没证据的判断等于猜；猜错会把人引向错误的修法 |

---

## 2. 七节检查

| 节 | 查什么 | 失败了意味着 |
|---|---|---|
| **引导** | `sys.path` / `.env` / 运行根 / 切 CWD | 后面所有项都会假失败，先看这节 |
| **环境** | Python 版本、`.venv`、依赖 | 装了没装的问题 |
| **路径与隔离** | 上游目录在不在、运行根可用、仓库根有没有 stray 目录 | 上游路径写错 / CWD 没切对 |
| **上游契约** | bridge 依赖的 16 个上游接口、挂钩能不能装 | 换了后端但接口对不上 |
| **标定自洽** | 阶段 == `PHASE_ORDER`、端点双向、前后端事件词表 | 标定和代码说谎了 |
| **服务** | `/api/health`、模型、检查点后端、`/app` | 服务没起 / 模型不通 / 前端没构建 |
| **历史与归因** | 最近运行的状态分布 + **逐条归因失败运行** | 这就是"审查"的主体 |

结论行只有三种：`PASS` / `WARN` / `FAIL`。**有 FAIL 就返回非零**，可以直接进 CI 或回归清单。

---

## 3. 失败归因：口径必须跟项目一致

归因不是随口分类——**归错类比不归因更糟**，它会让人朝错误方向修。
所以口径直接沿用项目自己的定义（`CYCLE.md` §12 / `能力评估报告.md`）：

| 类别 | 含义 | 应对 |
|---|---|---|
| **模型能力类** | 规格已写清，模型没做到 | 换更强模型；**不适合在工作流里打补丁** |
| **架构缺口类** | 系统缺少某个**显式模型** | 补机制，不是换模型 |
| **预算耗尽** | 轮次 / 步数 / 重试次数用完 | 调 `ModelLimits` 或缩小任务粒度 |
| **环境问题** | 依赖缺失、路径不对、服务不可达 | 与模型能力和工作流都无关 |
| **验收标准问题** | 验收命令本身有毛病（语法错、恒真、不可能成立） | 检查调用方给的 `verify` |
| **规划失败** | 主循环没能拆出可执行任务 | 提示词或目标描述太含糊 |
| **人工取消** | 按请求中止 | 不是失败 |

> **边界很重要**：`manifest` 已执行但内容不合格（文件没写、缺符号、语法错），
> 属于**模型能力类**——因为 manifest 本身就是为补那个架构缺口做的。
> 只有 `checked=False`（压根没有交付声明）才是**架构缺口类**。
>
> 这条边界踩错过一次：早先把 `declared-broken`（写出来的文件语法都错）归成架构缺口，
> 等于说"系统缺机制"，会把人引向去补机制，而真正的问题是模型写坏了代码。
> **是在一次真实失败运行上发现的**，现在有 `test_triage.py` 钉住。

---

## 4. 输出长什么样

```
# 失败归因：run_20260926_002100_4d6778

- 目标：写一个汉诺塔的递归循环并验证
- 终态：`error` · 尝试 1 次
- 首次失败阶段：`attempt 1`

## 1. 模型能力类 — 产出的文件无法解析（语法错误）

**应对**：规格已写清但模型没做到 → 换更强模型；不适合在工作流里打补丁

证据：
- `declared-broken: test_hanoi.py 存在但无法解析: SyntaxError: invalid syntax (line 2)`

## 2. 环境问题 — 运行期异常

**应对**：依赖缺失、路径不对、模型服务不可达 → 与模型能力和工作流都无关

```
TypeError: CodingCycle._emit() got multiple values for argument 'kind'
```

## 关键时间线
...
```

**每一条都能指回原始事件**（`data/storage_data/runs/<id>/events.jsonl`）。
没有证据时它不会硬编一个结论——会明确说"证据不足"。

---

## 5. 纳入回归

```powershell
python scripts\doctor.py                  # 有 FAIL 即非零
python tests\unit\test_triage.py          # 归因分类（35 项，离线）
python scripts\layout.py --check          # 目录归属没归类即非零
```

`test_triage.py` 是这套归因的**看门测试**：每一类都给一个合成事件流、
断言类别。归错类会立刻红——因为归因是给人下判断用的，错了比没有更糟。

---

## 6. 尚未做

- **归因只看单次运行**：没有跨运行的"同一类失败反复出现"的趋势分析。
  那需要历史语料，属于 `CYCLE.md` §11.4 规划的跨周期角色。
- **不能自动修**：只诊断不治疗。要自动修得先有回退与验证网——
  这个项目有，但"改哪儿"还需要人（或 Agent）判断。
- **`doctor --e2e` 会真跑流程**：约 20 秒，且会写 `data/`。默认不开，按需加 `--e2e`。

---

## 7. 责任自审查（`/api/audit`）—— 「该改谁」

上面那套是**本地**体检（bridge 与上游同进程时可用）。如果服务是独立的，
本地脚本够不到它内部——所以服务自己也要能回答一个问题：

> **服务与前端不兼容时，该改前端，还是后端接口定义有问题？**

```bash
curl http://127.0.0.1:8000/api/audit          # 服务自审：声明 vs 实现
curl -X POST http://127.0.0.1:8000/api/audit -d '{...前端期望...}'
```

### 7.1 判定分界线

**核心是「声明」，不是「实现」。** 服务是黑盒，前端唯一能依赖的就是它声明了什么。
所以：声明与实现不符 = 后端的问题；实现与前端期望不符 = 前端的问题。

★ 但**归属按仓库边界**（`.interface_contract` 的 `boundary_definition`）：
**`bridge/` 里的问题算 `frontend`**。所以"声明与实际不符"里，
凡是**声明写在 `bridge/`** 的（阶段清单、端点声明、标定表），都归前端；
只有**事实源在上游**的（`PHASE_ORDER`、上游接口）才归后端。

| 现象 | 归属 | 严重度 | 理由 |
|---|---|---|---|
| 服务**声明了** X，前端不认识 X | `frontend` | `degraded` | 服务守约了；前端没跟上声明 |
| 服务**声明了** X，实际**不做** X（事实源在上游） | `backend` | `breaking` | 自相矛盾——上游词表与实现不符 |
| 端点**声明与注册**不一致 | `frontend` | `breaking` | 两者都写在 `bridge/spec.py` |
| 上游端点被删（bridge 声称重暴露的没了） | `backend` | `breaking` | 上游删了它承诺过的面 |
| 前端认得服务不声明的事件（孤儿） | `both` | `degraded` | 无法从事实源单方面判定，需协商 |
| 前端画的阶段双方都没有 | `both` | `degraded` | 同上 |
| 前端漏画上游阶段 | `frontend` | `degraded` | 服务声明了，前端没跟上 |
| 契约版本没上报 / 对不上 | `frontend` | `degraded` | 重新构建即可对齐 |
| 服务多了端点（additive，前端还没用） | `frontend` | **`info`** | 不是错，只是还没用到 |
| 服务不可达 / 前端没构建 | `ops` | `breaking` | 与双方契约无关 |

**`info` 不参与结论**（契约 `severity_vocabulary` 明规，且有实测支撑：
上游新增 28 个端点全是 `info`，结论仍是 `ok`）。否则"上游加东西"
就会被报成"有事要改"。

一次审查可能牵涉**多方**，结论（6 值）会如实反映：`ok` / `ops-action` /
`backend-action` / `frontend-action` / `need-negotiation` / `multi-action`。
**`ops` 优先判定**——环境没弄好，后面判什么都没意义。

### 7.1b `warnings`：**和结论一起看**（否则会漏）

自契约 v1.0.5 起，有一类事实**不参与 verdict**，只出现在 `warnings` 里：
**被传输层证伪的 ops 事实**（请求已成功送达，却报了 `service_down`）。

```
verdict = ok                                    ← 只看这里，什么都看不出来
⚠ 客户端上报 service_down=true，但该请求已成功送达本服务 ——
  这条 ops 事实被传输层证伪（code=O-service-down），未参与判定。
ops 栏 = {'service_down': True}                 ← 运维要看的"上次已知状态"
```

| 现象 | verdict | 哪里能看到 |
|---|---|---|
| 陈旧 `service_down` | **`ok`** | **`warnings` / `ops` 栏** |
| `frontend_not_built` | 仍是 `ops-action` | verdict 就能看到 |

**所以判断环境问题不要只看 `verdict`。** 契约因此立了一条消费方义务：
「展示 verdict 的消费方**应当同时展示 warnings**」——
界面上的落点是顶栏徽标（带提示条数）+ 展开后的提示段。

**排查时看哪一处**（`doctor.py` 与 `/api/audit` 都遵循这个分工）：

| 想知道 | 看 |
|---|---|
| 谁该改（要动手的） | `verdict` + `responsibility` |
| 环境/运行态（含"上次已知状态"） | `ops` 栏 |
| 被证伪、因此不进结论的观测 | `warnings` |
| 只是提醒、不参与结论 | `info` 项（`info_count`） |

### 7.2 前端「按什么写死的」从哪来

前端在启动时 POST 上自己的期望。这份期望**由构建期从源码扫出来**
（`frontend/scripts/gen-expectations.mjs` → `src/generated/expectations.ts`）：

| 期望 | 扫哪里 |
|---|---|
| `events` | `store/run.ts` 的 `case '...'` |
| `endpoints` | `api/*.ts` 的 `need('...')` / `endpoint('...')` |
| `stages` | `api/spec.ts` 的 `DEFAULT_SPEC` |
| `proxied_upstream` | `vite.config.ts` 的 proxy 表 |

**为什么不手写**：手写的一定会漂；那时审查会给出**错误的责任判定**，
比不审查更糟——它会让人去修不该修的那一方。

上报体用契约 `client_report_schema` 的字段名，**事件与阶段按来源分开**
（缺口 G2/G3/G4）。分区**判据来自服务**（`/api/spec`），**成员来自生成物**：

```
POST /api/audit  {
  contract_version, schema_version,
  upstream_event_kinds[12], frontend_event_kinds[21],
  phases[5],                bridge_gate_steps[manifest],
  upstream_endpoints[7],    frontend_endpoints[13]
}
```

界面上顶栏有个「✓ 兼容 / ⚠ 契约 / ⇄ 待协商」徽标，点开就是分好归属的清单
（阻塞项在上，`info` 折起来）。**不需要人去比对两份定义。**

### 7.3 四条自检

```powershell
python scripts\doctor.py                          # 本地七节体检（含 /api/audit 那部分）
python tests\unit\test_contract_vocab.py          # 78 项：词表 vs 契约 JSON（离线）
python tests\unit\test_partition.py               # 55 项：三条分区 vs 契约快照（离线）
python tests\unit\test_audit.py                   # 107 项：归属断言（离线）
python tests\unit\test_audit_authority.py         # 35 项：对账入口按职责切分（离线）
python tests\unit\test_staleness.py               # 34 项：上游副本陈旧检测（离线）
$env:AGENT_BASE="http://127.0.0.1:8220"; `
  python tests\diagnostics\check_contract_report.py   # 端到端上报体 + 双入口归属对账
```

### 7.4 两个入口的**职责切分**（架构清单 A1a）

上游和 bridge 各有一个对账入口。**不是二选一，也不是合并 —— 是按职责切**：

| 入口 | 权威范围 | 明确**不**负责 |
|---|---|---|
| `GET/POST /contract/check`（上游） | **跨侧对账**：归属、严重度、结论、`both` 协商项 | 本地环境细节 |
| `GET/POST /api/audit`（bridge） | **本地自检**：bridge 声明 vs 实现 vs 环境（钩子、构建产物、标定） | **跨侧归属**（引用上游 code，不自立判据） |

`/api/audit` 的响应里带 `authority: "local-self-check"` 与 `authority_note`
自述这件事。**为什么不是删掉一个**：`/api/audit` 看得见上游看不见的东西
（`frontend_not_built`、钩子是否装上、bridge 自己的声明自洽性）——
那些事实本来就无法由上游观测。硬合并会丢掉这些观测能力。

**排查时该看哪一份**：跨侧不一致（谁该改）以上游 `/contract/check` 为准；
"本机/本进程/本适配层哪里不对"看 `/api/audit`。
`check_contract_report.py` 会**同时**打两个入口，断言同一跨侧不一致的 owner 一致。

### 7.5 上游来源与陈旧：**服务活着不代表机制可用**

仓库自带的 `backend/` 副本**缺 `core/contract.py`**，于是新契约机制整体静默不可用，
而服务照常启动、界面照常显示。查这一项：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health |
  Select-Object backend_dir, backend_is_bundled, backend_stale, backend_stale_reason,
                backend_bundled_override, frontend_asset
python scripts\doctor.py            # 「路径与隔离」节
```

**★ 自 A2b 起，bundled 不再是"警告"而是"拒绝启动"**（退出码 2，端口不监听）。

原因不是"警告写得不醒目"，而是**"警告"这个手段本身不够**：
A2 的四条验收标准（探针、警告、陈旧检测、doctor）**全部通过**之后，
用户实例仍以 bundled 方式跑了约 10 轮，上游修复一条都没生效 ——
**「可见」被当成了「足够」，而它不够。**

| 情形 | 行为 |
|---|---|
| 解析到 bundled 副本 | **不启动**（退出码 2），并打印 `backend_dir` + 带后果的理由 + 可复制的修复命令 |
| 显式 `--allow-bundled` / `AGENT_ALLOW_BUNDLED=1` | 启动，但 `/api/health` 报 `backend_bundled_override=true` —— **降级必须留痕** |
| 指向真上游 | 正常启动，`backend_is_bundled=false`、`override=false` |

★ **门禁判「形态」不判「状态」**：即使副本此刻恰好同步，也照样拒绝 ——
"此刻同步"是一个会过期的属性，而这条规则要防的是"**你以为在跑上游、其实在跑副本**"。

**判据是 `paths.BACKEND_DIR`**，不是"能 import `core`"——仓库里有两个同名 `core` 包。

**`frontend_asset`** 回答的是另一个问题："**我打开看到的是哪一版**"。
它从 `dist/index.html` **引用的那个 JS** 读（不是"目录里最新的那个"——
两者在构建中断时会不一致）。
