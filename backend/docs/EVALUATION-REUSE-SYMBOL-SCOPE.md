# 变更评估文档 · `REUSE-SYMBOL-SCOPE`

- **变更编号**：`REUSE-SYMBOL-SCOPE`（工作单里的 **P7b**）
- **提出方**：统筹（能力基线 T9 的真实运行）
- **执行侧**：backend
- **日期**：2026-09-28
- **契约版本**：`1.0.28`

---

## 1. 变更意图

引统筹方原话（`WORK_ORDER` / `dispatch/backend.md` 本轮）：

> 模型写的 `app.py` **完全正确** …… 而你们的复用层给出 **blocking**：
> `app.py 引用了不存在的符号 `app.route` —— `app` 里只有 ['app', 'ping']`
> …… **更糟的是：模型在 `self_report` 里写下「app.py 代码静态检查未通过」** ——
> **工具把正确代码判成错的，还让模型以为自己对代码是错的、去"反思"它。**

> **必须同时满足两条，缺一不可**：① 不再误判（A/B 都 0 且**结论一致**）；
> ② **不能靠关掉检查来"修"**（反空洞）。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（位置全写）

| 事实 | 位置 |
|---|---|
| 触发：模型交付物 `app.py` 里是 `app = Flask(__name__)` + `@app.route(...)`，而**文件名恰好也叫 `app.py`** | 运行 `run_20260928_221011_7b7bfc`（T9） |
| 「形式 1」对 `app.route` 取 `owner = "app"`，直接进模块反查 | `core/reuse_checks.py`（旧 `:188-208`） |
| `_lookup(owner)` **只查模块索引**（`by_module` / `by_stem`），而 `by_stem` 兜底会按"文件名主干"命中同名模块 | 旧 `:184-186` |
| 于是"在本文件里是**变量**的 `app`"被当成"**模块** `app`"，在它里面找 `route` → 找不到 → **blocking** | 旧 `:197-208` |
| `_bound_names(tree)`（收集本文件绑定名）**早就存在，但形式 1 没用它** —— 又一次"机制在，没接上" | `core/reuse_checks.py:69`（当时已有） |
| 复用层有**硬否决权**（用户已批准）⇒ 正确代码被否决：`check_status=failed`、`phase=failed` | `core/pipeline.py::run_check`（P2） |

根因一句话：**引用反查没有作用域概念** —— "模块名"与"本文件里的绑定名"撞车时，
把**实例属性**当成了**模块属性**。

### 2.2 复现命令

统筹方的复现脚本（**只读运行**，它在我可写范围之外，我没改它）：

```powershell
python D:\PythonProject\SimpleAgent2_Integration\04-tests\cases\probe_p7_symbol_collision.py
```

实测输出（修复前）：

```
--- A) 工作区里**有** app.py（= 模型自己刚写的那个文件） ---
    索引里的模块 : ['app']
    违规         : 1 条
      [blocking] undefined-symbol: app.py 引用了不存在的符号 `app.route` —— `app` 里只有 ['app', 'ping']
--- B) 工作区里**没有** app.py（同一份代码、同一个变量名） ---
    违规         : 0 条
A 的 blocking 条数 = 1（复现）   B 的 blocking 条数 = 0
```

我这一侧的**新判据版**探针（同一份代码、两种工作区必须**结论一致**）：

```powershell
python tests/diagnostics/probe_symbol_scope.py     # 14/14
python tests/unit/test_reuse_scope.py              # 24/24
```

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M core/reuse_checks.py
 M docs/CHANGELOG.md
 M docs/FRONTEND_CONTRACT.md
 M docs/VERSIONS.md
 M tests/unit/test_doc_invariants.py
?? tests/diagnostics/probe_symbol_scope.py
?? tests/unit/test_reuse_scope.py

