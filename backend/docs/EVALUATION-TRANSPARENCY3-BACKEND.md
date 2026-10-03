# 变更评估文档 · `TRANSPARENCY3-BACKEND`

- **变更编号**：`TRANSPARENCY3-BACKEND`（P6 / P7 / P8）
  > 编号说明：`TRANSPARENCY2-BACKEND` 已被上一轮（P1–P5，v1.22）用掉，
  > 本轮是**基线复验新发现的三个缺陷**，另起一号；两份文档互相引用，不覆盖。
- **提出方**：统筹（能力基线复验实测发现）
- **执行侧**：backend
- **日期**：2026-09-28
- **契约版本**：`1.0.25`

---

## 1. 变更意图

引统筹方原话（`WORK-ORDER.md` P6 / P7 / P8）：

> **P6 值得单说**：它使**所有 `fail` 读数都可能不可信**。
> 这与你们已修的 `FIX-VERIFY-WIRING` 同族 —— **被验证的对象，必须就是被交付的对象。**

> **P7**：`app = Flask(__name__)` 被判 `缺少符号: app` ⇒ **假失败**。……
> **它直接毁掉了一个能力轴的读数。**

> **P8**：`decompose_review.passed` 恒为 `False`（含通过的任务）……
> 于是**"审查未通过"与"运行通过"在报告里并存**，读起来困惑。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 P6 · 判词不描述产物（**机制我定位到了**）

统筹方实测：11 个任务 ×2 遍，**两个任务报 `fail`，而归档产物是对的**
（同一条判据对归档产物在干净进程里重跑 **都 PASS**）；并已排除"判词过时"。

他们写「具体机制（进程内模块缓存？cwd？）**我还没定位**」——
**我定位到了，而且是可确定性复现的**：

| 事实 | 证据 |
|---|---|
| `tools/verify.py:26-33` 用 `cwd=WORKSPACE_DIR` + 独立子进程 + `PYTHONPATH` | 所以**不是** cwd 问题，也**不是**进程内 `sys.modules` 复用 |
| 但子进程是 `python <tmp>.py`，**会读 `__pycache__/*.pyc`** | 缓存陈旧就有了入口 |
| `__pycache__` 的失效判据是 **源码 (mtime, size)** | 而本项目的回退/快照用 **`shutil.copy2`（保留原 mtime）** → **极易**凑成"mtime 与 size 都与旧 `.pyc` 一致" |
| 于是 `import` 执行**旧代码** | 实测（`test_artifact_binding.py` 第 1 组） |

**决定性复现**（同一长度 + 还原 mtime）：

```
第一跑: A                     ← 生成 __pycache__/mod.cpython-310.pyc
源码改写为 B（同长度），把 mtime 还原成 A 的时间
不清缓存 → import 得到 'A'    ← ★ 危险是真的：执行的不是磁盘上那份产物
清掉 __pycache__ → import 得到 'B'
```

**位置**：`tools/verify.py:37-55`（`_run_sync`：`["python", tmp_name]` + 只清 `TMP_DIR` 的临时文件）、
`core/pipeline.py` 旧 `run_verify`（**完全没记"验的是哪份产物"**）。

### 2.2 P7 · 符号表不收模块级赋值

`core/symbol_index.py` 旧版只访问 `visit_FunctionDef` / `visit_AsyncFunctionDef` /
`visit_ClassDef`，**没有 `visit_Assign` / `visit_AnnAssign`**
⇒ `app = Flask(__name__)` 不算符号 ⇒ `core/manifest.py:273` 判 `symbol-missing`
⇒ **交付物是模块级对象就假失败**。

### 2.3 P8 · 审查模式不显式

`decompose_review` 事件的 `passed=false` 在 `warn` 模式下**不影响运行通过**，
但事件里没有 `mode`，报告里"审查未通过"与"运行通过"并存。
**位置**：`core/coding_cycle.py::_review_decomposition` 的 `_emit("decompose_review", ...)`。

### 2.4 复现命令（我这一侧，**不调模型**）

