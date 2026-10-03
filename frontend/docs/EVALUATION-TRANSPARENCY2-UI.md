# 变更评估文档 · `TRANSPARENCY2-UI`

- **变更编号**：`TRANSPARENCY2-UI`（工作单建议名；也可叫 `UI-SCROLL`，本轮四件事都在里面）
  · 追加项 **`P5`（🔴 阻塞：挂钩包装器镜像签名）** 见 §10
- **提出方**：用户（对两次运行的界面反馈）→ 统筹方拆成 P1–P4；随后追加 P5
- **执行侧**：frontend（`SimpleAgent2_Cycle_VueWeb`，含 `bridge/` 与 `frontend/`）
- **日期**：2026-09-27 / 28
- **契约版本**：`1.0.25` → **`1.0.26`**（镜像与主本 SHA256 一致）

---

## 1. 变更意图

> 引指令原文（`DISPATCH.md` / `WORK-ORDER.md`）：

> **P1 · `dist` 陈旧 —— 用户现在看到的不是你们最新交付的那一版。**
> 我实测…服务的 `index-BcJOtip4.js`，而当前源码重新构建出来是 `index-BazGZyJn.js`。
> **你们改了源码但没重建。** → **每次交付一并 `npm run build`**，并在评估文档里附构建产物哈希。

> **P2 · 右上角任务列表：任务一多就失去可视化价值。**
> 用户原话：「太多了就会压缩，也不会自动滚动」。**实测他两次运行就是 10 个 / 11 个任务。**
> 四条要求：**行高固定不压缩 · 面板固定最大高度内部滚动 · 新任务自动滚到当前项（用户手动滚过则不抢）· 量大时折叠已完成但当前项与失败项永远可见。**

> **P3 · D19-D3**：按**结局四值**呈现（`pass`/`fail`/`abstain`/`invalid`）+
> 结论旁显示「**判据来自谁**」（`caller`/`model`）+ **审查是否独立**（`REVIEW` 未启用时显示「非独立/未启用」）。

> **P4**：（后端产线就绪后）**③ 拆解合规审查结论**的展示：
> `violated` 与 `undecidable` **视觉上分开** —— **"判不了"不等于"通过"**。

> **"我们自己的测试过了"不算完成依据。**

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 P1：`dist` 与 `src` 分了家

**现象**：交付物里的前端 JS 缺三个事件（`orchestrator_round` / `self_report` /
`verify_criterion`）的字符串 —— 逐字节确认过：旧产物里没有它们，新产物里有。

**复现命令**（离线，不需要服务）：

```powershell
python scripts/freshness.py
```

**当时的实际输出**（修之前）：

```
  比对目标 dist : frontend\dist
  dist 提供     : index-BcJOtip4.js, index-DZFXNCxx.css
  当前源码构建   : index-BazGZyJn.js, index-DZFXNCxx.css
差异（**逐文件比内容，不看 mtime**）：
  + 应有却没有：index-BazGZyJn.js
  - 多出个不该有的：index-BcJOtip4.js（当前源码构建不出来这个文件名）
FRESHNESS state = fail
```

**根因（两个时间点）**：

| 时刻 | 事件 |
|---|---|
| **13:43:17** | `dist/index.html` 被构建（当时的 `frontend/scripts/gen-expectations.mjs` 还是旧的：只扫 `store/run.ts` 的 `case`） |
| **13:43:42** | 我把 `gen-expectations.mjs` 改成"前端词表 = `case` ∪ 采集器声明"（**晚了 25 秒**） |
| 13:49 / 13:52 | 两次备份的 preflight 只跑 `npm run typecheck` —— 它**只重新生成** `src/generated/expectations.ts`，**从不重建 dist** |

**为什么这是问题**：**改过的东西，不一定就是交付的东西。**
用户看到的界面不是最新交付的那一版，他提的界面意见可能有一部分已经过时。

### 2.2 P2：19 个任务下挤成一团

**现象**：`.task` 缺 `flex-shrink: 0`，而面板是有界高度的 flex 列
（`App.vue` 的 `.panel { max-height: 44vh }`）——子项默认 `flex-shrink: 1`，
**先被压缩、永不溢出**，于是 `overflow-y: auto` 永不生效。
**同一个机制同时解释了用户的两句话**（"太多了就会压缩" + "也不会自动滚动"）。

**复现命令**：

```powershell
cd frontend; node scripts/replay-check.mjs        # [P2] 段
```

**实测的事实**（比工作单说的更多）：验收方说的那两次运行按 `task_start` 数是
**14 与 19** 个任务，其中 `run_20260927_225939_f4daaa` 里 **`t9` 出现了两次**。

### 2.3 P3/P4：仪表没有刻度 / "判不了"会被读成"通过"

