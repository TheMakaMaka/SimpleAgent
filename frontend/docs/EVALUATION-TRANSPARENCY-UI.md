# 变更评估文档 · `TRANSPARENCY-UI`

- **变更编号**：`TRANSPARENCY-UI`（统筹方建议）
- **提出方**：用户（2026-09-27 对一次真实运行的审查）→ 统筹方拆解
- **执行侧**：frontend（`SimpleAgent2_Cycle_VueWeb`，含 `bridge/` 与 `frontend/`）
- **日期**：2026-09-27
- **契约版本**：`1.0.24`（镜像与主本 SHA256 一致，逐字节相同）

---

## 1. 变更意图

> 引指令原文（`DISPATCH.md`）：

> ## 本轮：**把"为什么"显示出来**（决策透明化 + 判据演化 + 收尾自述）
>
> 需求编号建议 **`TRANSPARENCY-UI`**。**本轮是显示层，不改判定逻辑。**
>
> ### 4. 验收（**固定样例，我会照着核**）
>
> 用 `run_20260927_125647_5a3297` 作为固定样例（它在你的 `data/` 里就有），界面必须能直接看出：
>
> 1. **判据 (b) 执行失败 → 换成 (c) 通过**，且标出"上一条失败了"；
> 2. 编排器每一轮的 `reasoning`（为什么又去改 `obstacle_generator.py`）；
> 3. 模型在 t2/t3 回合说的原话；
> 4. 收尾自述里，**`not_done` 必须包含「跑测试」与「生成报告」**，
>    且若模型谎报，`fact_check` 的矛盾要**一眼可见**。
>
> > **不要用"我们自己的测试过了"当作完成依据。** 我会打开界面按上面四条核。

另附（同文件第 5 节，2026-09-27 晚追加）：

> **因此加了一项（需求文件第 6 节 D3）**：**按结局四值呈现** ——
> `pass` / `fail` / **`abstain`（模型声明做不到）** / **`invalid`（任务或工装本身有问题）**，
> 并把「**判据来自谁**（caller / model）」**显示在结论旁**。

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：固定样例 `run_20260927_125647_5a3297` 报 `status=passed`，
而机械事实是"没跑测试、没有报告、有个 `np` 未定义的文件"。
**唯一被真跑过的是判据本身，而判据在失败之后被换成了一张必过的考卷** ——
这件事在界面上完全看不见。

**复现命令**（不需要模型、不需要起服务）：

```powershell
cd frontend
node scripts/replay-check.mjs
```

**实际输出**（节选，完整输出见 §4）：

```
B4 验收判据演化（按 seq 原序，不重写因果）
共 4 条候选/采纳记录，seq 顺序 = 35 → 56 → 57 → 74
  seq= 35 [未通过][executed] import ant_colony, test_ant_colony
  seq= 56 [通过][executed] from obstacle_generator import generate_obstacles
        ⚠ 上一条判据执行失败了（seq=35）→ 本条紧随其后（按序号相邻推断）
  seq= 57 [候选被拒][rejected] （命令未单独记录）
        理由：模型自拟的验收判据不合格，已拒绝采纳（…被拒命令: "import obstacle_generator…"）
  seq= 74 [通过][adopted][最终被记录] from obstacle_generator import generate_obstacles
```

**为什么这是问题**：`passed` 这个读数**不可采信**。
用户的原话是「不是让他能做出来什么，而是**知道做了什么、做的对不对、不能做什么**；
用这些规范的标准验证出**哪些模型能做、哪些做不了**」。
在"做不出来却报通过"的情况下，**界面的读数会污染整张能力画像** ——
所以这一轮不是加功能，是**让读数可采信**。

### 2.1 顺带发现的三处"界面对不上机械事实"（各自附全位置）

