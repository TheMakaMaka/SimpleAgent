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
```

## 约定

- **断言用非零退出码表示失败**，`run_unit.py` 据此汇总。新增单测请沿用：
  末尾 `raise SystemExit(1 if failed else 0)`，或使用 `_bootstrap.Checker`。
- 需要 `workspace/` 的脚本请从 `_bootstrap` 取 `WORKSPACE`，
  **不要写 `os.path.abspath("workspace")`**——那是 CWD 相对的，换个目录跑就错。
- 生成的产物一律写 `tests/output/`，不要散落在仓库根目录。
- `sys.path` 引导：`unit/` 下的文件已内联 sys.path shim；
  子目录脚本（bench/diagnostics）同样内联了 shim，无需额外设置。