- **P3**：没有四值，人看到的还是一个笼统的"成功/失败"，
  而「**这次是模型自己出的考卷**」看不见（实测：39 条运行里判据来自调用方的是 0 条）。
- **P4**：`decompose_review` 的 `undecidable` 若与 `violated` 混在一起，
  或因为 `passed=true` 就画成绿色，就等于把**审查范围不完整**说成**审查通过**
  （契约 `core/contract.py:214-216` 专门写了这条警告）。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260927-134929_v16-transparency-ui
```

<!-- MECHANICAL-DIFF -->
```
[改动] 28
   ~ bridge\partition.py
   ~ bridge\runner.py
   ~ bridge\spec.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\EVALUATION-TRANSPARENCY-UI.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ frontend\dist\index.html
   ~ frontend\scripts\replay-check.mjs
   ~ frontend\src\App.vue
   ~ frontend\src\components\TaskPanel.vue
   ~ frontend\src\components\TransparencyPanel.vue
   ~ frontend\src\components\VerifyPanel.vue
   ~ frontend\src\generated\expectations.ts
   ~ frontend\src\store\run.ts
   ~ frontend\src\store\transparency.ts
   ~ frontend\src\types.ts
   ~ README.md
   ~ scripts\backup.ps1
   ~ tests\diagnostics\make_transparency_fixture.py
   ~ tests\fixtures\transparency-fixture.json
   ~ tests\unit\test_event_contract.py
   ~ tests\unit\test_partition.py
   ~ tests\unit\test_transparency_ui.py
[新增] 7
   + docs\EVALUATION-TRANSPARENCY2-UI.md
   + frontend\dist\assets\index-Bu5N1N67.js
   + frontend\dist\assets\index-yo24bi27.css
   + frontend\src\store\tasklist.ts
   + scripts\fix_bom.py
   + scripts\freshness.py
   + tests\unit\test_dist_freshness.py
[删除] 3
   - frontend\dist\assets\index-BcJOtip4.js
   - frontend\dist\assets\index-DZFXNCxx.css
   - tmp_doc2.txt

改动合计 38 个文件。
```

**P5 追加项的机械输出**（同一基线 `v17-transparency2-ui` 再比一次）：

```powershell
.\scripts\backup.ps1 -Verify -From 20260928-000917_v17-transparency2-ui
```

```
[改动] 13
   ~ bridge\hooks.py
   ~ bridge\partition.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\EVALUATION-TRANSPARENCY2-UI.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ README.md
   ~ tests\unit\test_event_contract.py
   ~ tests\unit\test_hooks_passthrough.py
[新增] 2
   + tests\diagnostics\hook_verify_e2e.py
   + tests\unit\test_hook_compat.py