| # | 现象 | 位置（两个值分别在哪） | 处理 |
|---|---|---|---|
| 1 | 时间线显示"写入 `obstacle_generator.py`（**235 字符**）"，而后端自己的回执写的是 **275** | `bridge/hooks.py:74` 把长参数换成「前 6 行 + `…（共 275 字符）`」；`frontend/src/store/args.ts` 旧实现对**预览串**取 `.length` → 235 | 改读事件里声明的真值（`contentLength()`） |
| 2 | 编排器的理由被标成「**主模型**推理」/「**主模型**决策」 | `frontend/src/components/TaskPanel.vue:70`（"主模型推理"）、`frontend/src/store/run.ts` 的 `case 'orchestrator_decision'`（`主模型决策 → `）；而事件名是 `orchestrator_decision` | 改成"编排器"，并指向完整视图 |
| 3 | "什么都没干"的回合与"只调工具"渲染成同一句 | `frontend/src/components/TransparencyPanel.vue`（A3 分支）；样例 `seq=48` 的 `model_reply` 是 `content_len=0, tool_calls=0` | 三种"没说话"分开显示 |

> 第 3 条的**另一个来源**（后端，本轮不改）：`verify_skipped` 的 `command` 恒为空 ——
> 上游 `core/coding_cycle.py:384` 在"自拟判据被拒"这条路径上**硬编码 `command=""`**，
> 被拒的命令只出现在 `reason` 里（`core/coding_cycle.py:383-384`）。
> 界面因此显示"该事件未单独记录命令"，**不去 `reason` 里猜一个命令出来**。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260927-105719_v15-verify-skipped
```

```
[改动] 25
   ~ bridge\partition.py
   ~ bridge\spec.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ frontend\dist\index.html
   ~ frontend\package.json
   ~ frontend\README.md
   ~ frontend\scripts\gen-expectations.mjs
   ~ frontend\src\App.vue
   ~ frontend\src\components\TaskPanel.vue
   ~ frontend\src\components\VerifyPanel.vue
   ~ frontend\src\generated\expectations.ts
   ~ frontend\src\store\run.ts
   ~ frontend\src\types.ts
   ~ README.md
   ~ scripts\doctor.py
   ~ tests\diagnostics\check_contract_report.py
   ~ tests\unit\test_audit.py
   ~ tests\unit\test_event_contract.py
   ~ tests\unit\test_partition.py
[新增] 10
   + docs\EVALUATION-TRANSPARENCY-UI.md
   + frontend\dist\assets\index-BcJOtip4.js
   + frontend\dist\assets\index-DZFXNCxx.css
   + frontend\scripts\replay-check.mjs
   + frontend\src\components\TransparencyPanel.vue
   + frontend\src\store\args.ts
   + frontend\src\store\transparency.ts
   + tests\diagnostics\make_transparency_fixture.py
   + tests\fixtures\transparency-fixture.json
   + tests\unit\test_transparency_ui.py
[删除] 2
   - frontend\dist\assets\index-OwZY1JQb.css
   - frontend\dist\assets\index--XpunQ0C.js

