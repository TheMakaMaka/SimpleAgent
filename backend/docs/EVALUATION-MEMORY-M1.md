# 变更评估文档 · `MEMORY-M1`（P21 / M1：外部记忆库独立库）

- **变更编号**：`MEMORY-M1`（工作单 **P21** 的第一期 **M1**；`DISPATCH.md` ⓪ 点名）
- **提出方**：用户（2026-10-03 提议）+ 统筹（`DISPATCH.md` / `WORK-ORDER.md`【P21】）
- **执行侧**：backend
- **日期**：2026-10-05
- **契约版本**：`1.0.34`（`ROUND.json` 随载荷声明；本轮**未改契约**）
- **本轮 round_id**：`R-c0c8ba72e3` —— **本轮完成 `R-c0c8ba72e3`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-c0c8ba72e3` 开工，
> 与仓库里上一轮记录的 `R-5bfd0ff2e5`（`docs/EVALUATION-REASONING-PROTOCOL.md`）**不同**
> ⇒ 有新指令。但 **`DISPATCH.md` / `WORK-ORDER.md` 的内容并未变化**
> （`ROUND.json` 声明的 `dispatch_sha256 = c2fe1af135a193bf`、`work_order_sha256 = 90ad6f724a1f369d`
> 与两份文件的实测 sha256 **逐位相同** —— 见 §2.1），所以本轮**不是**"上一轮的清单重做一遍"：
> 本轮开工的是那份清单里**唯一没做过、也没被推迟**的一项 —— **P21 M1**。
> 开工前逐条核对仓库事实的依据写在 §2.2（`ROUND.json` 的 `[ ]` 复选框是载荷里的历史文本，
> 不随交付回填；这一条本身就是本项目在治的"声明 vs 实现不符"）。

---

## 1. 变更意图

**用户原话（2026-10-03 提议，逐字）**：

> 外部记忆链表 + **物理存储上下文的区域** + 按**对话时间/关键词**分区 + 类知识库 +
> 每个上下文/知识存进**特定单元** + 单元**平常不调用** + **调用分机制**（定制化需求加权）
> ⇒ **分数达一个量级就调用；达可调用但非必须量级就申请人工介入** ——
> 目的是**释放模型的上下文限制**。

**用户指定的做法（逐字）**：**后端单独开一个区域 · 独立测试 · 成型之后再考虑接入模型** ·
做好**沙箱隔离**与**物理文件隔离**。

**统筹方 `DISPATCH.md` ⓪（逐字）**：

> ### ⓪【P21】**上下文链路调用算法**（用户提议 · **本轮只做 M1 独立库**）
>
> 用户指定：**后端单独开一个区域 · 独立测试 · 成型之后再谈接入** · 做好**沙箱隔离**与**物理文件隔离**。
> **我补的三条硬要求**（不写进去就是把看得见的限制换成看不见的）：
>
> 1. 判据要覆盖 **漏召 / 误召**，不能只看「调用成功」；
> 2. 必须有**第二路召回** —— 挂在已有结构索引（`find_symbol`/`get_module`/`get_architecture`）上，**别另起关键词库**；
> 3. **阈值第一阶段不许定死**：只记分、不决策，用数据校准（我在 S3 上刚栽过「拍阈值」）。
>
> **本轮的活只有 M1**：存储与检索 + 独立根 + 越界拒绝，**不接模型**。
> 详见 `WORK-ORDER.md` 的 **P21**（M1/M2/M3 三期验收，**不许跳级**）。

**统筹方 M1 验收（逐字）**：① 写入/读取可机械复现；② 越界写被**结构化拒绝**；
③ 库根在两侧仓库之外（可机判）；④ 有**归档**而非删除。

**统筹方另三条实现约束（逐字）**：

> | **4** | **必须能一键关闭**（A/B 开关）…**在跨模型对比结论出来之前，不得进主链路** |
> | **5** | **物理隔离**：库根独立（建议 `<work area>\08-memory\`），**绝不写进两侧仓库**、也不进 `.interface_contract\`；**越界即拒**（复用 P15 的 `ScopeError` / `scope_error_result`） |
> | **6** | **淘汰 = 归档，不是删除**：单元会无限增长 ⇒ 需要淘汰；但**淘汰不得抹掉证据**…移入归档层并留索引 |

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 先证明"本轮指令与上一轮同源、但只剩一件没做"（可复现的机械判据）

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import hashlib,json,os; d=r'D:\PythonProject\SimpleAgent2_Cycle\.interface_contract'; r=json.load(open(os.path.join(d,'ROUND.json'),encoding='utf-8')); [print(n, 'raw=', hashlib.sha256(open(os.path.join(d,n),'rb').read()).hexdigest()[:16], 'claimed=', r['dispatch_sha256'] if n=='DISPATCH.md' else r['work_order_sha256']) for n in ('DISPATCH.md','WORK-ORDER.md')]; print('round_id=', r['round_id'])"
```