改动合计 15 个文件。
```

> 三条"删除"都不是源码删除：两条是 `dist` **构建产物换名**（哈希变了），
> 一条 `tmp_doc2.txt` 是上一轮遗留的临时输出（已清掉）。
> `docs/EVALUATION-TRANSPARENCY-UI.md` 出现在"改动"里，是因为这一版的基线是
> **v16**（13:49），而上一轮收尾时我又补过它一次（v16.1，13:52）。

**手写导读（非判据）**

| # | 文件 | 为什么改 |
|---|---|---|
| 1 | `scripts/freshness.py` | **新**：P1 的判据 —— 用当前源码构建到临时目录再逐文件比（与统筹方同一条判据） |
| 2 | `tests/unit/test_dist_freshness.py` | **新**：把 P1 拉进门禁，含**负向**（改脏 dist 必须报陈旧） |
| 3 | `scripts/backup.ps1` | preflight 加"交付新鲜度"一项（根因就在这个函数里：跑 typecheck 却不重建 dist） |
| 4 | `frontend/src/store/tasklist.ts` | **新**：P2 的纯逻辑（`taskRows` 折叠分组 + `FollowMode` 跟随决策） |
| 5 | `frontend/src/components/TaskPanel.vue` | P2：不压缩 / 内部滚动 / 自动跟随 / 折叠已完成；推理块移出滚动区 |
| 6 | `frontend/src/store/transparency.ts` | P3/P4：`readVerdict` / `readDecomposeReview` / `readReuse` + `ingestReport()` |
| 7 | `frontend/src/types.ts` | P3/P4 视图（`VerdictView` / `DecomposeReviewView` / `ReuseView`）+ `RunInfo.report` |
| 8 | `frontend/src/components/VerifyPanel.vue` | P3：结论四值 + 判据来源 + 独立性（**结论旁**）；复用性检查（有否决权） |
| 9 | `frontend/src/components/TransparencyPanel.vue` | P4：新增「拆解合规」tab（`violated` 与 `undecidable` 分块）+ 标题栏独立性 |
| 10 | `frontend/src/store/run.ts` | `ingestReportInfo`（报告那条路） |
| 11 | `frontend/src/App.vue` | 运行详情取一次报告（旧运行的事件里没有 verdict） |
| 12 | `bridge/runner.py` | `run_end` 带上 verdict 那组字段（**只加不改**，实时与回放同源） |
| 13 | `bridge/spec.py` | 给 `reuse` / `decompose_review` 补标定（否则真上游下 `/api/spec` 报未标定） |
| 14 | `bridge/partition.py` | `CONTRACT_LAG_KINDS` 换成 v1.3 那两个；离线回退表升到 16/37 |
| 15 | `frontend/scripts/replay-check.mjs` | P1/P2/P3/P4 的机械断言（86 → 108 条） |
| 16 | `frontend/scripts/gen-expectations.mjs` | 前端词表含采集器声明（上一轮的改动的延续）→ 期望 37 → 39 |
| 17 | `tests/diagnostics/make_transparency_fixture.py` | 夹具扩到 P3/P4，**全部调后端真函数**产出 |
| 18 | `tests/fixtures/transparency-fixture.json` | 上面那一步的产物（verdicts / decompose_review / reuse） |
| 19 | `tests/unit/test_transparency_ui.py` | 断言条数、新条目、P3/P4 夹具来源核对 |
| 20 | `tests/unit/test_partition.py` | 落后分支不再写死名字（§31.3 的教训），改守"方向" |
| 21 | `scripts/fix_bom.py` | **新**：改完 `.ps1` 补 BOM 的一行命令（编辑工具会去掉 BOM，每次必踩） |
| 22 | 文档 | `docs/CHANGELOG.md` §33、`MODULES.md` §28、`DIAGNOSTICS.md` §8.4/§8.5、`OPERATIONS.md` 交付清单、`README.md` 登记与版本戳 |

---

## 4. 主张与验证命令（对应 C2、C3）

### 4.1 P1 · 交付新鲜度

```powershell
python scripts/freshness.py
python tests/unit/test_dist_freshness.py
```

实测（**修之后**）：

```
  dist 提供     : index-Bu5N1N67.js, index-yo24bi27.css
  当前源码构建   : index-Bu5N1N67.js, index-yo24bi27.css
      index-Bu5N1N67.js  sha256:d30297e6f3e7e769
      index-yo24bi27.css  sha256:f68c3a6352e41d3f
FRESHNESS state = ok（dist 与当前源码构建的结果逐文件一致）
```

```
  PASS  FRESHNESS state = ok   exit=0
  PASS  输出里有构建产物的哈希（可写进评估文档）
  PASS  负向：改脏 dist 之后 state = fail   exit=1
  PASS  负向：差异里点出「同名但内容不同」   ['~ 同名但内容不同：index-BazGZyJn.js  dist=43e6bf3a1c2e861b  重建=6621e0be937a15f8']
通过 6/6
```

**交付产物哈希（本版，两条命令都可复现）**：
`index-Bu5N1N67.js` = `sha256:d30297e6f3e7e769` ·
`index-yo24bi27.css` = `sha256:f68c3a6352e41d3f`。

> 负向那一条是关键：它证明这条门禁**不是永远绿** ——
> 而且它模拟的正是真实发生过的形态（**同名、内容不同**），比"少一个文件"更难发现。

### 4.2 P2 · 任务面板

```powershell
cd frontend; node scripts/replay-check.mjs        # [P2] 段（状态级 + 渲染级）
```

实测节选：

```
P2 任务面板：真实运行的 19 个任务（run_20260927_230240_0a42df）
  折叠视图：渲染 2 行（含折叠行）· 折叠 18 项
  PASS  ★ 任务确实很多（>10，足以复现用户说的"压缩"）   19
  PASS  ★ 量大时出现折叠行，且数量 == 被藏起来的任务数   group=18 藏=18 done=19
  PASS  ★ 折叠时**当前项永远可见**
  PASS  ★ **藏起来的只能是已完成**（不许藏 running/failed）   hidden=18
  PASS  ★ 展开后一个都不少（不丢任务）   19/19
  PASS  ★ key 唯一（任务 id 会重复：实测同一轮里 t9 出现过两次）   19/19
  PASS  ★ 跟随模式下会跟随 / 手动滚过之后**不抢** / 程序自己滚动**不改变**模式
  PASS  ★ [渲染] 折叠行在 HTML 里，并**写明数量**（收起要说出来）   已完成 18 项
  PASS  ★ [渲染] 当前项的描述在 HTML 里（当前项永远可见）
  PASS  ★ [渲染] 面板说明"折叠的只是已完成"（不许让人以为项丢了）
  PASS  ★ [样式] 不压缩：`.task { flex: 0 0 auto }`
  PASS  ★ [样式] 内部滚动：`.tasks__body { overflow-y: auto }`
  PASS  ★ [样式] 面板有界高（`max-height: 44vh`）