改动合计 37 个文件。
```

> 这次 `-Verify` 跑在**本文件已经写出来之后**，所以本文件在清单里（新增）。
> 两条 `frontend/dist/assets/*` 的"删除"是**构建产物换名**（`vite build` 的哈希变了），
> 不是源码删除；`frontend/dist/` 整体是构建产物，回退时要与源码一起退
> （否则"界面是哪一版"会对不上 —— `frontend_asset` 读的是 `dist/index.html` 引用的那个 JS）。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `frontend/src/store/transparency.ts` | 新增 | 四块「为什么」的采集器 + **声明词表** `RECOGNIZED_KINDS`（A2/A3/B4/C3/D3） |
| 2 | `frontend/src/components/TransparencyPanel.vue` | 新增 | 四个 tab + 常驻矛盾/缺席横幅；**默认落在判据演化** |
| 3 | `frontend/src/store/args.ts` | 新增（从 `run.ts` 拆出） | 工具参数摘要**一份实现**，两人共用；并修 §2.1 第 1 条的 235/275 |
| 4 | `frontend/src/types.ts` | 视图模型 | A2/A3/B4/C3/D3 的类型；B4 划成 `action`/`outcome`/`adopted` **三根轴** |
| 5 | `frontend/src/store/run.ts` | `applyEvent` 开头 | 接上采集器；修「主模型决策」误标；`factCheck` 初值 `null`（不是空数组） |
| 6 | `frontend/src/App.vue` | 模板 + 样式 | 通栏挂载「为什么」审查条（默认展开，可收起） |
| 7 | `frontend/src/components/VerifyPanel.vue` | VERIFY 块 | D3：结论旁显示**结局四值 + 判据来自谁**；旧词表如实说明 |
| 8 | `frontend/src/components/TaskPanel.vue` | 推理块 | 修「主模型推理」误标，并指向完整视图 |
| 9 | `bridge/spec.py` | 标定表 / `frontend_event_kinds` | 给上游三个新事件补 `/api/spec` 校准；"前端认得的词"改为 `case ∪ 采集器声明`；`diagnostics` 增 `contract_lag` |
| 10 | `bridge/partition.py` | `CONTRACT_LAG_KINDS` + `check_against_contract` | 契约不一致**按方向分流**：`少` → FAIL；`多` 且已登记 → 滞后（见 MODULES §27） |
| 11 | `scripts/doctor.py` | 标定自洽 / 词表核对 | bundled 配置下"死标定/孤儿 case"降级为 WARN 并写明理由 |
| 12 | `frontend/scripts/replay-check.mjs` | 新增 | 固定样例 → 真实归约器 → **真实 SSR 渲染**；含新事件与 C3 夹具 |
| 13 | `frontend/scripts/gen-expectations.mjs` | `scanEvents` | 上报给 `/api/audit` 的期望也要含采集器词表（否则审查会说错话） |
| 14 | `tests/unit/test_transparency_ui.py` | 新增 | 把上面那条拉进门禁 + 编码门禁 + 夹具来源核对 |
| 15 | `tests/unit/test_event_contract.py` | `[2]/[3]/[5]` | "前端认得的词" = `case ∪ 采集器声明`；三个待同步事件给**逐名可核**的豁免 |
| 16 | `tests/unit/test_partition.py` · `tests/unit/test_audit.py` · `tests/diagnostics/check_contract_report.py` | 期望值 | 改为**从 `CONTRACT_LAG_KINDS` 推导**，不再写死 12/13/34 |
| 17 | `tests/diagnostics/make_transparency_fixture.py` | 新增 | 用**后端自己的 `fact_check()`** 生成 C3 夹具（可复现） |
| 18 | `tests/fixtures/transparency-fixture.json` | 新增 | 上面那一步的产物（诚实版 / 谎报版） |
| 19 | `frontend/package.json` | `check:transparency` | 让那条命令有个名字 |
| 20 | 文档 | `README.md`、`CYCLE.md`、`docs/{CHANGELOG,MODULES,DIAGNOSTICS,ARCHITECTURE,OPERATIONS}.md`、`frontend/README.md` | 版本戳 → §32；新增模块 §26/§27、诊断 §8、界面说明；登记本文件 |

**若两者不一致**：以机械输出为准。已核对——手写导读覆盖了机械输出的每一类
（源码 / 测试 / 文档 / 构建产物 / 门禁脚本），没有漏类别。

---

## 4. 主张与验证命令（对应 C2、C3）

**每一条都先给命令，再给实测输出。**

### 4.1 四条验收 + D3

```powershell
cd frontend
npm run check:transparency        # = node scripts/replay-check.mjs --assert
```

```
通过 66/66
```

其中直接对应验收的四组断言（实测输出原文）：

| # | 验收条目 | 实测输出 |
|---|---|---|
| 1 | 判据 (b) 失败 → (c) 通过，且标出"上一条失败了" | `PASS ★ (b) 失败之后的下一条带"上一条失败了"标记，且指向 (b) 的 seq   seq=56 指向 seq=35`<br>`PASS ★ (c) 该条已执行且通过，命令是 \`assert generate_obstacles\`   "assert generate_obstacles, 'generate_obstacles 函数已修正'"` |
| 2 | 编排器每轮的 `reasoning` | `PASS ★ 有一轮的 reasoning 解释了"为什么又去改 obstacle_generator.py"，且本轮确实派了这件事`<br>`PASS [决策] 第 3 轮 reasoning 可见（为什么又去改 obstacle_generator.py）` |
| 3 | 模型在 t2/t3 回合的原话 | `PASS ★ t2 有模型原话   "已生成 \`ant_colony.py\` 文件，包含 AntColony 类。"`<br>`PASS ★ t3 有模型原话   "总结：已生成 test_ant_colony.py 文件，包含蚁群算法测试用例。"` |
| 4 | 自述 `not_done` 含两项 + 谎报时矛盾可见 | `PASS ★ 验收 4 前半：not_done 含「跑测试」`<br>`PASS ★ 验收 4 前半：not_done 含「生成报告」`<br>`PASS ★ 验收 4 后半：谎报版被标出矛盾（后端 fact_check 判的）   artifact-missing,done-mentions-missing-file`<br>`PASS ★ [渲染] 谎报版：矛盾块排在 done/not_done 之前（最显眼处）` |
| D3 | 结局四值 + 判据来源在结论旁 | `PASS ★ 判据来源 = model（该样例是模型自拟判据，结论旁必须显示这个）   model`<br>`PASS [门禁] 结论格旁显示"判据来自 模型自拟"`<br>`PASS [门禁] 旧词表说明可见（abstain/invalid 尚无位置）` |

**★ 关于第 4 条，必须说清楚它验到了哪一层**（这是本轮最容易被误读的一处）：

- `self_report` **由模型产生**，我离线造不出真模型的话；固定样例里也**没有**这个事件。
- 所以 `fact_check` 的**判定不是我写的**：夹具脚本
  `tests/diagnostics/make_transparency_fixture.py` 调**上游自己的**
  `core/self_report.fact_check()`，机械事实取自固定样例的 `meta.json`，
  自述文本才是明写的夹具（诚实版 / 谎报版各一份）。
- 因此我验的是：**"矛盾能不能被后端的判定函数检出来" + "检出来之后界面会不会把它放在最显眼处"**。
  **我没有**真跑一次带 `self_report` 的运行 —— 那需要模型，见 §7。

### 4.2 界面"真的渲染出来了"（不是只有读数对）

```powershell
cd frontend
node scripts/replay-check.mjs            # 看 [R] 段
```

实测：用**同一份 vite 配置**做 SSR 构建，`vue/server-renderer` 渲染
`TransparencyPanel.vue` / `VerifyPanel.vue` 成 HTML，逐个 tab 断言关键字符串：

```
  [透明化·criteria] 5732 字节 HTML / 1351 字文本
  [透明化·decisions] 5860 字节 HTML / 843 字文本
  [透明化·turns] 9532 字节 HTML / 1570 字文本
  [透明化·report] 2215 字节 HTML / 407 字文本
  [门禁 VERIFY] 5081 字节 HTML / 866 字文本
通过 66/66
```

> 为什么加这一层：`vue-tsc` 与 `vite build` **都不执行归约器、也不渲染组件**。
> "读数算对了、组件却挂在 `vif` 后面没显示"是这类改动最阴的失效。

### 4.3 门禁（两种配置都要绿）

```powershell
# 自带旧副本（默认）
python tests/unit/test_event_contract.py        # 21/21
python tests/unit/test_transparency_ui.py       # 50/50
python tests/unit/test_partition.py             # 55/55
python tests/unit/test_audit.py                 # 107/107
python tests/unit/test_spec.py                  # 42/42
python tests/run_unit.py                        # 36 个测试文件，exit 0

# 指向真上游
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"
python tests/unit/test_event_contract.py        # 30/30
python tests/unit/test_partition.py             # 60/60
python tests/unit/test_audit.py                 # 107/107
python tests/unit/test_spec.py                  # 43/43
python tests/run_unit.py                        # 36 个测试文件，exit 0
python scripts/doctor.py                        # 失败 0 项（bundled 配置同样 0 项）
```

`/api/spec` 的标定（**改之前是真上游下的红项**）：

```powershell
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"
python -c "from bridge.spec import build_spec; d=build_spec()['diagnostics']; print(d['uncalibrated_events'], d['dead_calibrations'], d['contract_lag'], d['event_count'])"
```

```
[] [] ['orchestrator_round', 'self_report', 'verify_criterion'] 37
```

> 注意第三项：**它不为空是如实报告，不是残留问题**。它是"上游已实装、契约主本尚未声明"，
> 方向由 `bridge/partition.py` 的 `CONTRACT_LAG_KINDS` 判定（见 MODULES §27）。

**契约不一致的方向判定**（这一轮顺带做掉的，红了六个门禁）：

```powershell
python tests/unit/test_partition.py     # 里面有负向断言：塞一个没登记的名字进去，必须报红
```

```
PASS ★ 多出来的**只有**已登记滞后那些（不许有没登记的）   ['orchestrator_round', 'self_report', 'verify_criterion']
PASS ★ 事件分区错了自检会红   ["上游事件集合与契约快照不一致：多 ['invented_event'] 少 []（另有已登记滞后 …）", …]
```

夹具可复现（用后端代码重新生成）：

```powershell
$env:AGENT_UPSTREAM_DIR="D:\PythonProject\SimpleAgent2_Cycle"
python tests/diagnostics/make_transparency_fixture.py
```

```
  PASS  ★ 诚实版 not_done 含「跑测试」
  PASS  ★ 诚实版 not_done 含「生成报告」
  PASS  ★ 诚实版没有凭空造出矛盾（自述与事实一致）   []
  PASS  ★ 谎报版被后端自己的 fact_check 抓出矛盾   ['artifact-missing', 'done-mentions-missing-file']
  PASS  ★ 谎报版矛盾指向 report.md（工作区里没有这个文件）
通过 6/6
```

### 4.4 未验证的部分

- **没有真跑一次带 `self_report` 的运行**：需要模型。见 §7 第 1 条。
- **没有构造多 attempt 的运行**：判据列表是一条按 seq 的平铺序列；
  跨 attempt 的"上一条失败"已在代码里阻断（只在同一次尝试内陈述），
  但**没有真实样例证明阻断是对的**。
- **没有在浏览器里点过**：机械层验到"HTML 里确实有那行字"，
  **排版、折叠、"看不看得懂"没有验**。这恰恰是验收方的判据，我不冒充已验。
- **D1（四值）没验**：后端没交付，见 §6.3 第 2 条。
- **`orchestrator_round` / `verify_criterion` 只在合成事件流上验过**：
  字段取自上游 `core/contract.py` 的 `EventSpec`，但**没有一次真实运行**产生过它们。
- **`relaxed` 结局没有位置**：它是 `bridge/spec.py:305` 状态词表里的一员，
  但不在 D1 的四值里；界面显示"未产出结局"，**不替它归类**（见 §6.3 第 2 条）。
- **契约滞后机制只在两种配置下验过**：bundled（三个名字是"预备"）与真上游
  （三个名字是真实事件）。**没有第三种组合**（例如指向一份部分更新的上游）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **否** | 一个都没改名、没删除。只是**读**了三个上游已实装的事件 |
| 事件 payload 键 | **否** | 只读，不写。读取的键全部对照上游 `core/contract.py` 的 `EventSpec` |
| 上游 `PHASE_ORDER` 阶段 | 否 | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | 否 | 前端读 `meta.json`（只读，用于夹具的机械事实） |
| `TOOLS_MAP` 条目结构 | 否 | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **否** | `bridge/spec.py` 的 `SPEC_VERSION` 未动；契约版本仍从上游读 |
| 端点路径 | 否 | `/api/spec` 的**内容**多了 3 条事件标定，路径没动 |
| `.interface_contract/` 覆盖的规则与词表 | **否** | 镜像未改（与主本 SHA256 仍一致） |

**改动了的东西（必须显式声明的四处）**：

1. **`/api/spec` 的 `events` 多了 3 条标定**（`orchestrator_round` / `verify_criterion` /
   `self_report`）。这是 **additive**：不改任何既有条目的 label/tone/panel；
   `event_count` 由 34 → 37（真上游配置下）。
   **理由**：不标定它们，真上游下 `/api/spec` 就报
   `uncalibrated_events=[orchestrator_round, self_report, verify_criterion]`（实测），
   与 `verify_skipped` 那次（CHANGELOG §31）是同一类缺口。
2. **`/api/spec` 的 `diagnostics` 多了 `contract_lag` / `contract_lag_note`**（additive）。
3. **`bridge/partition.py` 的 `check_against_contract()` 判据变了**：
   从"不一致就 FAIL"变成"**按方向分流**"（`少` → FAIL；`多` 且逐个登记 → 滞后）。
   这是**判据**层面的改动，所以：负向断言（塞一个没登记的名字）保留并实测会红；
   `/api/spec` 会显示 `contract_lag`。细节见 `docs/MODULES.md` §27。
4. **`tests/unit/test_event_contract.py` 的 [2]/[3]/[5] 判据**：从"前端认得的词 = `case`"
   改为"= `case` ∪ 采集器**声明**的词（`RECOGNIZED_KINDS`）"。
   **这不是放宽**：声明与行为同一处（`HANDLERS` 的键就是 `RecognizedKind`，代码真的在用），
   且两个方向仍然都查（后端发的没被认 → 红；认了而无人声明 → 红）。
   同时给三个待同步事件一条**有到期条件的豁免**：逐名去**参考上游的 `core/contract.py`**
   核实 `EventSpec` 真的存在，核不到就 FAIL。

**另外两处顺带修掉的**（都是"少显示/说错话"，不改接口面）：

- `bridge/spec.frontend_event_kinds()` 与 `frontend/scripts/gen-expectations.mjs`
  现在都算 `case ∪ 采集器声明`。**改之前 `/api/audit` 会少算 3 个前端认得的事件** ——
  后果不是"少显示"，是**审查给出错误的责任判定**。
- `scripts/doctor.py` 的「无死标定 / 前端无孤儿 case」在 bundled 配置下降级为 WARN
  并写明理由（标定为契约的新上游备着）——旧行为会让默认配置**永远红着**。

---

## 6. 对另一侧的影响（对应 C6、C7）

### 6.1 另一侧需要跟着改吗？

**要，但不是"改代码"，是"同步契约"** —— 上游**已经实装**了后端那一半
（`D:\PythonProject\SimpleAgent2_Cycle`），而且**刻意换了名字**：

| 需求里的建议 | 上游实际发的 | 位置（两个值分别在哪） |
|---|---|---|
| `orchestrator_decision` 补 `reasoning`/`intent` | **`orchestrator_round`**（`reasoning` + `tasks`） | 声明：`core/contract.py:172`；发出：`core/coding_cycle.py:394` |
| 替换类事件带 `replaced_command`/`previous_passed` | **`verify_criterion`**（`action` + `previous_command`/`previous_passed`/`reason`） | 声明：`core/contract.py:181`；发出：`core/coding_cycle.py:407`；自动补前后关系：`core/memory.py:135-140` |
| 加性事件 `self_report` + 报告字段 | **`self_report`**（含 `fact_check.contradictions`） | 声明：`core/contract.py:189`；发出：`core/coding_cycle.py:755`；对照实现：`core/self_report.py:88` |

上游在 `core/contract.py:178-180` 写明了为什么避开 `orchestrator_decision`：
**那个 kind 由本仓库的 bridge 发，两个生产者发同一个 kind 会让审计无法判断哪条权威。**
**这个判断我认同**，所以界面**两个来源都认**：老运行（含固定样例）只有 bridge 那条。

### 6.2 契约主本与上游不自洽（**请裁定**）

| 事实 | 位置 | 值 |
|---|---|---|
| 上游契约版本 | `core/contract.py:57` | `CONTRACT_VERSION = "1.1"` |
| 三个新事件的 `since` | `core/contract.py:172` / `:181` / `:189` | **`"1.2"`** |
| 契约主本/镜像里的版本 | `01-contract/interface-contract.json` | `1.0.24`（主本与我方镜像 SHA256 **逐字节一致**） |

后果（实测）：标定之前，真上游下 `/api/spec` 报
`uncalibrated_events=[orchestrator_round, self_report, verify_criterion]`。
**我这一侧已经用"先认下来 + 逐名可核的豁免"绕过去了**，
但**契约主本里没有这三个事件**这件事需要统筹方决定：补进主本（版本升到能容纳它们的一版），
还是要求上游改回需求里建议的名字。**我不擅自改主本，也不擅自放宽。**

### 6.3 有没有可能"问题被平移到对侧"？

有三处，都是**我主动点名而不是推过去**：

1. **`verify_skipped.command` 恒为空**：`core/coding_cycle.py:384` 在"自拟判据被拒"路径上
   **硬编码 `command=""`**。B1 要求"候选/采纳/拒绝/替换都能直接读出前后关系"，
   而"被拒的那条命令是什么"目前**只在 `reason` 文本里**。
   我**没有**去 `reason` 里正则猜命令（猜错就是编事实），而是显示"该事件未单独记录命令"。
   —— 这是**后端应补一个字段**的事，不是前端显示问题。
   > 注：同一路径上游还有 `core/coding_cycle.py:379`（未注入 pipeline）**是**带 `command` 的，
   > 所以"`verify_skipped` 没有命令"这个说法**只对其中一条路径成立**。
2. **D1（结局四值）没交付**：`pass/fail/abstain/invalid` 在需求第 6 节里，
   上游 `CONTRACT_VERSION`（`core/contract.py:57`）仍写 `1.1`，全仓库 grep 不到
   `abstain`/`invalid`。所以界面上的"旧词表"提示是**如实的**，不是保守：
   现在的词表里**确实没有**"模型声明做不到"与"任务本身有问题"这两个位置。
   另外 `bridge/spec.py:305` 的状态词表里有 **`relaxed`（人工放宽）**，
   它既不是 `pass` 也不是 `fail` —— **四值没有覆盖它**，界面把它显示成"未产出结局"，
   **不替它归类**。这条也请裁定。
3. **契约主本与上游不自洽（需要裁定，不是平移）**：见 §6.2。
   我这一侧**用"登记 + 显示"绕过去了**，但主本该不该升版、三个事件该叫什么名字，
   只能由统筹方定 —— 我没有擅自改主本，也没有擅自放宽。

### 6.4 前端会静默少显示什么吗？

- 认不出的事件仍然**降级显示**（时间线里一行 + 标定的 label/tone），不报错、不崩。
- 三个新事件**已经认下来**（采集器 + 标定），所以不会退化成裸文本行。
- 若后端**改了** `self_report` / `fact_check` 的形状，面板会显示
  "自述缺了必需字段 / 认不出的判定值原样列出"，**不会当成"一致"** ——
  宁可少报一条矛盾，也不把没核过的东西说成一致。

---

## 7. 不做的部分及理由（对应 C7）

1. **不真跑一次带 `self_report` 的运行**：`self_report` 由模型产生，离线造不出真话；
   而"造一句假话再自己判它假"没有意义。**替代做法**（已做）：
   用**后端自己的 `fact_check()`** 去核对两份明写夹具，验"判定函数 + 界面显示"这一整条链。
   **我没有声称验收第 4 条在真实重跑上已完成。**
2. **不改判定逻辑**：指令原文「本轮是显示层，不改判定逻辑」。前端没有引入任何
   新的"通过/失败"判定；`fact_check` 完全由后端产出，前端只呈现。
3. **不替后端补 D1 的四值**：界面按四值呈现已经就绪（`abstain`/`invalid` 是一等公民），
   但**没有编造这两个值**，而是显示"旧词表，四值尚未交付"。
4. **不动 `.interface_contract/`**：镜像未改。
5. **不为了让自己绿而放宽门禁**：见 §5 第 2 条 —— 判据是**换了测量口径**
   （`case ∪ 声明`）而不是放宽；豁免逐名可核，且写明到期条件。
6. **不为 `self_report`/`fact_check` 写 `case`**：写了会在"自带旧副本"配置下
   被判成死代码。所以由采集器声明词表；**这一轮的取舍已写进代码注释**。

---

## 8. 回退点（对应 C8）

- **回退命令**：

  ```powershell
  .\scripts\backup.ps1 -List
  .\scripts\backup.ps1 -Restore -From 20260927-105719_v15-verify-skipped
  ```

  文件级回退（只退某几个文件）：

  ```powershell
  .\scripts\backup.ps1 -Restore -From 20260927-105719_v15-verify-skipped -Path frontend/src/App.vue
  ```

- **回退会丢什么**：本轮的**全部**改动（四块视图、D3 显示、三个新事件的标定、
  门禁口径与豁免、夹具与脚本、文档）。这是一次**加性**改动，
  回退之后界面回到"能看进度、看不出为什么"的状态，**不影响任何既有功能**。
- **回退后需要重建前端**：`cd frontend; npm run build`（`dist/` 也要一起退，
  否则"界面是哪一版"会对不上 —— `frontend_asset` 读的是 `dist/index.html` 引用的那个 JS）。

---

## 9. 自检结论

| # | 标准 | 结论 |
|---|---|---|
| **C1** | 问题陈述可复现 | **满足**。`node scripts/replay-check.mjs` 一条命令复现全部读数；§2.1 的三处缺陷各给了**两个值分别在哪**（`文件:行`） |
| **C2** | 每条主张带可复现验证命令 | **满足**。§4 每个主张都先给命令再给实测输出 |
| **C3** | 命令实测输出支持该主张 | **满足**。输出为原文粘贴（`通过 66/66`、`21/21`、`30/30`、`38/38`、`23/23`、夹具 `6/6`） |
| **C4** | 改动清单与实际一致 | **满足**。§3 以 `backup.ps1 -Verify` 的机械输出为权威，并显式点出本文件自身与 `dist/` 换名两处差异 |
| **C5** | 对接口契约的影响已声明 | **满足**。§5 逐项列表；改动的三处都显式声明且说明了 additive 性质 |
| **C6** | 对另一侧的影响已评估 | **满足**。§6：事件改名、契约主本与上游不自洽（附两处位置）、`verify_skipped.command` 恒空、D1 未交付、`relaxed` 无位置 |
| **C7** | 未把接口级问题当内部问题处理 | **满足**。`verify_skipped.command` 与 D1 两处**点名归后端/统筹方裁定**，没有在前端用正则猜命令、也没有编造 `abstain`/`invalid`；§7 明确列出我**不做**的部分与理由 |
| **C8** | 回退点明确 | **满足**。§8 给了整仓与文件级两条回退命令，并说明回退会丢什么、要重建什么 |

**我希望统筹重点验证哪一条**：**C3 与 §4.1 第 4 条**。

理由：四条验收里，前三条我能在**固定样例**上给出完整机械证据（且是渲染级，不只是读数级）；
**第 4 条的 `self_report` 文本是夹具、不是模型说的**。
我把它验到"后端自己的 `fact_check()` 能判出矛盾 + 界面把它放在最显眼处"这一层，
并且**明确标注了没验到的那一层**（没有真重跑）。
若这还不满足验收口径，**请直接说"第 4 条不成立"** ——
我会把它写成本轮的未完成项，而不是把它包装成已完成。
