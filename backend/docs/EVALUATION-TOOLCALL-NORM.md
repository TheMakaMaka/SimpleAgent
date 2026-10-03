# 变更评估文档 · `TOOLCALL-NORM`（P9）

- **变更编号**：`TOOLCALL-NORM`（工作单里的 **P9**）
- **提出方**：用户（2026-10-03 架构方向）→ 统筹方落成契约 `tool_call_contract`
- **执行侧**：backend
- **日期**：2026-10-03
- **契约版本**：`1.0.30`
- **本轮 round_id**：`R-69ec731ff3` —— **本轮完成 `R-69ec731ff3`**（下一轮据此判断要不要开工）

---

## 1. 变更意图

用户 2026-10-03 的原话（统筹方引用，逐字）：

> 「工具调用要做规范化处理，模型只需要判断要做什么、怎么做、调用什么工具，
> 剩下的就是工具格式化的规范，这样就可以**避免每一次生成的东西不一样**，
> **工具生成的东西也要做检验**，其他主体不变。」

统筹方 `DISPATCH.md` 把本轮唯一指令定为 **【P9】工具调用规范化 + 工具产出检验**，
并给了实测根因与两条验收。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 现象与根因（位置全写）

| 事实 | 位置 / 机械依据 |
|---|---|
| 18 个工具的 `parameters` **一个都没声明** `additionalProperties` | `tools/registry.py:66` `tool_schemas()` 直接透传 `info["parameters"]`；各 `@register(parameters=…)` |
| JSON Schema 默认「额外键一律允许」⇒ 传错键**不报错、被静默忽略** | JSON Schema 规范默认值；`core/worker.py:300`（旧版）`fn(**args)` 只做 Python 绑定，多出来的键会落进 `**kwargs`（若签名有）或被 `TypeError` 兜成一句字符串 |
| `properties` 为空的 2 个工具（`get_system_info` / `list_workspace`）同样收任意键 | `tools/basic.py:71`、`tools/code_checks.py:166`（旧行号） |
| 结果只有"是不是 `ok:false`"一个判据，**没有任何东西校验产出形状** | `tools/registry.py:114` `is_error_result()` |
| 同一意图两种形状的实测旁证 | 统筹方：`{"filename":…,"content":…}` vs `{"code":…}`；`!pip install` 写进 `.py` |

**根因一句话**：不是模型不听话，是**判据没立在"工具那一层"** ——
形状没有 canonical 形式，就无法比较两次调用、无法复用，也无法做能力测量。

### 2.2 复现命令与实测输出

**统筹方门禁**（在**修复前**跑，逐字粘贴，这是"它现在就是红的"的机械证据）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe `
  D:\PythonProject\SimpleAgent2_Integration\03-scripts\tool-contract-lint.py
```

```
  工具数            : 18（下限 18）
  缺 additionalProperties : 18
  显式允许任意键    : 0
  properties 为空    : 2

  [FAIL] **18/18 个工具未声明 `additionalProperties`**（JSON Schema 默认允许任意键 ⇒ 传错键不报错、被静默忽略）：calculate、check_and_run、check_syntax、fetch_url、find_symbol、get_architecture、get_module、get_system_info…
TOOLLINT state=fail problems=1 tools=18
```

**我这一侧的探针**（新增，含反空洞）：

```powershell
D:\PythonProject\SimpleAgent2_Cycle_VueWeb\.venv\Scripts\python.exe tests\diagnostics\probe_tool_contract.py
```

（输出见 §4.1，节选；完整原文由该命令随时可复现。）

---

## 3. 拟改动清单（对应 C4）

### 3.1 机械输出（权威）