```powershell
python tests/unit/test_artifact_binding.py     # P6 / P7 / P8（24 项，含危险复现）
```

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M core/coding_cycle.py
 M core/contract.py
 M core/manifest.py
 M core/memory.py
 M core/orchestrator.py
 M core/outcome.py
 M core/pipeline.py
 M core/symbol_index.py
 M tools/verify.py
?? tests/unit/test_artifact_binding.py

$ git -c safe.directory=<repo> diff --stat
 core/coding_cycle.py | 40 +++++++++++++++++++++++
 core/contract.py     | 17 +++++++---
 core/manifest.py     | 44 +++++++++++++++++++------
 core/memory.py       | 13 ++++++++
 core/orchestrator.py |  8 ++++-
 core/outcome.py      |  4 +++
 core/pipeline.py     | 62 +++++++++++++++++++++++++++++++++++-
 core/symbol_index.py | 90 +++++++++++++++++++++++++++++++++++++++++++++++++++
 tools/verify.py      |  7 +++-
 9 files changed, 269 insertions(+), 16 deletions(-)
```

（外加 1 个新单测；文档面随后补齐，最终以备份点 `git show --stat <tag>` 为准。）

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/pipeline.py` | `run_verify(command, files=None)` | **P6**：验前记**内容哈希** + 清 `__pycache__` + 明确 `cwd`；验后再记一次 |
| 2 | `core/pipeline.py` | `artifact_hashes()` / `_purge_pycache()`（新增） | 哈希只取**内容**（mtime 不可对账）；清缓存失败**必须显式声明** |
| 3 | `tools/verify.py` | `_clean_env()` / `_run_sync` | **P6 要求 4**：`PYTHONDONTWRITEBYTECODE=1` + `python -B`（不再写字节码） |
| 4 | `core/orchestrator.py` | 验证回流处 | 把 `files` 传给 `run_verify`，并把哈希/cwd 带进 `set_verify` |
| 5 | `core/memory.py` | `set_verify(...)` | `verify_state` 加 `artifact_hashes`/`cwd`/`cache_cleared`/`cache_warning` |
| 6 | `core/coding_cycle.py` | RECORD 前 | **P6 要求 2**：重新取一次**最终产物**哈希 → 对不上 **不打检查点**、结局 `invalid` |
| 7 | `core/coding_cycle.py` | `verify` 事件 | payload 加 `artifact_hashes` / `cwd`（判词可对账） |
| 8 | `core/outcome.py` | 映射表 | 新增 `artifact-mismatch → invalid` |
| 9 | `core/symbol_index.py` | `visit_Assign` / `visit_AnnAssign` + `raw_module_bindings()` | **P7**：模块级赋值进符号表；并给出**独立第二意见**用于区分"真没有/没索引到" |
| 10 | `core/manifest.py` | 符号判定 | **P7 要求 2/3**：`symbol-unindexed`（warning，不拦路）vs `symbol-missing`（error，带 `文件:行`） |
| 11 | `core/coding_cycle.py` + `core/contract.py` | `decompose_review` 事件 | **P8**：`mode` + `applied` 显式 |

### 3.3 若两者不一致，差异是什么