实际输出：

```
DISPATCH.md raw= c2fe1af135a193bf claimed= c2fe1af135a193bf
WORK-ORDER.md raw= 90ad6f724a1f369d claimed= 90ad6f724a1f369d
round_id= R-c0c8ba72e3
```

⇒ 载荷**就是** `ROUND.json` 的生成源（哈希逐位相同），所以"有新指令"的判定成立；
但载荷内容既然没变，**能干的事只有载荷里还没被做掉的那些** —— 见 §2.2。

### 2.2 为什么本轮做 P21 M1（逐条对仓库事实，不是自述）

`ROUND.json` 的 `open_items_for_this_side` 有 7 条。逐条给出**可复现的核对命令**：

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import os,sys; sys.path.insert(0,'.'); print('P17 core/evidence.py      :', os.path.exists('core/evidence.py')); print('P17 test_pass_evidence.py :', os.path.exists('tests/unit/test_pass_evidence.py')); print('D43 test_model_swap.py    :', os.path.exists('tests/unit/test_model_swap.py')); import core.coding_cycle as cc; print('P18/P20 DECOMPOSE_GATE_DEFAULT:', cc.CodingCycle.DECOMPOSE_GATE_DEFAULT); import core.llm as llm; print('P19 request_messages      :', callable(llm.request_messages)); print('P19 AGENT_REASONING_REPLAY:', llm.REASONING_REPLAY_ENV)"
```

实际输出：

```
P17 core/evidence.py      : True
P17 test_pass_evidence.py : True
D43 test_model_swap.py    : True
P18/P20 DECOMPOSE_GATE_DEFAULT: warn
P19 request_messages      : True
P19 AGENT_REASONING_REPLAY: AGENT_REASONING_REPLAY
```

| 工单项 | 事实 | 处置 | 依据 |
|---|---|---|---|
| **D38** P17 结果信封扩到主流程 | v1.28 已交付 | 不重做 | 上面 `evidence.py` / `test_pass_evidence.py` = True |
| **D39** P18 关卡默认 `block` | v1.29 交付，**v1.30 的 P20 已按工单退回 `warn` 并分档** | 不重做 | 上面 `DECOMPOSE_GATE_DEFAULT = warn` |
| **D40** P19 `reasoning_content` | v1.30 已交付 | **明确不要改** | `WORK-ORDER.md` P19 的 2026-10-05 更正条逐字："**已由我独立复核通过（26/26）**，`AGENT_REASONING_REPLAY` **保持 `auto`，不要改成 `never`**" |
| **D41** P20 退 `warn` + `undecidable` 分档 | v1.30 已交付 | 不重做 | 同上 + `core/coding_cycle.py::_review_decomposition` 按 `violated` 否决 |
| **D43** 假换冒烟 | v1.30 已交付 | 不重做 | 上面 `test_model_swap.py` = True |
| **D37** P16 多语言 | `DISPATCH.md` 逐字「**P16（多语言）现在别动**」（用户裁决"随后再上"） | **不动** | `DISPATCH.md` §① 末与 `WORK-ORDER.md`【P16】标题 |
| **D30** 文档版本号/计数漂移 | v1.24–v1.30 逐轮收口 | 机械复查 | `test_doc_invariants.py` 第 8/10 组（自带反向"判据有牙齿"）本轮全绿 |

⇒ 剩下唯一**没做过、也没被推迟**的一项 = `DISPATCH.md` ⓪ 点名的 **P21 M1**。

`ROUND.json` 里那些 `- [ ]` 之所以还空着，是因为它是**载荷里的历史文本**，交付不会回填它
（这正是本项目一路在治的 U- 类：**声明 vs 实现不符**）。本节的表就是对它的收口。

### 2.3 现状取证：仓库里**没有**外部记忆库（P21 M1 的出发点）

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe -c "import os; print('core/context_store exists:', os.path.isdir('core/context_store')); print([n for n in os.listdir('core') if 'memor' in n or 'retriev' in n])"
```

改动前实际输出：