```powershell
$ git -c safe.directory=<repo> status --short
 M CYCLE.md
 M README.md
 M core/contract.py
 M core/worker.py
 M docs/ARCHITECTURE.md
 M docs/CHANGELOG.md
 M docs/FRONTEND_CONTRACT.md
 M docs/MODULES.md
 M docs/OPERATIONS.md
 M tests/README.md
 M tools/__init__.py
 M tools/arch.py
 M tools/basic.py
 M tools/code_checks.py
 M tools/docs.py
 M tools/files.py
 M tools/net.py
 M tools/parse.py
 M tools/python_exec.py
 M tools/quality.py
 M tools/reflect.py
 M tools/verify.py
?? docs/EVALUATION-TOOLCALL-NORM.md
?? tests/diagnostics/probe_tool_contract.py
?? tests/unit/test_tool_contract.py
?? tools/tool_contract.py

$ git -c safe.directory=<repo> diff --stat
 CYCLE.md                  |  2 +-
 README.md                 |  3 +-
 core/contract.py          | 12 ++++++++
 core/worker.py            | 73 ++++++++++++++++++++++++++++++++++++-----------
 docs/ARCHITECTURE.md      |  2 +-
 docs/CHANGELOG.md         | 62 ++++++++++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md | 16 +++++++++++
 docs/MODULES.md           | 53 +++++++++++++++++++++++++++++++++-
 docs/OPERATIONS.md        |  3 +-
 tests/README.md           |  2 ++
 tools/__init__.py         | 25 ++++++++++++++++
 tools/arch.py             |  4 +++
 tools/basic.py            | 11 ++++++-
 tools/code_checks.py      | 10 ++++++-
 tools/docs.py             |  2 ++
 tools/files.py            |  2 ++
 tools/net.py              |  1 +
 tools/parse.py            |  1 +
 tools/python_exec.py      |  1 +
 tools/quality.py          |  1 +
 tools/reflect.py          |  2 ++
 tools/verify.py           | 11 ++++++-
 22 files changed, 275 insertions(+), 24 deletions(-)
```

四个**新增文件**（`git diff --stat` 不含未跟踪文件，故单列）：

```
tools/tool_contract.py                     454 行  ← 别名表 / 归一 / 产出检验（实现）
tests/unit/test_tool_contract.py           267 行  ← 会红的门禁（40 项）
tests/diagnostics/probe_tool_contract.py   170 行  ← 机械输出探针
docs/EVALUATION-TOOLCALL-NORM.md                 ← 本评估文档
```

### 3.2 手写导读（非判据）

| # | 文件 | 位置 | 为什么改 |
|---|---|---|---|
| 1 | `tools/tool_contract.py`（新） | — | 单一实现点：`ALIASES` 声明式别名表；`normalize_args()`（别名→未知键拒绝→类型强制→必需键→缺省填充）；`validate_result()`（信封 `{ok,kind,data,error}`）；`audit()` / `describe_contract()` |
| 2 | `tools/*.py`（11 个） | 各 `@register(parameters=…)` | 18 个工具全部显式 `additionalProperties: false`；可选参数补 `default`（`get_architecture.limit` / `review_document.path` / `reflect_on_history.limit_cycles` / `check_and_run.expect_exit`） |
| 3 | `tools/verify.py` | `check_and_run` 的 `parameters` | **顺带补 U- 类**：`expect_exit` 一直是真实参数却没写进模型可见 schema —— 收紧形状时补上，否则它会被"未知键"判据拒掉，能力反而丢失 |
| 4 | `core/worker.py` | `_invoke` / `_args_for_read` / `_maybe_artifact` | `_parse_args` 之后、执行之前归一；产出检验；去重/兜底/归档三条旁路也走归一后的实参（否则 `{"script":…}` 会被去重逻辑读成空串） |
| 5 | `tools/__init__.py` | 导出 | 公开 `normalize_args` / `validate_result` / `ALIASES` / … |
| 6 | `core/contract.py` | `describe()` | `/profile.contract.tool_call_contract` **公开别名表 + audit**（"声明出来，别藏在代码里"） |
| 7 | `tests/unit/test_tool_contract.py`（新） | — | 40 项门禁；★ 未知键结构化拒绝 + **工具函数一次都没执行**；★ 信封不合规被拒；旧字符串仍可读 |
| 8 | `tests/diagnostics/probe_tool_contract.py`（新） | — | 统筹方验收要的**机械输出**（含"去掉封闭声明立刻变红"的反空洞） |
| 9 | 文档面 | `CHANGELOG §39` / `VERSIONS.md`（备份机制带入）/ `MODULES §31` / `FRONTEND_CONTRACT §4.1` / `OPERATIONS §8.2` 第 12 项 / `tests/README` / 5 处版本戳 | 声明与实现同步 |

### 3.3 若两者不一致，差异是什么