一致。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | **P6** 缓存陈旧的危险**可复现**（执行的不是磁盘那份产物） | `python tests/unit/test_artifact_binding.py` | `★ 危险可复现：读到的是旧代码` PASS |
| 2 | **P6** 清理有效，且不再假失败 | 同上 | `★ 清理有效` + `★ 缓存陈旧不再导致假失败` PASS |
| 3 | **P6 要求 1** 记录并暴露被验产物的**内容哈希** | 同上 | 报告 + `verify` 事件都有 `artifact_hashes` PASS |
| 4 | **P6 要求 3** 工作目录明确定义并暴露 | 同上 | `verify.cwd` 非空 PASS |
| 5 | **P6 要求 4** 不复用陈旧模块 | 同上 | `-B` + 清缓存；`cache_cleared` 可读 PASS |
| 6 | **P6 要求 2** 对不上 → `invalid`（不是 `fail`） | 同上 | `★ 结局是 invalid` + `kind=artifact-mismatch` PASS |
| 7 | **P6** 两个哈希**可比**、且不打检查点 | 同上 | `artifact_hashes` vs `artifact_hashes_final` + `commit` 空 PASS |
| 8 | **P7** `app = Flask(__name__)` 不再假失败 | 同上 | `★ 不再假失败` PASS |
| 9 | **P7** 真没有仍是 error、带 `文件:行` | 同上 | `★ 阻塞判定带可复核位置` PASS |
| 10 | **P7** 「有但我没索引到」可区分 | 同上 | `symbol-unindexed`（warning）PASS |
| 11 | **P8** `mode`/`applied` 显式 | 同上 | `mode='warn'` + `applied=False` PASS |
| 12 | 全量回归 | `python tests/run_unit.py` | `通过 39/39` |
| 13 | 契约符合性 / 前端契约 / 文档 | 各 `tests/unit/test_*.py` | 44/44 · 25/25 · 35/35 · 31/31 · 18/18 |

### 4.1 实测输出（粘贴原文）

**P6 机制（决定性复现）**：

```
第一跑: A
pycache 存在: True ['mod.cpython-310.pyc']
长度 A/B: 24 24
篡改 mtime 后（不清缓存）: A      ← ★ 磁盘上是 'B'，执行的是 'A'
清缓存后: B
```

**P6 端到端（产物漂移 → invalid）**：

```
[P6-3] ★ 产物在验证之后被改过 → 结局是 `invalid`，不是 `fail`
  phase=failed outcome=invalid kind=artifact-mismatch
  mismatch=['mod.py: 验证时 3f1c… → 交付时 9ab2…']
  error=被验证的产物**不等于**被交付的产物 —— 判词不描述产物，本次读数**invalid**
  ★ 没有打检查点（commit 为空）
```

**P7**：

```
索引到的符号：[('CONFIG', 'variable'), ('app', 'variable'), ('run', 'function')]
manifest: passed=True violations=[]
真缺符号：other.py 缺少声明的符号: nope（该文件里没有这些名字的任何模块级绑定） | at=other.py:1
索引缺口场景 → ['symbol-unindexed']        ← warning，不拦路；不再报 symbol-missing
通过 24/24
```

### 4.2 未验证的部分（诚实列出）

- **他们的两次原始失败我无法逐字重放**（那两次的运行记录在他们手里）。
  我做到的是：**把机制确定性地复现出来**（同长度 + 还原 mtime → 读到旧代码），
  并证明修复消除了它。**若那两次的真实成因不是 `.pyc` 陈旧**，
  本轮的"哈希对账"仍然能**独立地**把"验证的不是交付物"这件事变成 `invalid` ——
  两条是互补的：一条堵入口，一条兜结论。
- **`__pycache__` 清理失败的情况只做了"显式声明"**（`cache_warning`），
  没有把它升级为 `invalid`。理由：声明出来就够了，硬判会把"环境不允许删除"
  变成模型失败。若统筹方要更硬，改一处即可。
- **P7 只收模块级赋值**：类属性、函数内定义仍不算符号（那是刻意的范围）。
  若某交付物的"符号"是类属性，仍会假失败 —— 遇到具体样例我再扩。
- **P8 只加了字段**，没有改 `passed` 的语义（他们给的第二个选项）。
  理由：`passed` 的含义在 v1.22 已写进契约注释，改语义会动已冻结的事实面；
  加 `mode`/`applied` 之后"审查未通过 ≠ 运行不通过"已经读得出来。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 19 种） | 只给既有事件加键 |
