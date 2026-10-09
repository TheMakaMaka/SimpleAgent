# 变更评估文档 · `MEMORY-SCORING`（P21 ★★：**调用分算法必须与模型无关**）

- **变更编号**：`MEMORY-SCORING`（工作单 **P21** 的 2026-10-05 新增节 **★★ / ★★★**；`DISPATCH.md` ⓪ 点名的 M1 范围内的打分层）
- **提出方**：用户（2026-10-04 追问「用哪个 / 实思路」）+ 统筹（`WORK-ORDER.md`【P21】新增两节）
- **执行侧**：backend
- **日期**：2026-10-05
- **契约版本**：`1.0.34`（`ROUND.json` 随载荷声明；本轮**未改契约**）
- **本轮 round_id**：`R-d11562e8d6` —— **本轮完成 `R-d11562e8d6`**（下一轮据此判断要不要开工）

> **交付状态说明（诚实记录）**：本轮从 `ROUND.json` 的 `round_id = R-d11562e8d6` 开工，
> 与仓库里上一轮记录的 `R-c0c8ba72e3`（`docs/EVALUATION-MEMORY-M1.md`）**不同** ⇒ 有新指令。
> `DISPATCH.md` **逐字节未变**（`dispatch_sha256 = c2fe1af135a193bf`，实测一致），
> 变的是 `WORK-ORDER.md`（上一轮记录的 `90ad6f724a1f369d` → 本轮 `eae6e312c0b12851`）。
> §2.1 用**可复现的哈希手术**证明：差的正是【P21】里新增的两节
> （`★★ 第四条硬要求 …… 调用分算法必须与模型无关` 与
> `★★★ 三种 scorer 同台对照`）。因此本轮的活 = **把已交付的 M1 打分层补齐到新增的硬要求上**，
> **不跳级做 M2/M3**（`DISPATCH.md` 逐字「本轮的活只有 M1」；`WORK-ORDER.md` 明写「不许跳级」）。

---

## 1. 变更意图

### 1.1 本轮新增的载荷原文（逐字，来自 `WORK-ORDER.md`【P21】）

> ### ★★ 第四条硬要求（用户 2026-10-04 追问「用哪个 / 实思路」后补）—— **调用分算法必须与模型无关**
>
> **我原先漏了这条，而它足以毁掉整个设计。**「调用分」由谁算，有三种选择，后果完全不同：
>
> | 选择 | 后果 | 判定 |
> |---|---|---|
> | **① 由 LLM 打分**… | 用被测模型 ⇒ 换模型会改变检索结果（可比性危险）… | **⚠ 不许禁，也不许默认 —— 作为对照臂之一** |
> | **② 固定不变的嵌入模型**算语义相似 | 可比性保住了…但要**引入新依赖 + 一个必须版本锁定的模型** | **△ 若要用，必须：独立配置 · 版本锁定 · 只读 · 与被测模型彻底分离 · 且计入"可一键关"的范围** |
> | **③ 确定性算法**：词法（BM25/关键词）+ **符号图** + 时间衰减 + 显式定制权重 | **完全可复现 · 零 token · 不随模型变 · 无需新依赖** | **✅ 默认方案** |
>
> **因此本次规定的实现思路（M1/M2 就按它做）**：
>
> 1. **打分必须是纯函数**：`score(unit, query_context) -> float`，**输入只有单元内容、查询上下文与配置权重**；
>    **不得调用任何模型**（既不得调被测模型，也不得调任何 LLM）。
> 2. **打分必须可复现**：同一输入两次调用**逐位相同**（浮点也要求一致或可解释）；
>    写成测试：同输入两次 `score()` ⇒ 相等。
> 3. **分数要可解释**：每个单元返回**分数构成**（词法命中 / 符号命中 / 时间衰减 / 定制加权各贡献多少），
>    便于校准阈值时看懂"为什么它得了这个分"。
> 4. **"定制化需求加权"走显式配置**（谁在什么条件下加多少），**不许让模型自由决定权重**。
> 5. **阈值来自数据校准**（见硬要求 3），**校准过程本身也必须可复现**（记录用哪些样本、算出哪条曲线）。
>
> **★★★ 用户 2026-10-04 的建议：三种 scorer 同台对照，别先禁掉任何一种**
>
> | 臂 | scorer |
> |---|---|
> | **S-A** | **确定性**：词法 + **符号图** + 时间衰减 + 显式定制权重 |
> | **S-B** | **固定嵌入模型**（版本锁定、独立配置） |
> | **S-C** | **LLM 打分** —— 但**以工具身份**接入 |
>
> **我的建议顺序**：**先做 S-A**（M1/M2 都用它当基线，因为它是唯一"完全不引入新变量"的），
> **再把 S-B / S-C 作为对照臂加上**。
> **并且**：**scorer 的选择必须进 `basis`**（与 `model` 并列）——
> 否则"换了 scorer 之后读数变了"会被误读成"模型变强了/变弱了"。

