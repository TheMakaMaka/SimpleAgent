# 变更评估文档 · `OUTPUT-CONTRACT`（P14 + P15 + P13 + P11）

- **变更编号**：`OUTPUT-CONTRACT`（工作单 **P14 / P15 / P13 / P11**，D35 / D36 / D37 家族）
- **提出方**：用户（2026-10-03 实跑反馈）+ 用户裁决（A9② / P11 已批准）
- **执行侧**：backend
- **日期**：2026-10-03
- **契约版本**：`1.0.32`（`runtime_paths_and_output_contract`）· `1.0.31`（`criterion_ownership`）
- **本轮 round_id**：`R-8b28b25a1f` —— **本轮完成 `R-8b28b25a1f`**（下一轮据此判断要不要开工）

---

## 1. 变更意图

用户 2026-10-03 实跑真实任务后的原话（逐字，来自工作单 P14/P15）：

> 「1. **没有明确文件输出路径和输出成果**，2. **缺少引入代码工作区的路径**」

同日的两条新需求/裁决：

> **P13**（用户裁决 A9②）：「只有判据出自 `caller` 时，`criterion-broken` 才允许记 `invalid`；
> **模型自拟的坏判据记 `fail`**。」

> **P11**（用户新需求 + 已批准）：「现在 agent 还不支持理解整个项目代码的能力，这个也要做一下，
> 我的思路就是用**工具做结构梳理**，然后**子模型做细节读取**。」
> —— 用户已裁决：**先只做 P11**（P12 等地图可信再上）。

另附统筹方低优先级 **D30**（文档里写死的计数漂移）。

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-8b28b25a1f` 开工，
> 与仓库里上一轮记录的 `R-4fb8a623b8`（`docs/EVALUATION-ENVELOPE-WIRING.md`）不同 ⇒ 有新指令。
> 所有结论均以仓库里的机器事实为准（`git diff --stat`、测试退出码、探针回显），不是印象。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（每条带 `文件:行`）

| # | 缺陷 | 位置 / 机械依据 |
|---|---|---|
| 1 | `/profile` 里**根本没有 `runtime` 段** ⇒ 调用方不知道交付物在哪 | `GET /profile`（`main.py` 旧版顶层键只有 `checkpoint_backend/code/contract/…`） |
| 2 | 写入只锚在一个**字面量相对前缀**上 | `tools/files.py:17` `_WORKSPACE_PREFIX = "workspace/"` |
| 3 | 搜不到任何「目标项目根」入口（`doc_access.project_root()` 是**上游自己的文档根**） | `core/doc_access.py` 的 `project_root()` |
| 4 | verify 失败**只对判据正文跑 `check_code`，不看 `report.verify["source"]`** ⇒ 模型自拟的坏判据也记 `invalid` | `core/coding_cycle.py:615-635`（`source` 在同函数上文 `:591` 已就绪） |
| 5 | 结构视图只回一句「只列前 N 个」，非 `.py` 与解析失败**一字不提**，而 `totals` 是全量 | `tools/arch.py` 旧 `get_architecture`；`core/symbol_index.py` 旧 `build_index` |

### 2.2 复现命令与实测输出

**修复前的 `/profile` 顶层键**（用 AST 从 `HEAD` 的 `main.py` 里把 `profile()` 的
返回字典键取出来，避免"肉眼数"）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import ast,subprocess;src=subprocess.run(['git','-c','safe.directory=D:/PythonProject/SimpleAgent2_Cycle','show','HEAD:main.py'],capture_output=True,text=True,encoding='utf-8').stdout;t=ast.parse(src);print([k.value for k in [n for f in t.body if isinstance(f,ast.AsyncFunctionDef) and f.name=='profile' for n in ast.walk(f) if isinstance(n,ast.Return) and isinstance(n.value,ast.Dict)][0].value.keys if isinstance(k,ast.Constant)])"
```

