# tests/

测试与诊断脚本。**所有命令都在仓库根目录执行。**

## 目录划分

```
tests/
├── run_unit.py          统一跑全部单元测试（离线，不需要模型）
├── _bootstrap.py        公共引导：把仓库根目录加入 sys.path、workspace 清理工具
├── unit/                纯逻辑断言，不调用模型，可随时跑
├── bench/               能力基准（难度阶梯），需要真实模型
├── diagnostics/         诊断与展示，需要真实模型
└── output/              运行产物（可随时删除，已 gitignore）
```

## 1. 单元测试（推荐常跑）

```bash
python tests/run_unit.py
```

| 文件 | 覆盖内容 |
|---|---|
| `unit/test_adapter.py` | 预算推导、JSON 容错、能力校验、工作流层无模型特判 |
| `unit/test_manifest.py` | 符号索引、manifest 判定、路径归一化、悬空导入 |
| `unit/test_arch_tools.py` | 架构视图三工具：总览/单模块/符号反查 |
| `unit/test_quality.py` | `review_code` 工具能抓到各类质量问题 |
| `unit/test_check_pipeline.py` | 检查流水线门禁 + 检查点提交/回退 |
| `unit/test_cycle_manifest.py` | manifest 接进 CHECK 阶段（用假编排器，确定性） |
| `unit/test_structured_context.py` | 压缩快照回流 prompt：判据优先、预算上限、截断必须写明、旁路异常不冒泡 |
| `unit/test_memory_budget.py` | prompt 字符预算推导与按优先级填充 |
| `unit/test_doc_consistency.py` | 上游文档与代码的**原文短语**一致性（版本戳、工具数、路径存在性） |
| `unit/test_doc_invariants.py` | 文档与代码的**可枚举不变量**（角色/profile/阶段/后端/决策类型） |
| `unit/test_doc_review.py` | `review_document` 工具的机械检查 |
| `unit/test_frontend_contract.py` | 上游→前端契约：事件词表声明==实际、`_emit` 单一来源且 kind 为字面量、payload 与冻结面只增不减、**`_emit` 调用点不得用 payload 键撞参数名** |
| `unit/test_suite_hygiene.py` | **测试套件自身的卫生**：每个 `tests/unit/test_*.py` 都必须能以退出码表达失败（只打印 FAIL 的测试在套件里等于不存在） |
| `unit/test_workspace_tool.py` | `list_workspace` 的跳过策略：`.git/` 等不外泄、截断要明说 |
| `unit/test_decision_path.py` | **人工决策路径**（此前零覆盖）：`_ask` 不抛异常、fail-safe 默认值、`decision_opened` 的 payload 键不与 `_emit` 参数名冲突 |
| `unit/test_contract_attribution.py` | 契约对账的**责任划分**：逐类归因正确、规则表无死条目、无未声明的 code、info 不参与 verdict |
| `unit/test_contract_conformance.py` | **契约符合性**：直接读 `.interface_contract/interface-contract.json` 原文逐条核对（规则表/词表/分区/版本轴/事实源/上报字段/`response_contract`）；镜像未安装则**跳过** |
| `unit/test_verify_wiring.py` | **验证链路接线**：不带 `verify_command` 的真实目标也必须进 VERIFY、`main` 必须注入 `pipeline`、`_setup_orchestrator` 不得覆盖已有命令（一个 `if` 曾让验证与结构化上下文同时不存在） |
| `unit/test_identity.py` | **代码身份**：指纹只随内容变、随路径/时间不变、`cycle_start` 与 `/profile` 两处必须一致可见 |
| `unit/test_verify_vacuous.py` | **自拟验收的下限**：`print('PASS')` 之类不引用交付物的恒真判据必须被拒；★ 含**反向证明**（关掉开关必须复现 `declared=0 → phase=record`），否则断言无法自证有效 |
| `unit/test_transparency.py` | **决策透明化 + 判据不得静默换弱**（`TRANSPARENCY-BACKEND` A1/B1/B2/B3）：每轮 `reasoning` 进事件、判据演化带前后关系、**换掉已失败的判据必须给理由**、自拟判据引用 `.py` 交付物就**必须调用**它（`assert 名字` 不算） |
| `unit/test_self_report.py` | **收尾自述与交叉核对**（C1/C2）：七字段齐备、进报告与事件；★ **模型谎报时 `fact_check` 必须红**（自称已产出/验证通过/检查通过三样都测），且自述**不改判定**、拿不到自述时显式降级 |
| `unit/test_outcome.py` | **结局四值**（P1）：`abstain`（说不出什么叫对）/ `invalid`（判据或环境自身坏了）/ `fail` / `pass` 各构造一次；★ **判据来源进判定链**（模型自拟 vs 调用方的"通过"不同形） |
| `unit/test_reuse_checks.py` | **机械复用性（P2，硬否决）+ 架构事实层（P4）**：★ 实测那两条"调用了不存在的符号"的判据**必须被抓住**；「用了没导入」阻塞、重复符号/命名只是警告；★ 手写架构文档**被拦下**、AST 渲染件**放行** |
| `unit/test_reuse_scope.py` | **复用层的作用域**（`REUSE-SYMBOL-SCOPE`/P7b）：★ 同一份正确代码在"有/没有同名文件"两种工作区下**结论必须一致且为 0**；撞车矩阵（变量/参数/self/with/for/except/推导式）；★ **反空洞**：`np.array` 缺 import、`from mylib import f`（无 f）、`t1.bar`（只有 foo）**必须仍然红** |
| `unit/test_decompose_review.py` | **③ 拆解合规关卡（P3）**：★ **用户那次真实运行的 plan 逐字复刻 → 必须判不通过**；Run A 型分解违反 P3/P4/P6/P7 四条全被抓；合规分解**通过**（不会一律报红）；`block` 模式下**否决权真的生效** |
| `unit/test_tool_contract.py` | **工具调用规范化 + 产出检验（P9）**：18/18 工具 `additionalProperties:false`；别名归一后同义写法**逐字节相同**；★ **传未声明键 ⇒ 结构化拒绝，且工具函数一次都没执行**（证明不是静默忽略）；类型强制/缺省填充；结果信封硬校验；**旧字符串结果仍被 `is_error_result()` 正确识别** |
| `unit/test_tool_envelope.py` | **产出检验真的接到工具上**（P9 追加验收 ③）：`audit().envelope_tools` **非空**；★ 经 `Worker._invoke` 的产出**就是**信封本体（`{ok,kind,data,error}`）；失败信封的 `error` 描述**真实失败**而非占位文案；★ **反空洞**：摘掉登记 ⇒ 判据立刻变红 **且** Worker 不再套信封；未登记的工具产出原样返回 |
| `unit/test_project_root.py` | **P15 目标项目根**：三个绝对根都存在且互不混淆；`project_root` **任务级**（`ContextVar`，退出即还原）；★ 换根后扫到的集合**真的变**；★ 越界写 ⇒ 结构化 `out-of-scope-write` **且文件真的没写出去**；与 `AGENT_BACKEND_DIR` 语义分离（同值/异值两向都判） |
| `unit/test_deliverables.py` | **P14 输出契约**：声明的交付物**存在且哈希一致**才通过，**不存在 ⇒ 不合格**（结构化 `deliverable-missing`）；★ 反空洞：**删掉产物后 pass 翻成 fail**；没声明时也回报**实际产物** `{path,sha256,size}` |
| `unit/test_criterion_ownership.py` | **P13 归因归属**：模型自拟的坏判据 ⇒ `fail`（`delivery-gap`），**只有** `caller` 的坏判据 ⇒ `invalid`（`criterion-broken`）；含语法错 / 缺依赖 / 来源缺失 / 普通断言失败四组对照（**两向都在红**） |
| `unit/test_arch_map.py` | **P11 可信结构地图**：覆盖率账目（`indexed/skipped/truncated` + `skipped` 逐条理由）；★ 解析失败 ⇒ 进 `skipped`，修好 ⇒ **移回 `indexed`**；超 `limit` ⇒ 逐条 `truncated_items`（禁止静默截断）；新鲜度哈希随内容变；反向索引；范围显式 |
| `unit/test_pass_evidence.py` | **P17 pass 必须带机械证据**：`checked_by` + `evidence_kind`（`executed{command,exit_code}` / `artifacts{path,sha256,size}` / `static_declared{reason}`）；★ `checked_by=model` 且无类别 ⇒ **不得记 pass**（`invalid/unsubstantiated-pass`，不落检查点）；★ **反空洞**：正常执行仍 pass，抽掉执行记录（`exit_code`）⇒ 同一个 pass 立刻被拒 |