### 1.2 本轮范围的判定（为什么只做打分层，不做 M2 对照臂）

| 依据 | 原文 | 结论 |
|---|---|---|
| `DISPATCH.md` ⓪ | 「**本轮的活只有 M1**：存储与检索 + 独立根 + 越界拒绝，**不接模型**」 | **只在 M1 内** |
| `WORK-ORDER.md` 分期表 | 「M1/M2/M3 三期验收，**不许跳级**」；M3「**需用户批准**」 | **不进 M2/M3** |
| `WORK-ORDER.md` ★★ | 「**本次规定的实现思路（M1/M2 就按它做）**」 | ★★ 的 1–5 条**适用于 M1** ⇒ 本轮落它 |
| `WORK-ORDER.md` ★★★ | 「**对照设计（M2 的核心活儿）**」 | 三臂对照 = **M2**，本轮只做 **S-A 基线** + 归因位 |
| `ROLE-BRIEF.md` §0.4 | 「**不许改环境**：不要 `pip install` 装东西来"让测试过"」 | `S-B`（嵌入模型）**不能**在本轮实现 |

⇒ 本轮 = **M1 打分层符合性**：`score()` 纯函数 + 可复现 + 四项构成 + 定制加权显式配置 + 校准可复现，
并把 **scorer 身份放进 `basis`**（S-A 已实现；S-B/S-C 如实标「未实现」）。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 本轮新内容是什么 —— 用哈希手术机判（不是猜、不是自述）

`ROUND.json` 声明 `work_order_sha256 = eae6e312c0b12851`；上一轮评估文档记录的是
`90ad6f724a1f369d`。把当前 `WORK-ORDER.md` 里【P21】新增的两节**整段删掉**，
剩余文本的 sha256 **应当逐位等于上一轮的哈希**：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe D:\PythonProject\SimpleAgent2_Cycle\.tmp\find_prev_wo.py
```

实际输出（原始回显）：

```
current bytes: 52626 sha256: eae6e312c0b12851
CRLF count: 0 LF count: 817
markers: 24656 25813 27116
remove ★★+★★★ block          bytes= 47291 sha256=90ad6f724a1f369d  MATCH=True
remove ★★★ only              bytes= 49909 sha256=d3d3aa600224d222  MATCH=False
remove ★★ only               bytes= 50008 sha256=357fc19e5a65fe46  MATCH=False
short-wording swaps          bytes= 52649 sha256=b667c5f8e09d62bb  MATCH=False
```

⇒ **只有**同时删掉 `★★ 第四条硬要求` 与 `★★★ 三种 scorer` 两节，才复现上一轮的哈希
（其余候选都 `MATCH=False`）⇒ 本轮新增内容**就是这两节**，且它落在 M1 明确适用的范围里
（★★ 原文：「M1/M2 就按它做」）。

### 2.2 旧打分层（v1.31）的缺口 —— 机械取证

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle show 949330f:core/context_store/retrieval.py | Select-String -Pattern '^def score|score_breakdown|time_decay|custom_bonus|config_sha256'
```

实际输出：

```
(以上为空 = 旧版没有这些)
```

`score_parts` 的形状（同一 commit）：

```
=== v1.31 的 score_parts 形状 ===
            "score_parts": {
                "keyword": round(W_KEYWORD * kw["score"], 6),
                "symbol": round(W_SYMBOL * sym["score"], 6),
            },
```

对照新增的 1–5 条硬要求：

| 新增硬要求 | v1.31 的事实 | 缺口 |
|---|---|---|
| 1 纯函数 `score(unit, query_context) -> float` | 搜 `^def score` **0 条** | **没有入口** |
| 2 同输入两次逐位相同 + 写成测试 | 没有该判据 | **无判据** |
| 3 四项构成 (词法/符号/时间衰减/定制加权) | `score_parts` **只有 2 键** | 缺 `time_decay` / `custom` |
| 4 定制加权走显式配置 | 只有两个模块常量，没有规则表 | **无显式配置** |
| 5 校准过程可复现 | `calibrate()` 只回曲线 | **无样本/配置/曲线指纹** |

### 2.3 现状取证（改动前）的两条旁证