$ git -c safe.directory=<repo> diff --stat
 core/reuse_checks.py              | 57 +++++++++++++++++++++++++++++++++++++++
 docs/CHANGELOG.md                 |  2 +-
 docs/FRONTEND_CONTRACT.md         |  2 +-
 docs/VERSIONS.md                  |  8 +++---
 tests/unit/test_doc_invariants.py | 56 +++++++++++++++++++++++++++++++++++++-
 5 files changed, 118 insertions(+), 7 deletions(-)
```

（文档面随后补齐 —— 评估文档/README/tests README/MODULES/OPERATIONS/版本戳；
最终以备份点 `git show --stat <tag>` 为准。）

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/reuse_checks.py` | 形式 1 之前 | **要求 1**：`_is_local_object(owner)` —— owner 的根名是**非 import 绑定**（变量/参数/`with as`/`for`/`except as`/推导式/def|class 名）⇒ 是**对象属性**，本地 AST 索引不可知 ⇒ **不判** |
| 2 | `core/reuse_checks.py` | `_lookup` 前置 | **要求 2**：`by_stem` 兜底匹配现在**必须先过**"该名字不是本文件绑定名"这一关 |
| 3 | `core/reuse_checks.py` | 形式 1 新增分支 | **要求 3 + 反空洞**：owner 的根名**既非绑定也非内置** ⇒ `undefined-name`（阻塞）—— `np.array(...)` 缺 import 属于这一类（**必须仍然红**） |
| 4 | `core/reuse_checks.py` | `has_star_import` | `from x import *` 会引入看不见的名字 ⇒ 这类文件不做"未定义名"判定（宁可漏报也不误报） |
| 5 | `tests/unit/test_reuse_scope.py`（新） | — | 24 项：A/B 一致 + 撞车矩阵 + **反空洞五条** + 工作区级 + 端到端 |
| 6 | `tests/diagnostics/probe_symbol_scope.py`（新） | — | 统筹方那个复现脚本的**新判据版**（A/B 都 0 且一致） |
| 7 | `tests/unit/test_doc_invariants.py` | 第 10 组 | 顺带项：**文档里写的"上游 N 种事件"必须等于 `len(EVENTS)`**（v1.22 曾把 18 写成 19） |
| 8 | `docs/FRONTEND_CONTRACT.md` / `docs/VERSIONS.md` / `docs/CHANGELOG.md` | — | 顺带项勘误：19 → **18**（VERSIONS 历史条目只加"勘误"注，不重排） |

### 3.3 若两者不一致，差异是什么

一致。**一处要说明**：统筹方给的复现脚本**不在我的可写范围内**
（`SimpleAgent2_Integration/` 是他们的仓库），所以我没有改它，
而是**另写了一份新判据版**（`tests/diagnostics/probe_symbol_scope.py`）。
他们那份的"预期"现在**已经不成立**（A 不再有误判）—— 请他们照新判据改，
或者直接用我这份。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | 要求 1：owner 是本文件绑定名时不判 blocking | `python tests/unit/test_reuse_scope.py` | 撞车矩阵 10 项 PASS |
| 2 | ★ 验收①：A/B 都 0 且**结论一致** | `python tests/diagnostics/probe_symbol_scope.py` | `★ 两种工作区结论一致` PASS |
| 3 | ★ 验收②（反空洞）：`np.array` 缺 import 仍红 | 同上 | `仍然红：np.array …（undefined-name）` PASS |
| 4 | ★ 反空洞：`from mylib import f`（无 f）仍红 | 同上 | PASS |
| 5 | ★ 反空洞：`t1.bar`（t1 里只有 foo）仍红 | 同上 | PASS |
| 6 | 反空洞：P2 那两条实测判据仍红 | `python tests/unit/test_reuse_scope.py` | 两条 PASS |
| 7 | 反空洞：按旧签名传参仍红 | 同上 | PASS |
| 8 | 工作区级不再整体否决正确代码 | 同上 | `★ 工作区级不再把正确代码判红` PASS |
| 9 | 端到端：正确 Flask 交付物 → `check.passed=True`、`reuse.blocking=[]` | 同上 | 三条 PASS |
| 10 | 顺带项：文档事件数 == 代码 | `python tests/unit/test_doc_invariants.py` | `…一致（18）` PASS + 非空转 PASS |
| 11 | 全量回归 | `python tests/run_unit.py` | `通过 40/40` |
| 12 | 契约符合性 / 前端契约 / 文档 | 各 `tests/unit/test_*.py` | 44/44 · 25/25 · 35/35 · 18/18 |