一处**需要说明**：**`docs/VERSIONS.md` 不在上面的 `diff --stat` 里** ——
它由 `tests/backup.py` 在提交**之后**追加 v1.25 记录、再 amend 进同一提交
（备份机制的固有行为）。所以以**备份点** `git show --stat <v1.25 提交>` 为准，
它比 §3.1 多一个 `docs/VERSIONS.md`。

另一个非差异：`.tmp/` 是本轮临时文件（拼装 `MODULES.md` 附加段与 `OPERATIONS.md`
新增行用的中间件），**已在备份前删除**，不属于交付物。

**行尾说明**：`docs/MODULES.md` 与 `docs/OPERATIONS.md` 是 `git` 的 `-text`
文件（历史上行尾混合）。本轮我**保持原字节**追加（先 `git checkout` 还原，
再用字节级替换/追加），因此没有出现"整份文件被翻成 CRLF"的假 diff ——
两次 `git diff --numstat` 分别是 `53/1` 与 `3/1`，与真实改动一致。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望输出 |
|---|---|---|---|
| 1 | ★ 验收①：统筹方门禁**由红转绿** | `python 03-scripts/tool-contract-lint.py`（绝对路径见 §2.2） | `TOOLLINT state=ok problems=0 tools=18`，退出码 0 |
| 2 | ★ 反空洞：门禁**不是空转** | `python tests/diagnostics/probe_tool_contract.py` | §2 `去掉声明 ⇒ 判据会红` PASS，恢复后回绿 |
| 3 | ★ 验收②：传未声明键 ⇒ **结构化拒绝**（原始 JSON） | 同上（§3） | `{"ok": false, "kind": "error", "error": {"code": "unknown-key", …}}` |
| 4 | ★ 被拒时**工具函数没有被执行**（不是"接受后忽略"） | 同上 | `工具函数被调用次数: 0` PASS |
| 5 | ★ 旧字符串结果仍被 `is_error_result()` 正确识别 | 同上（§4） | `Error:` / `错误：` / `{"ok":false}` → `True`；普通文本 / `{"ok":true}` → `False` |
| 6 | 同义写法归一后**逐字节相同** | `python tests/unit/test_tool_contract.py` | `{filename,content}` == `{filename,code}` 归一结果一致 |
| 7 | 18/18 工具 `additionalProperties:false`、`type==object`、`required ⊆ properties` | 同上 | 三条全 PASS，且 `len(tool_schemas(None)) == 18` |
| 8 | 结果信封不合规 ⇒ `reject` | 同上 / 探针 §4 | `action=reject`，回灌 `tool-result-invalid` |
| 9 | 全量单测无回归 | `python tests/run_unit.py` | 通过数与基线一致或更多（基线 40/40） |
| 10 | 契约符合性 / 前端契约 / 文档一致性 / 文档不变量 / 文档审查 | 各自 `tests/unit/test_*.py` | 全部 PASS（数字见 §4.1） |

### 4.1 实测输出（粘贴原文）

**★ 验收①：门禁由红转绿**（同一命令，修复后）：

```
  工具数            : 18（下限 18）
  缺 additionalProperties : 0
  显式允许任意键    : 0
  properties 为空    : 2

  ★ 全部工具的实参形状都是**封闭**的：传错键会被拒，而不是被静默忽略。
TOOLLINT state=ok problems=0 tools=18
```

**★ 反空洞 + 结构化拒绝 + 兼容**（探针节选，逐字）：

```
[2] ★ 反空洞：去掉一个工具的封闭声明，同一判据立刻变红
  临时去掉 read_file 的声明后，门禁判据变红的工具: ['read_file']
  PASS  去掉声明 ⇒ 判据**会红**（证明 [1] 不是空转）
  PASS  工具自己的 audit() 也如实报红
  PASS  恢复声明 ⇒ 判据回到全绿

[3] ★ 传未声明键 ⇒ 结构化拒绝（且工具函数没有被执行）
  回灌给模型的原始 JSON: {"ok": false, "kind": "error", "error": {"code": "unknown-key", "message": "工具 read_file 不认识键 ['bogus']；未声明的键一律拒绝，不会静默忽略", "hint": "可用键: ['filename']；已知别名: ['file', 'file_name', 'filepath', 'name', 'path']"}, "tool": "read_file"}
  工具函数被调用次数: 0
  PASS  ★ 被拒时工具函数一次都没执行（不是'接受后忽略'）

[4] 工具产出检验：信封 `{ok, kind, data, error}` + 旧字符串仍可读
  半成品信封 → action=reject problems=['kind 必须是非空字符串', 'ok=false 时 error 必须含 code/message']
  PASS  半成品信封被拒（不会被当成成功读）
  PASS  合规信封被接受
  is_error_result('Error: 旧格式失败') = True（期望 True）
  is_error_result('错误：旧格式失败') = True（期望 True）
  is_error_result('{"ok": false, "issues": []}') = True（期望 True）
  is_error_result('{"ok": true, "output": "hi"}') = False（期望 False）
  is_error_result('文件 a.py 内容：\nprint(1)') = False（期望 False）

★ 全部通过：形状封闭 · 未知键结构化拒绝 · 产出检验有牙齿 · 旧结果仍可读
```