```

**这里能验到哪一层、验不到哪一层**（必须说清）：

- **验到了**：分组的**结果**（19 个任务 → 当前项与失败项必在可见集合、藏起来的全是 `done`、
  展开不丢项、key 唯一）、跟随的**决策**（纯函数三态）、渲染出的 HTML 里确实有折叠行与当前项、
  以及**样式契约**（`flex: 0 0 auto` / `overflow-y: auto` / 有界高）在源码里存在。
- **没验到**：**滚轮真的能滚、平滑滚动真的发生**、以及"手动滚过就不抢"在**真浏览器**里的时序。
  这需要浏览器（本仓库没有浏览器自动化）。我没有把它说成"已验证"。

### 4.3 P3 · 结局四值 + 判据来源 + 独立性

夹具**由后端自己的函数产出**（`build_verdict` / `classify_verify_detail`），不是我手写：

```powershell
$env:AGENT_UPSTREAM_DIR="D:\PythonProject\SimpleAgent2_Cycle"
python tests/diagnostics/make_transparency_fixture.py
```

```
  pass_model_self_authored: outcome=pass source=model trust=model-self-authored independent=false kind=verified
  abstain_no_criterion: outcome=abstain source=（空） trust=none independent=false kind=no-admissible-criterion
  invalid_criterion_broken: outcome=invalid source=model trust=none independent=false kind=criterion-broken
  fail_verify_failed: outcome=fail source=caller trust=none independent=true kind=verify-failed
  PASS  ★ 四值**都**由后端产出过（pass/fail/abstain/invalid）
  PASS  ★ 模型自拟判据的通过带 `model-self-authored` 且 `criterion_independent=false`
  PASS  ★ 调用方判据带 `criterion_independent=true`
  PASS  ★ `abstain` 与 `invalid` 各有可读理由（不是空串）
```

渲染级（四种各渲染一次，走**事件**那条路）：

```
  PASS  ★ [渲染·门禁] pass_model_self_authored：pass · 来源=model · 独立=false
  PASS  ★ [渲染·门禁] fail_verify_failed：fail · 来源=caller · 独立=true
  PASS  ★ [渲染·门禁] abstain_no_criterion：abstain · 来源=空 · 独立=false
  PASS  ★ [渲染·门禁] invalid_criterion_broken：invalid · 来源=model · 独立=false
  PASS  ★ [渲染·门禁] 后端**没给**独立性 → 徽标显示「未给（判不了）」，**不是**"非独立"
```

### 4.4 P4 · 拆解合规审查

```powershell
# 夹具的输入是**真实那次拆分**（run_20260927_230240_0a42df：19 任务 / 2 交付物）
cd frontend; node scripts/replay-check.mjs        # [P4] 段
```

实测：

```
  输入：{"tasks":19,"files":2}
  passed=false independent=false checked_by=tool
  violated(5) = ["P3","P4","P6","P7","P8"]
  undecidable(2) = ["P2","P5"]
    P2 [undecidable] 当前拆解形态没有**逐叶判据**（只有 cycle 级一条）…
    P5 [undecidable] 拆解里没有给出『根目标的明确要求』清单 …
    P7 [violated] 叶子数 19 超过上限 12
  PASS  ★ violated 与 undecidable **同时存在**（这样才能验"两者分开显示"）   5/2
  PASS  ★ `undecidable` 非空时 `passed=false`（后端自己就不把它算通过）
  PASS  ★ [渲染] 「违反」与「判不了」分成两块（措辞不同、不混）
  PASS  ★ [渲染] **不出现**"全部通过"（`passed=false` 时更不许）
  PASS  ★ [渲染] 逐条原则里 P2/P5（判不了）与 P3/P7（违反）都在
  PASS  ★ [渲染] 后端未产出时显示「尚未产出」而不是"审查通过"