```
core/context_store exists: False
['memory.py']
```

`core/memory.py` 是 `SharedMemory`（**一轮运行内的全局状态**：verify/check/交付物），
与"跨任务的外部记忆库"是两件事 —— 用户要的是后者，而它此前**不存在**。
（同一判据在改动后变为 `True`，见 §4.6。）

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
git -c safe.directory='*' -C D:\PythonProject\SimpleAgent2_Cycle status --short
git -c safe.directory='*' -C D:\PythonProject\SimpleAgent2_Cycle diff --stat
```

```
=== git status --short ===
 M CYCLE.md
 M README.md
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
?? core/context_store/
?? docs/EVALUATION-MEMORY-M1.md
?? tests/diagnostics/probe_memory_store.py
?? tests/unit/test_memory_store.py
=== git diff --stat ===
 CYCLE.md             |  2 +-
 README.md            |  3 +-
 docs/ARCHITECTURE.md |  2 +-
 docs/CHANGELOG.md    | 89 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 docs/MODULES.md      | 73 ++++++++++++++++++++++++++++++++++++++++++++++++--
 docs/OPERATIONS.md   |  2 +-
 6 files changed, 165 insertions(+), 6 deletions(-)
```

> `git diff --stat` **不含未跟踪的新文件**（`core/context_store/` 五个文件、本评估文档、
> 两个新测试）。新文件的权威依据是上面的 `??` 行与 §8 的备份点。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/context_store/units.py` | 新文件 | 单元结构 + 抽取：内容寻址 id / 关键词 / **符号引用** / `file:line` / 内容哈希（M1「时间·关键词·符号引用」） |
| 2 | `core/context_store/scope.py` | 新文件 | **独立根**（默认 `D:\PythonProject\08-memory`，在两侧仓库之外）+ **越界结构化拒绝**（约束 5） |
| 3 | `core/context_store/retrieval.py` | 新文件 | **两路召回**（关键词 / 结构符号）+ 记分；`calibrate()` 给漏召/误召读数与**候选**阈值曲线（硬要求 1/2/3） |
| 4 | `core/context_store/store.py` | 新文件 | `ContextStore`：`write`/`read`/`list_units`/`recall`/`calibrate`/`archive`/`profile`；索引 `units.jsonl`（约束 6：**没有删除路径**） |
| 5 | `core/context_store/__init__.py` | 新文件 | 包级 `describe()`：阶段 / 是否接主链路 / 根 / 召回 / 归档 / 下一期 |
| 6 | `tests/unit/test_memory_store.py` | 新文件 | M1 四条验收 + 三条硬要求 + 独立性（**71 项**，含反空洞） |
| 7 | `tests/diagnostics/probe_memory_store.py` | 新文件 | 五段机械取证（本文 §4 的原始回显都来自它） |
| 8 | `docs/CHANGELOG.md` | 新增 §45 | 过程记录 + §45.1 的"这一轮为什么只做这一件" |
| 9 | `docs/MODULES.md` | 新增 §34 | 模块与接口参考（含两条硬规则、两路召回、测试逃生口） |
| 10 | `README.md` | 文档导航加一行 + 版本戳 §44→§45 | 登记本评估文档（否则 `test_doc_invariants` 第 7 组会红） |
| 11 | `CYCLE.md` / `docs/ARCHITECTURE.md` / `docs/OPERATIONS.md` | 版本戳 §44→§45 | 文档一致性门禁要求 == CHANGELOG 最新条目 |
| 12 | `docs/EVALUATION-MEMORY-M1.md` | 新文件 | 本评估文档 |

**若两者不一致**：机械输出里 `git diff --stat` 不含第 1–7、12 项（未跟踪新文件）
与 `docs/VERSIONS.md`（由备份流程/本轮手工追加）；这几项的权威依据是 §8 的备份点。

**本轮刻意没碰的**：`main.py`、`tools/`、`core/` 下**任何既有模块**、`.interface_contract/`、
对侧仓库、集成工作区。§4.6 用 AST 与"工具数仍 18"证明这件事。

---

## 4. 主张与验证命令（对应 C2、C3）

> 以下回显全部来自 `tests/diagnostics/probe_memory_store.py` 与
> `tests/unit/test_memory_store.py` 的本轮实跑（原始粘贴，未概括）。

