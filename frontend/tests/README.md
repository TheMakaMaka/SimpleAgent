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
| `unit/test_webui_runtime.py` | 进度事件总线（no-op / 隔离 / 取消穿透）+ 运行管理器（事件日志、增量 tail、终态判定、演示运行全链路） |
| `unit/test_isolation.py` | **前后端隔离**：上游里没有 bridge 痕迹、运行根在任意 CWD 下生效、仓库根不被污染、契约自检真能报错（含负向测试）、挂钩幂等且不改上游行为 |
| `unit/test_event_contract.py` | **事件词表契约**：前端 `case` == 后端会发的 kind（AST 扫上游 `_emit` / `bridge/hooks.py` / `bridge/runner.py` 三处） |
| `unit/test_spec.py` | **标定方案**：事实 == 代码现状；无漏标/死标；端点声明与真实路由双向一致；**前端兜底 `DEFAULT_SPEC` 不许漂**；override 能改标定但改不了事实 |
| `unit/test_triage.py` | **失败归因**：每一类失败都给合成事件流并断言类别（归错类比不归因更糟）；boundary: manifest 不合格属模型能力类，只有 `checked=False` 才是架构缺口 |
| `unit/test_audit.py` | **责任自审查**：九个场景的归属断言（服务声明了前端不认→前端；声明了却不做→后端；服务多了内容版本没升→后端；客户端孤儿→前端且**不许诬告后端**；服务不可达→运维） |

这些都不需要 Ollama，全部离线。完整清单见 `python tests/run_unit.py` 的输出（26 个文件）。

## 2. 能力基准（需要模型）

```bash
python tests/bench/run_levels.py          # 跑全部 8 级
python tests/bench/run_levels.py 1 4      # 只跑 1~4 级
python tests/bench/analyze_levels.py      # 汇总失败根因分类
```

难度阶梯定义在 `bench/levels.json`，每级都带机器可判定的 `verify` 断言。
结果写入 `output/levels_result.json`，各级 CycleReport 在 `output/logs/`。

**注意**：跑批会清空 `data/workspace/`（原有文件备份到 `output/_ws_backup` 并在结束时还原）。

## 3. 诊断

```bash
python tests/diagnostics/cycle_e2e.py            # 正向路径：跑一轮并打印 CycleReport（需要模型）
python tests/diagnostics/gate_check.py           # 反向路径：注入不可能满足的断言，验证门禁会拦住（需要模型）
python tests/diagnostics/diag_level.py 8         # 单级诊断：dump 实际产出代码 + 完整 verify 结果（需要模型）
python tests/diagnostics/run_with_full_log.py    # 完整流程日志，写到 output/full_cycle_log.txt（需要模型）
python tests/diagnostics/check_frontend_stream.py   # 前端事件流端到端：**不需要模型**，但需要后端已在 8000 端口运行
```

`check_frontend_stream.py` 走的是浏览器同一条路：`POST /api/runs` 不阻塞、
SSE 逐条推进、服务端主动 `close`、按 `seq` 断线续传不重不漏。
先起服务：

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## 4. 目录归属自检

```bash
python scripts/layout.py --check     # 有没归类的顶层目录就返回非零
python scripts/layout.py             # 打印当前「谁是谁」完整清单
```

上游出新版、或者谁在根目录加了新东西时跑一下。归属规则见 `docs/LAYOUT.md`。

## 约定

- **断言用非零退出码表示失败**，`run_unit.py` 据此汇总。新增单测请沿用：
  末尾 `raise SystemExit(1 if failed else 0)`，或使用 `_bootstrap.Checker`。
- 需要 `data/workspace/` 的脚本请从 `_bootstrap` 取 `WORKSPACE`，
  **不要写 `os.path.abspath("workspace")`**——那是 CWD 相对的，换个目录跑就错。
- 生成的产物一律写 `tests/output/`，不要散落在仓库根目录。
- `sys.path` 引导：`unit/` 下的文件已内联 sys.path shim；
  子目录脚本（bench/diagnostics）同样内联了 shim，无需额外设置。