```

### 4.5 门禁与全量

```powershell
python tests/run_unit.py                          # 自带副本
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"; python tests/run_unit.py
python scripts/doctor.py                          # 两种配置
python scripts/layout.py --check
python scripts/fix_bom.py                         # 改完 .ps1 必跑
```

实测：

| 检查 | 自带副本 | 真上游 |
|---|---|---|
| 离线全量 `tests/run_unit.py` | **37/37 文件，exit 0** | **37/37 文件，exit 0** |
| `test_event_contract.py` | 21/21 | 30/30 |
| `test_partition.py` | 55/55 | 60/60 |
| `test_audit.py` | 107/107 | 107/107 |
| `test_spec.py` | 42/42 | 43/43 |
| `test_transparency_ui.py` | 65/65 | —— |
| `test_dist_freshness.py` | 6/6 | —— |
| `scripts/doctor.py` | 失败 **0** 项（WARN 10 提示） | 失败 **0** 项（WARN 6 提示） |
| `scripts/layout.py --check` | exit 0 | —— |
| `scripts/fix_bom.py` + `test_ps1_encoding.py` | 12/12 | —— |

### 4.6 未验证的部分

- **浏览器里的滚动行为**：见 §4.2 结尾。**这是本轮最大的未验项**，
  而验收方明确说会"打开界面"看 —— 所以我不把它写成已完成。
- **`decompose_review` 的真实事件**：上游**已声明、尚未发出**
  （`core/contract.py:207` 有 EventSpec，全仓 `_emit("decompose_review"…)` 一处都没有）。
  所以 P4 走的是**报告那条路**（`run.decompose_review`），事件路径只在合成事件上验过。
- **`reuse` 的真实事件**：上游**在发**（`core/coding_cycle.py:507`），但那两次验收运行
  早于它（事件流里没有）。所以我用**合成事件**验渲染，用**真函数**（`check_workspace()`）
  验"没有发现时是什么样"。**没有一条真实运行带过它。**
- **`verdict` 落进真实运行的报告**：`core/outcome.py` 已交付，但那两次验收运行的
  `meta.json.report` 里**没有** `outcome`/`verdict` 键（它们是更早的后端产出的）。
  所以四值的证据是"**后端的判定函数 + 我的呈现**"，**不是**"某次真实运行的四值"。
- **`run_end` 带 verdict 那条路**：改动在 `bridge/runner.py`，本轮**没有真跑一次运行**去产生
  带 verdict 的 `run_end`（需要模型）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **否** | 不新增、不改名 |
| 事件 payload 键 | **加了（additive）** | `run_end` 新增 `outcome` / `outcome_kind` / `outcome_reason` / `criterion_source` / `criterion_trust` / `criterion_independent` / `outcome_note`（`bridge/runner.py`）。**只在报告里有 verdict 时才带**，缺席时不补默认值 |
| 上游 `PHASE_ORDER` 阶段 | 否 | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | 否（**只读**） | 前端读 `report.verdict` / `report.decompose_review` / `report.reuse_checks` |
| `TOOLS_MAP` 条目结构 | 否 | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | 否 | — |
| 端点路径 | 否 | 复用了既有的 `GET /api/runs/{id}`（运行详情里本来就有 `report`） |
| `.interface_contract/` 覆盖的规则与词表 | 否 | 镜像未改（与主本 SHA256 仍一致） |

**另外两处显式声明**：

1. `/api/spec` 的 `events` 新增两条标定：`reuse`、`decompose_review`
   （不标定，真上游下 `uncalibrated_events` 非空 —— 实测过）。**additive**。
2. `/api/spec` 的 `diagnostics.contract_lag` 内容换了：
   第一批（`orchestrator_round`/`verify_criterion`/`self_report`）**已到期删除**（契约 v1.0.25 声明了），
   现在是第二批（`reuse`/`decompose_review`）。

---

## 6. 对另一侧的影响（对应 C6、C7）

### 6.1 另一侧需要跟着改吗？

**要两处小的**（都不阻塞我这一侧）：

1. **`decompose_review` 已声明、尚未发出**：契约里 `since="1.3"` 有它，
   报告键 `FROZEN_REPORT_KEYS` 里也有 `decompose_review`，但
   `core/coding_cycle.py` 里**没有对应的 `_emit`**。后果：
   - 我的界面**能显示**（走报告那条路，夹具已用后端真函数验过渲染）；
   - 但 `/api/audit` 会报 `U-dead-event`（"声明了但代码从不发"）—— **那条报得对**。

   **两处位置写全（按 C1 的"文件:行"要求）**：
   - **声明在**：`D:\PythonProject\SimpleAgent2_Cycle\core\contract.py:207-216`
     （`EventSpec("decompose_review", …)`，`since="1.3"`）+ 报告键 `core/contract.py:228`；
   - **发出点没有**：`D:\PythonProject\SimpleAgent2_Cycle\core\coding_cycle.py`
     —— 同目录对照，`reuse` 是在 `:507` 发出的，而 `decompose_review` 全文件无 `_emit`。
2. **契约主本仍落后于上游一个批次**：`reuse` / `decompose_review` 都是 `since="1.3"`，
   主本 v1.0.25 里没有。我按既有机制登记（`CONTRACT_LAG_KINDS`）并**显示出来**
   （`/api/spec` 的 `diagnostics.contract_lag`），**没有擅改主本**。

### 6.2 有没有可能"问题被平移到对侧"？

一处，**我点名而不推过去**：`decompose_review` 的 EventSpec 与报告键都在，
**发出点不在** —— 这是后端侧要补的一行 `_emit`，不是前端显示问题。
我这一侧已经把"未产出"这一态显示清楚（不画绿色、不说"通过"），
所以**不会**因为后端没发就被读成"审查通过"。

### 6.3 前端会静默少显示什么吗？

- 认不出的事件仍然**降级显示**（时间线一行 + 标定 label/tone），不报错。
- 两个新事件已标定 + 认下，不会退化成裸文本行。
- **报告拿不到时**（`GET /api/runs/{id}` 失败）：只少一块明细，主流程照旧 ——
  `store.ingestReportInfo(null)` 是 no-op，**不会**把已有的 verdict 擦掉。

---

## 7. 不做的部分及理由（对应 C7）

1. **不验浏览器里的滚动**：没有浏览器自动化，装了就是新增一整套工具链与不确定性。
   我把它明确列进 §4.6，并让**样式契约**与**分组结果**可机械验证 —— 这是能诚实做到的上限。
2. **不手写 verdict / decompose_review 夹具**：那样只能证明"我的模板会渲染它"，
   证明不了"后端真会产出这个形状"。所以夹具走**后端真函数**
   （`build_verdict` / `review_decomposition` / `check_workspace`）。
3. **不替后端补 `decompose_review` 的发出**：`bridge/` 是我的，`core/` 不是。
4. **不把 `criterion_independent` 的 `null` 显示成 `false`**：见 §4.3。
5. **不动 `.interface_contract/`**：镜像未改。
6. **不为省事把 `reuse` 的合成事件说成真实事件**：§4.6 里写明了它是合成的。

---

## 8. 回退点（对应 C8）

- **回退命令**：

  ```powershell
  .\scripts\backup.ps1 -List
  .\scripts\backup.ps1 -Restore -From 20260928-091633_v18-hooks-passthrough
  ```

  文件级（例如只想退掉任务面板）：

  ```powershell
  .\scripts\backup.ps1 -Restore -From 20260928-091633_v18-hooks-passthrough `
      -Path frontend/src/components/TaskPanel.vue,frontend/src/store/tasklist.ts
  ```