### 4.1 实测输出（粘贴原文）

**验收①（A/B 一致，不再误判）**：

```
  A) 工作区里**有** app.py（模型自己刚写的） → blocking=0
  B) 工作区里**没有** app.py            → blocking=0
  PASS  A 不再误判（0 条 blocking）
  PASS  B 仍是 0（对照组）
  PASS  ★ 两种工作区结论**一致**（原缺陷的症候就是不一致）
```

**名字撞车不止 `app`**：

```
  变量 app 撞模块 app.py → blocking=0
  变量 data 撞模块 data.py → blocking=0
  变量 utils 撞模块 utils.py → blocking=0
  变量 config 撞模块 config.py → blocking=0
  变量 main 撞模块 main.py → blocking=0
  self 属性 → blocking=0      参数属性 → blocking=0      with as → blocking=0
  （另有 for 目标 / except as / 推导式目标 三项在单测里）
```

**★ 验收②（反空洞：三条必须仍然红）** —— 这是"机械输出"，逐字贴：

```
  红  np.array 但没 import numpy → ['undefined-name']
      m.py 第 2 行用了未定义的 `np`（没有 import，也没有任何绑定）—— 必然 NameError
  红  from mylib import f（mylib 里只有 g） → ['undefined-symbol']
      m.py 从 `mylib` 导入了不存在的符号 `f` —— 它只有 ['g']
  红  t1.py 有 foo，t2.py 调 t1.bar → ['undefined-symbol']
      t2.py 引用了不存在的符号 `t1.bar` —— `t1` 里只有 ['foo']
  红  ant_colony 里没有 generate_obstacles → ['undefined-symbol']（P2 实测反例）
  红  obstacle_generator 里没有 generate_obstacle_grid → ['undefined-symbol']（P2 另一条）
  红  按旧签名传参 → ['symbol-arity-mismatch']
```

**端到端**：

```
  phase=record check={'checked': True, 'passed': True, 'status': 'passed'}
  reuse.blocking=[]   manifest.passed=True
  PASS  ★ check 阶段通过（复用层不再否决正确代码）
```

**顺带项（事件数勘误 + 门禁）**：

```
实际事件种类数 = 18
  PASS  docs/FRONTEND_CONTRACT.md 的事件种类数与代码一致（18）
  PASS  事件数门禁确实扫到了声明（否则空转）
```

### 4.2 未验证的部分（诚实列出）

- **我没有改统筹方那份复现脚本**（不在可写范围）。所以"那份脚本退出码 0"
  这一条**由他们复验**；我另写的新判据版脚本 14/14，等价覆盖同一组断言。
- **T9 的真实重跑没做**（需要 `--only T9` 的能力基线环境，属他们的测量仪）。
  我做到的是：**同一份代码、同一组判据**在工作区级与 cycle 级都不再被否决（用例 8/9）。
- **"顶多 `info`"我只做到"不报"**：本地对象属性一律不产生条目，
  没有额外产出 `info` 级记录。理由见 §7。
- **`by_stem` 兜底的其它撞车面没穷举**：现在它只在"该名字不是本文件绑定名"时生效，
  但**跨文件**的同名（`utils.py` 与另一个包里的 `utils`）仍可能命中 —— 那属于
  "模块名歧义"，与本次的作用域缺陷不同族，遇到样例再修。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 **18** 种） | 本次不改事件面 |