```
['code', 'checkpoint_backend', 'decision_channel', 'roles', 'vision', 'contract', 'models']
```

⇒ **没有 `runtime`**（这正是 P14 的取证）。修复后见 §4.1。

**修复前的 verify 失败分支**（同一份 `HEAD` 源码）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import subprocess;s=subprocess.run(['git','-c','safe.directory=D:/PythonProject/SimpleAgent2_Cycle','show','HEAD:core/coding_cycle.py'],capture_output=True,text=True,encoding='utf-8').stdout;i=s.find('if not report.verify');seg=s[i:i+1400];print(seg[:660]);print('reads report.verify[source]:', 'report.verify.get' in seg and 'source' in seg)"
```

```
if not report.verify["passed"]:
                # ★ P1：**判据自己坏了 ≠ 模型没做到**。
                # 优先看判据的符号引用是否真实存在（"调用了不存在的符号"是
                # 实测那两次失败的直接原因 —— 它们应该记成 `invalid`，
                # 否则能力画像里会把"判据写错"算成"模型不行"）。
                from .outcome import classify_verify_detail
                from .reuse_checks import BLOCKING_KINDS, check_code

                crit_kind, crit_why = "verify-failed", ""
                cmd = str(report.verify.get("command") or "")
                crit_violations, _refs = (check_code(cmd, label="<判据>")
                                          if cmd else ([], set()))
                blocking = [v for v in crit_violatio
reads report.verify[source]: False
```

⇒ 该分支**只对判据正文跑 `check_code`**，`source` 一次都没读 —— 这就是 P13 的根因。

**为什么这是问题**：没有 `runtime`，调用方**无法核对"有没有产出、产出了什么"**；
没有目标项目根，面对已有代码库**无处落脚**；不看 `source` 会让"尺子坏了"与
"模型没做到"混在一起，**冲淡能力画像**；结构地图不报覆盖率，模型会把
「我没查」读成「不存在」。

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

`git diff --stat`（**不含**未跟踪的新文件）：

```powershell
$ git -c safe.directory=D:/PythonProject/SimpleAgent2_Cycle diff --stat
 .env.example                             |  19 +++
 .gitignore                               |   4 +
 CYCLE.md                                 |   2 +-
 README.md                                |  14 +-
 core/coding_cycle.py                     | 128 ++++++++++++--
 core/contract.py                         |   2 +
 core/cycle.py                            |   8 +
 core/pipeline.py                         |  71 ++++++--
 core/symbol_index.py                     | 210 +++++++++++++++++++++++
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  75 +++++++++
 docs/EVALUATION-TRANSPARENCY2-BACKEND.md |   8 +
 docs/FRONTEND_CONTRACT.md                |  16 ++
 docs/MODULES.md                          | 280 ++++++++++++++++++++-----------
 docs/OPERATIONS.md                       | 130 ++++++++------
 docs/PENDING_DECISIONS.md                |  31 ++++
 main.py                                  |  49 +++++-
 tests/README.md                          |   5 +
 tests/unit/test_doc_consistency.py       |   6 +-
 tests/unit/test_outcome.py               |  39 ++++-
 tools/arch.py                            | 257 +++++++++++++++++++++++-----
 tools/code_checks.py                     |  23 ++-
 tools/files.py                           |  84 ++++++----
 tools/verify.py                          |  24 ++-
 24 files changed, 1216 insertions(+), 271 deletions(-)
```

新增文件（`git diff --stat` 不含未跟踪文件）：

```
core/runtime.py                              ← 三个根 + 任务级目标项目根 + 交付物对账
tests/unit/test_project_root.py              ← P15 门禁（32 项）
tests/unit/test_deliverables.py              ← P14 门禁（15 项）
tests/unit/test_criterion_ownership.py       ← P13 门禁（13 项）
tests/unit/test_arch_map.py                  ← P11 门禁（16 项）
tests/diagnostics/probe_output_and_map.py    ← 五段机械取证（21 项）
docs/EVALUATION-OUTPUT-CONTRACT.md           ← 本评估文档
```

`docs/VERSIONS.md` **不在**上面的 `diff --stat` 里 —— 它由 `tests/backup.py` 在提交
**之后**追加 v1.27 记录、再 amend 进同一提交（备份机制的固有行为）。
所以以**备份点** `git show --stat <v1.27 提交>` 为准，它比 §3.1 多一个 `docs/VERSIONS.md`。

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/runtime.py`（新） | 全文件 | 三个绝对根 + `ContextVar` 任务级目标根 + `ScopeError` 结构化拒绝 + `check_deliverables` |
| 2 | `core/symbol_index.py` | `build_index_report` / `freshness_of` / `reverse_index` / `SKIP_REASONS` | P11 覆盖率账目 + 新鲜度 + 反向索引（**加性**，`build_index` 未改） |
| 3 | `tools/arch.py` | `_report` / `_coverage_out` / `_scope_out` / 三个工具 | 视图带覆盖率/新鲜度/范围/反向索引；根改走 `runtime.effective_root()` |
| 4 | `tools/files.py` | `read_file` / `write_file` | 根改走 `runtime`；越界 ⇒ 结构化拒绝；`outputs/` 前缀 → 输出根 |
| 5 | `tools/code_checks.py` | `list_workspace` | 根改走 `runtime`；返回加 `root` / `scope` |
| 6 | `tools/verify.py` | `_run_sync` / `_clean_env` | cwd / PYTHONPATH 改走 `effective_root()`；临时脚本仍放工作区根的 `_tmp/` |
| 7 | `core/pipeline.py` | `run_manifest` / `run_check` / `artifact_hashes` / `run_verify` / `_purge_pycache` | 取根改走 `runtime`；`outputs/` 标签经 `resolve_write` 还原；**只清工作区根的 pycache**（三方隔离） |
| 8 | `core/coding_cycle.py` | `run` 包装 + `_run_cycle` + **P13 分支** + 交付物对账 | 任务级 `project_root` 作用域；交付物 gate；归因读 `source` |
| 9 | `core/cycle.py` / `core/contract.py` | `deliverables` 字段 + `FROZEN_REPORT_KEYS` | 运行记录回报实际产物（**加性**） |
| 10 | `main.py` | `/profile` 的 `runtime`；`/encode` `/run` 的 `project_root` / `deliverables` | 接口面暴露（**加性**） |
| 11 | `tests/unit/test_outcome.py` | `[2]` 改判 + 新增 `[2b]` | P13 是**规则变更**：旧的"模型自拟坏判据 ⇒ invalid"断言必须改成 `fail`，并把 caller 的 `invalid` 补回来 |
| 12 | `tests/unit/test_doc_consistency.py` | `RUNTIME_DIRS` | `outputs/` 是运行期目录（与 `workspace`/`sessions` 同类），加入排除集 |
| 13 | `docs/EVALUATION-TRANSPARENCY2-BACKEND.md` | §9 C5 之后 | **D30 勘误注**（「事件 16 → 19」实测 18；历史条目只加注不重排） |
| 14 | 文档面 | CHANGELOG §41 / MODULES §10·§17·§19·§32 / OPERATIONS §4.22·§6.2 / README / FRONTEND_CONTRACT §4.2 / PENDING_DECISIONS C15–C17 / tests/README / `.env.example` / `.gitignore` / 5 处版本戳 | 声明与实现同步 |

### 3.3 若两者不一致，差异是什么

> **★ C4 勘误（v1.27.1 追加）**：§3.1 的 `git diff --stat` 是**提交前**快照
> （只覆盖当时已跟踪的文件），与备份点 `git show --stat cd1891b` 有**三处**差异，
> 以**备份点为准**：
>
> 1. `.gitignore` 实际 **6 行**（快照时 4 行）：快照之后又加了 `.tmp/` 的两行
>    —— 角色简报要求临时产物放 `.tmp/`，所以顺手把它也挡在版本库外；
> 2. `docs/MODULES.md` 实际 **282 行**（快照时 280 行）：快照之后才把该文件的
>    版本戳从 §40 改成 §41（`test_doc_consistency` 当场抓到，见下）；
> 3. 统计口径：§3.1 是 `git diff --stat`（**24 个已跟踪文件**，不含新增文件与
>    本评估文档）；备份点 `git show --stat cd1891b` 是**32 个文件**
>    （含 `core/runtime.py`、四个新单测、探针、本评估文档与 `docs/VERSIONS.md`）。
>
> **这正是 C4 的意义**：交出去核对的数字必须对；数字对不上时**以机械输出为准**，
> 并**明写差异**，而不是回去改机械输出。

1. **`docs/VERSIONS.md` 不在 `diff --stat` 里** —— 备份机制在提交后追加再 amend（§3.1）。
2. **`tools/arch.py` / `tools/files.py` 的 diff 偏大**：两者是 CRLF 文件，
   本轮写回时先变成 LF，`test_doc_invariants` 第 9 组（行尾门禁）**当场抓到**，
   已用一次性脚本按 git 索引逐文件还原（修复脚本在 `.tmp/`，**不进提交**）。
   最终 `git ls-files --eol` 与索引一致 —— 这正是那条门禁存在的意义。
3. **`.tmp/` 是本轮临时件**（`fix_eol.py`、`head_probe.py` 与冒烟脚本目录），
   **不进提交、已删除**；本轮同时把 `.tmp/` 加进 `.gitignore`（上一条勘误第 1 点）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | ★ `/profile.runtime` 给出三个**绝对路径且都存在**，工作区根与输出根**分开** | `tests/unit/test_project_root.py` §[1] | `PASS` × 9 |
| 2 | ★ 任务级 `project_root` 设了之后**扫到的集合随之改变** | 同上 §[3]；`tests/diagnostics/probe_output_and_map.py` §[2] | root/文件集合都变；`scope.source=project_root` |
| 3 | ★ 与 `AGENT_BACKEND_DIR` **语义分离**（同值/异值两向都判） | `tests/unit/test_project_root.py` §[2] | `distinct_from_backend_dir` True / False |
| 4 | ★ 越界写 ⇒ **结构化拒绝**（`out-of-scope-write`），且**文件真的没写出去** | 同上 §[4]；探针 §[3] | `ok=false` + `allowed_roots`；`os.path.exists==False` |
| 5 | ★ 声明的交付物**不存在 ⇒ 不合格**（结构化 `deliverable-missing`） | `tests/unit/test_deliverables.py` §[2] | `outcome=fail` / `outcome_kind=delivery-gap` |
| 6 | ★ 反空洞：**删掉产物后 pass 翻成 fail** | 同上 §[4] | `passed: True → False` |
| 7 | ★ 没有声明也回报**实际产物** `{path, sha256, size}` | 同上 §[5] | `actual=[(…, True, 19)]` |
| 8 | ★ 模型自拟坏判据 ⇒ `fail`；caller 坏判据 ⇒ `invalid`（**两向都在红**） | `tests/unit/test_criterion_ownership.py` | 13/13 |
| 9 | ★ 结局四值回归（含新增 `[2b]` caller→invalid） | `tests/unit/test_outcome.py` | 20/20 |
| 10 | ★ 解析失败**逐条**进 `skipped`，修好**移回 `indexed`**；超 `limit` 逐条进 `truncated_items` | `tests/unit/test_arch_map.py` §[1]/§[5] | 16/16 |
| 11 | ★ 新鲜度：改内容 ⇒ 哈希变 | 同上 §[4] | 两个 sha256 不同 |
| 12 | 五段机械取证（三个根 / 换根 / 越界 / 交付物 / 覆盖率） | `tests/diagnostics/probe_output_and_map.py` | 21/21，末行 ★ |
| 13 | 全量单测无回归 | `tests/run_unit.py` | 见 §4.1 |
| 14 | 文档一致性 / 不变量 / 审查 / 契约符合性 / 前端契约 | `test_doc_consistency` / `test_doc_invariants` / `test_doc_review` / `test_contract_conformance` / `test_frontend_contract` | 全 PASS（数字见 §4.1） |

### 4.1 实测输出（粘贴原文）

**★ 探针五段（节选关键行，完整 21/21）：**

```
[1] P14/P15：/profile.runtime 的三个根 + 目标项目根（与 AGENT_BACKEND_DIR 分离）
  runtime_root     = D:\PythonProject\SimpleAgent2_Cycle  exists=True
  workspace_root   = D:\PythonProject\SimpleAgent2_Cycle\workspace  exists=True
  output_root      = D:\PythonProject\SimpleAgent2_Cycle\outputs  exists=True
  effective_root   = D:\PythonProject\SimpleAgent2_Cycle\workspace (source=workspace_root)
  project_root.active      = D:\PythonProject\SimpleAgent2_Cycle
  project_root.lifetime    = per-task
  AGENT_BACKEND_DIR        = D:\PythonProject\SimpleAgent2_Cycle\workspace
  distinct_from_backend_dir= True
[2] P15：换根后扫到的集合随之改变（用仓库自己的 core/ 当目标根对真值）
  未设 root：root=D:\PythonProject\SimpleAgent2_Cycle\workspace files=0
  设 root  ：root=D:\PythonProject\SimpleAgent2_Cycle\core files=35
  get_architecture scope=D:\PythonProject\SimpleAgent2_Cycle\core source=project_root indexed=35
[3] P15：越界写 ⇒ 结构化拒绝（且文件真的没写出去）
  越界写返回: {"ok": false, "kind": "error", "tool": "write_file", "error":
    {"code": "out-of-scope-write", "message": "写路径越出目标根: …",
     "allowed_roots": [...]}}
  越界目标**没有被写出去**：PASS
[4] P14：声明的交付物必须存在且哈希一致（实际产物 {path,sha256,size}）
  存在  ⇒ passed=True actual=[{'path': 'outputs/report.txt', 'exists': True,
          'sha256': '52f979fdc5b55dce…', 'size': 13, 'root': 'output_root'}]
  不存在⇒ passed=False violations=['deliverable-missing']
[5] P11：覆盖率账目（解析失败/非 .py/超 limit **逐条**留痕）+ 新鲜度
  scanned=4 indexed=2 skipped=2 truncated=1 skipped_dirs=0
  by_reason={'parse-failed': 1, 'non-python': 1, 'over-limit': 1}
    - broken.py :: parse-failed :: SyntaxError: invalid syntax (line 1)
    - notes.md :: non-python :: 扩展名 .md 不在本工具支持范围
    - world.py :: over-limit :: 已解析但超出本次返回上限 limit=1（共 2 个）
  reverse_index={'good': ['world.py']}
★ 全部通过：三个根 · 任务级目标根 · 越界结构化拒绝 · 交付物对账 · 可信结构地图
通过 21/21
```

**★ P13 双向（`test_criterion_ownership.py` 节选）：**

```
[1] 模型自拟判据 + 引用未交付符号 ⇒ fail / delivery-gap
  outcome=fail kind=delivery-gap
  error=验证未通过: NameError… （**模型自拟**的判据引用了自己没交付的符号：… →
        记 fail：判据是模型写的，就属被测行为的一部分，不能算「尺坏了」）
[2] caller 判据 + 同样的引用错 ⇒ invalid / criterion-broken
  outcome=invalid kind=criterion-broken
[4] 环境缺依赖：caller ⇒ invalid(environment-missing)；model ⇒ fail
通过 13/13
```

**★ 全量单测（本轮实跑，`tests/run_unit.py`）：**

```
tests/unit/test_project_root.py              通过 32/32（新增）
tests/unit/test_deliverables.py              通过 15/15（新增）
tests/unit/test_criterion_ownership.py       通过 13/13（新增）
tests/unit/test_arch_map.py                  通过 16/16（新增）
tests/unit/test_outcome.py                   通过 20/20（按 P13 改判更新）
全量单测                                      通过 46/46
包络式汇总（另跑）：文档一致性 35/35 · 文档不变量 35/35 · 文档审查 18/18
契约符合性 / 前端契约 / 工具契约 / 信封门禁   44/44 · 25/25 · 40/40 · 35/35
```

（全量单测的官方数字见 `docs/VERSIONS.md` 的 v1.27 备份记录。）

### 4.2 未验证的部分（诚实列出）

- **没有做真实模型 E2E**验证"设了 `project_root` 后整轮 `/encode` 跑通" ——
  那需要模型配额；本轮做的是**确定性**证据（工具级 + 假编排器级 + 探针）。
  可以确定的是：工具层、check/verify 取根、交付物 gate 都在同一根上（同一判据源）。
- **检查点/回退不覆盖目标项目根**（刻意）：回退仍锚在工作区根，避免对别人的仓库
  `git reset --hard`。已记 `docs/PENDING_DECISIONS.md` C16。
- **目标根里的陈旧 `__pycache__` 不清**（刻意，三方隔离）：验前只清工作区根的缓存，
  并在 `verify.cache_warning` 里写明。同上 C16。
- **P12（子模型细读）/ P16（多语言）未开工**（用户裁决随后再上）：本轮只让
  「非 `.py` **逐条**可见」，**不是"真的支持"**。见 C17。
- **D30 的历史影响面**：本仓库事件库（`storage_data/events.jsonl`）里 verify 失败
  事件 **0 条**，故**没有历史读数因此改判**；统筹方能力基线里那两条
  （`ant_colony.generate_obstacles` / `obstacle_generator.generate_obstacle_grid`）
  是模型自拟判据，需要他们按新规则重算 —— 我改不了他们的数字。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 18 种） | 本轮不发新事件 |
| 事件 payload 键 | **无** | 同上 |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` 字段 | **加性** | 新增 `deliverables`（已进 `FROZEN_REPORT_KEYS`，只增不减） |
| `TOOLS_MAP` 条目结构 | **无**（顶层键仍 4 个） | 只改了 description 文案与工具**内部**取根 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无**（仍 `1.1` / `1.0` / `1.0`） | 加性实现 |
| 端点路径 | **无** | 只有 `/encode` `/run` 的**请求/响应字段**加性扩展 |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 未改规则表/词表；契约目录只读未动 |
| `/profile` 顶层键 | **加性** | 新增 `runtime` |
| `/encode` 请求/响应字段 | **加性** | 请求 `project_root` / `deliverables`；响应 `runtime` / `project_root` / `deliverables` |

**结论**：**additive**（新增，安全）。没有删除或改名任何前端依赖的事实面；
前端 `POST /encode` 不带新字段时行为**逐字不变**（旧默认 = workspace 根）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不需要**。所有新增字段都是可选的；不传时
  `project_root = None` → 行为与改造前完全一致（`effective_root == workspace_root`）。
  前端若想在界面上显示"这次产出落在哪"，读 `/encode` 响应的
  `deliverables.actual`（`{path, sha256, size}`）或 `/profile.runtime` 即可。
- **有没有可能"问题被平移到对侧"**：没有。根路径与交付物判定全部在**上游内部**
  （`core/runtime.py` + 工具层 + `CodingCycle`），判据与实现同侧；前端不承担新义务。
- **前端会静默少显示什么吗**：不会（纯加性）。仍保留统筹方记的 **D32**
  （bridge `/api/spec` 的 `tools[]` 不含 `parameters`）—— 那是前端侧可选增强，与本轮无关。

---

## 7. 不做的部分及理由（对应 C7）

- **不重写 `tools/arch.py`**：`render_architecture_view` 的"不许润色"设计未动、
  **仍未注册成工具**（它成为架构事实第二份拷贝的风险不变）；`get_architecture`
  现有键与语义未改，只**加**覆盖率/新鲜度/范围/反向索引。
- **不改工具名与参数语义、不新增工具**（仍 18 个）、**不引新依赖**（不用向量库/RAG）。
- **不动 `checkpoint.py` 的锚点**（工作区根）：不让 `git reset --hard` 伸进目标仓库。
- **不代前端做事**（D32 仍留给前端）。
- **不靠放宽门禁变绿**：P13 是**收紧**（`invalid` 只留给 caller 的坏判据）；
  `test_outcome.py` 的旧断言按新规则改判，并**补上 caller 的 `invalid`**（两向都在红）。
- **不动 `.interface_contract/`**（只读权威源）；**不动对侧仓库与集成工作区**
  （探针只用本仓库 `core/` 当目标根做**只读**扫描）。
- **P12 / P16 不开工**（用户裁决随后再上）。

---

## 8. 回退点（C8）

- **回退命令**：见 `docs/VERSIONS.md` 的 `v1.27` 条目，
  `git log --oneline --grep "^v1.27:"` 定位提交，`git reset --hard <该提交>`。
- **回退会丢什么**：
  1. `core/runtime.py`（三个根 / 任务级目标根 / 越界拒绝 / 交付物对账）；
  2. 六个工具的取根改造与 `outputs/` 前缀；`/profile.runtime`、
     `/encode` `/run` 的新字段、`CycleReport.deliverables`；
  3. P13 的归因改判（验 fail 的归因退回"模型自拟坏判据 ⇒ invalid"）；
  4. P11 的覆盖率/新鲜度/范围/反向索引（`build_index_report` 等）；
  5. 四个新单测 + 探针 + 本评估文档 + 文档面同步。
- **回退不会丢什么**：v1.26 及以前的全部改动（P9 规范化/信封、P7b 作用域、
  P6 判词描述产物、P1 结局四值、P2/P3 机械关卡等）。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 逐条给 `文件:行`；§2.2 给复现命令与修复前状态 |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 14 条，全部离线可跑 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘探针/P13/全量单测原文 |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明 `VERSIONS.md`（备份带入）、`.tmp/`（临时件）与**行尾事故**（第 9 组门禁抓到并已还原） |
| **C5** 对接口契约的影响已声明 | **满足**。§5 逐面声明；唯一"改动"是加性字段，事件/阶段/端点/版本轴/工具结构均未动 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：前端不需改；不传新字段时行为逐字不变；D32 仍是前端可选增强 |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 明确边界：不动契约、不动对侧、不重写 arch、不给目标仓库做破坏性操作、不靠放宽门禁 |
| **C8** 回退点明确 | **满足**。§8 给出 `v1.27` 定位命令与丢失项清单 |

**我希望统筹重点验证哪两条**：

1. **P13 是"收紧"而不是"放宽"**：请用你们能力基线里那两条真实判据
   （`ant_colony.generate_obstacles` / `obstacle_generator.generate_obstacle_grid`）
   重跑 —— 它们应当从 `invalid` **改判为 `fail`**；同时构造一条**调用方**给的坏判据，
   它**必须仍然是 `invalid`**（`tests/unit/test_criterion_ownership.py` §[1]/§[2] 是这两向）。
2. **交付物对账真的有牙齿**：请声明一个**不存在**的交付物（应 `delivery-gap → fail`），
   再声明一个**存在但哈希写错**的（应 `deliverable-hash-mismatch → fail`），
   最后声明一个**存在且哈希正确**的（应通过）——
   `tests/unit/test_deliverables.py` §[1]–[4] 就是这三向 + 删除后的反向。