- **回退会丢什么**：本轮的 P1–P4 全部改动（新鲜度工具与门禁、任务面板、四值呈现、
  拆解合规 tab、`run_end` 的附加字段、两条新标定、伴随的文档）。**全部是加性**：
  回退后界面回到"任务挤成一团、结局只有一个笼统状态"的状态，
  **不影响任何既有功能**，也不会让接口契约失效。
- **回退后必须重建 dist 并复核**：

  ```powershell
  cd frontend; npm run build
  cd ..; python scripts/freshness.py
  ```

  （回退源码却不重建 dist，就正好复现本轮 P1 的那个坑。）

---

## 9. 自检结论

| # | 标准 | 结论 |
|---|---|---|
| **C1** | 问题陈述可复现 | **满足**。P1 给两个**时间点**（13:43:17 / 13:43:42）；P2 给真实任务数（14/19）；P3/P4 各给夹具来源与命令 |
| **C2** | 每条主张带可复现验证命令 | **满足**。§4 每个主张先给命令再给实测输出 |
| **C3** | 命令实测输出支持该主张 | **满足**。输出为原文粘贴（`state=ok`、负向 `exit=1`、`108/108`、`6/6`） |
| **C4** | 改动清单与实际一致 | **满足**。§3 以 `backup.ps1 -Verify` 的机械输出为权威，手写表只作导读 |
| **C5** | 对接口契约的影响已声明 | **满足**。§5 逐项；改动的三处（`run_end` 附加字段、两条标定、滞后表内容）都显式声明且说明是 additive |
| **C6** | 对另一侧的影响已评估 | **满足**。§6：`decompose_review` 缺 `_emit`、契约主本落后一批次 |
| **C7** | 未把接口级问题当内部问题处理 | **满足**。§6.2 点名"缺发出点"归后端；§7 列出不做的六件事与理由，包括"不手写夹具" |
| **C8** | 回退点明确 | **满足**。§8 给整仓与文件级命令，并写明**回退后必须重建 dist**（否则复现本轮的坑） |

**我希望统筹重点验证哪一条**：**P1 与 P2**。

- **P1** 是**已经造成事实损害**的那一条（用户看的不是交付的那一版）。
  我用三条命令（检查器 / 门禁 / 备份 preflight）把它钉住了，但**请你自己重建复核**，
  并确认哈希与 §4.1 一致。
- **P2** 的验收条件是"打开界面看"，而我**只能验到"分组与样式契约"**（§4.2 结尾）。
  所以**浏览器里的那一眼以你为准**；如果滚动或跟随在真机上有问题，
  **请直接说"P2 不成立"**，我会按现象改，而不是拿机械断言顶过去。

---

## 10. 追加项 `P5`（🔴 阻塞）：挂钩包装器**镜像签名** —— 已修

> 这一项是在 P1–P4 交付之后由 `DISPATCH.md` 追加的。**它与前面几项独立**，
> 单独立节，自查同样按 C1–C8。

### 10.1 问题陈述与复现（对应 C1）