**同义不同形被治掉**（单测节选）：

```
  canonical: {'filename': 'a.py', 'content': 'x = 1'}
  别名写法 : {'filename': 'a.py', 'content': 'x = 1'}
  PASS  ★ 两种写法归一后**逐字节相同**（同义不同形被治掉）
  同归一键取值冲突: ambiguous-key
```

**门禁与套件汇总**（本轮实跑）：

```
tests/unit/test_tool_contract.py            通过 40/40
tests/diagnostics/probe_tool_contract.py    全部 PASS
TOOLLINT                                    state=ok problems=0 tools=18
契约符合性 44/44 · 前端契约 25/25 · 文档一致性 36/36 · 文档不变量 (31+2)/33 · 文档审查 18/18
```

（全量单测 `tests/run_unit.py` 的数字见 `docs/VERSIONS.md` 的 v1.25 备份记录。）

### 4.2 未验证的部分（诚实列出）

- **没有把现役 18 个工具改成结果信封**。契约的 `result_envelope.compatibility`
  明写"旧字符串结果仍**必须可读**，本条只要求**新工具**走结构化" ——
  所以我实现并接通了信封校验，但 `ENVELOPE_TOOLS` 现役为空集；
  它的"会红"由探针/单测用**临时登记**的样例工具证明（§4.1 [5]），
  而不是靠改现役工具的产出形状（那会动到前端与 `core/pipeline.py` 的读法）。
- **没有做真实模型 E2E**跑一轮验证"别名归一后模型更少出错"——
  那需要 `simple-agent` 实例与模型配额，且**读数应归统筹方的能力基线**。
  本轮只做了确定性证据（门禁 + 探针 + 单测）。
- **别名表没有穷举模型的所有写法**。它覆盖了实测出现过的形状
  （`code`/`source`/`script`/`file`/`path`/`name`/…）与同族常见写法；
  `ambiguous-key` 与 `unknown-key` 两条判据保证"没覆盖到的写法"**报错而不是被猜**——
  这比"猜一个"更安全，但也意味着漏掉的别名会表现为一次拒绝。
- **`validate_result` 对未登记信封的工具只做分类**（`legacy-json` / `plain-string`），
  不拒绝；这是刻意的兼容策略，不是遗漏（见 §7）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无**（仍 18 种） | 本轮不发新事件 |
| 事件 payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **顶层键无改动**（仍 `description`/`function`/`parameters`/`profiles`）；`parameters` **内部**加 `additionalProperties` 与 `default` | 属契约 `scope_exclusions` 里"只补封闭性声明"；`parameters` 本就是冻结 tool-info 键 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | **无**（仍 `1.1` / `1.0` / `1.0`） | 加性收紧不升契约版本 |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无** | 未改规则表/词表/事件分区 |
| `/profile` 的 `contract` 段 | **加性**：新增 `tool_call_contract`（别名表 + audit） | 前端只增不减，认不出就忽略 |

**结论**：**additive**（新增，安全）。没有删除/改名任何前端依赖的事实面。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗**：**不需要**。
  工具名、参数语义、`TOOLS_MAP` 顶层结构、事件、端点都没动；
  `/profile.contract` 只多了一个键。已在 `docs/FRONTEND_CONTRACT.md §4.1` 写明。
- **有没有可能"问题被平移到对侧"**：没有。本轮全部改在**上游工具层**
  （`tools/` + `core/worker.py`）内部，判据与实现同侧；
  前端不承担任何新义务。