| 事件 payload 键 | **无** | — |
| `PHASE_ORDER` / `CycleReport` / `Snapshot` / `Event` / `TOOLS_MAP` | **无** | — |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1` / `1.0`） | — |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 事件种类数不变 → 台账**无需更新** |

**行为面变化**（不是契约面）：`reuse` 的 `blocking` 少了一类**误报**，
多了一类**真报**（"根名未定义"从 `undefined-symbol` 细分为 `undefined-name`；
两者都在 `BLOCKING_KINDS` 里，**否决强度不变**）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不需要**（事件与字段都没动）。
  但他们那份**复现脚本的预期要改**（见 §3.3）—— 那是"验证资产"而不是产品代码。
- **有没有可能"问题被平移到对侧"**：没有。这是上游内部的判据缺陷，
  且**修好之后模型不再被迫"反思"正确代码**（T9 那条自述就是被误判带偏的）。
  对他们的影响只是：**T9 这一轴的读数会从"无效"变成有效** ——
  若他们基线的 T9 数字要重跑，那是他们的判断（与本轮 P6 的 C14 同类）。
- **前端会静默少显示什么吗**：不会。`reuse.blocking` 只是变少了（少的是误报）。

---

## 7. 不做的部分及理由（对应 C7）

- **不给"本地对象属性"补 `info` 级条目**。要求里写的是"顶多 `info`"，
  我选择**不报**：`self.db.execute()` 这类引用在本层**永远无法判定**，
  每条都留一个 `info` 会把 `reuse` 事件变成噪音，而**噪音会让真正的 blocking 被忽略**。
  若统筹方要 info 轨迹，加一段即可（一处）。
- **不靠"取消 block"来修**：这是本轮**最重要**的一条纪律 ——
  §4.1 里那三条"仍然红"的机械输出就是为此存在的（**反空洞**）。
- **不扩到"跨文件同名模块歧义"**：见 §4.2；那是另一族问题，改法也不同。
- **不动统筹方的仓库**（复现脚本）：不可写，且"改验证资产"应由他们确认新判据后再动。
- **不改 `BLOCKING_KINDS`**：本次只调**判据的作用域**，不动**否决强度**。

---

## 8. 回退点（C8）

- **回退命令**：见本变更的备份点 `docs/VERSIONS.md`（`v1.24`），`git reset --hard <tag>`。
- **回退会丢什么**：
  1. 作用域排除 ⇒ **正确代码重新被否决**（T9 那类假失败回归；
     模型会再次"反思"正确的代码）；
  2. "根名未定义"这条反空洞分支（`np.array` 缺 import 会**退回漏报**，
     只剩 `F821` 那条兜底 —— 若环境没有 ruff，兜底走 AST，仍然是红的，
     但**判据的来源会少一条**）；
  3. 事件数门禁（文档里的数字会再次漂）。
- **回退不会丢什么**：v1.17–v1.23 的全部改动。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 逐条给 `文件:行`；§2.2 给出**他们的**脚本与实测输出 |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 12 条 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘原文（含三条反空洞的机械输出） |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明"没改他们的脚本" |
| **C5** 对接口契约的影响已声明 | **满足**。§5：契约面**零改动**，只改行为面（并说明 `blocking` 的组成变化） |
| **C6** 对另一侧的影响已评估 | **满足**。§6：不需要改产品代码；**他们的复现脚本预期要改** |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 五条"不做"，含"不靠关检查来修"这条纪律 |
| **C8** 回退点明确 | **满足**。§8 逐条写清 |

**我希望统筹重点验证哪两条**：

1. **反空洞那三条**（§4.1）—— 这是"修好误判"与"把检查关掉"的唯一分界线；
   我特意让它们**逐字可复核**。
2. **"结论与工作区无关"这条不变量**：同一份代码在两种工作区下结论必须一致 ——
   它比"某一种工作区下是 0"更强，也更能防住以后同类的作用域回归。