* 旧 `recall()` 结果里没有 `basis`，也没有 `score_explain` ⇒ 「scorer 的选择必须进 `basis`」无处安放；
* 旧 `describe()["recall"]` 没有 `scorer` 段 ⇒ 契约面上看不出用的是哪条臂，更看不出 S-B/S-C 是否存在。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威；快照时本评估文档与 `docs/VERSIONS.md` 的 v1.32 条目尚未落盘）**

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle -c core.quotepath=false status --short
git -c safe.directory=D:\PythonProject\SimpleAgent2_Cycle -c core.quotepath=false diff --stat
```

```
=== git status --short ===
 M CYCLE.md
 M README.md
 M core/context_store/__init__.py
 M core/context_store/retrieval.py
 M core/context_store/store.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
?? tests/diagnostics/probe_memory_scoring.py
?? tests/unit/test_memory_scoring.py
=== git diff --stat ===
 CYCLE.md                        |   2 +-
 README.md                       |   3 +-
 core/context_store/__init__.py  |  11 +-
 core/context_store/retrieval.py | 428 +++++++++++++++++++++++++++++++++++++---
 core/context_store/store.py     |  24 ++-
 docs/ARCHITECTURE.md            |   2 +-
 docs/CHANGELOG.md               |  68 +++++++
 docs/MODULES.md                 |  61 +++++-
 docs/OPERATIONS.md              |   2 +-
 9 files changed, 559 insertions(+), 42 deletions(-)
```

> `git diff --stat` **不含未跟踪的新文件**（两个新测试）与 `docs/EVALUATION-MEMORY-SCORING.md`、
> `docs/VERSIONS.md`。它们的权威依据是上面的 `??` 行与 §8 的备份点。

**手写导读（非判据）**

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `core/context_store/retrieval.py` | `score()` / `score_breakdown()` | ★★ 第 1/2/3 条：**唯一纯函数入口** + 四项构成相加 == 总分 |
| 2 | 同上 | `time_decay_factor()` | ★★ 第 3 条：时间衰减**纯函数**（`now` 显式；`half_life_days=None` 默认关闭） |
| 3 | 同上 | `canonical_config()` / `config_sha256()` / `custom_bonus()` | ★★ 第 4 条：定制加权**显式配置**，非法配置结构化拒绝 |
| 4 | 同上 | `calibrate()` | ★★ 第 5 条：`config_sha256` + `samples_sha256` + `curve_sha256` |
| 5 | 同上 | `recall()` / `describe()` / `scoring_profile()` | ★★★ :`basis`（scorer 与 model 并列）+ scorer 臂清单 |
| 6 | `core/context_store/store.py` | `recall()` / `calibrate()` / `profile()` | 转发 `config` / `now`；`profile()["scoring"]`；`STORE_VERSION` `m1.1`→`m1.2` |
| 7 | `core/context_store/__init__.py` | exports / `describe()` | 公开 `score` / `score_breakdown` / `scoring_profile` / `SCORER_ID` |
| 8 | `tests/unit/test_memory_scoring.py` | 新文件 | ★★ 判据 **63 项**（含 4 条反空洞） |
| 9 | `tests/diagnostics/probe_memory_scoring.py` | 新文件 | 六段机械取证（本文 §4 的原始回显都来自它） |
| 10 | `docs/CHANGELOG.md` | 新增 §46 | 过程记录 |
| 11 | `docs/MODULES.md` | 新增 §35 + §34.4 融合式更新 | 模块与接口参考 |
| 12 | `README.md` | 文档导航 + 一行 + 版本戳 | 登记本评估文档（否则 `test_doc_invariants` 第 7 组会红） |
| 13 | `CYCLE.md` / `docs/ARCHITECTURE.md` / `docs/OPERATIONS.md` | 版本戳 §45→§46 | 文档一致性门禁要求 == CHANGELOG 最新条目 |
| 14 | `docs/VERSIONS.md` | 追加 v1.32 条目 | 版本记录 |

**若两者不一致**：以 §3 的机械输出为准；第 8/9/14 项与本文档在快照时尚未落盘/未跟踪。

**本轮刻意没碰的**：`main.py`、`tools/`、`core/` 下**任何既有模块**、`core/context_store/units.py`、
`core/context_store/scope.py`、`.interface_contract/`、对侧仓库、集成工作区。

---

## 4. 主张与验证命令（对应 C2、C3）

> 以下回显全部来自 `tests/diagnostics/probe_memory_scoring.py` 与
> `tests/unit/test_memory_scoring.py` 的本轮实跑（原始粘贴，未概括）。

### 4.1 六段机械取证（探针原文）

```powershell
cd D:\PythonProject\SimpleAgent2_Cycle
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe tests\diagnostics\probe_memory_scoring.py
```

```
==========================================================================
[F1] 纯函数入口：score(unit, query_context) -> float
==========================================================================
  score 签名      : score(unit: 'dict', query_context: 'dict') -> 'float'
  形参            : ['unit', 'query_context']
  score() 返回值  : 0.262537683  (float)
  score == breakdown.score : True
  调用后入参未被改         : True
  配置权重是声明输入之一   : True (config_sha256=44bb9450bb4991f7)
  PASS  score 恰好两个形参 (unit, query_context)
  PASS  score 返回 float（唯一实现：== score_breakdown）
  PASS  不改入参（纯函数）