| 事件 payload 键 | **有** | `verify` += `artifact_hashes` / `cwd`；`decompose_review` += `mode` / `applied` |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` 字段 | **无新增**（`verify` 是 dict，内部加 `artifact_hashes` / `artifact_hashes_final` / `artifact_mismatch` / `cwd` / `cache_cleared` / `cache_warning`） | `manifest` 的 `violations` 新增 `kind=symbol-unindexed`（**additive 的取值**，字段结构未变） |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` | **无**（仍 `1.1` / `1.0`） | additive |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 事件种类数**不变** → 台账无需更新 |

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：不必。但前端建议：
  1. `verify.artifact_hashes` / `artifact_hashes_final` **值得显示**（一格两行即可）——
     它们是"这次判词验的是哪份产物"的唯一凭据；
  2. `outcome=invalid` + `outcome_kind=artifact-mismatch` 要**与 `fail` 分色**，
     否则又会把"读数无效"看成"模型不行"；
  3. `manifest.violations` 里出现 `symbol-unindexed`（warning）时，
     文案要写成"**索引缺口，请报 bug**"，而不是"交付不完整"。
- **有没有可能"问题被平移到对侧"**：**没有新增平移**。P6 是"上游把自己的读数
  做成可对账"，P7 是"上游少收了一类符号"，P8 是"上游少写了一个字段" ——
  三者都在本侧闭合。**唯一的外溢是"读数变可信"之后，历史 `fail` 数字可能需要重跑**：
  如果他们基线里那些 `fail` 有一部分是 `.pyc` 陈旧造成的，重跑后应当变成 `pass`
  或 `invalid`。**这件事得他们来判**（我拿不到那两次的现场）。
- **前端会静默少显示什么吗**：不会，只多字段。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `check_and_run` 的执行方式**（仍是"写临时文件 + 子进程"）：它本身是对的
  （独立进程、显式 cwd、显式 `PYTHONPATH`），问题只在**字节码缓存**与**没有对账**。
- **不把"清缓存失败"升级为 `invalid`**：见 §4.2。
- **不扩符号表的范围**（类属性、嵌套定义）：见 §4.2；遇到样例再扩。
- **不改 `decompose_review.passed` 的语义**（P8 的第二个选项）：见 §4.2。
- **不动前端**；也没替前端决定那两个哈希怎么显示。

---

## 8. 回退点（C8）

- **回退命令**：见本变更的备份点 `docs/VERSIONS.md`（`v1.23`），`git reset --hard <tag>`。
- **回退会丢什么**：
  1. **产物对账**（判词与最终产物不再可比 → P6 的假失败会以任意机制重新出现）；
  2. **字节码缓存清理**（`.pyc` 陈旧重新可能执行旧代码）；
  3. **模块级赋值进符号表**（`app = Flask(...)` 重新假失败 → 那个能力轴的读数再次无效）；
  4. `decompose_review.mode/applied`（"审查未通过"与"运行通过"重新并存而无法解释）。
- **回退不会丢什么**：v1.17 / v1.19 / v1.20 / v1.21 / v1.22 的全部改动。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 给出**机制级**复现（含 `文件:行`）；§2.4 一条命令 |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 13 条 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘原文（含危险复现与修复对照） |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威 |
| **C5** 对接口契约的影响已声明 | **满足**。§5：只加事件键，事件种类数不变 |
| **C6** 对另一侧的影响已评估 | **满足**。§6 三条建议 + **"历史 fail 数字可能需要重跑，得他们判"** |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 五条"不做" |
| **C8** 回退点明确 | **满足**。§8 逐条写清丢什么/不丢什么 |

**我希望统筹重点验证哪两点**：
1. **P6 的机制是否就是他们那两次的成因** —— 我只能证明"**存在**一条这样的通道"
   （`.pyc` + `copy2` 保留 mtime），并把它堵上；要确认是不是**那两次**的成因，
   需要他们那边的运行现场（或**按同一场景重跑**）。**若重跑后那两个任务变 `pass`/
   `invalid`，就说明命中了。**
2. **P7 的 `symbol-unindexed`**：我只在人为制造索引缺口时验证过它。
   真实场景里它应当**永远不出现**（出现了就是我又漏收了一类节点）——
   所以它更像一条**自检**：出现即报 bug。