**现象（统筹方给的原文）**：

```
TypeError: install.<locals>._run_verify() takes 2 positional arguments but 3 were given
```

**三个位置（全写出来，按 C1 的"文件:行"要求）**：

| 侧 | 位置 | 形态 |
|---|---|---|
| 上游（新增可选参数） | `D:\PythonProject\SimpleAgent2_Cycle\core\pipeline.py:361` | `async def run_verify(self, command: VerifyCommand, files: list[str] \| None = None) -> dict` |
| 上游（改成两个位置参数调用） | `D:\PythonProject\SimpleAgent2_Cycle\core\orchestrator.py:246` | `vr = await self.pipeline.run_verify(vc, files)` |
| 我们（镜像了旧签名） | `bridge/hooks.py:392`（旧） | `async def _run_verify(self, command):` |

**后果**：每一次运行在 ~6 秒内失败，**验证整条链停摆**。
**而我们的全量单测是绿的** —— 因为这个包装器不在测试范围内。
（统筹方的原话：「与 D7 同一类」。）

**复现命令**（离线，不需要模型）：

```powershell
python tests/unit/test_hook_compat.py
```

### 10.2 根因：D9 的教训**只学到了一处**

D9 那次是 `_emit` 包装器**镜像签名**导致撞名（`got multiple values for argument 'kind'`），
修法是"用 `inspect.signature` 向上游要签名"。
**那个教训写进了注释，却没有推广到另外九个挂钩点。**

**审计结果：11 个挂钩点，9 个是镜像的**（清单见 `docs/CHANGELOG.md` §34.1）。
这不是"漏了一处"，而是**同一类问题在同一个文件里有九份副本** ——
所以修法不是"把 `_run_verify` 改一下"，而是**让镜像再也写不出来**。

### 10.3 改动（对应 C4）

| # | 文件 | 为什么改 |
|---|---|---|
| 1 | `bridge/hooks.py` | 新增 `HOOK_POINTS`（**唯一名单**）+ `bind_arguments` / `make_sync_hook` / `make_async_hook` / `make_hook`；`install()` 改为**按名单遍历**，不再逐个手写赋值 |
| 2 | `tests/unit/test_hook_compat.py` | **新**：逐个挂钩点断言"接得住上游签名（含多加一个可选参数）"，含**负向** |
| 3 | `tests/diagnostics/hook_verify_e2e.py` | **新**：真跑一次流程并**走到 verify**（离线，worker 换桩） |
| 4 | `tests/unit/test_event_contract.py` | `[4]` 组从**文本断言**改成**读名单 + 读实际安装结果**（旧写法补不上新挂钩点） |
| 5 | `tests/unit/test_hooks_passthrough.py` | 断言改成新的安装形态（`make_emit_wrapper(orig)`），不变量不变 |
| 6 | `bridge/partition.py` | 契约 v1.0.26 又声明了 `reuse`/`decompose_review` → 滞后表**第二次到期清空**，回退表升到 18/39 |

**四条纪律（每条都是被真实事故逼出来的）**：

1. 包装器**不镜像签名**：就是 `(*args, **kwargs)`，原样 `orig(*args, **kwargs)`；
2. **同步/异步问上游**（`inspect.iscoroutinefunction(orig)`）—— 手写这个判断就是又一份镜像；
3. **刻意不用 `functools.wraps`**：它把 `__wrapped__` 指回原方法，于是
   `inspect.signature(包装器)` 会**报告上游签名**（看着像镜像），而实际能力是"什么都收"。
   统筹方的 `hook-compat.py` 按签名判断兼容性时，**看到的必须是真相**；
4. `install()` 按名单遍历 —— 手写十处 = 十份会漂的镜像。

### 10.4 验证（对应 C2、C3）

```powershell
python tests/unit/test_hook_compat.py                                  # 自带副本
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"; python tests/unit/test_hook_compat.py
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"; python tests/diagnostics/hook_verify_e2e.py
```

实测：

| 检查 | 自带副本 | 真上游 |
|---|---|---|
| `test_hook_compat.py` | **18/18** | **21/21** |
| `hook_verify_e2e.py` | 2/2 + SKIP（旧副本接线本来就到不了 verify） | **7/7** |

真上游下的关键输出（**这就是"真的跑一次任务能走到 verify"**）：