==========================================================================
[F2] 可复现：同输入逐位相同 · 不读时钟 · 不碰网络（含反空洞）
==========================================================================
  同输入 5 次      : [0.262537683, 0.262537683, 0.262537683, 0.262537683, 0.262537683]
  repr 集合大小    : 1
  PASS  同输入两次 ⇒ 逐位相同
  时钟+网络双 tripwire 下 : [0.262537683, 0.262537683]
  时间衰减仍可算          : factor=0.015565768
  PASS  时钟 tripwire 下仍算得出 ⇒ 不读时钟
  PASS  网络 tripwire 下仍算得出 ⇒ 不碰网络
  ★ 反空洞：换成漂移打分器 ⇒ [0.982973248, 0.991027899]  （同一条判据判不可复现: True）
  PASS  ★ 反空洞：非确定性打分器被同一条判据判红
  PASS  ★ 恢复真打分器 ⇒ 判据回到绿（红/绿同源）
  PASS  ★ 反空洞：读时钟的打分器被 tripwire 抓住

==========================================================================
[F3] 分数可解释：四项构成相加 == 总分
==========================================================================
  单元文本        : reuse 层把 app.route 判成不存在符号
  构成            : {"lexical": 0.405465108, "symbol": 0.4, "time_decay": -0.792927425, "custom": 0.25}
  四项之和        : 0.262537683
  总分            : 0.262537683
  逐项理由        : lexical={'reuse': 'declared-keyword', 'positive': 'declared-keyword'} symbol=['app.route']
                    time_decay=0.5 ** (age/365.0)，下限 min_factor factor=0.015565768
                    custom=['用户定制：T9 相关记忆加权']
  PASS  构成恰好四项（lexical/symbol/time_decay/custom）
  PASS  四项相加 == 总分
  PASS  四项都有理由可读（可解释，不是黑箱）
  默认（half_life=None）: time_decay=0.0 applied=False
  PASS  ★ 默认配置时间衰减关闭（half_life 参数没被拍死）
  半衰期 → 因子   : [(3650.0, 0.659503424), (730.0, 0.124762846), (365.0, 0.015565768), (30.0, 0.0)]
  PASS  时间衰减随半衰期单调减小（形状可预期）
  下限 min_factor : 0.25（配置 0.25）
  PASS  min_factor 下限生效（可配置成「不许衰减到 0」）
  PASS  ★ 反空洞：改掉某一项 ⇒ 同一条对账判据判红