- **前端会静默少显示什么吗**：不会（纯加性）。
  顺带仍保留统筹方记的 **D32**：bridge 的 `/api/spec` 的 `tools[]` 不含
  `parameters`，所以界面看不到模型实际受约束的那份声明 —— 那是**前端侧可选增强**，
  不是本轮义务；本轮之后 `parameters` 里多了 `additionalProperties`/`default`，
  前端若要展示可直接透传。

---

## 7. 不做的部分及理由（对应 C7）

- **不把现役工具改成信封**：契约明确只要求新工具；旧字符串是前端与
  `core/pipeline.py` 的现有读法，改它会变成破坏性变更。
- **不加新工具**：`FLOOR=18` 是下限，工具数不变最稳；本轮治的是"形状"不是"能力"。
- **不靠"放宽/关掉检查"来让门禁变绿**：门禁的 B 判据（`additionalProperties:false`）
  是**真的往 18 个 schema 里写**，不是改判据；探针 §2 的反空洞就是为此存在的
  （去掉声明必须立刻变红）。
- **不改 `is_error_result()` 语义**：它是老读数的唯一判据，
  兼容纪律要求回退路径原样保留（§4.1 的旧结果判定表）。
- **不动 `.interface_contract/`**：契约是统筹方权威源，只读。
- **不动对侧仓库与集成工作区**：只读运行了统筹方两份脚本（门禁 / 探针参照），未写入。

---

## 8. 回退点（C8）

- **回退命令**：见 `docs/VERSIONS.md` 的 `v1.25` 条目，
  `git log --oneline --grep "^v1.25:"` 定位提交，`git reset --hard <该提交>`。
- **回退会丢什么**：
  1. 18 个工具的 `additionalProperties:false` 与 `default` ⇒ 门禁**重新变红**，
     "任意键都收、传错静默忽略"回归；
  2. `tools/tool_contract.py`（别名表 / 归一 / 产出检验）与其接线 ⇒
     别名不再收敛、未声明键不再被拒、产出不再校验；
  3. `expect_exit` 的 schema 声明 ⇒ 又变回"实现有、声明没有"的 U- 类；
  4. `/profile.contract.tool_call_contract`、`MODULES §31`、本评估文档与
     `tests/unit/test_tool_contract.py`（回退点之后的东西全丢）。
- **回退不会丢什么**：v1.24 及以前的全部改动（事件仍 18 种、契约仍 `1.1`）。

---

## 9. 自检结论

| 标准 | 结论 |
|---|---|
| **C1** 问题陈述可复现 | **满足**。§2.1 给出 `文件:行` 级别的根因；§2.2 给出统筹方门禁的**修复前**机械输出（我进入本轮时先跑的基线） |
| **C2** 每条主张带可复现验证命令 | **满足**。§4 表 10 条，逐条给命令 |
| **C3** 命令实测输出支持该主张 | **满足**。§4.1 粘贴门禁红→绿、探针反空洞、结构化拒绝原始 JSON、旧结果判定表 |
| **C4** 改动清单与实际一致 | **满足**。§3.1 机械输出权威；§3.3 点明 `VERSIONS.md`（备份机制带入）与 `.tmp/`（临时件已删）两处差异 |
| **C5** 对接口契约的影响已声明 | **满足**。§5 逐面声明；唯一改动的 `parameters` 内部属加性封闭声明；`/profile` 新增键已声明 |
| **C6** 对另一侧的影响已评估 | **满足**。§6：前端不需改；`/api/spec` 的 D32 仍是前端可选增强，本轮不产生义务 |
| **C7** 未把接口级问题当内部问题处理 | **满足**。§7 明确"不关检查、不加工具、不改老判据语义、不动对侧与契约" |
| **C8** 回退点明确 | **满足**。§8 给出 `v1.25` 定位命令与丢失项清单 |

**我希望统筹重点验证哪两条**：

1. **门禁的"真绿"而不是"假绿"**：请重跑
   `03-scripts/tool-contract-lint.py`（应 `state=ok problems=0 tools=18`），
   并对照 §3.1 确认改动是**写进 18 个 schema**，不是改门禁判据。
2. **反空洞那两条**（§4.1）：①去掉一个工具的封闭声明 ⇒ 判据立刻变红；
   ②传未声明键时**工具函数一次都没执行**。这两条是"规范化真的生效"
   与"把检查关掉"的唯一分界线。