```
  当前生效上游 run_verify 的位置参数：['command', 'files']（v1.23 形态，含 files）
  PASS  ★ 所有包装器都不是镜像签名（签名 = `*args, **kwargs`）   []
  PASS  ★ 所有包装器都接得住上游参数，**并且多加一个可选参数也接得住**
  PASS  ★ 同步/异步与上游一致（从上游读，不手写）   []
  PASS  ★ 所有挂钩点都是工厂造的（没有手写的镜像包装器）   []
  PASS  ★★ P5 复现：上游的**两个位置参数**形态不再抛 TypeError   None
  PASS  ★★ 且真的走到了验证（`verify_probe` 发出来了）   ['verify_probe']

  本轮真跑到的挂钩点：8/8
  PASS  ★ 跑完没有异常（P5 形态会让它在 ~6 秒内抛 TypeError）   None
  PASS  ★ 走到了验证：发出 `verify_probe`
  PASS  ★ 验证真的执行了（`passed=true`）
  PASS  ★ 事件链完整：run_start → verify_probe → verify → cycle_end   []
  PASS  ★ `verify_probe` 带命令原文（前端判据演化要显示它）   import math_utils
  PASS  ★ 最终 phase 是 `record`（走完了 VERIFY 才可能到 RECORD）   record
通过 7/7
```

**负向（证明判据不是永远绿）**：

```
  PASS  ★ 负向：镜像签名不会被误判成透传   ['self', 'command']
  PASS  ★ 负向：镜像签名**接不住**多加的那个参数（正是上游 v1.23 的形态）
```

### 10.5 未验证的部分（P5）

- **`hook_verify_e2e.py` 里 `Worker.run` / `LLMClient.chat` / `Worker._invoke` 三个挂钩点没有被真跑触发**
  —— 因为 harness 把 worker 换成了桩（那是唯一需要模型的部分）。
  **它们的签名兼容性由 `test_hook_compat.py` 的 [2]/[3] 覆盖**（按上游真实签名 + 多加一个参数），
  但"在这三个点上真的跑一轮"**没有验**。要验需要给 `LLMClient` 起一个假 HTTP 端点。
- **没有用统筹方的 `hook-compat.py` 自己跑过**：我没有那个脚本的执行入口
  （它在 `03-scripts/`，我按你给的路径读过它的判据思路）。
  **请以你的那一次为准**；如果它报红，请把输出贴回来，我按它改。
- **自带旧副本配置下"走到 verify"是 SKIP**（那份副本的接线在 `FIX-VERIFY-WIRING` 之前）——
  这是如实分流，不是把失败写成跳过。

### 10.6 对接口契约的影响（P5，对应 C5）

| 事实面 | 是否改动 |
|---|---|
| 事件 `kind` / payload 键 | **否**（事件一个没变；`emit_progress` 调用点全部照旧） |
| 端点 / 阶段 / `TOOLS_MAP` / `CONTRACT_VERSION` | 否 |
| `bridge/hooks.py` 的**内部形态** | 改了（工厂 + 名单），但**它不是契约面** |
| `.interface_contract/` | 未改 |

**唯一"看得见"的变化**：`hooks.install()` 返回的 dict 多了 `points` 字段
（`{"installed": [...], "skipped": [...], "points": 11}`）—— **additive**，仅供自审查/测试读。

### 10.7 另一侧的影响（P5，对应 C6、C7）

- **上游不需要改**：上游那次变更是**加性且向后兼容**的（他们 39 个单测全过）。
  是**我们的镜像**收不下 —— 责任在我这一侧，已修。
- **有没有把问题平移**：没有。修法是"我们不再镜像签名"，
  而不是"要求上游别加参数"（那会让上游每一次加性变更都变成一次协同）。
- **还有没有同类隐患**：`HOOK_POINTS` 之外的挂钩点**没有**（名单就是全集，测试逐个查）；
  但**下一批上游加性变更仍可能触发** —— 现在它会在 `test_hook_compat.py` 的 [3] 上**立刻红**，
  而不是等到用户跑了六秒才发现。

### 10.8 回退点（P5，对应 C8）

与 §8 同一处快照（`v18-hooks-passthrough`）。回退只影响 `bridge/hooks.py` 的安装形态
与两个测试：**回退即恢复 P5 那个 bug**（第一次运行就炸），所以**不建议单独回退这一项**。

### 10.9 P5 自检结论

| # | 标准 | 结论 |
|---|---|---|
| C1 | 问题可复现 | **满足**：三个位置全写出来（上游两处 + 我们一处）；`test_hook_compat.py` 离线复现 |
| C2 | 每条主张带命令 | **满足** |
| C3 | 输出支持主张 | **满足**：真上游 21/21 + 7/7；负向 2 条 |
| C4 | 改动清单一致 | **满足**：§10.3 + §3 的机械输出 |
| C5 | 契约影响已声明 | **满足**：§10.6（契约面未动，唯一 additive 是 `install()` 返回值多一个 `points`） |
| C6 | 另一侧影响已评估 | **满足**：§10.7（上游无需改；责任在我侧） |
| C7 | 未把接口级问题当内部问题处理 | **满足**：这是**纯内部实现问题**（我们镜像了别人的签名），没有平移 |
| C8 | 回退点明确 | **满足**：§10.8（并说明"单独回退本项会恢复那个 bug"） |