### 4.1 M1 验收① · 写入/读取**可机械复现**

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe tests\diagnostics\probe_memory_store.py
```

`[A]` 段回显：

```
  文本        : T9 失败是因为 reuse 层把 app.route 判成了「不存在的符号」
  第一次写入  : id=237496d3d750a77d status=written created=True
  第二次写入  : id=237496d3d750a77d status=exists deduped=True
  库内单元数  : 1
  读回的单元  :
   {
     "id": "237496d3d750a77d",
     "created_at": "2026-10-05T17:46:21",
     "keywords": ["app","positive","reuse","route","t9","不存在的符号","判成了","失败是因为","层把"],
     "symbol_refs": ["reuse","app","route","app.route"],
     "refs": [],
     "source": "T9",
     "sha256": "9156406895a1522f6a5ba86512db500e97447d65ef272750e948e85f25f0cd5b",
     "status": "active"
   }
  读回哈希 == 内容哈希: True
  重放两次 units.jsonl 逐字节相同: True
  units.jsonl（确定性排序，一行一条）:
   {"archived_at": null, "content": "第一条", "created_at": "2026-10-05T10:00:00", "id": "0c720ab2d9850122", …
   {"archived_at": null, "content": "第二条", "created_at": "2026-10-05T10:01:00", "id": "b0a9a18f0799a257", …
   {"archived_at": null, "content": "第三条", "created_at": "2026-10-05T10:02:00", "id": "22514c69da85fa2f", …
```

**主张**：同 source 同内容 ⇒ 同 id、**不重复**、读回**逐字相同**、重放 `units.jsonl`
**逐字节相同**。单测里另加了跨平台判据（CRLF/LF 归一 ⇒ 同 id）与"不同 source ⇒ 两条记忆"。

### 4.2 M1 验收② · 越界写被**结构化拒绝**（且文件真的没写出去）

`[B]` 段回显：

```
  请求路径: ../workspace/_p21_probe_should_not_exist.json
  拒绝信封: {"ok": false, "kind": "error", "error": {"code": "out-of-scope-write",
    "message": "路径越出记忆库根: D:\\…\\.tmp\\workspace\\_p21_probe_should_not_exist.json（库根 D:\\…\\.tmp\\p21_probe_41v4y0jl）",
    "path": "D:\\…\\.tmp\\workspace\\_p21_probe_should_not_exist.json",
    "allowed_roots": ["D:\\…\\.tmp\\p21_probe_41v4y0jl"], "hint": "不要用 `..` 逃出库根"}}
  目标文件是否被写出去: False
  拒绝码: out-of-scope-write
  允许的根: ['D:\\…\\.tmp\\p21_probe_41v4y0jl']
  绝对路径越界  : code=out-of-scope-write path=D:\PythonProject\SimpleAgent2_Cycle\core\x.json
  空路径        : code=empty-path message=库内路径为空
  库内合法路径  : D:\…\\.tmp\p21_probe_41v4y0jl\archive\x.json
  仍在库根之内  : True
```

> 拒绝信封形状与 `core/runtime.py::scope_error_result()` **逐键对齐**
> （`ok` / `kind` / `error{code,message,path,allowed_roots,hint}`）——
> 统筹方约束 5 说"复用 P15 的 `ScopeError` / `scope_error_result`"，
> 本模块**不 import `core.runtime`**（M1 是独立库），而是**同形**，
> 因此 M3 接入时一行适配即可。

### 4.3 M1 验收③ · 库根在**两侧仓库之外**（可机判）

`[C]` 段回显：

```
  ENV 开关      : AGENT_CONTEXT_STORE_ROOT
  默认库根      : D:\PythonProject\08-memory
  默认根命中仓库: None
  默认根在 SimpleAgent2_Cycle               内: False
  默认根在 SimpleAgent2_Cycle_VueWeb        内: False
  默认根在 SimpleAgent2_Integration         内: False
  把库根指进仓库的后果（三方各试一次）:
    D:\PythonProject\SimpleAgent2_Cycle ⇒ code=store-root-inside-repo
    D:\PythonProject\SimpleAgent2_Cycle_VueWeb ⇒ code=store-root-inside-repo
    D:\PythonProject\SimpleAgent2_Integration ⇒ code=store-root-inside-repo
  环境变量指向仓库内:
    code=store-root-inside-repo path=D:\PythonProject\SimpleAgent2_Cycle\.tmp\p21-env
```

**"可机判"** = `os.path.normcase` + 前缀比较（`scope.repo_of` / `scope.within`），
不是约定；默认根取统筹方建议的 `<work area>\08-memory`。

### 4.4 M1 验收④ · 淘汰 = **归档**，不是删除

`[D]` 段回显：

```
  归档前计数: {"units": 2, "active": 2, "archived": 0, "archive_files": 0, "max_units": 5000, "unreadable_index_lines": 0}
  归档返回  : {"ok": true, "id": "4efa533918f61970", "status": "archived",
              "archive_path": "archive/4efa533918f61970.json", "unit": {… "status": "archived", "archived_at": "2026-10-05T09:46:21+00:00" …}}
  归档后计数: {"units": 2, "active": 1, "archived": 1, "archive_files": 1, "max_units": 5000, "unreadable_index_lines": 0}
  归档后仍读得到原文: True content='要归档的旧记忆：reuse 层误判'
  索引里的状态      : status=archived archived_at=2026-10-05T09:46:21+00:00
  归档层文件        : archive/4efa533918f61970.json （存在=True）
  删除类方法        : 无
  profile.delete_path: None
```

> `删除类方法: 无` 是**机械判据**：单测扫 `dir(store)` 里是否出现
> `delete` / `remove` / `purge` / `drop`，一个都没有 ⇒ "淘汰只归档"不是纪律口号，是可机判事实。

### 4.5 三条硬要求 · 漏召/误召 + 第二路召回 + 只记分不决策

`[E]` 段回显：

```
  关键词路 reuse/false-positive          → [('9dfdb57cc468608c', 1.098612, 'keyword')]
  符号路 build_index_report             → [('22166abfe4011d5a', 0.4, 'symbol')]
  关键词路 auth/token                    → [('f70b7d17fb5cb873', 1.098612, 'keyword')]
  关键词路 cleanup                       → [('74e0aac29305e6dc', 0.549306, 'keyword')]
  符号路 no_such_symbol_anywhere        → []
  单元 id 对照: A=9dfdb57cc468608c B=22166abfe4011d5a C=f70b7d17fb5cb873 D=74e0aac29305e6dc
  分数分布    : {"values": [1.098612], "count": 1, "min": 1.098612, "max": 1.098612, "mean": 1.098612}
  合计读数: {"cases": 5, "cases_with_labels": 5, "relevant": 5, "hit": 3, "retrieved": 4,
            "false_recalled": 1, "micro_recall": 0.6, "micro_precision": 0.75,
            "macro_recall": 0.6, "miss_rate": 0.4, "false_recall_rate": 0.2}
  逐条漏召/误召:
    关键词该召 A                              recall=1.0 precision=1.0 failures=[] missed=[] false_recalled=[]
    符号该召 B（关键词召不回）                       recall=1.0 precision=1.0 failures=[] missed=[] false_recalled=[]
    关键词该召 C                              recall=1.0 precision=1.0 failures=[] missed=[] false_recalled=[]
    误召（相关的是 A，实际召回 D…）                   recall=0.0 precision=0.0 failures=['miss', 'false-recall'] missed=['9dfdb57cc468608c'] false_recalled=['74e0aac29305e6dc']
    漏召（库里有 A，查询召不回）                      recall=0.0 precision=None failures=['miss'] missed=['9dfdb57cc468608c'] false_recalled=[]
  候选阈值曲线（前若干行；**不推荐阈值**）:
    thr=0.4      kept=1 tp=1 fp=0 fn=0 P=1.0 R=1.0 F1=1.0
    …
  点数=75 recommended_threshold=None
```

| 硬要求 | 判据 | 本轮读数 |
|---|---|---|
| ① 覆盖漏召 / 误召 | `missed` / `false_recalled` / `failures` + `miss_rate` / `false_recall_rate` | `miss_rate=0.4`、`false_recall_rate=0.2`、`micro_recall=0.6` —— **不是"调用成功"** |
| ② 第二路召回挂在结构索引上 | 单元 B 的**关键词与正文都没有查询词面**，只有 `symbol_refs` 命中 | 符号路召回 B（`paths=['symbol']`）；`structure_lookup.via = find_symbol\|get_module\|get_architecture`；`new_keyword_library=False` |
| ③ 阈值不许定死 | `recall()` 无阈值参数；返回**全部**候选；`calibrate()` 只给曲线 | 单测 `inspect.signature` 钉住"无 threshold 参数"；`recommended_threshold=None`；`threshold=None` / `decision="none"` |

**反空洞（"不是把检查关掉"）**：单测里那个"关键词绝对召不回"的单元就是第二路召回
**有没有牙**的判据 —— 若把 `symbol_hits` 摘掉，它立刻变空/召不回（单测当场红）。

### 4.6 独立性 · "不接模型"是可机判的（约束 4 的前置）

`[9]` 段回显：

```
  core/context_store 的 import: ['.', '.store', '__future__', 'datetime', 'hashlib', 'json', 'math', 'os', 're']
  PASS  ★ 不 import 任何主链路模块（core.* / tools.*）
  PASS  ★ 只用标准库（无新依赖 ⇒ 没有把环境改掉）
  PASS  ★ 相对导入只指向本包自己（独立库，不反向依赖主链路）
  PASS  ★ 没有把记忆库注册成工具（工具数仍是 18）
  PASS  ContextStore 也没有 @register 装饰器
  PASS  ★ main.py 未引用 context_store（M1 不接入）
  PASS  ★ profile() 自陈未接主链路 + 阶段是 M1
```

⇒ M1 **没有**改变主链路：`main.py` 未引用、`TOOLS_MAP` 仍 18 个、包内只有标准库与相对导入。
统筹方约束 4 说"**在跨模型对比结论出来之前，不得进主链路**"——
本轮把这条从"纪律"变成了**机判事实**（`profile()["wired_into_main_chain"] is False`）。

### 4.7 `profile()` 的可读事实（两处诚实标注）

`[E]` 段末回显：

```json
{
  "phase": "M1",
  "wired_into_main_chain": false,
  "root": "D:\\…\\.tmp\\p21_probe_r83wy3ne",
  "outside_repos": {
    "repos": ["D:\\PythonProject\\SimpleAgent2_Cycle",
              "D:\\PythonProject\\SimpleAgent2_Cycle_VueWeb",
              "D:\\PythonProject\\SimpleAgent2_Integration"],
    "root_repo": "D:\\PythonProject\\SimpleAgent2_Cycle",
    "ok": false,
    "relaxed": true
  },
  "counts": {"units": 4, "active": 4, "archived": 0, "archive_files": 0, "max_units": 5000, "unreadable_index_lines": 0},
  "delete_path": null,
  "recall_weights": {"keyword": 0.5, "symbol": 0.4},
  "recall_threshold": null,
  "recall_paths": ["keyword", "symbol"],
  "unit_keys": ["id","created_at","content","keywords","symbol_refs","refs","source","sha256","status","archived_at"]
}
```

**两处必须点名的诚实标注**：

1. `"relaxed": true` —— 探针/单测的临时库根在 `.tmp/`（**仓库内**），
   因为本轮硬边界**只许写本仓库**，而 M1 要求库根在仓库之外 ⇒ 两者直接冲突。
   处置：给 `assert_outside_repos()` / `ContextStore()` 加一个**显式关键字**逃生口
   `allow_inside_repos=True`，**只能显式传**（生产代码无一处会传），
   且放宽事实会印在 `profile()["scope"]["outside_repos"]["relaxed"]`。
   **默认值仍是拒绝**（§4.3 的三条仓库 + 环境变量共四例证明不传就拦）。
   探针末尾也如实打印"默认库根未被创建"。
2. `"unreadable_index_lines": 0` —— 索引坏行也是事实（"读不出来"≠"不存在"），
   `profile()` 把它印出来而不是静默跳过。

### 4.8 其他门禁

| # | 主张 | 验证命令 | 结果 |
|---|---|---|---|
| 1 | 新增单测通过 | `python tests\unit\test_memory_store.py` | **71/71**（exit 0） |
| 2 | 全量单测通过 | `python tests\run_unit.py` | **50/50**（exit 0） |
| 3 | 文档一致性通过 | `python tests\unit\test_doc_consistency.py` | **35/35**（exit 0） |
| 4 | 文档不变量通过 | `python tests\unit\test_doc_invariants.py` | **35/35**（exit 0） |
| 5 | 文档审查通过 | `python tests\unit\test_doc_review.py` | **18/18**（exit 0） |
| 6 | 契约符合性通过 | `python tests\unit\test_contract_conformance.py` | **44/44**（exit 0） |
| 7 | 前端契约通过 | `python tests\unit\test_frontend_contract.py` | **25/25**（exit 0） |
| 8 | 套件卫生通过 | `python tests\unit\test_suite_hygiene.py` | **4/4**（exit 0） |

> 一条**踩过的坑**（记一笔，避免下次误判）：把 `run_unit.py` 的输出接进
> `Select-String` 管道时，PowerShell 会报告 `[exit code: 1]` —— 那是管道的退出码，
> **不是**测试失败。判据要看它自己打印的 `通过 50/50`；重定向到文件时
> `$LASTEXITCODE = 0`。所以上面每一条都记了 exit code。

**未验证的部分**（诚实列出，比假装验过有价值）：

- **没有用真实数据校准阈值**（M2 才做）。本轮的 `threshold_curve` 只有 5 条标注样例，
  **不足以**支持任何阈值主张 —— 所以 `recommended_threshold` 恒为 `None`，
  这正是硬要求 3"只记分、不决策"的落点。
- **没有把第二路召回接到 `find_symbol` / `get_module` / `get_architecture` 的实调用上**：
  M1 只产出 `structure_lookup` 这个**原料**（`{symbols, via}`），
  真正去查结构索引属于 M2/M3（接入）。这样 M1 才保持"独立库、不依赖主链路"。
- **没有做 M2 的"分数 + 事后判定落盘"、没有做 M3 的一键开关与接入**：
  统筹方明写"三期、**不许跳级**"，且 M3 **需用户批准**。
- **没有真去创建默认库根** `D:\PythonProject\08-memory`：那会写到本仓库之外的
  平台目录，违反本轮硬边界（与工作单"绝不写进两侧仓库"的隔离要求同向）。
  默认根的隔离性用**纯路径计算**证明（§4.3）。
- **没有改 `.interface_contract/`**（只读），也没有跑/改统筹方的门禁脚本。
- **`keywords_from()` 的正文兜底抽取是启发式**（中文整串、英文标识符 + 停用词表）：
  它的作用是"让没带关键词的记忆**至少**能被召回"（防静默漏召），
  质量由 M2 的分数校准来治 —— 这一点写进了 `units.describe()`，不是隐藏行为。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 仍 18 种（本模块**一个事件都不发**） |
| 事件 payload 键 | **无** | 未动 |
| 上游 `PHASE_ORDER` 阶段 | **无** | 仍 `plan/write/check/verify/record` |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | 未动 |
| `TOOLS_MAP` 条目结构 | **无** | 仍 18 个工具；本模块**不注册成工具** |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 仍 `1.1` / `1.0` / `1.0` |
| 端点路径 | **无** | 未动；`/profile` 也**没有**加 `context_store` 段（M1 不接入 ⇒ 不该出现在接口上） |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 只读未动 |

**结论**：本次对接口契约**零改动、零破坏**。这不是"加性变更"——
而是**根本不在接口面上**：没有生产代码 import 它，也没有任何事件/字段/端点变化
（§4.6 的 AST + 工具数 + `main.py` 三条判据）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不要**。M1 不产生任何前端可见事实：
  无事件、无端点、无 `/profile` 字段、无 `CycleReport` 字段。
  前端**没有东西可显示，也就不会静默少显示**。
- **有没有可能"问题被平移到对侧"**？**没有**。这条工作完全在本仓库内部，
  且**不接入**主链路 ⇒ 对侧的行为与读数**逐字节不变**。
- **如果将来 M3 接入**：那会改变模型的输入（检索结果进上下文），
  所以统筹方约束 4 要求"**必须能一键关闭**（A/B 开关）"、
  "**在跨模型对比结论出来之前，不得进主链路**"。
  本轮把 `wired_into_main_chain=False` 做成**机判字段**，
  等于给 M3 留了一个可核对的起点；M3 需要用户批准，不在本轮范围。
- **会静默少显示什么吗**？不会 —— 本轮没有任何接口面变化。

---

## 7. 不做的部分及理由（对应 C7）

- **不做 M2（记分不决策的落盘）与 M3（接入 + 一键关）**：
  `DISPATCH.md` ⓪ 逐字「**本轮的活只有 M1**」；`WORK-ORDER.md`【P21】明写
  「M1/M2/M3 三期验收，**不许跳级**」，且 **M3 需用户批准**。
- **不把第二路召回接到结构索引的实调用上**：`symbol_refs` 是**原料**，
  M1 把它如实带出（`structure_lookup`）；真正查 `find_symbol`/`get_module`/
  `get_architecture` 属于接入期 —— 否则 M1 就不再是"独立库"。
- **不定阈值、不推荐阈值**：统筹方硬要求 3「阈值第一阶段不许定死：只记分、不决策，
  用数据校准（我在 S3 上刚栽过「拍阈值」）」。
- **不引新依赖**（无向量库 / 无 RAG / 无外部包）：M1 只用标准库（§4.6 的 AST 判据）。
- **不动 P16（多语言）**：`DISPATCH.md` 逐字「P16（多语言）现在别动」。
- **不重做 D38–D43**：§2.2 逐条给了"已交付"的机械依据。
- **不动 `core/memory.py`（`SharedMemory`）**：它是一轮运行内的全局状态，
  与"跨任务外部记忆库"是两件事；改名或合并会让既有读数失真。
- **不往默认库根 `D:\PythonProject\08-memory` 写任何东西**：那在本仓库之外 ⇒
  违反本轮硬边界；隔离性用纯路径计算证明。
- **不手工重排 `VERSIONS.md` 历史条目**：只在末尾追加本轮条目（历史只增不改）。

---

## 8. 回退点（对应 C8）

- **回退命令**：`git reset --hard <v1.31 备份点>`（定位：
  `git log --oneline --grep "^v1.31:"`）。
- **回退会丢什么**：`core/context_store/` 整个包、两个新测试、本评估文档、
  CHANGELOG §45、MODULES §34、README 登记行与五处版本戳。
- **更细粒度的回退**（不用回退整个提交）：
  - 只想去掉这层能力：**删掉 `core/context_store/` 即可** —— 没有任何生产代码
    引用它（`main.py` 未 import、无工具注册）⇒ 删除后主链路行为不变；
  - 换库根：`AGENT_CONTEXT_STORE_ROOT=<path>`（在仓库之外；指进仓库会被结构化拒绝）；
  - 不想要归档也不想要删除：`archive()` 本身是**唯一**的淘汰入口，且它只复制+改状态。
- **回退不会丢什么**：不存在需要"迁移回来"的持久状态 —— 除了临时库根
  （`.tmp/`，探针会自行清理；默认库根本轮**从未创建**）。

---

## 9. 自检结论

- **C1 问题陈述可复现**：满足。§2.1 用 sha256 证明载荷与 `ROUND.json` 同源；
  §2.2 逐条给出"已交付/不动/可做"的核对命令与回显；§2.3 给出"改动前没有外部记忆库"的取证。
- **C2 每条主张带可复现验证命令**：满足。§4.1–§4.8 每条都有完整命令与原始回显；
  四条验收各占一段（§4.1–§4.4），三条硬要求有专段（§4.5）。
- **C3 命令实测输出支持该主张**：满足。所有回显均来自本轮实跑；
  反空洞判据（"关键词绝对召不回"的单元、`删除类方法: 无`、三仓库隔离各试一次、
  AST import 扫描）都贴在正文里。
- **C4 改动清单与实际一致**：满足。§3 先贴 `git status --short` + `git diff --stat`，
  并显式点出机械输出**不含**未跟踪的新文件与 `VERSIONS.md`（以备份点为准）。
- **C5 对接口契约的影响已声明**：满足。§5 逐项写"无"，并说明这不是"加性"而是**不在接口面上**。
- **C6 对另一侧的影响已评估**：满足。§6 结论是"不需要跟改、不平移、不静默少显示"，
  并把 M3 的接入风险与统筹方约束 4 的对应关系写明。
- **C7 未把接口级问题当内部问题处理**：满足。§7 明确划出未做范围（M2/M3、真实阈值校准、
  结构索引实调用、P16、`core/memory.py`），并说明每一条的**理由**（多数是工单明写的不许跳级/不许动）。
- **C8 回退点明确**：满足。§8 给出 `git reset --hard` 的定位命令、回退会丢什么，
  以及"删掉一个包即可，无生产引用"的细粒度回退。
- **契约目录只读**：满足。`.interface_contract/` 未被写入（只读取 `ROUND.json`/`DISPATCH.md`/
  `WORK-ORDER.md` 与模板）。
- **对侧仓库 / 集成工作区未写入**：满足。本轮所有写操作都在
  `D:\PythonProject\SimpleAgent2_Cycle` 内；`08-memory` 默认库根**只做路径计算、未创建**。
- **未改环境**：满足。没有 `pip install` 任何东西；新包只用标准库（§4.6）。

**希望统筹重点验证哪一条**：

**§4.5 的第二路召回那条反空洞** —— 用一个"关键词与正文都没有查询词面重叠、
只有 `symbol_refs` 命中"的单元证明：第二路不是装饰，而且它走的是**同一份符号引用**
（`structure_lookup.via = find_symbol|get_module|get_architecture`），
**没有另起关键词库**。这条直接对应统筹方硬要求 2，也是"漏召不会变成静默"
（硬要求 1）能不能成立的关键。