上表只列**主要**测试文件；完整清单以 `run_unit.py` 实际收集到的为准。

这些都不需要 Ollama，全部离线。

## 2. 能力基准（需要模型）

```bash
python tests/bench/run_levels.py          # 跑全部 8 级
python tests/bench/run_levels.py 1 4      # 只跑 1~4 级
python tests/bench/analyze_levels.py      # 汇总失败根因分类
```

难度阶梯定义在 `bench/levels.json`，每级都带机器可判定的 `verify` 断言。
结果写入 `output/levels_result.json`，各级 CycleReport 在 `output/logs/`。

**注意**：跑批会清空 `workspace/`（原有文件备份到 `output/_ws_backup` 并在结束时还原）。

## 3. 诊断（需要模型）

```bash
python tests/diagnostics/cycle_e2e.py            # 正向路径：跑一轮并打印 CycleReport
python tests/diagnostics/gate_check.py           # 反向路径：注入不可能满足的断言，验证门禁会拦住
python tests/diagnostics/diag_level.py 8         # 单级诊断：dump 实际产出代码 + 完整 verify 结果
python tests/diagnostics/run_with_full_log.py    # 完整流程日志，写到 output/full_cycle_log.txt
python tests/diagnostics/repro_user_goal.py      # 复现用户需求的真实形态（非 .py 交付物）
python tests/diagnostics/backend_dir_check.py    # **前端到底会加载哪一份后端**（只读；陈旧即报）
python tests/diagnostics/sync_backend_copy.py    # 把上游同步进前端自带副本（默认只预演）
python tests/diagnostics/verify_wiring_http.py   # **HTTP 路径**（TestClient）复跑同一接线断言：单测过≠线上过
python tests/diagnostics/repro_vacuous_verify.py # **自拟验收恒真**：真实模型跑"不给 verify_command"的目标（含 caller/model 来源对照）
python tests/diagnostics/repro_user_run_20260927.py  # **统筹方固定样例**：重跑那次 `passed` 的目标，打印决策依据/判据演化/自述与矛盾
python tests/diagnostics/probe_symbol_scope.py  # P7b 新判据版探针：A/B 两种工作区都 0 且结论一致（含反空洞三条）
python tests/diagnostics/probe_tool_contract.py # P9 机械输出：18/18 封闭 · 反空洞（去掉声明立刻变红）· 未声明键结构化拒绝 · 旧结果仍可读 · ★ 产出检验真的接到工具上
python tests/diagnostics/probe_output_and_map.py # P14/P15/P11 机械输出：三个根 · 任务级目标根（换根生效）· 越界结构化拒绝 · 交付物对账 · 覆盖率账目/新鲜度/反向索引（全离线）
python tests/diagnostics/probe_pass_evidence.py # P17 机械输出：生产路径的真实退出码 ⇒ executed 证据；★ 抽掉执行记录 ⇒ pass 被拒；artifacts 输出根内外；static_declared 理由（全离线）
```

## 约定

- **断言用非零退出码表示失败**，`run_unit.py` 据此汇总。新增单测请沿用：
  末尾 `raise SystemExit(1 if failed else 0)`，或使用 `_bootstrap.Checker`。
- 需要 `workspace/` 的脚本请从 `_bootstrap` 取 `WORKSPACE`，
  **不要写 `os.path.abspath("workspace")`**——那是 CWD 相对的，换个目录跑就错。
- 生成的产物一律写 `tests/output/`，不要散落在仓库根目录。
- `sys.path` 引导：`unit/` 下的文件已内联 sys.path shim；
  子目录脚本（bench/diagnostics）同样内联了 shim，无需额外设置。