==========================================================================
[F4] 定制加权 = 显式配置（谁 / 在什么条件下 / 加多少）
==========================================================================
  无规则 → 有规则 : 0.202732554 → 0.452732554（差 0.25）
  默认规则表      : []
  PASS  默认没有任何定制规则（权重不是藏起来的默认值）
  PASS  加一条规则 ⇒ 分数恰好加 add
  PASS  缺 why（『谁』不许省）          ⇒ ValueError: config[custom][0].why 必填（'谁在什么条件下加多少'里的『谁』不许省）
  PASS  未知条件键                  ⇒ ValueError: config[custom][0].when 出现未声明条件键 ['module']（可用 ['id', 'source', 'keywor
  PASS  条件值不是列表                ⇒ ValueError: config[custom][0].when[source] 必须是列表
  PASS  空条件                    ⇒ ValueError: config[custom][0].when 必须是非空对象
  PASS  负半衰期                   ⇒ ValueError: config[time_decay][half_life_days] 必须 > 0（或 None=关闭）
  PASS  下限越界                   ⇒ ValueError: config[time_decay][min_factor] 必须落在 [0, 1]
  PASS  权重不是数字                 ⇒ ValueError: config[weights][lexical] 必须是数字，收到 str
  PASS  未声明权重键                 ⇒ ValueError: config[weights] 出现未声明键 ['unknown']
  PASS  规则里出现未声明键              ⇒ ValueError: config[custom][0] 出现未声明键 ['extra']
  规范化配置      : {"custom": [{"add": 0.25, "when": {"source": ["T9"]}, "why": "用户定制：T9 相关记忆加权"}], "lexical": {"content": 0.6, "declared": 1.0}, "time_decay": {"half_life_days": 365.0, "min_factor": 0.0}, "weights": {"lexical": 0.5, "symbol": 0.4}}
  PASS  配置可 JSON 往返 & 不含任何模型字段
  PASS  配置指纹对配置敏感

==========================================================================
[F5] 校准过程可复现：samples / config / curve 三个指纹
==========================================================================
  第 1 次  config=3497bcb547f40285 samples=d6fb53e508900cc2 curve=7953c24a617773eb
  第 2 次  config=3497bcb547f40285 samples=d6fb53e508900cc2 curve=7953c24a617773eb
  换权重    config=44b47baab0adaa35 samples=d6fb53e508900cc2 curve=2611379aa5b79e42
  样本清单        : [{"id": "关键词命中", "relevant": ["9dfdb57cc468608c"]}, {"id": "符号命中", "relevant": ["22166abfe4011d5a"]}, {"id": "误召", "relevant": ["9dfdb57cc468608c"]}, {"id": "漏召", "relevant": ["9dfdb57cc468608c"]}]
  PASS  同样本同配置两次 ⇒ 三个指纹全部相同
  PASS  记录点名了用哪些样本（可复现的样本集）
  PASS  ★ 换配置且重算召回 ⇒ config 与 curve 指纹都变
  PASS  ★ 反空洞：改一条样本的标注 ⇒ samples 指纹变
  recommended_threshold = None
  PASS  校准仍不推荐阈值（第一阶段只记分）

==========================================================================
[F6] scorer 身份进 basis；S-B/S-C 如实标未实现；仍是 M1
==========================================================================
  basis           : {"scorer": "S-A", "scorer_kind": "deterministic", "model": null, "config_sha256": "3497bcb547f40285c0cb0cec68c7a1ecac563199a350e988cb9431092a16ff0a"}
  describe.scorer : {"id": "S-A", "kind": "deterministic", "model": null, "why": "确定性算法（词法 + 符号图 + 显式时间衰减 + 显式定制权重）：完全可复现、零 token、不随模型变、无需新依赖", "arms": {"S-A": "确定性（本模块已实现，M1/M2 的基线臂）", "S-B": "固定嵌入模型（版本锁定、独立配置）—— **M2 对照臂，未实现**", "S-C": "LLM 打分（以工具身份接入）—— **M2 对照臂，未实现**"}, "one_switch": "M1 未接入主链路；M3 接入时必须可一键关（否则分不清「模型变强」还是「记忆层变好」）"}
  profile.scoring : scorer=S-A pure=True model_free=True clock_free=True
  score_parts     : ['lexical', 'symbol', 'time_decay', 'custom']
  phase / wired   : M1 / False (threshold=None, decision=none)
  PASS  basis: scorer 与 model 并列（scorer=S-A, model=None）
  PASS  basis 带配置指纹
  PASS  S-A 标已实现；S-B/S-C 标未实现（不假装三条臂都有）
  PASS  每条候选都带四项构成
  PASS  仍是 M1：不接主链路 / 没有阈值参数 / 不决策
  PASS  main.py 未引用 context_store

探针结束（临时库根已清理；默认库根未被创建）
全部 PASS
```

### 4.2 新增硬要求逐条对账（主张 ↔ 判据 ↔ 读数）

| 新增硬要求 | 判据落在哪 | 本轮读数 |
|---|---|---|
| 1 纯函数 `score(unit, query_context) -> float`，不调模型 | 探针 [F1] / 单测 [V1] | 形参 `['unit','query_context']`；`score == score_breakdown.score`；入参未改 |
| 2 同输入两次**逐位相同** | 探针 [F2] / 单测 [V2] | 5 次全 `0.262537683`，`repr` 集合大小 = 1 |
| 2′ 不得调用任何模型（既非被测、也非 LLM） | 单测 [V2] 静态 + 动态 | 包内 import 无 `openai/anthropic/requests/urllib/http/socket/llm/model/transformers/numpy/torch/core/tools`；时钟+网络双 tripwire 下仍算得出分 |
| 3 分数构成：词法 / 符号 / 时间衰减 / 定制加权 | 探针 [F3] / 单测 [V3] | `{lexical: 0.405465108, symbol: 0.4, time_decay: -0.792927425, custom: 0.25}`，和 = `0.262537683` = 总分 |
| 4 定制加权走**显式配置**，不许模型决定权重 | 探针 [F4] / 单测 [V4] | 加一条规则分数**恰好** +0.25；9 类非法配置全部 `ValueError`；配置 JSON 里无模型字段 |
| 5 校准过程**可复现**（记录哪些样本、哪条曲线） | 探针 [F5] / 单测 [V5] | 两次校准三个指纹全同；换配置/换样本 ⇒ 指纹变 |
| ★★★ scorer 身份进 `basis`（与 `model` 并列） | 探针 [F6] / 单测 [V6] | `basis = {scorer:"S-A", scorer_kind:"deterministic", model:null, config_sha256:…}` |
| ★★★ 三臂如实（不许假装已有） | 探针 [F6] / 单测 [V6] | `S-A` 标「已实现」；`S-B`/`S-C` 标「**M2 对照臂，未实现**」 |
| 边界：仍是 M1（不接模型/不接主链路/不决策） | 探针 [F6] | `phase=M1`、`wired_into_main_chain=False`、`threshold=None`、`decision=none`、`main.py` 未引用 |

### 4.3 反空洞（"不是把检查关掉"）—— 4 条，红/绿同源

| # | 做法 | 期望 | 实测回显（探针 [F2]/[F3]/[F5]） |
|---|---|---|---|
| 1 | 把 `time_decay_factor` 换成**带计数**的非确定性打分器 | 同一条「两次逐位相同」判据**变假** | `[0.982973248, 0.991027899]` ⇒ `判不可复现: True`；恢复真打分器 ⇒ 回到相等 |
| 2 | 换成**读时钟**的打分器 | 时钟 tripwire 抓住 | `PASS ★ 反空洞：读时钟的打分器被 tripwire 抓住` |
| 3 | 把四项里的 `custom` 人为 `+0.001` | 同一条「相加 == 总分」判据**变假** | `PASS ★ 反空洞：改掉某一项 ⇒ 同一条对账判据判红` |
| 4 | 改一条样本的标注（`relevant` 加一个 id） | `samples_sha256` **变** | `PASS ★ 反空洞：改一条样本的标注 ⇒ samples 指纹变` |

> 注意 #1/#3/#4 用的是**与绿判据完全相同的那一条断言**（`a == b` / 四项求和对账 / 指纹不等），
> 只是把被测对象换成了故意做坏的版本 —— 证明这些判据**有牙**，不是为了变绿而写的空转。

### 4.4 其他门禁

| # | 主张 | 验证命令 | 结果 |
|---|---|---|---|
| 1 | 新增打分门禁通过 | `python tests\unit\test_memory_scoring.py` | **63/63**（exit 0） |
| 2 | M1 原有门禁**未放宽、未删项** | `python tests\unit\test_memory_store.py` | **71/71**（exit 0） |
| 3 | 全量单测通过 | `python tests\run_unit.py` | **51/51**（exit 0） |
| 4 | 文档一致性通过 | `python tests\unit\test_doc_consistency.py` | **35/35**（exit 0） |
| 5 | 文档不变量通过 | `python tests\unit\test_doc_invariants.py` | **35/35**（exit 0） |
| 6 | 文档审查通过 | `python tests\unit\test_doc_review.py` | **18/18**（exit 0） |
| 7 | 契约符合性通过 | `python tests\unit\test_contract_conformance.py` | **44/44**（exit 0） |
| 8 | 前端契约通过 | `python tests\unit\test_frontend_contract.py` | **25/25**（exit 0） |
| 9 | 套件卫生通过 | `python tests\unit\test_suite_hygiene.py` | **4/4**（exit 0） |

> 一条**踩过的坑**（沿用上一轮记录，避免误判）：把 `run_unit.py` 的输出接进
> `Select-Object` 管道时，PowerShell 会把**管道**的退出码报成 `[exit code: 1]` ——
> 那不是测试失败。判据看它自己打印的 `通过 51/51`；单独运行各脚本时 `$LASTEXITCODE = 0`。

> **一次未复现的抖动（如实记录）**：本轮全量单测共跑 5 次 —— **4 次 51/51**，
> 其中 **1 次报 50/51**（当时未捕获到失败项名）。随后逐项单独重跑 6 个门禁**全绿**，
> 新增门禁 `test_memory_scoring.py` 单独连跑 **5 次**均 63/63，**该抖动未能复现**，
> 成因**未定位**（不排除与当时并发写文档 / git 元数据有关，但这是推测，不是结论）。
> **本轮的每条主张都不依赖那一次运行**：每个门禁都有独立的 exit code 与通过数依据。

**未验证的部分**（诚实列出，比假装验过有价值）：

- **没有用真实标注数据校准任何参数**：`half_life_days` / `min_factor` / 权重 / 定制规则
  全部保持**未校准**（默认衰减关闭、定制规则为空）。第 5 条硬要求只做到"**校准过程可复现**"，
  真正的校准属于 **M2**（`WORK-ORDER.md` 分期表：M2 = 记分不决策 + 事后判定落盘 + 分布与曲线）。
- **没有实现 S-B / S-C 对照臂**：S-B 需引入版本锁定的嵌入模型（新依赖，违反本轮硬边界），
  S-C 需调 LLM（违反「不接模型」）。它们在 `describe()` 里如实标「未实现」。
- **没有做 M2 的"分数 + 事后判定落盘"、没有做 M3 的一键开关与接入**：工单「不许跳级」，
  M3 另需用户批准。
- **没有把第二路召回接到 `find_symbol` / `get_module` / `get_architecture` 的实调用上**：
  仍是 M1 的边界（只产出 `structure_lookup` 原料）。
- **没有改 `.interface_contract/`**（只读），也没有跑/改统筹方的门禁脚本。
- **时间衰减的"形状"有判据，"数值"没有权威**：单调性与下限有测试，
  但半衰期取多少必须等 M2 的数据 —— 本轮**刻意不给推荐值**。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 / payload 键 | **无** | 仍 18 种；本模块**一个事件都不发** |
| 上游 `PHASE_ORDER` 阶段 | **无** | 仍 `plan/write/check/verify/record` |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | 未动 |
| `TOOLS_MAP` 条目结构 / 工具数 | **无** | 仍 18 个；本模块**不注册成工具** |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无** | 仍 `1.1` / `1.0` / `1.0` |
| 端点路径 | **无** | 未动；`/profile` 也**没有**加 `context_store` 段（M1 不接入） |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 只读未动 |

**结论**：对接口契约**零改动、零破坏**。这不是"加性变更"，而是**根本不在接口面上**
（没有生产代码 import 它）。唯一对外可见的变化是**本包自己的自述面**：
`ContextStore.profile()["scoring"]`、`recall()` 的 `basis`/`config`/`score_parts` 四项、
`calibrate()` 的 `calibration` 段，以及库内版本号 `STORE_VERSION` `m1.1` → `m1.2`
（它只进 `profile()["store_version"]` 与 `manifest.json`，**不在契约面上**）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**？**不要**。本轮不产生任何前端可见事实：
  无事件、无端点、无 `/profile` 字段、无 `CycleReport` 字段。
- **有没有可能"问题被平移到对侧"**？**没有**。改动全部在本仓库的独立库内部，
  且**不接入**主链路 ⇒ 对侧行为与读数**逐字节不变**。
- **会静默少显示什么吗**？不会 —— 本轮没有接口面变化。
- **将来 M2/M3 接入时**：★★★ 要求「scorer 的选择必须进 `basis`」，
  本轮已把 `basis` 做成 `recall()` 的返回字段；M3 接入时必须**可一键关**，
  且跨模型对比结论出来之前不得进主链路 —— 这些在 `describe()["scorer"]["one_switch"]`
  与 `profile()["wired_into_main_chain"]` 里都有可机判的落点。

---

## 7. 不做的部分及理由（对应 C7）

- **不做 M2（对照臂 S-B/S-C、记分落盘、真实阈值校准）**：`DISPATCH.md` 逐字「本轮的活只有 M1……的存储与检索」，
  `WORK-ORDER.md` 分期表「**不许跳级**」，且 ★★★ 明写对照设计是「**M2 的核心活儿**」。
- **不实现 S-B（固定嵌入模型）**：会**引入新依赖**（违反 `ROLE-BRIEF.md` §0.4「不许改环境」）。
- **不实现 S-C（LLM 打分）**：会**调用模型**（违反 M1「不接模型」与「跨模型对比结论出来之前不得进主链路」）。
- **不定时间衰减的半衰期 / 不定阈值**：★★ 第 5 条与硬要求 3「阈值第一阶段不许定死，用数据校准」⇒
  默认 `half_life_days=None`（关闭），只提供形状与判据。
- **不改 M1 的四条验收语义**（内容寻址、越界拒绝、库根隔离、归档非删除）：
  `test_memory_store.py` 71/71 未动一行判据。
- **不动 P16（多语言）**：`DISPATCH.md` 逐字「P16（多语言）现在别动」。
- **不重做 D38–D43**：§2.2 的前提在上一轮已逐条核对交付（P17/P18/P19/P20/D43），本轮不重复。
- **不动 `units.py` / `scope.py`**：单元结构、独立根、越界拒绝语义不变；本轮只碰打分层。

---

## 8. 回退点（对应 C8）

- **回退命令**：`git reset --hard <v1.32 备份点>`（定位：
  `git log --oneline --grep "^v1.32:"`；提交信息以 `v1.32:` 开头。
  **本轮备份点 = `ab2842e`**，其后的 `v1.32 记录` 提交只追加本文件中引用的复核说明，不含代码）。
- **回退会丢什么**：`core/context_store/retrieval.py` 的打分层（`score` / `score_breakdown` /
  `time_decay_factor` / `canonical_config` / `config_sha256` / `custom_bonus` / `calibration` 段）、
  `store.py` 的转发与 `profile()["scoring"]`、`__init__.py` 的导出、两个新测试、
  CHANGELOG §46、MODULES §35、README 文档导航行与本评估文档。
- **更细粒度的回退**（不用回退整个提交）：
  - 只想去掉新增判据门禁：删 `tests/unit/test_memory_scoring.py` 与
    `tests/diagnostics/probe_memory_scoring.py`（生产代码不受影响）；
  - 想回到"只有两项构成"的旧读数：保留 `recall()` 但忽略 `time_decay` / `custom`
    （把 `config["time_decay"]["half_life_days"]` 留 `None`、`custom` 留空 ⇒ 两项贡献恒为 0，
    总分与 v1.31 的 `keyword+symbol` 完全一致）；
  - 换 scorer：`basis.scorer` 是读数字段，替换 scorer 时**必须**同步改它（否则归因失真）。
- **回退不会丢什么**：不存在需要"迁移回来"的持久状态 —— 记忆库索引格式未变
  （`STORE_VERSION` 只在自述里从 `m1.1` 记到 `m1.2`），默认库根本轮**从未创建**。

---

## 9. 自检结论

- **C1 问题陈述可复现**：满足。§2.1 用**哈希手术**证明本轮新内容就是【P21】新增的两节
  （只有同时删两节才复现上一轮哈希，其余候选 `MATCH=False`）；
  §2.2 用 `git show 949330f:…` 的机械输出列出旧打分层的五处缺口；
  §2.3 给出两条旁证。
- **C2 每条主张带可复现验证命令**：满足。§4.1 整段粘贴探针原始回显；
  §4.2 把每一条新增硬要求映射到具体判据与读数；§4.4 给出全部门禁命令与通过数。
- **C3 命令实测输出支持该主张**：满足。所有回显均来自本轮实跑；
  反空洞 4 条（§4.3）是"把被测对象换成故意做坏的版本后同一条判据变红"，
  不是另写一条更弱的检查。
- **C4 改动清单与实际一致**：满足。§3 先贴 `git status --short` + `git diff --stat`，
  并显式点出机械输出**不含**未跟踪的新测试与尚未落盘的本文档/`VERSIONS`。
- **C5 对接口契约的影响已声明**：满足。§5 逐项写"无"，并说明本包**不在接口面上**；
  唯一自述面变化是 `STORE_VERSION` `m1.1`→`m1.2`（不进契约）。
- **C6 对另一侧的影响已评估**：满足。§6 结论是"不需要跟改、不平移、不静默少显示"，
  并把 M2/M3 接入的风险与 `basis` / 一键关的对应关系写明。
- **C7 未把接口级问题当内部问题处理**：满足。§7 明确划出未做范围（M2/M3、S-B/S-C、
  真实参数校准、结构索引实调用、P16、`units.py`/`scope.py`），并说明每一条的**理由**。
- **C8 回退点明确**：满足。§8 给出 `git reset --hard` 的定位命令、回退会丢什么，
  以及"只删两个新测试"/"把衰减与定制留空即回到旧读数"的细粒度回退。
- **契约目录只读**：满足。`.interface_contract/` 未被写入（只读取 `ROUND.json`/`DISPATCH.md`/
  `WORK-ORDER.md`）。
- **对侧仓库 / 集成工作区未写入**：满足。本轮所有写操作都在
  `D:\PythonProject\SimpleAgent2_Cycle` 内；`.tmp/` 里的临时探针/补丁脚本属本仓库。
- **未改环境**：满足。没有 `pip install` 任何东西；新代码只用标准库
  （`hashlib` / `json` / `math` / `datetime`），包内 import 判据仍绿。

**希望统筹重点验证哪一条**：

**§4.3 的第 1 条反空洞（非确定性打分器 ⇒ 同一条判据判红）**。
它直接回答第四条硬要求的**第 2 条**「打分必须可复现」是不是被真的立起来了 ——
如果 `score()` 里藏着任何时钟/随机/环境依赖，那条判据就会变红；
而证明它"有牙"的方式是把被测打分器换成带计数的版本，**用同一条断言**判它红。
配合 §4.2 的静态 import 判据（打分路径没有任何模型/网络模块可 import），
这一条就是「**调用分算法与模型无关**」能不能成立的机判形态。
