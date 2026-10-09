# 版本备份记录

每个版本都在**验证通过后**提交。回退点见各条目的 commit；
回退命令：`git reset --hard <commit>`（会丢弃其后所有改动）。

> 本文件由 `tests/backup.py` 自动追加，不要手工重排条目。

---

## v1.0 — 2026-09-25 23:21

**改动**：基线版本：两轮架构雏形 + 门禁/回退/技能/反思/封装优化/远程决策/文档审查/多模态接口/上下文预算。此版本为进入下一轮优化前的已验证基线。

**commit**：`20ed52c`

**验证**：
- 全量单测 PASS (22/22)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 28 个 · 测试文件 22 个

**本次提交的文件**：
```
20ed52c v1.0: 基线版本：两轮架构雏形 + 门禁/回退/技能/反思/封装优化/远程决策/文档审查/多模态接口/上下文预算。此版本为进入下一轮优化前的已验证基线。
 .env.example                                       | 135 +++
 .gitignore                                         |  66 ++
 CYCLE.md                                           | 431 +++++++++
 README.md                                          | 229 +++++
 core/__init__.py                                   | 179 ++++
 core/checkpoint.py                                 | 385 ++++++++
 core/coding_cycle.py                               | 628 ++++++++++++++
 core/compress.py                                   | 367 ++++++++
 core/config.py                                     | 254 ++++++
 core/context.py                                    |  44 +
 core/cycle.py                                      | 116 +++
 core/decisions.py                                  | 290 +++++++
 core/doc_access.py                                 | 156 ++++
 core/doc_review.py                                 | 269 ++++++
 core/llm.py                                        | 165 ++++
 core/manifest.py                                   | 296 +++++++
 core/memory.py                                     | 209 +++++
 core/model_profile.py                              | 364 ++++++++
 core/notify.py                                     | 219 +++++
 core/orchestrator.py                               | 321 +++++++
 core/package.py                                    | 493 +++++++++++
 core/pipeline.py                                   | 198 +++++
 core/promote.py                                    | 235 +++++
 core/prompts.py                                    | 120 +++
 core/reflect.py                                    | 394 +++++++++
 core/shape.py                                      | 132 +++
 core/skill_runner.py                               | 188 ++++
 core/skills.py                                     | 400 +++++++++
 core/symbol_index.py                               | 348 ++++++++
 core/task.py                                       |  56 ++
 core/vision.py                                     | 238 +++++
 core/worker.py                                     | 339 ++++++++
 docs/ARCHITECTURE.md                               | 369 ++++++++
 docs/CHANGELOG.md                                  | 956 ++++++++++++++++++++
 docs/MODULES.md                                    | 964 +++++++++++++++++++++
 docs/OPERATIONS.md                                 | 718 +++++++++++++++
 docs/PUSH_TO_GITHUB.md                             | 133 +++
 main.py                                            | 483 +++++++++++
 storage/__init__.py                                |   3 +
 storage/session.py                                 |  68 ++
 storage/store.py                                   | 211 +++++
 storage_data/skills/demo_single_func.json          |  43 +
 tests/README.md                                    |  64 ++
 tests/_bootstrap.py                                |  94 ++
 tests/backup.py                                    | 199 +++++
 tests/bench/analyze_levels.py                      |  55 ++
 tests/bench/levels.json                            |  50 ++
 tests/bench/run_levels.py                          | 183 ++++
 tests/diagnostics/cycle_e2e.py                     |  62 ++
 tests/diagnostics/diag_level.py                    |  74 ++
 tests/diagnostics/gate_check.py                    |  57 ++
 tests/diagnostics/run_with_full_log.py             | 130 +++
 tests/run_unit.py                                  |  61 ++
 tests/unit/test_adapter.py                         | 102 +++
 tests/unit/test_approval_web.py                    | 141 +++
 tests/unit/test_arch_tools.py                      | 155 ++++
 tests/unit/test_check_pipeline.py                  |  88 ++
 tests/unit/test_cycle_manifest.py                  | 181 ++++
 tests/unit/test_decisions.py                       | 242 ++++++
 tests/unit/test_doc_consistency.py                 | 282 ++++++
 tests/unit/test_doc_review.py                      | 100 +++
 tests/unit/test_encode_contract.py                 |  66 ++
 tests/unit/test_git_backend.py                     | 130 +++
 tests/unit/test_manifest.py                        | 184 ++++
 tests/unit/test_memory_budget.py                   | 149 ++++
 tests/unit/test_net_guard.py                       |  92 ++
 tests/unit/test_package.py                         | 275 ++++++
 tests/unit/test_phase_order.py                     |  87 ++
 tests/unit/test_quality.py                         | 117 +++
 tests/unit/test_reflect.py                         | 186 ++++
 tests/unit/test_roles.py                           | 133 +++
 tests/unit/test_skills.py                          | 379 ++++++++
 tests/unit/test_storage.py                         | 256 ++++++
 tests/unit/test_tool_profiles.py                   | 135 +++
 tests/unit/test_vision.py                          | 209 +++++
 tools/__init__.py                                  |  30 +
 tools/arch.py                                      | 203 +++++
 tools/basic.py                                     |  83 ++
 tools/code_checks.py                               | 187 ++++
 tools/docs.py                                      |  93 ++
 tools/files.py                                     |  99 +++
 tools/net.py                                       |  72 ++
 tools/parse.py                                     | 111 +++
 tools/python_exec.py                               | 114 +++
 tools/quality.py                                   | 290 +++++++
 tools/reflect.py                                   | 101 +++
 tools/registry.py                                  | 125 +++
 tools/verify.py                                    | 181 ++++
 web/__init__.py                                    |   1 +
 web/decisions.py                                   | 193 +++++
 ...257\204\344\274\260\346\212\245\345\221\212.md" | 124 +++
 91 files changed, 18937 insertions(+)
```

---

## v1.1 — 2026-09-25 23:24

**改动**：新增 tests/backup.py 版本备份机制（验证不过拒绝备份）与 docs/VERSIONS.md 记录；新增 test_doc_invariants.py 文档不变量检查（20 项），首次运行抓到 decisions/notify 两模块在上游文档无章节的真漂移，已补 MODULES §20 与 OPERATIONS §9.0；修正新检查器 4 处判据误报（大小写、固定段数、形参名）。

**commit**：`66b4477`

**验证**：
- 全量单测 PASS (23/23)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 28 个 · 测试文件 23 个

**本次提交的文件**：
```
66b4477 v1.1: 新增 tests/backup.py 版本备份机制（验证不过拒绝备份）与 docs/VERSIONS.md 记录；新增 test_doc_invariants.py 文档不变量检查（20 项），首次运行抓到 decisions/notify 两模块在上游文档无章节的真漂移，已补 MODULES §20 与 OPERATIONS §9.0；修正新检查器 4 处判据误报（大小写、固定段数、形参名）。
 CYCLE.md                          |   2 +-
 README.md                         |   2 +-
 docs/ARCHITECTURE.md              |   2 +-
 docs/CHANGELOG.md                 |  68 ++++++++++++++
 docs/MODULES.md                   |  52 ++++++++++-
 docs/OPERATIONS.md                |  10 ++-
 docs/VERSIONS.md                  | 120 +++++++++++++++++++++++++
 tests/backup.py                   |   4 +-
 tests/unit/test_doc_invariants.py | 185 ++++++++++++++++++++++++++++++++++++++
 9 files changed, 439 insertions(+), 6 deletions(-)
```

---

## v1.2 — 2026-09-25 23:35

**改动**：压缩快照回流进编排器 prompt：CodingCycle._structured_context() 每轮决策前从事件流重算快照（纯函数，不过模型），经 Orchestrator.context_provider 注入 SharedMemory.set_structured_context()，渲染在『结构化上下文』段（位置：验证结论之后、模型自述之前，独立预算上限 max(200,min(budget//3,1500))，截断必写明）。旁路纪律：取快照任何环节异常只降级为无此段，不影响主循环。expected_output 接线：进入 plan 事件的 intent，压缩为 declared 事实（自由文本不许当门禁）。修复三处文档真漂移：CYCLE.md §9 把已落地能力错标为『尚未完成』（重写并新增 §9.1 设计理由）、MODULES §12 summary_for_orchestrator 签名与输出顺序仍是旧版（验证结论已改为最前+字符预算）、ARCHITECTURE §9 已实现/计划中表陈旧；MODULES 补 §21 compress 与 §22 vision（这两个模块此前无章节）。新增 tests/unit/test_structured_context.py（31 项，含判据自身守卫：判据优先/预算不超支/截断必写明/旁路不冒泡）。新增 docs/PENDING_DECISIONS.md 待确认清单（A1-A5 阻塞项、B 策略项、C 缺口项，含建议与缺省行为）。真实 E2E：L1 PASS phase=record attempts=1 11.5s。

**commit**：`09e8a2b`

**验证**：
- 全量单测 PASS (24/24)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 28 个 · 测试文件 24 个

**本次提交的文件**：
```
09e8a2b v1.2: 压缩快照回流进编排器 prompt：CodingCycle._structured_context() 每轮决策前从事件流重算快照（纯函数，不过模型），经 Orchestrator.context_provider 注入 SharedMemory.set_structured_context()，渲染在『结构化上下文』段（位置：验证结论之后、模型自述之前，独立预算上限 max(200,min(budget//3,1500))，截断必写明）。旁路纪律：取快照任何环节异常只降级为无此段，不影响主循环。expected_output 接线：进入 plan 事件的 intent，压缩为 declared 事实（自由文本不许当门禁）。修复三处文档真漂移：CYCLE.md §9 把已落地能力错标为『尚未完成』（重写并新增 §9.1 设计理由）、MODULES §12 summary_for_orchestrator 签名与输出顺序仍是旧版（验证结论已改为最前+字符预算）、ARCHITECTURE §9 已实现/计划中表陈旧；MODULES 补 §21 compress 与 §22 vision（这两个模块此前无章节）。新增 tests/unit/test_structured_context.py（31 项，含判据自身守卫：判据优先/预算不超支/截断必写明/旁路不冒泡）。新增 docs/PENDING_DECISIONS.md 待确认清单（A1-A5 阻塞项、B 策略项、C 缺口项，含建议与缺省行为）。真实 E2E：L1 PASS phase=record attempts=1 11.5s。
 CYCLE.md                              |  46 ++++--
 README.md                             |   5 +-
 core/coding_cycle.py                  |  68 +++++++++
 core/compress.py                      |   9 ++
 core/memory.py                        |  36 +++++
 core/orchestrator.py                  |  34 +++++
 docs/ARCHITECTURE.md                  |  17 ++-
 docs/CHANGELOG.md                     | 114 ++++++++++++--
 docs/MODULES.md                       | 132 +++++++++++++++--
 docs/OPERATIONS.md                    |  23 ++-
 docs/PENDING_DECISIONS.md             | 230 ++++++++++++++++++++++++++++
 docs/VERSIONS.md                      |  30 ++++
 tests/README.md                       |   7 +
 tests/unit/test_structured_context.py | 272 ++++++++++++++++++++++++++++++++++
 14 files changed, 982 insertions(+), 41 deletions(-)
```

---

## v1.3 — 2026-09-25 23:37

**改动**：文档清单不变量：test_doc_invariants 新增第 7 组（docs/*.md 必须被 README 登记 + README 引用的 docs 文件必须存在），首次运行即抓到 docs/VERSIONS.md 从未登记，已补 README 文档表一行。CHANGELOG 回归基线去掉写死的测试文件数（原写 9，实际 24），改为由 run_unit.py 自己打印。文档不变量检查 20 -> 22 项。

**commit**：`2d06a3a`

**验证**：
- 全量单测 PASS (24/24)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 28 个 · 测试文件 24 个

**本次提交的文件**：
```
2d06a3a v1.3: 文档清单不变量：test_doc_invariants 新增第 7 组（docs/*.md 必须被 README 登记 + README 引用的 docs 文件必须存在），首次运行即抓到 docs/VERSIONS.md 从未登记，已补 README 文档表一行。CHANGELOG 回归基线去掉写死的测试文件数（原写 9，实际 24），改为由 run_unit.py 自己打印。文档不变量检查 20 -> 22 项。
 CYCLE.md                          |  2 +-
 README.md                         |  3 ++-
 docs/ARCHITECTURE.md              |  2 +-
 docs/CHANGELOG.md                 | 36 ++++++++++++++++++++++++++++++++++++
 docs/MODULES.md                   |  2 +-
 docs/OPERATIONS.md                |  2 +-
 docs/VERSIONS.md                  | 35 +++++++++++++++++++++++++++++++++++
 tests/unit/test_doc_invariants.py | 24 ++++++++++++++++++++++++
 8 files changed, 101 insertions(+), 5 deletions(-)
```

---

## v1.4 — 2026-09-26 01:32

**改动**：上游→前端兼容契约：新增 core/contract.py（声明 EVENT 词表12种+payload键+五组冻结面，并用与前端同款 AST 技术自扫描 _emit 字面量，audit() 十项全机器可判定）+ capabilities()（vision 由 role_available 推导，不手写）。守两条硬约束：事件只能从 CodingCycle._emit 发出（实测生产代码 append_event 仅此一处）、kind 必须字面量（否则前端 AST 扫不到）。只增不减规则写入契约：加事件/payload键必须补声明，删改必须先标 deprecated 保留一版并升 CONTRACT_VERSION。/profile 新增 contract 段（describe+audit），实测 ok=True 事件12 工具18 emit_files=[core/coding_cycle.py]。新增 tests/unit/test_frontend_contract.py（20项）与 docs/FRONTEND_CONTRACT.md（改上游前的检查表）。顺带修 OPERATIONS §8.2 回归清单表格本身损坏（7行后又跟同号3行），合并为11行并补入契约检查项；写死的 33/33 改为不写死。文档不变量 22/22、一致性 35/35、全量单测 25/25、真实 E2E L1 PASS phase=record 14.9s。

**commit**：`13f540c`

**验证**：
- 全量单测 PASS (25/25)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 25 个

**本次提交的文件**：
```
13f540c v1.4: 上游→前端兼容契约：新增 core/contract.py（声明 EVENT 词表12种+payload键+五组冻结面，并用与前端同款 AST 技术自扫描 _emit 字面量，audit() 十项全机器可判定）+ capabilities()（vision 由 role_available 推导，不手写）。守两条硬约束：事件只能从 CodingCycle._emit 发出（实测生产代码 append_event 仅此一处）、kind 必须字面量（否则前端 AST 扫不到）。只增不减规则写入契约：加事件/payload键必须补声明，删改必须先标 deprecated 保留一版并升 CONTRACT_VERSION。/profile 新增 contract 段（describe+audit），实测 ok=True 事件12 工具18 emit_files=[core/coding_cycle.py]。新增 tests/unit/test_frontend_contract.py（20项）与 docs/FRONTEND_CONTRACT.md（改上游前的检查表）。顺带修 OPERATIONS §8.2 回归清单表格本身损坏（7行后又跟同号3行），合并为11行并补入契约检查项；写死的 33/33 改为不写死。文档不变量 22/22、一致性 35/35、全量单测 25/25、真实 E2E L1 PASS phase=record 14.9s。
 CYCLE.md                             |   2 +-
 README.md                            |   3 +-
 core/contract.py                     | 328 +++++++++++++++++++++++++++++++++++
 docs/ARCHITECTURE.md                 |   3 +-
 docs/CHANGELOG.md                    |  79 +++++++++
 docs/FRONTEND_CONTRACT.md            | 143 +++++++++++++++
 docs/MODULES.md                      |  56 +++++-
 docs/OPERATIONS.md                   |  33 ++--
 docs/VERSIONS.md                     |  29 ++++
 main.py                              |   6 +
 tests/README.md                      |   1 +
 tests/unit/test_frontend_contract.py | 133 ++++++++++++++
 12 files changed, 802 insertions(+), 14 deletions(-)
```

---

## v1.5 — 2026-09-26 01:34

**改动**：备份点自包含修复：早先备份记录写在提交之后，导致「v1.4 的记录」落在 v1.5 的提交里，按打印的 git reset --hard 回退会丢掉该版本自己的记录。现在把记录写完后 amend 进同一提交（一次备份 = 一次提交），记录内不再自引用 hash（那会造成改一次追一次的无穷回归），改为提交信息以 tag 开头并用 git log --grep 定位。附带把待确认清单 A5 更新为「上游侧契约已冻结，剩前端版本协商」。

**备份点**：本条目所在的提交（提交信息以 `v1.5:` 开头）

**定位命令**：`git log --oneline --grep "^v1.5:"`

**验证**：
- 全量单测 PASS (25/25)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 25 个

**本次提交的文件**：
```
4a3e1c6 v1.5: 备份点自包含修复：早先备份记录写在提交之后，导致「v1.4 的记录」落在 v1.5 的提交里，按打印的 git reset --hard 回退会丢掉该版本自己的记录。现在把记录写完后 amend 进同一提交（一次备份 = 一次提交），记录内不再自引用 hash（那会造成改一次追一次的无穷回归），改为提交信息以 tag 开头并用 git log --grep 定位。附带把待确认清单 A5 更新为「上游侧契约已冻结，剩前端版本协商」。
 docs/PENDING_DECISIONS.md | 31 +++++++++++------
 docs/VERSIONS.md          | 33 ++++++++++++++++++
 tests/backup.py           | 87 ++++++++++++++++++++++++++++++++++++-----------
 3 files changed, 122 insertions(+), 29 deletions(-)
```

---

## v1.6 — 2026-09-26 01:35

**改动**：CHANGELOG §22 记录备份点自包含修复（v1.5 已改代码，本次补过程记录并升文档版本戳 §21→§22）。

**备份点**：本条目所在的提交（提交信息以 `v1.6:` 开头）

**定位命令**：`git log --oneline --grep "^v1.6:"`

**验证**：
- 全量单测 PASS (25/25)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 25 个

**本次提交的文件**：
```
d026821 v1.6: CHANGELOG §22 记录备份点自包含修复（v1.5 已改代码，本次补过程记录并升文档版本戳 §21→§22）。
 CYCLE.md             |  2 +-
 README.md            |  2 +-
 docs/ARCHITECTURE.md |  2 +-
 docs/CHANGELOG.md    | 59 ++++++++++++++++++++++++++++++++++++++++++++++++++++
 docs/MODULES.md      |  2 +-
 docs/OPERATIONS.md   |  2 +-
 6 files changed, 64 insertions(+), 5 deletions(-)
```

---

## v1.7 — 2026-09-26 01:47

**改动**：契约对账的责任划分（谁去改）：core/contract.py 新增 ISSUE_RULES 20 条规则（每条带 owner/severity/why/action，code 稳定可引用）+ compare() 责任划分报告 + upstream_issues()/peer_issues()；一条判定原则『事实源在哪一侧责任就在哪一侧』，无法单方面判定的两项（事件历史归属、版本号无法比较）刻意标 both 需协商。severity 三档且 info 不参与 verdict，否则 additive 新增会被误判成『有事要改』。三个调用口：GET /contract/check 自检、POST /contract/check 完整对账、python -m core.contract（服务没起来也能查），/profile 暴露 contract.responsibility 规则表供前端离线归因。启动时上游自查且只在失败时打印一行。顺带修 GET / 端点列表一直是手写的（漏了 /skills、/candidates），改为从 app.routes 推导 _route_paths()。写测试时抓到两个真问题：P-schema-mismatch 是死规则（无分支触发，已补版本无法解析时触发）、P-version-unparsable 级别定错（原 info 导致版本对不上时 verdict 仍是 ok，已改 degraded）。新增 test_contract_attribution.py 72 项，含双向自洽检查（观察到的 code == ISSUE_RULES，同时抓死规则与未声明 code）。全量 26/26、文档一致性 35/35、文档不变量 22/22、真实 E2E L1 PASS 10.9s。

**备份点**：本条目所在的提交（提交信息以 `v1.7:` 开头）

**定位命令**：`git log --oneline --grep "^v1.7:"`

**验证**：
- 全量单测 PASS (26/26)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (17/17)

> **勘误（v1.8 追加）**：本条改动说明里写「`ISSUE_RULES` **20** 条」，实测为
> **21** 条（`U-` 7 + `P-` 14）。代码当时就是 21 条，是记录写错了。
> 由统筹方实测发现（记为 F1）。已在 `test_doc_invariants.py` 加机械检查防止复发，
> 详见 `docs/CHANGELOG.md` §24.5。历史条目不做改写，仅此勘误。

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 26 个

**本次提交的文件**：
```
27755b0 v1.7: 契约对账的责任划分（谁去改）：core/contract.py 新增 ISSUE_RULES 20 条规则（每条带 owner/severity/why/action，code 稳定可引用）+ compare() 责任划分报告 + upstream_issues()/peer_issues()；一条判定原则『事实源在哪一侧责任就在哪一侧』，无法单方面判定的两项（事件历史归属、版本号无法比较）刻意标 both 需协商。severity 三档且 info 不参与 verdict，否则 additive 新增会被误判成『有事要改』。三个调用口：GET /contract/check 自检、POST /contract/check 完整对账、python -m core.contract（服务没起来也能查），/profile 暴露 contract.responsibility 规则表供前端离线归因。启动时上游自查且只在失败时打印一行。顺带修 GET / 端点列表一直是手写的（漏了 /skills、/candidates），改为从 app.routes 推导 _route_paths()。写测试时抓到两个真问题：P-schema-mismatch 是死规则（无分支触发，已补版本无法解析时触发）、P-version-unparsable 级别定错（原 info 导致版本对不上时 verdict 仍是 ok，已改 degraded）。新增 test_contract_attribution.py 72 项，含双向自洽检查（观察到的 code == ISSUE_RULES，同时抓死规则与未声明 code）。全量 26/26、文档一致性 35/35、文档不变量 22/22、真实 E2E L1 PASS 10.9s。
 CYCLE.md                                |   2 +-
 README.md                               |   2 +-
 core/contract.py                        | 473 +++++++++++++++++++++++++++++++-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  92 +++++++
 docs/FRONTEND_CONTRACT.md               | 424 ++++++++++++++++++----------
 docs/MODULES.md                         |  47 +++-
 docs/OPERATIONS.md                      |  25 +-
 docs/PENDING_DECISIONS.md               |  45 +--
 main.py                                 |  71 ++++-
 tests/README.md                         |   1 +
 tests/unit/test_contract_attribution.py | 231 ++++++++++++++++
 12 files changed, 1234 insertions(+), 181 deletions(-)
```

---

## v1.8 — 2026-09-26 02:37

**改动**：采纳统筹契约（interface-contract.json v1.0.0）后端工作单 2 项：W-B1 归属词表补 ops（OWNER_OPS + OWNER_ORDER 四值且 ops 优先 + compare 结果从三栏变四栏含顶层 ops 键 + 新增 O-service-down/O-frontend-not-built 两条规则，action 文案取契约 new_rules_required 原文）；W-B2 结论词表补 ops-action（VERDICTS 六值，判定顺序先判 ops）。21 条既有规则归属与级别零改判（契约原样采纳）。describe() 增 owner_values/verdict_values/ops_fact_rules 供统筹方比对两侧词表。ops 事实经 POST /contract/check 的并列字段上报而不进 PEER_FIELDS——契约把 PEER_FIELDS 定为 canonical_fields（声明类），而 ops 是运行态观测类，加进去会让契约当场过期；上游在服务活着时无法观测自身不可达，故事实由看得见环境的一侧上报、code 仍由本表定义。修统筹方记的 F1 漂移（文档写 20 条、实际 21 条）并加机械检查：test_doc_invariants 第 8 组（文档点名的规则数 == len(ISSUE_RULES) + 防空转断言 + 4 归属/6 结论词表齐全），该检查第一版就抓到 PENDING_DECISIONS 里漏改的一处 20 条。顺带修 doc_review 的真缺陷：§ 交叉引用检查把『同步至 CHANGELOG §N』版本戳误当本文档内引用（此前靠 MODULES 恰好有同名章节号巧合通过），且指向 CHANGELOG 的 §N 引用从来没被真正校验过——现版本戳排除在外、CHANGELOG/VERSIONS/FRONTEND_CONTRACT/PENDING_DECISIONS 的章节号纳入校验池。未动 .interface_contract/（只读资产），未做架构级提案（待用户批准）。全量 26/26、文档一致性 35/35、文档不变量 26/26、契约不变量 20/20、归因 90/90、文档审查 18/18、真实 E2E L1 PASS 10.7s。

**备份点**：本条目所在的提交（提交信息以 `v1.8:` 开头）

**定位命令**：`git log --oneline --grep "^v1.8:"`

**验证**：
- 全量单测 PASS (26/26)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 26 个

**本次提交的文件**：
```
bebd4f9 v1.8: 采纳统筹契约（interface-contract.json v1.0.0）后端工作单 2 项：W-B1 归属词表补 ops（OWNER_OPS + OWNER_ORDER 四值且 ops 优先 + compare 结果从三栏变四栏含顶层 ops 键 + 新增 O-service-down/O-frontend-not-built 两条规则，action 文案取契约 new_rules_required 原文）；W-B2 结论词表补 ops-action（VERDICTS 六值，判定顺序先判 ops）。21 条既有规则归属与级别零改判（契约原样采纳）。describe() 增 owner_values/verdict_values/ops_fact_rules 供统筹方比对两侧词表。ops 事实经 POST /contract/check 的并列字段上报而不进 PEER_FIELDS——契约把 PEER_FIELDS 定为 canonical_fields（声明类），而 ops 是运行态观测类，加进去会让契约当场过期；上游在服务活着时无法观测自身不可达，故事实由看得见环境的一侧上报、code 仍由本表定义。修统筹方记的 F1 漂移（文档写 20 条、实际 21 条）并加机械检查：test_doc_invariants 第 8 组（文档点名的规则数 == len(ISSUE_RULES) + 防空转断言 + 4 归属/6 结论词表齐全），该检查第一版就抓到 PENDING_DECISIONS 里漏改的一处 20 条。顺带修 doc_review 的真缺陷：§ 交叉引用检查把『同步至 CHANGELOG §N』版本戳误当本文档内引用（此前靠 MODULES 恰好有同名章节号巧合通过），且指向 CHANGELOG 的 §N 引用从来没被真正校验过——现版本戳排除在外、CHANGELOG/VERSIONS/FRONTEND_CONTRACT/PENDING_DECISIONS 的章节号纳入校验池。未动 .interface_contract/（只读资产），未做架构级提案（待用户批准）。全量 26/26、文档一致性 35/35、文档不变量 26/26、契约不变量 20/20、归因 90/90、文档审查 18/18、真实 E2E L1 PASS 10.7s。
 CYCLE.md                                |   2 +-
 README.md                               |   2 +-
 core/contract.py                        |  74 ++++++++++++++++++--
 core/doc_review.py                      |  23 ++++++-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       | 116 +++++++++++++++++++++++++++++++-
 docs/FRONTEND_CONTRACT.md               |  75 +++++++++++++++++----
 docs/MODULES.md                         |  34 +++++++---
 docs/OPERATIONS.md                      |   2 +-
 docs/PENDING_DECISIONS.md               |  48 +++++++------
 docs/VERSIONS.md                        |   5 ++
 main.py                                 |  10 ++-
 tests/unit/test_contract_attribution.py |  55 ++++++++++++++-
 tests/unit/test_doc_invariants.py       |  44 ++++++++++++
 tests/unit/test_doc_review.py           |  17 ++++-
 15 files changed, 449 insertions(+), 60 deletions(-)
```

---

## v1.9 — 2026-09-26 03:08

**改动**：确认 ops.service_down 通道语义（统筹方 WORK-ORDER 的 AWAITING_SIDE_CONFIRMATION 项）。统筹倾向选项 1（只加 info、不改 verdict），我判断选项 1 只买到可见性、它自己指出的危害仍在，故采用『选项 2 语义 + 选项 1 可见性 + 一条判定修正』：新增 OPS_STALE_BY_TRANSPORT={'O-service-down'}——POST /contract/check 能成功送达即证明上游可达，故随请求报上来的 service_down 只能是『上次已知状态』；它照常出现在 ops 栏（evidence 带 semantics=last_known_state / current=false / contradicted_by=request_succeeded）但不驱动 verdict，理由是该事实把 ops 优先的前提（服务不可达时后面一切不成立）证伪了；报告新增顶层 warnings:[] 明说这条矛盾，ok 时 next 也追加提示。frontend_not_built 与可达性不矛盾，仍驱动 ops-action。规则 code/owner/severity 与 23 条规则表零改动。另加行尾门禁（test_doc_invariants 第 9 组，逐文件比对工作区与 HEAD 是否含 CRLF，已做负向测试确认会抓）——它在本轮抓到两次真实 churn：我的版本引用脚本把 core/contract.py 从 LF 翻成 CRLF（1770 行假 diff）、升版本戳脚本又把 5 个上游文档翻成 LF；并如实记录『仓库混合行尾是我历轮脚本累积的产物』，一次性统一留作待办 C8。顺带修 _cli() 读 peer 文件不容忍 BOM（utf-8-sig，PowerShell 5.1 的 Set-Content -Encoding UTF8 会写 BOM 且报错看不出原因）。新增 docs/EVALUATION-OPS-1.md（按统筹模板九节 + C1-C8 自检，十条主张逐条实测并粘贴真实输出，含 11 文件/335 增 24 删的 diff stat 与显式声明 stat 之外的登记文件）。全量 26/26、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、契约不变量 20/20、归因 97/97、真实 E2E L1 PASS 10.2s。

**备份点**：本条目所在的提交（提交信息以 `v1.9:` 开头）

**定位命令**：`git log --oneline --grep "^v1.9:"`

**验证**：
- 全量单测 PASS (26/26)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 26 个

**本次提交的文件**：
```
1447a7e v1.9: 确认 ops.service_down 通道语义（统筹方 WORK-ORDER 的 AWAITING_SIDE_CONFIRMATION 项）。统筹倾向选项 1（只加 info、不改 verdict），我判断选项 1 只买到可见性、它自己指出的危害仍在，故采用『选项 2 语义 + 选项 1 可见性 + 一条判定修正』：新增 OPS_STALE_BY_TRANSPORT={'O-service-down'}——POST /contract/check 能成功送达即证明上游可达，故随请求报上来的 service_down 只能是『上次已知状态』；它照常出现在 ops 栏（evidence 带 semantics=last_known_state / current=false / contradicted_by=request_succeeded）但不驱动 verdict，理由是该事实把 ops 优先的前提（服务不可达时后面一切不成立）证伪了；报告新增顶层 warnings:[] 明说这条矛盾，ok 时 next 也追加提示。frontend_not_built 与可达性不矛盾，仍驱动 ops-action。规则 code/owner/severity 与 23 条规则表零改动。另加行尾门禁（test_doc_invariants 第 9 组，逐文件比对工作区与 HEAD 是否含 CRLF，已做负向测试确认会抓）——它在本轮抓到两次真实 churn：我的版本引用脚本把 core/contract.py 从 LF 翻成 CRLF（1770 行假 diff）、升版本戳脚本又把 5 个上游文档翻成 LF；并如实记录『仓库混合行尾是我历轮脚本累积的产物』，一次性统一留作待办 C8。顺带修 _cli() 读 peer 文件不容忍 BOM（utf-8-sig，PowerShell 5.1 的 Set-Content -Encoding UTF8 会写 BOM 且报错看不出原因）。新增 docs/EVALUATION-OPS-1.md（按统筹模板九节 + C1-C8 自检，十条主张逐条实测并粘贴真实输出，含 11 文件/335 增 24 删的 diff stat 与显式声明 stat 之外的登记文件）。全量 26/26、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、契约不变量 20/20、归因 97/97、真实 E2E L1 PASS 10.2s。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/contract.py                        |  60 ++++++-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       | 102 ++++++++++++
 docs/EVALUATION-OPS-1.md                | 285 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |  38 ++++-
 docs/MODULES.md                         |  26 ++-
 docs/OPERATIONS.md                      |   2 +-
 docs/PENDING_DECISIONS.md               |  25 ++-
 tests/unit/test_contract_attribution.py |  38 ++++-
 tests/unit/test_doc_invariants.py       |  61 +++++++
 12 files changed, 620 insertions(+), 24 deletions(-)
```

---

## v1.9.1 — 2026-09-26 03:10

**改动**：评估文档 docs/EVALUATION-OPS-1.md 的 C4 声明勘误：v1.9 备份点实际是 13 个文件，我原先声明 12 个（漏了 docs/VERSIONS.md —— 它由 tests/backup.py 在提交后追加 v1.9 记录带入，属备份机制固有行为）。改为显式列入 #10 并写明『以备份点 git show --stat 为准，实测 13 个』。这条本身是 C4『改动清单与实际一致』的自纠：交出去核对的文件里数字必须对。

**备份点**：本条目所在的提交（提交信息以 `v1.9.1:` 开头）

**定位命令**：`git log --oneline --grep "^v1.9.1:"`

**验证**：
- 全量单测 PASS (26/26)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 26 个

**本次提交的文件**：
```
818f85e v1.9.1: 评估文档 docs/EVALUATION-OPS-1.md 的 C4 声明勘误：v1.9 备份点实际是 13 个文件，我原先声明 12 个（漏了 docs/VERSIONS.md —— 它由 tests/backup.py 在提交后追加 v1.9 记录带入，属备份机制固有行为）。改为显式列入 #10 并写明『以备份点 git show --stat 为准，实测 13 个』。这条本身是 C4『改动清单与实际一致』的自纠：交出去核对的文件里数字必须对。
 docs/EVALUATION-OPS-1.md | 9 +++++++--
 1 file changed, 7 insertions(+), 2 deletions(-)
```

---

## v1.10 — 2026-09-26 09:29

**改动**：新增契约符合性门禁 tests/unit/test_contract_conformance.py（25 项）：不再写我自己的期望值，而是直接读 .interface_contract/interface-contract.json 原文逐条核对本侧实现——rule_crosswalk.upstream_only 21 条逐条 code/owner/severity、new_rules_required O1/O2 含 action 文案逐字、owner/verdict 词表集合、event_partition 12 事件与声明 count、phases_partition 5 阶段且顺序相同、version_axes 的两条版本、client_report_schema.canonical_fields 字段集合、fact_sources 的 backend 路径真实可解析、endpoint_partition 里前端代理的 7 条上游端点仍在提供、response_contract 的 warnings 类型/缺席即空/ops 栏保留未判定项/profile 新增项；并加防空转断言（从契约推导出的断言数≥18），契约结构一变解析取不到东西就会假通过。动机：统筹方是打接口手工复验（OPS-1 那次 6/6 手工），手工复验只覆盖那一轮，我之后改代码没人再看。它第一次运行就抓到两处真问题：(1) 契约 canonical_fields 是 9 项（v1.0.2 起就含 ops），而我的 PEER_FIELDS 只有 8 项——我上一轮为了『不让契约过期』刻意排除 ops，结果变成我的 describe().peer_report_fields 与契约对不上，属我在已交出的评估文档里的错，已修 PEER_FIELDS 并同步 FRONTEND_CONTRACT §6.2/§6.4/§8 与 MODULES §23，并在 EVALUATION-OPS-1 加 §5.1 勘误（不改写已交文档的结论）；(2) 检查器自己的 bug——fact_sources 的 core.cycle.CycleReport.to_dict 这种点号属性路径只 rpartition 一次解析不了，改为从长到短试模块前缀再逐级 getattr。顺带把契约版本引用升到 v1.0.5，并改用字节读写做批量替换（Path.read_text/write_text 的换行翻译本轮已坑两次）。契约目录仍只读。全量 27/27、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、契约不变量 20/20、归因 97/97、符合性 25/25、真实 E2E L1 PASS。

**备份点**：本条目所在的提交（提交信息以 `v1.10:` 开头）

**定位命令**：`git log --oneline --grep "^v1.10:"`

**验证**：
- 全量单测 PASS (27/27)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 27 个

**本次提交的文件**：
```
aac2657 v1.10: 新增契约符合性门禁 tests/unit/test_contract_conformance.py（25 项）：不再写我自己的期望值，而是直接读 .interface_contract/interface-contract.json 原文逐条核对本侧实现——rule_crosswalk.upstream_only 21 条逐条 code/owner/severity、new_rules_required O1/O2 含 action 文案逐字、owner/verdict 词表集合、event_partition 12 事件与声明 count、phases_partition 5 阶段且顺序相同、version_axes 的两条版本、client_report_schema.canonical_fields 字段集合、fact_sources 的 backend 路径真实可解析、endpoint_partition 里前端代理的 7 条上游端点仍在提供、response_contract 的 warnings 类型/缺席即空/ops 栏保留未判定项/profile 新增项；并加防空转断言（从契约推导出的断言数≥18），契约结构一变解析取不到东西就会假通过。动机：统筹方是打接口手工复验（OPS-1 那次 6/6 手工），手工复验只覆盖那一轮，我之后改代码没人再看。它第一次运行就抓到两处真问题：(1) 契约 canonical_fields 是 9 项（v1.0.2 起就含 ops），而我的 PEER_FIELDS 只有 8 项——我上一轮为了『不让契约过期』刻意排除 ops，结果变成我的 describe().peer_report_fields 与契约对不上，属我在已交出的评估文档里的错，已修 PEER_FIELDS 并同步 FRONTEND_CONTRACT §6.2/§6.4/§8 与 MODULES §23，并在 EVALUATION-OPS-1 加 §5.1 勘误（不改写已交文档的结论）；(2) 检查器自己的 bug——fact_sources 的 core.cycle.CycleReport.to_dict 这种点号属性路径只 rpartition 一次解析不了，改为从长到短试模块前缀再逐级 getattr。顺带把契约版本引用升到 v1.0.5，并改用字节读写做批量替换（Path.read_text/write_text 的换行翻译本轮已坑两次）。契约目录仍只读。全量 27/27、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、契约不变量 20/20、归因 97/97、符合性 25/25、真实 E2E L1 PASS。
 CYCLE.md                                |   2 +-
 README.md                               |   2 +-
 core/contract.py                        |  15 +-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  68 ++++++++
 docs/EVALUATION-OPS-1.md                |  17 ++
 docs/FRONTEND_CONTRACT.md               |  19 +-
 docs/MODULES.md                         |  11 +-
 docs/OPERATIONS.md                      |   2 +-
 tests/README.md                         |   1 +
 tests/unit/test_contract_conformance.py | 296 ++++++++++++++++++++++++++++++++
 11 files changed, 420 insertions(+), 15 deletions(-)
```

---

## v1.11 — 2026-09-26 09:44

**改动**：架构清单 A1b（用户已批准 P1-P5，后端侧唯一一项）：让 /contract/check 自述权威范围。新增 AUTHORITY_SCOPE（id/role/covers/not_covers/rule_source/counterpart/policy，单一来源，同时进 /contract/check 响应与 /profile 的 contract 段），其中 not_covers 主动划出本侧不该管的范围（本地环境细节→/api/audit），因为 A1 的决定是按职责切分而非合并，切分成立的前提是两侧各自声明管什么。新增 responsibility_fingerprint()：规则表内容指纹，只覆盖 code|owner|severity——刻意收窄，改 why/action 文案不该惊动消费方，而增删规则或改归属/级别必须可察；实测三态：原 740c48d2、改文案后不变、改 owner 后 4ff7e560、恢复后回原值。A1 验收『两入口 owner 归属一致』：/api/audit 在前端仓库本侧调不到，故做静态锚定版——拿契约 rule_crosswalk（两侧商定的统一映射）当锚点逐行断言本侧 owner == unified_owner；实测 17 行中 8 行无上游等价（属 bridge 本地自检）、8 行完整比对、2 行部分等价、1 行 SPLIT，owner/severity 零不一致。踩到一个坑并修掉：upstream_equivalent 是带注释自由文本（U-removed-surface (部分) / SPLIT / 无（…）），第一版直接查表误报 5 条『本侧缺失』，改成取前导 code + 识别限定词（部分等价只比 owner、SPLIT 只验存在）后归零——与 §26 同型：检查器第一版总是判据写宽了。新增 docs/EVALUATION-ARCH-A1B.md（九节 + C1-C8 自检，含改动清单 2 文件 166 增 2 删 + 显式列出 stat 之外的登记文件含 VERSIONS.md，并把上轮漏写 VERSIONS.md 的教训写进去）。契约目录仍只读。全量 27/27、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、符合性 37/37、归因 97/97、契约不变量 20/20、真实 E2E L1 PASS。

**备份点**：本条目所在的提交（提交信息以 `v1.11:` 开头）

**定位命令**：`git log --oneline --grep "^v1.11:"`

**验证**：
- 全量单测 PASS (27/27)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 27 个

**本次提交的文件**：
```
9fd88c2 v1.11: 架构清单 A1b（用户已批准 P1-P5，后端侧唯一一项）：让 /contract/check 自述权威范围。新增 AUTHORITY_SCOPE（id/role/covers/not_covers/rule_source/counterpart/policy，单一来源，同时进 /contract/check 响应与 /profile 的 contract 段），其中 not_covers 主动划出本侧不该管的范围（本地环境细节→/api/audit），因为 A1 的决定是按职责切分而非合并，切分成立的前提是两侧各自声明管什么。新增 responsibility_fingerprint()：规则表内容指纹，只覆盖 code|owner|severity——刻意收窄，改 why/action 文案不该惊动消费方，而增删规则或改归属/级别必须可察；实测三态：原 740c48d2、改文案后不变、改 owner 后 4ff7e560、恢复后回原值。A1 验收『两入口 owner 归属一致』：/api/audit 在前端仓库本侧调不到，故做静态锚定版——拿契约 rule_crosswalk（两侧商定的统一映射）当锚点逐行断言本侧 owner == unified_owner；实测 17 行中 8 行无上游等价（属 bridge 本地自检）、8 行完整比对、2 行部分等价、1 行 SPLIT，owner/severity 零不一致。踩到一个坑并修掉：upstream_equivalent 是带注释自由文本（U-removed-surface (部分) / SPLIT / 无（…）），第一版直接查表误报 5 条『本侧缺失』，改成取前导 code + 识别限定词（部分等价只比 owner、SPLIT 只验存在）后归零——与 §26 同型：检查器第一版总是判据写宽了。新增 docs/EVALUATION-ARCH-A1B.md（九节 + C1-C8 自检，含改动清单 2 文件 166 增 2 删 + 显式列出 stat 之外的登记文件含 VERSIONS.md，并把上轮漏写 VERSIONS.md 的教训写进去）。契约目录仍只读。全量 27/27、文档一致性 35/35、文档不变量 28/28、文档审查 18/18、符合性 37/37、归因 97/97、契约不变量 20/20、真实 E2E L1 PASS。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/contract.py                        |  57 +++++++
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  82 +++++++++
 docs/EVALUATION-ARCH-A1B.md             | 294 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |  37 ++++
 docs/MODULES.md                         |  25 ++-
 docs/OPERATIONS.md                      |   2 +-
 tests/unit/test_contract_conformance.py | 111 +++++++++++-
 10 files changed, 605 insertions(+), 10 deletions(-)
```

---

## v1.12 — 2026-09-26 10:34

**改动**：ARCH-D1：P-phase-unknown 由 backend/breaking 改判 both/degraded（契约 v1.0.7 先行改判，本侧跟随）。原判是错的：判词写『上游删/改了阶段名』，即看到对端报了一个我没有的阶段就推定是自己删的——而实测那个 manifest 是 bridge 在 write 与 check 之间自补的门禁节点，后端从没删过任何阶段；契约 empirical_evidence.S2 已在真实服务上打出 verdict=backend-action 这个错误归因。改后同一输入 verdict 由 backend-action 变 need-negotiation，backend 栏归零。不丢检测的论证：真正的『上游删阶段』由 U-removed-surface(backend/breaking) 覆盖，它与本条的判据完全不同——前者拿本侧冻结面与本侧代码比、不依赖对端上报，后者才依赖对端；已写成两条断言（U-removed-surface 仍 backend/breaking、该情形下 backend 栏必须为空）。同时补做契约 v1.0.7 带出的另一半任务：新增 bridge_gate_steps 上报字段（PEER_FIELDS 第 10 项）+ 实现 client_report_schema.phase_unknown_decision_tree 三支（命中 bridge_gate_steps→frontend 且 action 直接指名；∈FROZEN_PHASES∉PHASE_ORDER→backend；其余→both 保持『先确认方向』不伪造方向），方向经 evidence.direction 机器可读暴露；为此新增 Issue.action_override——刻意只允许改文案、owner/severity 永远取规则表，否则『归属只有一个来源』就破了，已写成断言。这半个任务是符合性门禁先发现的（canonical_fields 由 9 项变 10 项报红），否则会漏。指纹按设计由 740c48d2 变 af6bfe2a（改归属必变），已同步 FRONTEND_CONTRACT/MODULES 当前值并在 EVALUATION-ARCH-A1B 注明那里是变更时点快照。上一轮三个提问均被契约以文本+机器可核方式回答（bridge_gate_steps/决策树、severity_consumer_obligation 明确 degraded 必须呈现且生产方不得抬回 breaking、指纹已登记进 profile_additions）。核过一个边界并写成一对断言：failed ∈FROZEN_PHASES 且 ∉PHASE_ORDER 看似命中情形2，实际不行——本规则触发条件是阶段∉全部 CyclePhase 值，而 failed 是 CyclePhase 成员。报两处契约内不一致（只报不改）：phases_partition.consequence 仍写 breaking/owner=backend 与 rule_crosswalk 已改判矛盾；open_items 的 awaiting_side_confirmation 仍列已结清的 ops_report_constraint、awaiting_user_approval 仍写当前 v1.0.2。顺带修：行尾门禁第一版每文件起一个 git 进程（约 200 次）导致全量测试超时，改用一次 git ls-files --eol，耗时 >120 秒降到 1.15 秒且顺带能抓 w/mixed——教训是慢门禁等于会被绕过的门禁。全量 27/27、文档一致性 35/35、文档不变量 29/29、文档审查 18/18、符合性 38/38、归因 113/113、前端契约不变量 20/20、真实 E2E L1 PASS。

**备份点**：本条目所在的提交（提交信息以 `v1.12:` 开头）

**定位命令**：`git log --oneline --grep "^v1.12:"`

**验证**：
- 全量单测 PASS (27/27)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 27 个

**本次提交的文件**：
```
fd7266b v1.12: ARCH-D1：P-phase-unknown 由 backend/breaking 改判 both/degraded（契约 v1.0.7 先行改判，本侧跟随）。原判是错的：判词写『上游删/改了阶段名』，即看到对端报了一个我没有的阶段就推定是自己删的——而实测那个 manifest 是 bridge 在 write 与 check 之间自补的门禁节点，后端从没删过任何阶段；契约 empirical_evidence.S2 已在真实服务上打出 verdict=backend-action 这个错误归因。改后同一输入 verdict 由 backend-action 变 need-negotiation，backend 栏归零。不丢检测的论证：真正的『上游删阶段』由 U-removed-surface(backend/breaking) 覆盖，它与本条的判据完全不同——前者拿本侧冻结面与本侧代码比、不依赖对端上报，后者才依赖对端；已写成两条断言（U-removed-surface 仍 backend/breaking、该情形下 backend 栏必须为空）。同时补做契约 v1.0.7 带出的另一半任务：新增 bridge_gate_steps 上报字段（PEER_FIELDS 第 10 项）+ 实现 client_report_schema.phase_unknown_decision_tree 三支（命中 bridge_gate_steps→frontend 且 action 直接指名；∈FROZEN_PHASES∉PHASE_ORDER→backend；其余→both 保持『先确认方向』不伪造方向），方向经 evidence.direction 机器可读暴露；为此新增 Issue.action_override——刻意只允许改文案、owner/severity 永远取规则表，否则『归属只有一个来源』就破了，已写成断言。这半个任务是符合性门禁先发现的（canonical_fields 由 9 项变 10 项报红），否则会漏。指纹按设计由 740c48d2 变 af6bfe2a（改归属必变），已同步 FRONTEND_CONTRACT/MODULES 当前值并在 EVALUATION-ARCH-A1B 注明那里是变更时点快照。上一轮三个提问均被契约以文本+机器可核方式回答（bridge_gate_steps/决策树、severity_consumer_obligation 明确 degraded 必须呈现且生产方不得抬回 breaking、指纹已登记进 profile_additions）。核过一个边界并写成一对断言：failed ∈FROZEN_PHASES 且 ∉PHASE_ORDER 看似命中情形2，实际不行——本规则触发条件是阶段∉全部 CyclePhase 值，而 failed 是 CyclePhase 成员。报两处契约内不一致（只报不改）：phases_partition.consequence 仍写 breaking/owner=backend 与 rule_crosswalk 已改判矛盾；open_items 的 awaiting_side_confirmation 仍列已结清的 ops_report_constraint、awaiting_user_approval 仍写当前 v1.0.2。顺带修：行尾门禁第一版每文件起一个 git 进程（约 200 次）导致全量测试超时，改用一次 git ls-files --eol，耗时 >120 秒降到 1.15 秒且顺带能抓 w/mixed——教训是慢门禁等于会被绕过的门禁。全量 27/27、文档一致性 35/35、文档不变量 29/29、文档审查 18/18、符合性 38/38、归因 113/113、前端契约不变量 20/20、真实 E2E L1 PASS。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/contract.py                        |  88 +++++++-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       | 177 +++++++++++++++
 docs/EVALUATION-ARCH-A1B.md             |   6 +
 docs/EVALUATION-ARCH-D1.md              | 369 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |  45 +++-
 docs/MODULES.md                         |  29 ++-
 docs/OPERATIONS.md                      |   2 +-
 tests/unit/test_contract_attribution.py |  81 ++++++-
 tests/unit/test_doc_invariants.py       |  71 +++---
 12 files changed, 815 insertions(+), 60 deletions(-)
```

---

## v1.13 — 2026-09-26 11:54

**改动**：修五个缺陷（用户报『只能跑样例需求，我跑的需求失败了』，需求=读取当前根目录所有文件输出一个txt）。定位：用户那次走前端独立运行根，事件在 SimpleAgent2_Cycle_VueWeb\data\storage_data\runs\run_20260926_112631_e0b705\events.jsonl，从事件流重建失败链。缺陷一（根因）：check_manifest 判断声明文件只查符号索引，而索引只收 .py，于是任何非 Python 交付物必然 declared-missing——files_list.txt 明明已写出92字节仍被判不存在，cycle 直接 failed；这就是『只能跑样例需求』的根因（阶梯样本全产 .py）。修法：声明文件先查索引（.py 走结构校验），不在索引就查磁盘（_disk_fact：存在性+size+sha1），另加 not-indexed / symbols-unverifiable 两条 warning 不静默通过。缺陷二：_ask 里 _emit('decision_opened',...,kind=kind) 的 kind 与 _emit 参数名同名，调用点在参数绑定阶段就抛 TypeError，连函数体都进不去——repeated_failure/risky_rollback 两条人工决策路径 100% 不可用，前端装 bridge 钩子时把整轮 run 变成 status=error；而 _ask 的 docstring 明写『本方法不会抛异常』且该路径零测试覆盖。修法：payload 键 kind→decision_kind（对任何镜像签名的钩子都安全）+ _emit 首参改名 event_kind 做二次防御 + 新增 AST 门禁（扫全部18个调用点，payload 键不得撞位置绑定参数名）+ 新增 test_decision_path.py 11项运行时回归（含文档承诺『不抛异常』）。缺陷三：list_workspace 只过滤 _ 开头目录，把 .git 里 249 个文件倒给模型，模型照单全收写进交付物；改为与 symbol_index._SKIP_DIRS 共用同一份策略并新增 total/listed/truncated/skipped_dir_names（截断要明说），同 workspace 从 251 降到 2 个文件。缺陷四（系统性）：5 个测试文件永远不会让套件变红——run_unit 与 backup 只看退出码，而 test_manifest/test_cycle_manifest/test_adapter/test_quality 只打印 PASS/FAIL、test_check_pipeline 8 个场景一条断言都没有；这直接解释了缺陷二为何能活很久。五个文件全部改为以退出码表达结论，check_pipeline 的 8 个场景落成 13 条真断言，并新增 test_suite_hygiene.py 门禁（AST 断言每个测试文件必须能失败，29/29 达标）。缺陷五：提示词例子自相矛盾——files.path/description 带 workspace/ 前缀而 verify 不带，而 tools/verify.py 与 python_exec 的 cwd 就是 workspace 根，模型照抄前缀写 verify 必然 FileNotFoundError；修法：ORCHESTRATOR_SYSTEM 补第13条路径约定（三处必须同一种写法）并统一例子去掉前缀、WORKER_SYSTEM 补第14条、write_file 保留前缀容忍但在返回值里就地纠正。端到端：用户原话做成常驻复现工具 tests/diagnostics/repro_user_goal.py（临时 workspace）；修复前 phase=failed+TypeError，只修缺陷一时 phase=record/4轮23.7s，全部修完后 phase=record/1轮6.9-7.3s，连跑3次 exit=0（其中一次模型首次列的清单内容不对、verify 反馈后自行重试成功——内容正确性仍受7B能力边界限制）。契约可见改动：decision_opened 的 payload 键 kind→decision_kind，已核实前端未读该键，已登记 EVENTS.note 与 FRONTEND_CONTRACT §3.1，未擅自升 CONTRACT_VERSION。另需前端把 bridge/hooks.py 的钩子包装器改成透传（*args/**kwargs）——它镜像了 _emit 签名、参数名叫 kind，现状已从调用点规避但结构上仍脆弱。全量 30/30、文档一致性 35/35、文档不变量 29/29、文档审查 18/18、契约不变量 23/23、归因 113/113、符合性 38/38、真实 E2E L1 PASS、用户需求复现 3/3 通过。

**备份点**：本条目所在的提交（提交信息以 `v1.13:` 开头）

**定位命令**：`git log --oneline --grep "^v1.13:"`

**验证**：
- 全量单测 PASS (30/30)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 30 个

**本次提交的文件**：
```
448d318 v1.13: 修五个缺陷（用户报『只能跑样例需求，我跑的需求失败了』，需求=读取当前根目录所有文件输出一个txt）。定位：用户那次走前端独立运行根，事件在 SimpleAgent2_Cycle_VueWeb\data\storage_data\runs\run_20260926_112631_e0b705\events.jsonl，从事件流重建失败链。缺陷一（根因）：check_manifest 判断声明文件只查符号索引，而索引只收 .py，于是任何非 Python 交付物必然 declared-missing——files_list.txt 明明已写出92字节仍被判不存在，cycle 直接 failed；这就是『只能跑样例需求』的根因（阶梯样本全产 .py）。修法：声明文件先查索引（.py 走结构校验），不在索引就查磁盘（_disk_fact：存在性+size+sha1），另加 not-indexed / symbols-unverifiable 两条 warning 不静默通过。缺陷二：_ask 里 _emit('decision_opened',...,kind=kind) 的 kind 与 _emit 参数名同名，调用点在参数绑定阶段就抛 TypeError，连函数体都进不去——repeated_failure/risky_rollback 两条人工决策路径 100% 不可用，前端装 bridge 钩子时把整轮 run 变成 status=error；而 _ask 的 docstring 明写『本方法不会抛异常』且该路径零测试覆盖。修法：payload 键 kind→decision_kind（对任何镜像签名的钩子都安全）+ _emit 首参改名 event_kind 做二次防御 + 新增 AST 门禁（扫全部18个调用点，payload 键不得撞位置绑定参数名）+ 新增 test_decision_path.py 11项运行时回归（含文档承诺『不抛异常』）。缺陷三：list_workspace 只过滤 _ 开头目录，把 .git 里 249 个文件倒给模型，模型照单全收写进交付物；改为与 symbol_index._SKIP_DIRS 共用同一份策略并新增 total/listed/truncated/skipped_dir_names（截断要明说），同 workspace 从 251 降到 2 个文件。缺陷四（系统性）：5 个测试文件永远不会让套件变红——run_unit 与 backup 只看退出码，而 test_manifest/test_cycle_manifest/test_adapter/test_quality 只打印 PASS/FAIL、test_check_pipeline 8 个场景一条断言都没有；这直接解释了缺陷二为何能活很久。五个文件全部改为以退出码表达结论，check_pipeline 的 8 个场景落成 13 条真断言，并新增 test_suite_hygiene.py 门禁（AST 断言每个测试文件必须能失败，29/29 达标）。缺陷五：提示词例子自相矛盾——files.path/description 带 workspace/ 前缀而 verify 不带，而 tools/verify.py 与 python_exec 的 cwd 就是 workspace 根，模型照抄前缀写 verify 必然 FileNotFoundError；修法：ORCHESTRATOR_SYSTEM 补第13条路径约定（三处必须同一种写法）并统一例子去掉前缀、WORKER_SYSTEM 补第14条、write_file 保留前缀容忍但在返回值里就地纠正。端到端：用户原话做成常驻复现工具 tests/diagnostics/repro_user_goal.py（临时 workspace）；修复前 phase=failed+TypeError，只修缺陷一时 phase=record/4轮23.7s，全部修完后 phase=record/1轮6.9-7.3s，连跑3次 exit=0（其中一次模型首次列的清单内容不对、verify 反馈后自行重试成功——内容正确性仍受7B能力边界限制）。契约可见改动：decision_opened 的 payload 键 kind→decision_kind，已核实前端未读该键，已登记 EVENTS.note 与 FRONTEND_CONTRACT §3.1，未擅自升 CONTRACT_VERSION。另需前端把 bridge/hooks.py 的钩子包装器改成透传（*args/**kwargs）——它镜像了 _emit 签名、参数名叫 kind，现状已从调用点规避但结构上仍脆弱。全量 30/30、文档一致性 35/35、文档不变量 29/29、文档审查 18/18、契约不变量 23/23、归因 113/113、符合性 38/38、真实 E2E L1 PASS、用户需求复现 3/3 通过。
 CYCLE.md                             |   2 +-
 README.md                            |   2 +-
 core/coding_cycle.py                 |  22 +++-
 core/contract.py                     |   7 +-
 core/manifest.py                     |  73 ++++++++++++-
 core/prompts.py                      |  14 ++-
 docs/ARCHITECTURE.md                 |   2 +-
 docs/CHANGELOG.md                    | 206 +++++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md            |  20 ++++
 docs/MODULES.md                      |  30 ++++-
 docs/OPERATIONS.md                   |   2 +-
 tests/README.md                      |   6 +-
 tests/diagnostics/repro_user_goal.py |  77 +++++++++++++
 tests/unit/test_adapter.py           |   9 +-
 tests/unit/test_check_pipeline.py    |  60 +++++++---
 tests/unit/test_cycle_manifest.py    |   5 +
 tests/unit/test_decision_path.py     | 150 +++++++++++++++++++++++++
 tests/unit/test_frontend_contract.py |  66 +++++++++++
 tests/unit/test_manifest.py          |  43 +++++++-
 tests/unit/test_quality.py           |   6 +-
 tests/unit/test_suite_hygiene.py     | 107 ++++++++++++++++++
 tests/unit/test_workspace_tool.py    |  91 ++++++++++++++++
 tools/code_checks.py                 |  34 +++++-
 tools/files.py                       |  26 ++++-
 24 files changed, 1019 insertions(+), 41 deletions(-)
```

---

## v1.14 — 2026-09-26 12:17

**改动**：ARCH-D7（含裁决② / D10 / D5）。D7 必修：bridge_gate_steps 在 HTTP 路径上是死代码——它只在 PEER_FIELDS 声明与 contract.py 决策树分支里，main.py 的 ContractPeer 漏了它，Pydantic 静默丢弃，于是那条『方向已定』分支在 HTTP 上永不触发；而生产路径（前端运维机制）走的就是 HTTP。决定性证据是同一输入两条路径结果不同：进程内 compare() 得到『方向已定』、HTTP 得到『先确认方向』。我上一轮自验之所以通过，是因为那份证据是进程内拿到的——验证方式与生产路径不一致，函数级测试全绿、接口层静默失效。修法：ContractPeer 补该字段 + 新增 test_contract_conformance [12] 组，必须经 HTTP 请求模型断言三件事（契约每个 canonical_field 都在请求模型里 / 经 HTTP 上报后 action 应当变化 / 方向已定后 owner 仍是 both），另把 docstring 的 8 项改为 10 项。裁决②：CONTRACT_VERSION 由 1.0 升 1.1——我原先判该 payload 改名非破坏性，依据是『已核实前端未读该键』，但核实不完整：漏了 bridge/runner.py 的扁平化 {seq,ts,kind,run_id,goal,attempt,**payload}（payload 在后展开，所以改名前 payload.kind 覆盖记录的 kind，ev.kind=决策种类；改名后 ev.kind=decision_opened，前端 run.ts 把决策种类显示成事件名），确实有消费方要改（前端 D8）。接受裁决的理由：契约的价值在于『破坏性改动=版本一定变了』这条无条件成立，我按『影响大不大』判断等于削弱信号本身。顺带修正版本轴断言的写法：CONTRACT_VERSION 的载体是本侧，契约 observed_value 是对我的快照，故 [4] 组改成方向感知——本侧领先=台账滞后（打印请更新，不判失败）、台账领先=硬失败。D10：payload 键还能覆盖前端扁平化后的记录字段（不报错、静默改语义，decision_opened.kind 就是这一类的真实事故）；新增 RECORD_FIELDS 与 PAYLOAD_SHARED_KEYS（goal/attempt 故意共用、必须写明理由），门禁逐条扫全部 _emit 调用点，实测未豁免却撞记录字段的为空。D5：文档门禁从查条数升级为逐行比对 §6.5 规则表的 (owner,severity)——它第一次运行就抓到两件事：我的解析器没处理 markdown 粗体（**协商** 导致误报 D4），以及 P-schema-behind/ahead 两个 code 挤在同一行导致机器无法逐行解析（已拆成两行）；修完 23 行/23 条/零不一致，并做负向测试证明它会抓（退出码 1，精确报出 owner 与 severity 两处不一致）——负向测试本身也踩了坑：PowerShell here-string 把反引号当转义符吃掉导致搜索串没匹配、文件根本没改、门禁报『无不一致』看起来像失效，改用脚本文件后正常。统筹方对我 §9 三问的回答已接受（不做删阶段演练、不改 degraded 级别而改展示策略、先确认方向可接受并已写成决策树）。全量 30/30、文档一致性 35/35、文档不变量 31/31、文档审查 18/18、符合性 43/43、前端契约不变量 25/25、归因 113/113、真实 E2E L1 PASS、§6.5 逐行 23/23 零不一致。

**备份点**：本条目所在的提交（提交信息以 `v1.14:` 开头）

**定位命令**：`git log --oneline --grep "^v1.14:"`

**验证**：
- 全量单测 PASS (30/30)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 30 个

**本次提交的文件**：
```
b16550a v1.14: ARCH-D7（含裁决② / D10 / D5）。D7 必修：bridge_gate_steps 在 HTTP 路径上是死代码——它只在 PEER_FIELDS 声明与 contract.py 决策树分支里，main.py 的 ContractPeer 漏了它，Pydantic 静默丢弃，于是那条『方向已定』分支在 HTTP 上永不触发；而生产路径（前端运维机制）走的就是 HTTP。决定性证据是同一输入两条路径结果不同：进程内 compare() 得到『方向已定』、HTTP 得到『先确认方向』。我上一轮自验之所以通过，是因为那份证据是进程内拿到的——验证方式与生产路径不一致，函数级测试全绿、接口层静默失效。修法：ContractPeer 补该字段 + 新增 test_contract_conformance [12] 组，必须经 HTTP 请求模型断言三件事（契约每个 canonical_field 都在请求模型里 / 经 HTTP 上报后 action 应当变化 / 方向已定后 owner 仍是 both），另把 docstring 的 8 项改为 10 项。裁决②：CONTRACT_VERSION 由 1.0 升 1.1——我原先判该 payload 改名非破坏性，依据是『已核实前端未读该键』，但核实不完整：漏了 bridge/runner.py 的扁平化 {seq,ts,kind,run_id,goal,attempt,**payload}（payload 在后展开，所以改名前 payload.kind 覆盖记录的 kind，ev.kind=决策种类；改名后 ev.kind=decision_opened，前端 run.ts 把决策种类显示成事件名），确实有消费方要改（前端 D8）。接受裁决的理由：契约的价值在于『破坏性改动=版本一定变了』这条无条件成立，我按『影响大不大』判断等于削弱信号本身。顺带修正版本轴断言的写法：CONTRACT_VERSION 的载体是本侧，契约 observed_value 是对我的快照，故 [4] 组改成方向感知——本侧领先=台账滞后（打印请更新，不判失败）、台账领先=硬失败。D10：payload 键还能覆盖前端扁平化后的记录字段（不报错、静默改语义，decision_opened.kind 就是这一类的真实事故）；新增 RECORD_FIELDS 与 PAYLOAD_SHARED_KEYS（goal/attempt 故意共用、必须写明理由），门禁逐条扫全部 _emit 调用点，实测未豁免却撞记录字段的为空。D5：文档门禁从查条数升级为逐行比对 §6.5 规则表的 (owner,severity)——它第一次运行就抓到两件事：我的解析器没处理 markdown 粗体（**协商** 导致误报 D4），以及 P-schema-behind/ahead 两个 code 挤在同一行导致机器无法逐行解析（已拆成两行）；修完 23 行/23 条/零不一致，并做负向测试证明它会抓（退出码 1，精确报出 owner 与 severity 两处不一致）——负向测试本身也踩了坑：PowerShell here-string 把反引号当转义符吃掉导致搜索串没匹配、文件根本没改、门禁报『无不一致』看起来像失效，改用脚本文件后正常。统筹方对我 §9 三问的回答已接受（不做删阶段演练、不改 degraded 级别而改展示策略、先确认方向可接受并已写成决策树）。全量 30/30、文档一致性 35/35、文档不变量 31/31、文档审查 18/18、符合性 43/43、前端契约不变量 25/25、归因 113/113、真实 E2E L1 PASS、§6.5 逐行 23/23 零不一致。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/contract.py                        |  32 +++-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       | 125 ++++++++++++
 docs/EVALUATION-ARCH-D7.md              | 330 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |  47 ++++-
 docs/MODULES.md                         |  12 +-
 docs/OPERATIONS.md                      |   2 +-
 main.py                                 |  23 ++-
 tests/unit/test_contract_conformance.py |  92 ++++++++-
 tests/unit/test_doc_invariants.py       |  45 +++++
 tests/unit/test_frontend_contract.py    |  31 +++
 13 files changed, 719 insertions(+), 27 deletions(-)
```

---

## v1.15 — 2026-09-26 13:30

**改动**：定位『修了但没生效』：前端加载的是它自带的陈旧后端副本（SimpleAgent2_Cycle_VueWeb/backend），我 v1.13 的五项修复一行都没被加载。证据：用户 12:51 那次运行失败签名与修之前逐字相同（declared-missing all_files.txt 而模型确实写了它 + TypeError: install.<locals>._emit() got multiple values for argument kind + list_workspace 又把 .git 喂给模型）；bridge/paths.py 的判据是 AGENT_BACKEND_DIR 未设就用 <VueWeb>/backend 兜底，而前端仓库没有 .env；逐文件比对显示该副本缺失 3 个文件（core/contract.py、core/vision.py、web/__init__.py）、17 个落后（core/manifest.py 停在 9-25 20:00），五项修复逐项核查全部为『缺』。★ 本轮真正的教训：我用 repro_user_goal.py 端到端跑通了同一需求却对用户毫无作用，因为那个复现是在我自己的运行时跑我自己的代码——与 D7 同一个病根（验证方式≠生产路径），这次是验证环境≠用户运行环境；记成纪律：任何『修好了』的主张必须先证明『跑的是这份代码』，即先回答『当前生效的到底是哪一份』。本侧交付两个只读/只预演的诊断工具：backend_dir_check.py（按与 paths.py 同源判据算出会加载哪个目录，逐文件比对缺失/落后，并逐项核查四项关键修复在不在那一份里，给出两种改法与结论）与 sync_backend_copy.py（兜底用的搬过去，默认只预演不写文件，只复制白名单子树 core/tools/storage/web+main.py，覆盖前备份，绝不删除副本多出的文件）。给用户两条命令（都不在我这侧，沙箱也不允许我写他们仓库）：①首选在前端仓库根建 .env 写 AGENT_BACKEND_DIR=D:\\PythonProject\\SimpleAgent2_Cycle（bootstrap.py 会 load_dotenv，指过去不搬代码，此后上游改动立即生效）；②兜底用 sync_backend_copy.py。并明确警示：不要用前端自带的 scripts/adopt-backend.ps1 -From <本仓库根>——它的实现是先清空 backend/ 再把 -From 下所有东西复制进去，会把 .venv/.git/workspace/tests/docs 一起搬进去。全量 30/30、文档一致性 35/35、文档不变量 31/31、文档审查 18/18。

**备份点**：本条目所在的提交（提交信息以 `v1.15:` 开头）

**定位命令**：`git log --oneline --grep "^v1.15:"`

**验证**：
- 全量单测 PASS (30/30)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 29 个 · 测试文件 30 个

**本次提交的文件**：
```
b43bf35 v1.15: 定位『修了但没生效』：前端加载的是它自带的陈旧后端副本（SimpleAgent2_Cycle_VueWeb/backend），我 v1.13 的五项修复一行都没被加载。证据：用户 12:51 那次运行失败签名与修之前逐字相同（declared-missing all_files.txt 而模型确实写了它 + TypeError: install.<locals>._emit() got multiple values for argument kind + list_workspace 又把 .git 喂给模型）；bridge/paths.py 的判据是 AGENT_BACKEND_DIR 未设就用 <VueWeb>/backend 兜底，而前端仓库没有 .env；逐文件比对显示该副本缺失 3 个文件（core/contract.py、core/vision.py、web/__init__.py）、17 个落后（core/manifest.py 停在 9-25 20:00），五项修复逐项核查全部为『缺』。★ 本轮真正的教训：我用 repro_user_goal.py 端到端跑通了同一需求却对用户毫无作用，因为那个复现是在我自己的运行时跑我自己的代码——与 D7 同一个病根（验证方式≠生产路径），这次是验证环境≠用户运行环境；记成纪律：任何『修好了』的主张必须先证明『跑的是这份代码』，即先回答『当前生效的到底是哪一份』。本侧交付两个只读/只预演的诊断工具：backend_dir_check.py（按与 paths.py 同源判据算出会加载哪个目录，逐文件比对缺失/落后，并逐项核查四项关键修复在不在那一份里，给出两种改法与结论）与 sync_backend_copy.py（兜底用的搬过去，默认只预演不写文件，只复制白名单子树 core/tools/storage/web+main.py，覆盖前备份，绝不删除副本多出的文件）。给用户两条命令（都不在我这侧，沙箱也不允许我写他们仓库）：①首选在前端仓库根建 .env 写 AGENT_BACKEND_DIR=D:\\PythonProject\\SimpleAgent2_Cycle（bootstrap.py 会 load_dotenv，指过去不搬代码，此后上游改动立即生效）；②兜底用 sync_backend_copy.py。并明确警示：不要用前端自带的 scripts/adopt-backend.ps1 -From <本仓库根>——它的实现是先清空 backend/ 再把 -From 下所有东西复制进去，会把 .venv/.git/workspace/tests/docs 一起搬进去。全量 30/30、文档一致性 35/35、文档不变量 31/31、文档审查 18/18。
 CYCLE.md                               |   2 +-
 README.md                              |   2 +-
 docs/ARCHITECTURE.md                   |   2 +-
 docs/CHANGELOG.md                      |  99 ++++++++++++++++++++
 docs/MODULES.md                        |   2 +-
 docs/OPERATIONS.md                     |   2 +-
 tests/README.md                        |   2 +
 tests/diagnostics/backend_dir_check.py | 163 +++++++++++++++++++++++++++++++++
 tests/diagnostics/sync_backend_copy.py | 116 +++++++++++++++++++++++
 9 files changed, 385 insertions(+), 5 deletions(-)
```

---

## v1.16 — 2026-09-26 13:40

**改动**：采纳统筹方 INCIDENT-20260926 事故分析（结论与 §31 一致：实例跑的是 VueWeb\backend 陈旧副本，v1.13 修复没进来）。只做归属本侧的四条：R3 运行记录自报代码身份——新增 core/identity.py（code_dir/package_dir/fingerprint/module_files），写进每次运行的 cycle_start 事件（事后可查）与 /profile 的 code 段（当场可查），EVENTS[cycle_start] 声明同步扩两个 additive 键并在 note 点明『backend 是检查点后端不是代码来源』这个易混点；R4 内容级陈旧判据——code_fingerprint() 对代码内容取 8 位指纹（只覆盖 core/tools/storage/web+main.py，刻意不含文档/测试/产物），backend_dir_check.py 现在并排打印两侧指纹（上游 da1c3994 vs 被加载的那一份 4062e75d → 一眼看出内容不同），前端 staleness 若要加内容级判据可直接取本模块，参照物由上游提供；R5 认知记录——实测确认透传包装器内部 sig.bind 会忠实复现被包装函数的签名，所以『包装器已透传』只保证上游以后再改也不怕，不等于旧上游也能跑（旧签名冲突仍在，只能在调用点/上游侧修），已写进 FRONTEND_CONTRACT §3.3 避免下次误判；R8 纪律——先确认要查的是哪一份代码，已写进 OPERATIONS §1.3.1 作为排查『改了没生效』的第一步。如实标注不属本侧的四条：R1 设 AGENT_BACKEND_DIR（部署配置/用户，根因）、R2 把 backend_stale 提到必经路径（前后端联动）、R6 过期副本处置（架构级需用户批准）、R7 统筹方自己的验收盲区（他们已认领）；并附实测提醒：前端 scripts/adopt-backend.ps1 -From 会先清空 backend/ 再复制 -From 下所有东西，不能指向本仓库根。★ 新能力特意在生产路径上验证（吸取 D7『验证方式≠生产路径』与 §31『验证环境≠用户环境』两条教训）：repro_user_goal.py 真实跑一轮后从真实存储读回 cycle_start 事件断言身份完整且与当前代码一致（实测 code_dir=D:\PythonProject\SimpleAgent2_Cycle code_fingerprint=da1c3994 自报完整=True 一致=True）。新增 test_identity.py 12 项（稳定/改一字节就变/加文档不变）。全量 31/31、文档一致性 35/35、文档不变量 31/31、文档审查 18/18、前端契约不变量 25/25、符合性 43/43、归因 113/113、真实 E2E L1 PASS。

**备份点**：本条目所在的提交（提交信息以 `v1.16:` 开头）

**定位命令**：`git log --oneline --grep "^v1.16:"`

**验证**：
- 全量单测 PASS (31/31)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 30 个 · 测试文件 31 个

**本次提交的文件**：
```
2f6545d v1.16: 采纳统筹方 INCIDENT-20260926 事故分析（结论与 §31 一致：实例跑的是 VueWeb\backend 陈旧副本，v1.13 修复没进来）。只做归属本侧的四条：R3 运行记录自报代码身份——新增 core/identity.py（code_dir/package_dir/fingerprint/module_files），写进每次运行的 cycle_start 事件（事后可查）与 /profile 的 code 段（当场可查），EVENTS[cycle_start] 声明同步扩两个 additive 键并在 note 点明『backend 是检查点后端不是代码来源』这个易混点；R4 内容级陈旧判据——code_fingerprint() 对代码内容取 8 位指纹（只覆盖 core/tools/storage/web+main.py，刻意不含文档/测试/产物），backend_dir_check.py 现在并排打印两侧指纹（上游 da1c3994 vs 被加载的那一份 4062e75d → 一眼看出内容不同），前端 staleness 若要加内容级判据可直接取本模块，参照物由上游提供；R5 认知记录——实测确认透传包装器内部 sig.bind 会忠实复现被包装函数的签名，所以『包装器已透传』只保证上游以后再改也不怕，不等于旧上游也能跑（旧签名冲突仍在，只能在调用点/上游侧修），已写进 FRONTEND_CONTRACT §3.3 避免下次误判；R8 纪律——先确认要查的是哪一份代码，已写进 OPERATIONS §1.3.1 作为排查『改了没生效』的第一步。如实标注不属本侧的四条：R1 设 AGENT_BACKEND_DIR（部署配置/用户，根因）、R2 把 backend_stale 提到必经路径（前后端联动）、R6 过期副本处置（架构级需用户批准）、R7 统筹方自己的验收盲区（他们已认领）；并附实测提醒：前端 scripts/adopt-backend.ps1 -From 会先清空 backend/ 再复制 -From 下所有东西，不能指向本仓库根。★ 新能力特意在生产路径上验证（吸取 D7『验证方式≠生产路径』与 §31『验证环境≠用户环境』两条教训）：repro_user_goal.py 真实跑一轮后从真实存储读回 cycle_start 事件断言身份完整且与当前代码一致（实测 code_dir=D:\PythonProject\SimpleAgent2_Cycle code_fingerprint=da1c3994 自报完整=True 一致=True）。新增 test_identity.py 12 项（稳定/改一字节就变/加文档不变）。全量 31/31、文档一致性 35/35、文档不变量 31/31、文档审查 18/18、前端契约不变量 25/25、符合性 43/43、归因 113/113、真实 E2E L1 PASS。
 CYCLE.md                               |   2 +-
 README.md                              |   2 +-
 core/__init__.py                       |   1 +
 core/coding_cycle.py                   |  11 +++-
 core/contract.py                       |   8 ++-
 core/identity.py                       |  85 ++++++++++++++++++++++++
 docs/ARCHITECTURE.md                   |   2 +-
 docs/CHANGELOG.md                      | 114 +++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md              |  32 +++++++++
 docs/MODULES.md                        |  51 +++++++++++++--
 docs/OPERATIONS.md                     |  31 ++++++++-
 main.py                                |   5 ++
 tests/diagnostics/backend_dir_check.py |  20 ++++++
 tests/diagnostics/repro_user_goal.py   |  20 +++++-
 tests/unit/test_identity.py            | 114 +++++++++++++++++++++++++++++++++
 15 files changed, 483 insertions(+), 15 deletions(-)
```

---

## v1.17 — 2026-09-26 14:22

**改动**：FIX-VERIFY-WIRING：真实用户目标从不执行验证（一个 if 决定两个能力是否存在）。去掉 CodingCycle 两处 if verify_command is not None 守卫，pipeline 与 context_provider 总是就位；main.py 补 pipeline=CheckPipeline()；_setup_orchestrator 在 verify_command 为 None 时保留原值（修掉清空 SkillRunner 烘焙命令的回归）；新增 OrchestratorResult.verify_skipped 与 verify_skipped 事件（词表 12->13）；失败文案区分「缺少命令」与「有命令但未执行」；_files_to_verify 改为 声明>产物>prior；repro_user_goal.py 改走 main._build_orchestrator()；新增 tests/unit/test_verify_wiring.py(17)、test_identity.py(12)、tests/diagnostics/verify_wiring_http.py(3)；代码身份 code_dir/code_fingerprint 进 cycle_start 与 /profile。验证：全量单测 32/32、契约符合性 44/44、文档一致性 35/35、不变量 31/31、HTTP 3/3、生产构造路径 repro phase=record 且 report.verify 非空。

**备份点**：本条目所在的提交（提交信息以 `v1.17:` 开头）

**定位命令**：`git log --oneline --grep "^v1.17:"`

**验证**：
- 全量单测 PASS (32/32)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 30 个 · 测试文件 32 个

**本次提交的文件**：
```
2bc0905 v1.17: FIX-VERIFY-WIRING：真实用户目标从不执行验证（一个 if 决定两个能力是否存在）。去掉 CodingCycle 两处 if verify_command is not None 守卫，pipeline 与 context_provider 总是就位；main.py 补 pipeline=CheckPipeline()；_setup_orchestrator 在 verify_command 为 None 时保留原值（修掉清空 SkillRunner 烘焙命令的回归）；新增 OrchestratorResult.verify_skipped 与 verify_skipped 事件（词表 12->13）；失败文案区分「缺少命令」与「有命令但未执行」；_files_to_verify 改为 声明>产物>prior；repro_user_goal.py 改走 main._build_orchestrator()；新增 tests/unit/test_verify_wiring.py(17)、test_identity.py(12)、tests/diagnostics/verify_wiring_http.py(3)；代码身份 code_dir/code_fingerprint 进 cycle_start 与 /profile。验证：全量单测 32/32、契约符合性 44/44、文档一致性 35/35、不变量 31/31、HTTP 3/3、生产构造路径 repro phase=record 且 report.verify 非空。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/coding_cycle.py                    |  74 ++++++--
 core/contract.py                        |   5 +
 core/orchestrator.py                    |  78 ++++++--
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  86 +++++++++
 docs/EVALUATION-FIX-VERIFY-WIRING.md    | 309 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |   2 +-
 docs/MODULES.md                         |   4 +-
 docs/OPERATIONS.md                      |  32 +++-
 docs/PENDING_DECISIONS.md               |   3 +-
 main.py                                 |   7 +-
 tests/README.md                         |   3 +
 tests/diagnostics/repro_user_goal.py    |  38 +++-
 tests/diagnostics/verify_wiring_http.py | 104 +++++++++++
 tests/unit/test_contract_conformance.py |  20 ++-
 tests/unit/test_verify_wiring.py        | 265 +++++++++++++++++++++++++++
 18 files changed, 988 insertions(+), 49 deletions(-)
```

---

## v1.18 — 2026-09-26 14:25

**改动**：文档收尾（v1.17 的文档面）：README 已知限制新增第 8 条——前端实例在 AGENT_BACKEND_DIR 未设时会兜底加载它自带的 backend/ 副本，导致上游修复一行都不生效（已实际发生一次，见 §31），处理办法写清是前端根 .env 指向上游 + 用 backend_dir_check.py 当场比对两份代码指纹。这条是用户侧当前真正的阻塞点，必须留在『当前仍存在的限制』里而不是只写在 CHANGELOG。其余文档同步（EVALUATION-FIX-VERIFY-WIRING 登记进 README 文档表、tests/README 登记 test_verify_wiring/test_identity/verify_wiring_http、OPERATIONS §4.10『验证没跑』排查项与 §7 解释器陷阱、五份上游文档版本戳同步至 §33、PENDING_DECISIONS 事件数 12→13）已在 v1.17 内。验证：全量单测 32/32、文档一致性 35/35、文档审查 18/18、不变量 31/31 全过；本轮另跑 L1 基准 PASS（claim 11）、HTTP 路径 3/3、生产构造路径 repro phase=record 且 report.verify 非空。

**备份点**：本条目所在的提交（提交信息以 `v1.18:` 开头）

**定位命令**：`git log --oneline --grep "^v1.18:"`

**验证**：
- 全量单测 PASS (32/32)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 30 个 · 测试文件 32 个

**本次提交的文件**：
```
a0c3bf8 v1.18: 文档收尾（v1.17 的文档面）：README 已知限制新增第 8 条——前端实例在 AGENT_BACKEND_DIR 未设时会兜底加载它自带的 backend/ 副本，导致上游修复一行都不生效（已实际发生一次，见 §31），处理办法写清是前端根 .env 指向上游 + 用 backend_dir_check.py 当场比对两份代码指纹。这条是用户侧当前真正的阻塞点，必须留在『当前仍存在的限制』里而不是只写在 CHANGELOG。其余文档同步（EVALUATION-FIX-VERIFY-WIRING 登记进 README 文档表、tests/README 登记 test_verify_wiring/test_identity/verify_wiring_http、OPERATIONS §4.10『验证没跑』排查项与 §7 解释器陷阱、五份上游文档版本戳同步至 §33、PENDING_DECISIONS 事件数 12→13）已在 v1.17 内。验证：全量单测 32/32、文档一致性 35/35、文档审查 18/18、不变量 31/31 全过；本轮另跑 L1 基准 PASS（claim 11）、HTTP 路径 3/3、生产构造路径 repro phase=record 且 report.verify 非空。
 README.md | 1 +
 1 file changed, 1 insertion(+)
```

---

## v1.19 — 2026-09-26 19:52

**改动**：VERIFY-VACUOUS：自拟验收可以恒真 —— print('PASS') 让什么都没做也判成功（统筹方缺陷报告 + 四条建议；★ 这是 FIX-VERIFY-WIRING 唤醒的洞，不是它的回归）。修法：给自拟判据一条可机器判定的下限 —— 新增 Orchestrator._deliverables（本轮交付物=声明∪write_file产物，刻意不含 prior_files）、_verify_references（命令须引用交付物：路径/文件名出现在文本里，或词干出现在代码里；先 tokenize 剥掉字符串字面量，故 print('add') 不算引用）、_model_verify_admissible（① 本轮必须有交付物 ② 命令必须引用其中之一）；不合格则不采纳该命令（也不清空前几轮已采纳的好判据）→ 走已有的未验证显式失败路径，错误文案分成第三种情况（判据不合格 vs 缺少命令 vs 有命令没执行）。附1：report.verify.source（caller/model）+ verify 事件加同名字段，只作事实不参与判定（技能烘焙的命令算 caller，显式标注）。附2：memory.verify_rejections 只增不减，cycle 逐条发成 verify_skipped（reason 带被拒命令原文）——实测模型先给坏判据被拒、换好判据才通过，成功时不能把留痕清掉。附3：check 阶段三态 checked/status(passed|failed|skipped) 进 CycleReport.check 与日志（原来只报 passed=True steps=0，没东西可查被读成绿灯）。顺带修掉 contract.py 里漂移的词表注释（12→13）。契约面只增不改名：无新事件（仍 13 种）、CONTRACT_VERSION 仍 1.1、FROZEN_REPORT_KEYS 加 check。★ 检查器被证明会失败：test_verify_vacuous.py 第 3 组把可采性开关关掉（复刻修复前）→ declared=0 + print('PASS') → phase=record 必定复现；没有这组，第 2 组断言无法自证。验证：全量单测 33/33（新 test_verify_vacuous.py 30 项）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18、L1 基准 PASS；真实模型 repro_vacuous_verify.py 6/6（同一目标不给 verify_command：模型改成真的写出 report.txt 并自拟 assert 'calc.py' in report_content…的判据，验证失败时诚实报 phase=failed；只读目标→判据被拒、事件流 verify_skipped=2 带被拒命令原文；调用方给 print('PASS') 仍 record 且 source=caller，证明没夺调用方的权）。

**备份点**：本条目所在的提交（提交信息以 `v1.19:` 开头）

**定位命令**：`git log --oneline --grep "^v1.19:"`

**验证**：
- 全量单测 PASS (33/33)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 30 个 · 测试文件 33 个

**本次提交的文件**：
```
b187ead v1.19: VERIFY-VACUOUS：自拟验收可以恒真 —— print('PASS') 让什么都没做也判成功（统筹方缺陷报告 + 四条建议；★ 这是 FIX-VERIFY-WIRING 唤醒的洞，不是它的回归）。修法：给自拟判据一条可机器判定的下限 —— 新增 Orchestrator._deliverables（本轮交付物=声明∪write_file产物，刻意不含 prior_files）、_verify_references（命令须引用交付物：路径/文件名出现在文本里，或词干出现在代码里；先 tokenize 剥掉字符串字面量，故 print('add') 不算引用）、_model_verify_admissible（① 本轮必须有交付物 ② 命令必须引用其中之一）；不合格则不采纳该命令（也不清空前几轮已采纳的好判据）→ 走已有的未验证显式失败路径，错误文案分成第三种情况（判据不合格 vs 缺少命令 vs 有命令没执行）。附1：report.verify.source（caller/model）+ verify 事件加同名字段，只作事实不参与判定（技能烘焙的命令算 caller，显式标注）。附2：memory.verify_rejections 只增不减，cycle 逐条发成 verify_skipped（reason 带被拒命令原文）——实测模型先给坏判据被拒、换好判据才通过，成功时不能把留痕清掉。附3：check 阶段三态 checked/status(passed|failed|skipped) 进 CycleReport.check 与日志（原来只报 passed=True steps=0，没东西可查被读成绿灯）。顺带修掉 contract.py 里漂移的词表注释（12→13）。契约面只增不改名：无新事件（仍 13 种）、CONTRACT_VERSION 仍 1.1、FROZEN_REPORT_KEYS 加 check。★ 检查器被证明会失败：test_verify_vacuous.py 第 3 组把可采性开关关掉（复刻修复前）→ declared=0 + print('PASS') → phase=record 必定复现；没有这组，第 2 组断言无法自证。验证：全量单测 33/33（新 test_verify_vacuous.py 30 项）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18、L1 基准 PASS；真实模型 repro_vacuous_verify.py 6/6（同一目标不给 verify_command：模型改成真的写出 report.txt 并自拟 assert 'calc.py' in report_content…的判据，验证失败时诚实报 phase=failed；只读目标→判据被拒、事件流 verify_skipped=2 带被拒命令原文；调用方给 print('PASS') 仍 record 且 source=caller，证明没夺调用方的权）。
 CYCLE.md                                  |   2 +-
 README.md                                 |   3 +-
 core/coding_cycle.py                      |  54 +++-
 core/contract.py                          |  12 +-
 core/cycle.py                             |   9 +
 core/memory.py                            |  53 +++-
 core/orchestrator.py                      | 176 ++++++++++++-
 core/pipeline.py                          |  18 +-
 core/prompts.py                           |  12 +-
 core/skill_runner.py                      |   3 +
 docs/ARCHITECTURE.md                      |   2 +-
 docs/CHANGELOG.md                         | 101 +++++++
 docs/EVALUATION-VERIFY-VACUOUS.md         | 421 ++++++++++++++++++++++++++++++
 docs/MODULES.md                           |  41 ++-
 docs/OPERATIONS.md                        |  49 +++-
 docs/PENDING_DECISIONS.md                 |  20 ++
 tests/README.md                           |   2 +
 tests/diagnostics/repro_vacuous_verify.py | 211 +++++++++++++++
 tests/unit/test_verify_vacuous.py         | 392 ++++++++++++++++++++++++++++
 19 files changed, 1547 insertions(+), 34 deletions(-)
```

---

## v1.20 — 2026-09-26 19:57

**改动**：VERIFY-VACUOUS 收尾（只动自检脚本 + 文档，无生产代码改动）：① tests/diagnostics/verify_wiring_http.py 的第 2 条断言原为『verify_passed 非空（= 验证真的执行过）』——VERIFY-VACUOUS 之后『验证没执行』多了一种**正确**原因（模型自拟判据不合格被拒），原断言会把一次正确的拒绝读成 FIX-VERIFY-WIRING 的回归。改为『非空 **或** 本轮判据被明确拒绝』，并打印被拒命令原文；这是『验证自身的判据也要跟着改』的一个小例子。② 文档补：CHANGELOG §34.3 附表加『附 4』并补 HTTP 3/3 与 L1 冒烟到 §34.5 验证表；EVALUATION-VERIFY-VACUOUS §3.2 加两行（yaml 断言改动 + 文档同步），§3.1 机械输出用最终 diff --stat 替换占位。验证：全量单测 33/33、文档一致性 35/35、文档审查 18/18、经 HTTP 3/3（改动后重跑，报告的 check 三态与 verify.source=model 均正确显形）。

**备份点**：本条目所在的提交（提交信息以 `v1.20:` 开头）

**定位命令**：`git log --oneline --grep "^v1.20:"`

**验证**：
- 全量单测 PASS (33/33)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 30 个 · 测试文件 33 个

**本次提交的文件**：
```
94cafee v1.20: VERIFY-VACUOUS 收尾（只动自检脚本 + 文档，无生产代码改动）：① tests/diagnostics/verify_wiring_http.py 的第 2 条断言原为『verify_passed 非空（= 验证真的执行过）』——VERIFY-VACUOUS 之后『验证没执行』多了一种**正确**原因（模型自拟判据不合格被拒），原断言会把一次正确的拒绝读成 FIX-VERIFY-WIRING 的回归。改为『非空 **或** 本轮判据被明确拒绝』，并打印被拒命令原文；这是『验证自身的判据也要跟着改』的一个小例子。② 文档补：CHANGELOG §34.3 附表加『附 4』并补 HTTP 3/3 与 L1 冒烟到 §34.5 验证表；EVALUATION-VERIFY-VACUOUS §3.2 加两行（yaml 断言改动 + 文档同步），§3.1 机械输出用最终 diff --stat 替换占位。验证：全量单测 33/33、文档一致性 35/35、文档审查 18/18、经 HTTP 3/3（改动后重跑，报告的 check 三态与 verify.source=model 均正确显形）。
 docs/CHANGELOG.md                       |  3 +++
 docs/EVALUATION-VERIFY-VACUOUS.md       |  3 ++-
 tests/diagnostics/verify_wiring_http.py | 25 ++++++++++++++++++++++---
 3 files changed, 27 insertions(+), 4 deletions(-)
```

---

## v1.21 — 2026-09-27 13:34

**改动**：TRANSPARENCY-BACKEND：流程允许模型把考卷换成一张必过的（统筹方对 run_20260927_125647_5a3297 的审查 + 需求文件）。A1：每轮决策依据进事件 orchestrator_round（reasoning + 这一轮打算做什么）——上游刻意不复用前端 bridge 的 orchestrator_decision（两个生产者发同一 kind 会让审计无法判断哪条权威；并附证据说明用户那次该事件缺 reasoning 是旧 bridge 造成的，现行 bridge/hooks.py:306 已经带 reasoning）。B1：判据演化逐条进事件 verify_criterion（action=adopted/rejected/executed + previous_command/previous_passed，由 memory.log_criterion 自动补齐前后关系，调用点不必各自记状态）。B2（用户裁决的行为改动）：换掉一条已执行且失败的判据必须给理由（verify.reason 非空），没给理由不采纳并走显式失败；允许换、但必须看得见。B3（统筹方点名要求不要默默处理）：自拟判据引用 .py 交付物就必须真的调用它——新增 _module_names_for / _called_modules（AST Call + import 别名解析），assert generate_obstacles 这类只断言名字的恒真判据被拒；我判定它与用户选的(2)不冲突（(2)管换判据怎么处理，B3管什么判据算合格），且只做 B2 拦不住 (c)；代价如实写在 OPERATIONS §9.2 与 PENDING C10：.py 只做存在性检查会被拒（调用方判据不受影响），可单独回退第三层。C1：新增 core/self_report.py + SELF_REPORT_SYSTEM，收尾自述 self_report（done/not_done/why/reflections/approach/confidence/open_questions/requirements/claims）进报告字段与事件。C2：fact_check 逐条与机械事实相等比较（交付物是否真在磁盘、verify 是否真通过、check.status 与 lint failed、目标要求缺状态的标未提及）；自述是报告不是门禁（phase/verify/commit 不受影响），拿不到自述记 ok=false+error 显式降级。★ 真调用生效：拿统筹方固定样例重跑同一目标，改动前 judge=assert generate_obstacles→record，改动后 judge=ant_colony.AntColony(...).run()==True→phase=failed detail=NameError: name 'random' is not defined（报告里的 bug 从 np 变成 random，说明判据摸到了真实代码）；事件流 orchestrator_round=20 verify_criterion=31 self_report=1，自述 not_done=[generate_ants 方法] 且把「连续测试验证」留成 unknown 被标未提及。验证：全量单测 35/35（新 test_transparency.py 24 项 + test_self_report.py 19 项）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18、真实模型固定样例 6/6、经 HTTP 3/3（HTTP 那次 fact_check 真抓到一条 check-claim-vs-fact：模型声称检查通过而 check.status=skipped）。契约面：事件 13→16、CycleReport 加 self_report、CONTRACT_VERSION 仍 1.1，全 additive。

**备份点**：本条目所在的提交（提交信息以 `v1.21:` 开头）

**定位命令**：`git log --oneline --grep "^v1.21:"`

**验证**：
- 全量单测 PASS (35/35)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 31 个 · 测试文件 35 个

**本次提交的文件**：
```
4824738 v1.21: TRANSPARENCY-BACKEND：流程允许模型把考卷换成一张必过的（统筹方对 run_20260927_125647_5a3297 的审查 + 需求文件）。A1：每轮决策依据进事件 orchestrator_round（reasoning + 这一轮打算做什么）——上游刻意不复用前端 bridge 的 orchestrator_decision（两个生产者发同一 kind 会让审计无法判断哪条权威；并附证据说明用户那次该事件缺 reasoning 是旧 bridge 造成的，现行 bridge/hooks.py:306 已经带 reasoning）。B1：判据演化逐条进事件 verify_criterion（action=adopted/rejected/executed + previous_command/previous_passed，由 memory.log_criterion 自动补齐前后关系，调用点不必各自记状态）。B2（用户裁决的行为改动）：换掉一条已执行且失败的判据必须给理由（verify.reason 非空），没给理由不采纳并走显式失败；允许换、但必须看得见。B3（统筹方点名要求不要默默处理）：自拟判据引用 .py 交付物就必须真的调用它——新增 _module_names_for / _called_modules（AST Call + import 别名解析），assert generate_obstacles 这类只断言名字的恒真判据被拒；我判定它与用户选的(2)不冲突（(2)管换判据怎么处理，B3管什么判据算合格），且只做 B2 拦不住 (c)；代价如实写在 OPERATIONS §9.2 与 PENDING C10：.py 只做存在性检查会被拒（调用方判据不受影响），可单独回退第三层。C1：新增 core/self_report.py + SELF_REPORT_SYSTEM，收尾自述 self_report（done/not_done/why/reflections/approach/confidence/open_questions/requirements/claims）进报告字段与事件。C2：fact_check 逐条与机械事实相等比较（交付物是否真在磁盘、verify 是否真通过、check.status 与 lint failed、目标要求缺状态的标未提及）；自述是报告不是门禁（phase/verify/commit 不受影响），拿不到自述记 ok=false+error 显式降级。★ 真调用生效：拿统筹方固定样例重跑同一目标，改动前 judge=assert generate_obstacles→record，改动后 judge=ant_colony.AntColony(...).run()==True→phase=failed detail=NameError: name 'random' is not defined（报告里的 bug 从 np 变成 random，说明判据摸到了真实代码）；事件流 orchestrator_round=20 verify_criterion=31 self_report=1，自述 not_done=[generate_ants 方法] 且把「连续测试验证」留成 unknown 被标未提及。验证：全量单测 35/35（新 test_transparency.py 24 项 + test_self_report.py 19 项）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18、真实模型固定样例 6/6、经 HTTP 3/3（HTTP 那次 fact_check 真抓到一条 check-claim-vs-fact：模型声称检查通过而 check.status=skipped）。契约面：事件 13→16、CycleReport 加 self_report、CONTRACT_VERSION 仍 1.1，全 additive。
 CYCLE.md                                     |   2 +-
 README.md                                    |   3 +-
 core/coding_cycle.py                         | 170 ++++++++++++
 core/contract.py                             |  33 ++-
 core/cycle.py                                |   8 +
 core/memory.py                               |  67 +++++
 core/orchestrator.py                         | 197 +++++++++++---
 core/prompts.py                              |  54 ++++
 core/self_report.py                          | 248 +++++++++++++++++
 docs/ARCHITECTURE.md                         |   2 +-
 docs/CHANGELOG.md                            |  80 ++++++
 docs/EVALUATION-TRANSPARENCY-BACKEND.md      | 381 +++++++++++++++++++++++++++
 docs/EVALUATION-VERIFY-VACUOUS.md            |   7 +
 docs/FRONTEND_CONTRACT.md                    |  13 +-
 docs/MODULES.md                              |  56 +++-
 docs/OPERATIONS.md                           | 115 +++++++-
 docs/PENDING_DECISIONS.md                    |  15 +-
 tests/README.md                              |   3 +
 tests/diagnostics/repro_user_run_20260927.py | 174 ++++++++++++
 tests/unit/test_self_report.py               | 278 +++++++++++++++++++
 tests/unit/test_transparency.py              | 255 ++++++++++++++++++
 tests/unit/test_verify_vacuous.py            |   4 +-
 22 files changed, 2121 insertions(+), 44 deletions(-)
```

---

## v1.22 — 2026-09-28 00:16

**改动**：TRANSPARENCY2-BACKEND（P1-P5）。P1 结局四值：新增 core/outcome.py（13 种原因种类 -> pass/fail/abstain/invalid），每个出口由 _end_cycle 显式设置而不是嗅探错误字符串；判据自身坏/环境缺依赖 -> invalid（criterion-broken/environment-missing/wiring），说不出什么叫对/模型 blocked -> abstain；★ 判据来源进判定链：verdict.criterion_trust（caller-authoritative vs model-self-authored）+ criterion_independent，模型自拟判据的通过与调用方判据的通过不再同形（39 条运行里调用方判据 0 条）。顺带修掉终局不发 cycle_end 的缺口。P2 机械复用性（硬否决）：新增 core/reuse_checks.py，五类缺陷里三类做成阻塞（调用了不存在的符号、用了没导入 F821、按旧签名传参）—— 实测那两条判据（ant_colony.generate_obstacles / obstacle_generator.generate_obstacle_grid）被抓住；重复符号/未用导入/命名不一致只做警告（理由与代价写在评估文档 §7，提升只需改 BLOCKING_KINDS 一行，PENDING C12）；lint 从非阻塞变成必然崩的三类阻塞（pipeline.py:157 那句注释的后果实测两次）。P3 拆解合规关卡：新增 core/decompose_review.py，八条原则（6 条完全机械 + P5/P6 机械近似 + undecidable 第三态），原则本体进契约 core/contract.py::DECOMPOSE_PRINCIPLES（L1：执行方只读）；★ 逐字复刻用户那次运行的 plan 判不通过（违反 P3），Run A 型分解违反 P3/P4/P6/P7 四条全被抓，合规分解通过（不会一律报红）；否决权真的生效（DECOMPOSE_GATE=block），默认 warn 因为阈值待基线校准 + 7B 必违反（PENDING C11）。P4 架构事实层：tools/arch.py 加 render_architecture_view（带 derived-from 标记），新增会红的检查 hand-written-architecture-doc（手写架构文档被拦、渲染件放行）。P5 reviewer 定位写死建议性 + 指明否决权在机械层（不动语义）。契约面：事件 16->18（reuse/decompose_review 新增，cycle_end 加 outcome/outcome_reason），CycleReport +5 字段，CONTRACT_VERSION 仍 1.1，全 additive。验证：全量单测 38/38（新 test_outcome 18 + test_reuse_checks 18 + test_decompose_review 19）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18；真实模型固定样例 6/6，那次运行里 decompose_review 判不通过（violated=[P3,P4,P6]、independent=false）、cycle_end 带 outcome=fail、reuse 事件进流、自述 fact_check 又抓到一次 lint-failed-not-disclosed。

**备份点**：本条目所在的提交（提交信息以 `v1.22:` 开头）

**定位命令**：`git log --oneline --grep "^v1.22:"`

**验证**：
- 全量单测 PASS (38/38)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 34 个 · 测试文件 38 个

**本次提交的文件**：
```
933b515 v1.22: TRANSPARENCY2-BACKEND（P1-P5）。P1 结局四值：新增 core/outcome.py（13 种原因种类 -> pass/fail/abstain/invalid），每个出口由 _end_cycle 显式设置而不是嗅探错误字符串；判据自身坏/环境缺依赖 -> invalid（criterion-broken/environment-missing/wiring），说不出什么叫对/模型 blocked -> abstain；★ 判据来源进判定链：verdict.criterion_trust（caller-authoritative vs model-self-authored）+ criterion_independent，模型自拟判据的通过与调用方判据的通过不再同形（39 条运行里调用方判据 0 条）。顺带修掉终局不发 cycle_end 的缺口。P2 机械复用性（硬否决）：新增 core/reuse_checks.py，五类缺陷里三类做成阻塞（调用了不存在的符号、用了没导入 F821、按旧签名传参）—— 实测那两条判据（ant_colony.generate_obstacles / obstacle_generator.generate_obstacle_grid）被抓住；重复符号/未用导入/命名不一致只做警告（理由与代价写在评估文档 §7，提升只需改 BLOCKING_KINDS 一行，PENDING C12）；lint 从非阻塞变成必然崩的三类阻塞（pipeline.py:157 那句注释的后果实测两次）。P3 拆解合规关卡：新增 core/decompose_review.py，八条原则（6 条完全机械 + P5/P6 机械近似 + undecidable 第三态），原则本体进契约 core/contract.py::DECOMPOSE_PRINCIPLES（L1：执行方只读）；★ 逐字复刻用户那次运行的 plan 判不通过（违反 P3），Run A 型分解违反 P3/P4/P6/P7 四条全被抓，合规分解通过（不会一律报红）；否决权真的生效（DECOMPOSE_GATE=block），默认 warn 因为阈值待基线校准 + 7B 必违反（PENDING C11）。P4 架构事实层：tools/arch.py 加 render_architecture_view（带 derived-from 标记），新增会红的检查 hand-written-architecture-doc（手写架构文档被拦、渲染件放行）。P5 reviewer 定位写死建议性 + 指明否决权在机械层（不动语义）。契约面：事件 16->18（reuse/decompose_review 新增，cycle_end 加 outcome/outcome_reason），CycleReport +5 字段，CONTRACT_VERSION 仍 1.1，全 additive。验证：全量单测 38/38（新 test_outcome 18 + test_reuse_checks 18 + test_decompose_review 19）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18；真实模型固定样例 6/6，那次运行里 decompose_review 判不通过（violated=[P3,P4,P6]、independent=false）、cycle_end 带 outcome=fail、reuse 事件进流、自述 fact_check 又抓到一次 lint-failed-not-disclosed。
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/coding_cycle.py                     | 173 +++++++++++--
 core/config.py                           |  11 +-
 core/contract.py                         |  63 ++++-
 core/cycle.py                            |  21 ++
 core/decompose_review.py                 | 280 +++++++++++++++++++++
 core/outcome.py                          | 109 +++++++++
 core/pipeline.py                         | 136 ++++++++++-
 core/reuse_checks.py                     | 405 +++++++++++++++++++++++++++++++
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  88 +++++++
 docs/EVALUATION-TRANSPARENCY2-BACKEND.md | 338 ++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md                |  13 +-
 docs/MODULES.md                          | 108 ++++++++-
 docs/OPERATIONS.md                       |  45 +++-
 docs/PENDING_DECISIONS.md                |  22 ++
 tests/README.md                          |   3 +
 tests/unit/test_decompose_review.py      | 268 ++++++++++++++++++++
 tests/unit/test_outcome.py               | 232 ++++++++++++++++++
 tests/unit/test_reuse_checks.py          | 236 ++++++++++++++++++
 tools/arch.py                            |  43 ++++
 22 files changed, 2574 insertions(+), 27 deletions(-)
```

---

## v1.23 — 2026-09-28 01:13

**改动**：TRANSPARENCY3-BACKEND（P6/P7/P8，统筹方能力基线复验新发现）。P6 判词必须描述产物（与 FIX-VERIFY-WIRING 同族：被验证的对象必须就是被交付的对象）：★ 机制我定位到了并确定性复现 —— tools/verify.py 本身是对的（独立子进程 + cwd=workspace + PYTHONPATH，不是 cwd 也不是进程内 sys.modules 复用），但子进程会读 __pycache__/*.pyc，而 .pyc 失效判据是源码 (mtime,size)，本项目回退/快照用 shutil.copy2 保留原 mtime ⇒ 极易凑成一致 ⇒ import 执行旧代码（实测：改写成同长度的另一版并还原 mtime，不清缓存 import 得到旧值 'A'，清掉 __pycache__ 得到 'B'）。修法两条互补：① run_verify 验前清 __pycache__ + 记内容哈希 + 明确 cwd，tools/verify.py 加 -B 与 PYTHONDONTWRITEBYTECODE=1（清不掉就显式记 cache_warning）；② 打检查点之前重取一次最终产物哈希，对不上则不打检查点、outcome_kind=artifact-mismatch ⇒ 结局 invalid（读数无效，不是模型不行）。报告与 verify 事件都能读到 artifact_hashes（验证时）/artifact_hashes_final（交付时）/cwd，两者可比。P7 符号表收模块级赋值：app = Flask(__name__) 被判『缺少符号 app』是假失败（根因 symbol_index 只访问 FunctionDef/AsyncFunctionDef/ClassDef，没有 Assign/AnnAssign）—— 它直接毁掉一个能力轴的读数；新增 visit_Assign/visit_AnnAssign（kind=variable，含 CONFIG: dict = {}）与 raw_module_bindings() 作为独立第二意见，于是『真没有』(symbol-missing, error, 带 文件:行) 与『有但我没索引到』(symbol-unindexed, warning, 不拦路) 可区分。P8 decompose_review 事件加 mode(off/warn/block) 与 applied，否则 warn 模式下 passed=false 会被读成『审查未通过而运行通过』。验证：全量单测 39/39（新 test_artifact_binding.py 24 项，含缓存陈旧的确定性复现与修复对照）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18；真实模型固定样例 6/6 且这次 phase=record，事件里 verify.artifact_hashes={'obstacle_generator.py':'f13e0b5d292d'}、cwd 有值、decompose_review 带 mode=warn/applied=False、cycle_end outcome=pass。契约面：事件种类数不变（18；勘误：先前写 19），只给 verify/decompose_review 加键，CONTRACT_VERSION 仍 1.1。新增待确认 C13（清缓存失败是否升级为 invalid）与 C14（历史 fail 数字是否重跑 —— 判断权在统筹方）。

**备份点**：本条目所在的提交（提交信息以 `v1.23:` 开头）

**定位命令**：`git log --oneline --grep "^v1.23:"`

**验证**：
- 全量单测 PASS (39/39)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 34 个 · 测试文件 39 个

**本次提交的文件**：
```
d6dce14 v1.23: TRANSPARENCY3-BACKEND（P6/P7/P8，统筹方能力基线复验新发现）。P6 判词必须描述产物（与 FIX-VERIFY-WIRING 同族：被验证的对象必须就是被交付的对象）：★ 机制我定位到了并确定性复现 —— tools/verify.py 本身是对的（独立子进程 + cwd=workspace + PYTHONPATH，不是 cwd 也不是进程内 sys.modules 复用），但子进程会读 __pycache__/*.pyc，而 .pyc 失效判据是源码 (mtime,size)，本项目回退/快照用 shutil.copy2 保留原 mtime ⇒ 极易凑成一致 ⇒ import 执行旧代码（实测：改写成同长度的另一版并还原 mtime，不清缓存 import 得到旧值 'A'，清掉 __pycache__ 得到 'B'）。修法两条互补：① run_verify 验前清 __pycache__ + 记内容哈希 + 明确 cwd，tools/verify.py 加 -B 与 PYTHONDONTWRITEBYTECODE=1（清不掉就显式记 cache_warning）；② 打检查点之前重取一次最终产物哈希，对不上则不打检查点、outcome_kind=artifact-mismatch ⇒ 结局 invalid（读数无效，不是模型不行）。报告与 verify 事件都能读到 artifact_hashes（验证时）/artifact_hashes_final（交付时）/cwd，两者可比。P7 符号表收模块级赋值：app = Flask(__name__) 被判『缺少符号 app』是假失败（根因 symbol_index 只访问 FunctionDef/AsyncFunctionDef/ClassDef，没有 Assign/AnnAssign）—— 它直接毁掉一个能力轴的读数；新增 visit_Assign/visit_AnnAssign（kind=variable，含 CONFIG: dict = {}）与 raw_module_bindings() 作为独立第二意见，于是『真没有』(symbol-missing, error, 带 文件:行) 与『有但我没索引到』(symbol-unindexed, warning, 不拦路) 可区分。P8 decompose_review 事件加 mode(off/warn/block) 与 applied，否则 warn 模式下 passed=false 会被读成『审查未通过而运行通过』。验证：全量单测 39/39（新 test_artifact_binding.py 24 项，含缓存陈旧的确定性复现与修复对照）、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量 31/31、文档审查 18/18；真实模型固定样例 6/6 且这次 phase=record，事件里 verify.artifact_hashes={'obstacle_generator.py':'f13e0b5d292d'}、cwd 有值、decompose_review 带 mode=warn/applied=False、cycle_end outcome=pass。契约面：事件种类数不变（18；勘误：先前写 19），只给 verify/decompose_review 加键，CONTRACT_VERSION 仍 1.1。新增待确认 C13（清缓存失败是否升级为 invalid）与 C14（历史 fail 数字是否重跑 —— 判断权在统筹方）。
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/coding_cycle.py                     |  40 +++++
 core/contract.py                         |  17 +-
 core/manifest.py                         |  44 ++++-
 core/memory.py                           |  13 ++
 core/orchestrator.py                     |   8 +-
 core/outcome.py                          |   4 +
 core/pipeline.py                         |  62 ++++++-
 core/symbol_index.py                     |  90 ++++++++++
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  67 +++++++
 docs/EVALUATION-TRANSPARENCY3-BACKEND.md | 275 +++++++++++++++++++++++++++++
 docs/MODULES.md                          |  59 ++++++-
 docs/OPERATIONS.md                       |  36 +++-
 docs/PENDING_DECISIONS.md                |  20 +++
 tests/unit/test_artifact_binding.py      | 290 +++++++++++++++++++++++++++++++
 tools/verify.py                          |   7 +-
 18 files changed, 1017 insertions(+), 22 deletions(-)
```

---

## v1.24 — 2026-09-28 22:27

**改动**：REUSE-SYMBOL-SCOPE（P7b）：复用层符号反查的**名字撞车**。缺陷（能力基线 T9 真实运行 run_20260928_221011_7b7bfc）：模型交付的 app.py 完全正确（from flask import Flask / app = Flask(__name__) / @app.route('/ping')），却被复用层判 blocking『app.py 引用了不存在的符号 app.route —— app 里只有 [app, ping]』，因为 owner=app 直接进了模块反查，而模型的文件恰好也叫 app.py（by_stem 兜底按文件名主干命中同名模块）；复用层有硬否决权 ⇒ 正确代码被否决、phase=failed，更糟的是模型在 self_report 里写下『静态检查未通过』——工具把正确判成错的还让模型去反思它。根因：引用反查没有作用域概念（_bound_names 早在同一文件里但形式 1 没用它——又一次机制在没接上）。修法（三条顺序，不动 BLOCKING_KINDS）：① owner 根名是**非 import 绑定**（变量/参数/with as/for/except as/推导式/def|class 名）⇒ 对象属性、本地 AST 索引不可知 ⇒ 不判；② 根名是 import 绑定 ⇒ 照旧模块反查（import t1 后 t1.bar 仍红）；③ 根名既非绑定也非内置 ⇒ undefined-name（阻塞，np.array 缺 import 属此类）；附：文件里有 from x import * ⇒ 该文件不做未定义名判定。★ 同时满足统筹方的两条缺一不可的验收：① A/B 两种工作区结论一致且都为 0（新判据版探针 tests/diagnostics/probe_symbol_scope.py 14/14，把『结论与工作区无关』写成断言）；② 反空洞——np.array 缺 import / from mylib import f（无 f）/ t1.bar（只有 foo）三条**必须仍然红**，机械输出已贴进评估文档 §4.1。顺带项：v1.22 曾把事件数写成 19（把 cycle_end 新增的两个 payload 键当成新事件），实测 len(EVENTS)=18 —— 已勘误 VERSIONS/FRONTEND_CONTRACT/CHANGELOG（历史条目只加勘误注不重排），并给 test_doc_invariants 加**第 10 组**门禁：文档里写的『上游 N 种事件』必须等于 len(contract.EVENTS)，且『一条都没扫到』本身判红（防空转）。验证：全量单测 40/40（新 test_reuse_scope.py 24 项）、探针 14/14、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量（31+2）/33、文档审查 18/18。契约面零改动：事件仍 18 种、CONTRACT_VERSION 仍 1.1 —— 本次只调判据作用域，不动否决强度。

**备份点**：本条目所在的提交（提交信息以 `v1.24:` 开头）

**定位命令**：`git log --oneline --grep "^v1.24:"`

**验证**：
- 全量单测 PASS (40/40)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 34 个 · 测试文件 40 个

**本次提交的文件**：
```
bbfb54e v1.24: REUSE-SYMBOL-SCOPE（P7b）：复用层符号反查的**名字撞车**。缺陷（能力基线 T9 真实运行 run_20260928_221011_7b7bfc）：模型交付的 app.py 完全正确（from flask import Flask / app = Flask(__name__) / @app.route('/ping')），却被复用层判 blocking『app.py 引用了不存在的符号 app.route —— app 里只有 [app, ping]』，因为 owner=app 直接进了模块反查，而模型的文件恰好也叫 app.py（by_stem 兜底按文件名主干命中同名模块）；复用层有硬否决权 ⇒ 正确代码被否决、phase=failed，更糟的是模型在 self_report 里写下『静态检查未通过』——工具把正确判成错的还让模型去反思它。根因：引用反查没有作用域概念（_bound_names 早在同一文件里但形式 1 没用它——又一次机制在没接上）。修法（三条顺序，不动 BLOCKING_KINDS）：① owner 根名是**非 import 绑定**（变量/参数/with as/for/except as/推导式/def|class 名）⇒ 对象属性、本地 AST 索引不可知 ⇒ 不判；② 根名是 import 绑定 ⇒ 照旧模块反查（import t1 后 t1.bar 仍红）；③ 根名既非绑定也非内置 ⇒ undefined-name（阻塞，np.array 缺 import 属此类）；附：文件里有 from x import * ⇒ 该文件不做未定义名判定。★ 同时满足统筹方的两条缺一不可的验收：① A/B 两种工作区结论一致且都为 0（新判据版探针 tests/diagnostics/probe_symbol_scope.py 14/14，把『结论与工作区无关』写成断言）；② 反空洞——np.array 缺 import / from mylib import f（无 f）/ t1.bar（只有 foo）三条**必须仍然红**，机械输出已贴进评估文档 §4.1。顺带项：v1.22 曾把事件数写成 19（把 cycle_end 新增的两个 payload 键当成新事件），实测 len(EVENTS)=18 —— 已勘误 VERSIONS/FRONTEND_CONTRACT/CHANGELOG（历史条目只加勘误注不重排），并给 test_doc_invariants 加**第 10 组**门禁：文档里写的『上游 N 种事件』必须等于 len(contract.EVENTS)，且『一条都没扫到』本身判红（防空转）。验证：全量单测 40/40（新 test_reuse_scope.py 24 项）、探针 14/14、契约符合性 44/44、前端契约 25/25、文档一致性 35/35、不变量（31+2）/33、文档审查 18/18。契约面零改动：事件仍 18 种、CONTRACT_VERSION 仍 1.1 —— 本次只调判据作用域，不动否决强度。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/reuse_checks.py                    |  57 +++++++
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  69 +++++++-
 docs/EVALUATION-REUSE-SYMBOL-SCOPE.md   | 279 ++++++++++++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md               |   2 +-
 docs/MODULES.md                         |  25 ++-
 docs/OPERATIONS.md                      |  18 ++-
 docs/VERSIONS.md                        |   8 +-
 tests/README.md                         |   2 +
 tests/diagnostics/probe_symbol_scope.py | 126 +++++++++++++++
 tests/unit/test_doc_invariants.py       |  56 ++++++-
 tests/unit/test_reuse_scope.py          | 231 ++++++++++++++++++++++++++
 14 files changed, 867 insertions(+), 13 deletions(-)
```

---

## v1.25 — 2026-10-03 12:25

**改动**：P9 TOOLCALL-NORM：工具调用规范化 + 工具产出检验（用户 2026-10-03 架构方向，契约 1.0.30 tool_call_contract；本轮 round_id R-69ec731ff3）。根因（统筹方实测）：18 个工具全部未声明 additionalProperties ⇒ JSON Schema 默认任意键都收，传错键不报错、被静默忽略 —— 「每次生成的东西不一样」能走到工具的机制性原因。修法四件：① 18 个工具 parameters 一律显式 additionalProperties:false（无参工具同样声明）+ 可选参数补 default；② 新增 tools/tool_contract.py：声明式别名表 ALIASES（write_file 的 code→content 等实测形状）+ normalize_args 五步（别名归一→未知键结构化拒绝→类型强制→必需键→缺省填充），未知键回灌 {ok:false,kind:error,error:{code,message,hint}} 并列出可用键与已知别名；③ validate_result 校验结果信封 {ok,kind,data,error}（ok=false 必填 error、ok=true 必填 data），旧字符串结果仍可读 —— is_error_result() 回退路径原样保留、语义未改；④ 接线 core/worker.py::_invoke（_parse_args 之后、执行之前），去重/兜底/归档三条旁路走 _args_for_read 归一后的实参。顺带修一个 U- 类：check_and_run 的 expect_exit 一直是真实参数却没写进模型可见 schema，收紧形状时补上，否则会被未知键判据拒掉。★ 反空洞：探针临时摘掉 read_file 的 additionalProperties ⇒ 门禁判据立刻报 [read_file]，恢复回绿；传未声明键时工具函数一次都没执行（间谍工具证明不是接受后忽略）；半成品信封被 reject。验证：统筹方门禁 tool-contract-lint.py 由 TOOLLINT state=fail problems=1 tools=18 转 state=ok problems=0 tools=18；新增 tests/unit/test_tool_contract.py 40/40、tests/diagnostics/probe_tool_contract.py 全 PASS、全量单测 41/41、契约符合性 44/44、前端契约 25/25、文档一致性 36/36、文档不变量 (31+2)/33、文档审查 18/18。接口面零破坏：事件/阶段/CycleReport/Snapshot/Event/端点/版本轴均未改，TOOLS_MAP 顶层键未改（只改 parameters 内部），/profile.contract 新增 tool_call_contract（别名表+audit）属加性。契约目录只读未动；对侧仓库与集成工作区未写入。

**备份点**：本条目所在的提交（提交信息以 `v1.25:` 开头）

**定位命令**：`git log --oneline --grep "^v1.25:"`

**验证**：
- 全量单测 PASS (41/41)
- 文档一致性 PASS (36/36)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 34 个 · 测试文件 41 个

**本次提交的文件**：
```
fb248b1 v1.25: P9 TOOLCALL-NORM：工具调用规范化 + 工具产出检验（用户 2026-10-03 架构方向，契约 1.0.30 tool_call_contract；本轮 round_id R-69ec731ff3）。根因（统筹方实测）：18 个工具全部未声明 additionalProperties ⇒ JSON Schema 默认任意键都收，传错键不报错、被静默忽略 —— 「每次生成的东西不一样」能走到工具的机制性原因。修法四件：① 18 个工具 parameters 一律显式 additionalProperties:false（无参工具同样声明）+ 可选参数补 default；② 新增 tools/tool_contract.py：声明式别名表 ALIASES（write_file 的 code→content 等实测形状）+ normalize_args 五步（别名归一→未知键结构化拒绝→类型强制→必需键→缺省填充），未知键回灌 {ok:false,kind:error,error:{code,message,hint}} 并列出可用键与已知别名；③ validate_result 校验结果信封 {ok,kind,data,error}（ok=false 必填 error、ok=true 必填 data），旧字符串结果仍可读 —— is_error_result() 回退路径原样保留、语义未改；④ 接线 core/worker.py::_invoke（_parse_args 之后、执行之前），去重/兜底/归档三条旁路走 _args_for_read 归一后的实参。顺带修一个 U- 类：check_and_run 的 expect_exit 一直是真实参数却没写进模型可见 schema，收紧形状时补上，否则会被未知键判据拒掉。★ 反空洞：探针临时摘掉 read_file 的 additionalProperties ⇒ 门禁判据立刻报 [read_file]，恢复回绿；传未声明键时工具函数一次都没执行（间谍工具证明不是接受后忽略）；半成品信封被 reject。验证：统筹方门禁 tool-contract-lint.py 由 TOOLLINT state=fail problems=1 tools=18 转 state=ok problems=0 tools=18；新增 tests/unit/test_tool_contract.py 40/40、tests/diagnostics/probe_tool_contract.py 全 PASS、全量单测 41/41、契约符合性 44/44、前端契约 25/25、文档一致性 36/36、文档不变量 (31+2)/33、文档审查 18/18。接口面零破坏：事件/阶段/CycleReport/Snapshot/Event/端点/版本轴均未改，TOOLS_MAP 顶层键未改（只改 parameters 内部），/profile.contract 新增 tool_call_contract（别名表+audit）属加性。契约目录只读未动；对侧仓库与集成工作区未写入。
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/contract.py                         |  12 +
 core/worker.py                           |  73 +++--
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  62 +++++
 docs/EVALUATION-TOOLCALL-NORM.md         | 348 +++++++++++++++++++++++
 docs/FRONTEND_CONTRACT.md                |  16 ++
 docs/MODULES.md                          |  53 +++-
 docs/OPERATIONS.md                       |   3 +-
 tests/README.md                          |   2 +
 tests/diagnostics/probe_tool_contract.py | 170 ++++++++++++
 tests/unit/test_tool_contract.py         | 267 ++++++++++++++++++
 tools/__init__.py                        |  25 ++
 tools/arch.py                            |   4 +
 tools/basic.py                           |  11 +-
 tools/code_checks.py                     |  10 +-
 tools/docs.py                            |   2 +
 tools/files.py                           |   2 +
 tools/net.py                             |   1 +
 tools/parse.py                           |   1 +
 tools/python_exec.py                     |   1 +
 tools/quality.py                         |   1 +
 tools/reflect.py                         |   2 +
 tools/tool_contract.py                   | 454 +++++++++++++++++++++++++++++++
 tools/verify.py                          |  11 +-
 26 files changed, 1514 insertions(+), 24 deletions(-)
```

---

## v1.26 — 2026-10-03 13:14

**改动**：P9 ENVELOPE-WIRING（D33 追加验收 ③ 后半 + D30 收口；round_id R-4fb8a623b8）。缺陷（统筹方独立复验 v1.25，不看自述）：产出侧只把机制建好了 —— validate_result/_envelope_problems/audit 都在，但 ENVELOPE_TOOLS 是空集 ⇒ 18 个工具里没有一个的结果会被校验，audit().envelope_tools=[]，他门禁的不变式 F（envelope_tools 非空）因此重新变红。这就是本项目反复栽的形状：机制存在 != 机制接上了。修法五件：① ENVELOPE_TOOLS 由空集合改为登记表（工具->结果类别 kind），现役非空 check_and_run->verification；② 新增 build_envelope()（唯一一处装配信封 {ok,kind,data,error}）+ _error_object()（错误信封的 code/message 从 error/parsed_error/message 抽真实失败，第一版回灌了占位文案『工具报错』已修）+ envelope_of()/unwrap_payload()（兼容旁路取回原产出）；③ 接线 core/worker.py::_invoke —— 先套信封、再检验信封本体（顺序反了会把工具自己的中间形状 {ok,syntax_passed} 判成不合规信封，实测踩到）；_maybe_artifact 用 envelope_of 取回 data；④ 分阶段迁移判据公开声明（STAGED_OUT_OF_ENVELOPE + envelope_policy -> /profile 的 result_envelope.staged）：其余 17 个逐个按产出形状登记，run_lint/check_syntax 因 pipeline.run_check 直调读 ok 而先动读法，新增工具必须直接登记；⑤ audit() 加 envelope_tool_count/bad_envelope_kinds，describe_contract 公开登记面与 built_by。反空洞（三条，机械输出已贴评估文档 §4.1）：摘掉登记 => envelope_tools 立刻变空 且 Worker 同时退回旧形状（机制与声明同源）；半成品信封 => reject + tool-result-invalid；错误信封 error.code=AssertionError/message=boom 而 data.parsed_error（frames/category/exit_code）仍完整可读 —— 信封是分类不是丢事实。D30：除 v1.24 已勘误的事件数外，又扫出同族第二处 —— docs/PENDING_DECISIONS.md 的 upstream_event_kinds 写『当前 13 个』实测 18，已改正；并把 test_doc_invariants 第 10 组补硬：新增 upstream_event_kinds（当前 N 个） 写法与 PENDING_DECISIONS 扫描面，另加反向（合成『上游 999 种事件』必须被判不一致）证明判据抓得住；第 10 组并进主汇总避免两个『通过 N/M』被 backup 抓错。验证：统筹方门禁 tool-contract-lint.py 由 TOOLLINT state=fail problems=1 tools=18（登记 0）转 state=ok problems=0 tools=18（登记 1）；统筹方独立验收 test_tool_norm_acceptance.py 11/11（含他自己的门禁有牙齿对照 0->1->0）；新增 tests/unit/test_tool_envelope.py 35/35；test_tool_contract 40/40；probe_tool_contract 扩到五段全 PASS；全量单测 42/42；契约符合性 44/44、前端契约 25/25、文档一致性 35/35、文档不变量 35/35、文档审查 18/18（数字见 VERSIONS v1.26）。行尾纪律（本轮真踩了一次，已记进评估文档 §3.3）：MODULES/OPERATIONS 是 git 的 -text 文件，第一版用编辑器改，新块被写成另一种行尾导致 numstat 从真实的 34/7、27/0 膨胀到 113/86、73/46；已还原并改字节级替换，现 bare LF=0。接口面零破坏：事件/阶段/CycleReport/Snapshot/Event/端点/版本轴/TOOLS_MAP 顶层键均未改，未登记工具产出原样返回（is_error_result 回退路径与 pipeline.run_check 读法未动），/profile.contract.result_envelope 新增 envelope_tool_count/built_by/staged 属加性。契约目录只读未动；对侧仓库与集成工作区未写入（只只读运行其门禁与验收脚本）。

**备份点**：本条目所在的提交（提交信息以 `v1.26:` 开头）

**定位命令**：`git log --oneline --grep "^v1.26:"`

**验证**：
- 全量单测 PASS (42/42)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 34 个 · 测试文件 42 个

**本次提交的文件**：
```
4697b2b v1.26: P9 ENVELOPE-WIRING（D33 追加验收 ③ 后半 + D30 收口；round_id R-4fb8a623b8）。缺陷（统筹方独立复验 v1.25，不看自述）：产出侧只把机制建好了 —— validate_result/_envelope_problems/audit 都在，但 ENVELOPE_TOOLS 是空集 ⇒ 18 个工具里没有一个的结果会被校验，audit().envelope_tools=[]，他门禁的不变式 F（envelope_tools 非空）因此重新变红。这就是本项目反复栽的形状：机制存在 != 机制接上了。修法五件：① ENVELOPE_TOOLS 由空集合改为登记表（工具->结果类别 kind），现役非空 check_and_run->verification；② 新增 build_envelope()（唯一一处装配信封 {ok,kind,data,error}）+ _error_object()（错误信封的 code/message 从 error/parsed_error/message 抽真实失败，第一版回灌了占位文案『工具报错』已修）+ envelope_of()/unwrap_payload()（兼容旁路取回原产出）；③ 接线 core/worker.py::_invoke —— 先套信封、再检验信封本体（顺序反了会把工具自己的中间形状 {ok,syntax_passed} 判成不合规信封，实测踩到）；_maybe_artifact 用 envelope_of 取回 data；④ 分阶段迁移判据公开声明（STAGED_OUT_OF_ENVELOPE + envelope_policy -> /profile 的 result_envelope.staged）：其余 17 个逐个按产出形状登记，run_lint/check_syntax 因 pipeline.run_check 直调读 ok 而先动读法，新增工具必须直接登记；⑤ audit() 加 envelope_tool_count/bad_envelope_kinds，describe_contract 公开登记面与 built_by。反空洞（三条，机械输出已贴评估文档 §4.1）：摘掉登记 => envelope_tools 立刻变空 且 Worker 同时退回旧形状（机制与声明同源）；半成品信封 => reject + tool-result-invalid；错误信封 error.code=AssertionError/message=boom 而 data.parsed_error（frames/category/exit_code）仍完整可读 —— 信封是分类不是丢事实。D30：除 v1.24 已勘误的事件数外，又扫出同族第二处 —— docs/PENDING_DECISIONS.md 的 upstream_event_kinds 写『当前 13 个』实测 18，已改正；并把 test_doc_invariants 第 10 组补硬：新增 upstream_event_kinds（当前 N 个） 写法与 PENDING_DECISIONS 扫描面，另加反向（合成『上游 999 种事件』必须被判不一致）证明判据抓得住；第 10 组并进主汇总避免两个『通过 N/M』被 backup 抓错。验证：统筹方门禁 tool-contract-lint.py 由 TOOLLINT state=fail problems=1 tools=18（登记 0）转 state=ok problems=0 tools=18（登记 1）；统筹方独立验收 test_tool_norm_acceptance.py 11/11（含他自己的门禁有牙齿对照 0->1->0）；新增 tests/unit/test_tool_envelope.py 35/35；test_tool_contract 40/40；probe_tool_contract 扩到五段全 PASS；全量单测 42/42；契约符合性 44/44、前端契约 25/25、文档一致性 35/35、文档不变量 35/35、文档审查 18/18（数字见 VERSIONS v1.26）。行尾纪律（本轮真踩了一次，已记进评估文档 §3.3）：MODULES/OPERATIONS 是 git 的 -text 文件，第一版用编辑器改，新块被写成另一种行尾导致 numstat 从真实的 34/7、27/0 膨胀到 113/86、73/46；已还原并改字节级替换，现 bare LF=0。接口面零破坏：事件/阶段/CycleReport/Snapshot/Event/端点/版本轴/TOOLS_MAP 顶层键均未改，未登记工具产出原样返回（is_error_result 回退路径与 pipeline.run_check 读法未动），/profile.contract.result_envelope 新增 envelope_tool_count/built_by/staged 属加性。契约目录只读未动；对侧仓库与集成工作区未写入（只只读运行其门禁与验收脚本）。
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/prompts.py                          |   5 +-
 core/worker.py                           |  34 ++-
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  85 +++++++
 docs/EVALUATION-ENVELOPE-WIRING.md       | 386 +++++++++++++++++++++++++++++++
 docs/MODULES.md                          |  43 +++-
 docs/OPERATIONS.md                       |  29 ++-
 docs/PENDING_DECISIONS.md                |   5 +-
 tests/README.md                          |   3 +-
 tests/diagnostics/probe_tool_contract.py |  74 +++++-
 tests/unit/test_doc_invariants.py        |  61 +++--
 tests/unit/test_tool_contract.py         |   8 +-
 tests/unit/test_tool_envelope.py         | 230 ++++++++++++++++++
 tools/__init__.py                        |  10 +-
 tools/tool_contract.py                   | 203 +++++++++++++++-
 17 files changed, 1121 insertions(+), 62 deletions(-)
```

---

## v1.27 — 2026-10-03 15:42

**改动**：P14+P15+P13+P11（round_id R-8b28b25a1f）：① 新增 core/runtime.py —— 运行根/工作区根/输出根三个互不混淆的绝对路径（/profile.runtime 暴露且保证存在；AGENT_RUNTIME_ROOT/AGENT_WORKSPACE_DIR/AGENT_OUTPUT_DIR 可覆盖），输出根与工作区根分开；② 任务级目标项目根 project_root（ContextVar，/encode 与 /run 逐次给、退出即还原），六个文件/结构工具与 check/verify 一律以它为根，outputs/ 前缀指向输出根，越界写返回结构化 out-of-scope-write（含 allowed_roots，且文件真的没写出去）；与 AGENT_BACKEND_DIR 语义分离并给 distinct_from_backend_dir 机判字段；③ 交付物声明 {path,sha256?,size?}：声明了必须存在且哈希一致否则 delivery-gap/fail，CycleReport.deliverables 与 /encode 响应回报实际产物 {path,sha256,size}；④ P13 归因看 report.verify.source：caller 的坏判据才记 invalid/criterion-broken，模型自拟走已现成的 delivery-gap/fail（方向是收紧）；⑤ P11 结构地图可信化：build_index_report 给出 indexed/skipped/truncated + skipped 逐条理由（non-python/parse-failed/permission-denied/skip-dir/over-limit）+ 每文件 sha256 + generated_at + root + 反向索引，get_architecture/get_module/find_symbol 只加不减。新增四个单测（P15 32 项 / P14 15 项 / P13 13 项 / P11 16 项）+ 五段探针 probe_output_and_map.py（21 项）；test_outcome 按 P13 改判并补 caller 的 invalid（两向都在红）；行尾门禁第 9 组本轮抓到 arch.py/files.py 被翻成 LF 已按索引还原。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/端点/版本轴未动，TOOLS_MAP 顶层键未改，/profile 加 runtime、/encode 请求响应加字段、CycleReport 加 deliverables（进 FROZEN_REPORT_KEYS）。D30：VERSIONS 的 v1.22 早已是 16->18，本轮给仍写着 16→19 的 EVALUATION-TRANSPARENCY2-BACKEND §9 加勘误注（历史条目不重排）。契约目录只读；对侧仓库与集成工作区未写入。

**备份点**：本条目所在的提交（提交信息以 `v1.27:` 开头）

**定位命令**：`git log --oneline --grep "^v1.27:"`

**验证**：
- 全量单测 PASS (46/46)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 35 个 · 测试文件 46 个

**本次提交的文件**：
```
9e990f8 v1.27: P14+P15+P13+P11（round_id R-8b28b25a1f）：① 新增 core/runtime.py —— 运行根/工作区根/输出根三个互不混淆的绝对路径（/profile.runtime 暴露且保证存在；AGENT_RUNTIME_ROOT/AGENT_WORKSPACE_DIR/AGENT_OUTPUT_DIR 可覆盖），输出根与工作区根分开；② 任务级目标项目根 project_root（ContextVar，/encode 与 /run 逐次给、退出即还原），六个文件/结构工具与 check/verify 一律以它为根，outputs/ 前缀指向输出根，越界写返回结构化 out-of-scope-write（含 allowed_roots，且文件真的没写出去）；与 AGENT_BACKEND_DIR 语义分离并给 distinct_from_backend_dir 机判字段；③ 交付物声明 {path,sha256?,size?}：声明了必须存在且哈希一致否则 delivery-gap/fail，CycleReport.deliverables 与 /encode 响应回报实际产物 {path,sha256,size}；④ P13 归因看 report.verify.source：caller 的坏判据才记 invalid/criterion-broken，模型自拟走已现成的 delivery-gap/fail（方向是收紧）；⑤ P11 结构地图可信化：build_index_report 给出 indexed/skipped/truncated + skipped 逐条理由（non-python/parse-failed/permission-denied/skip-dir/over-limit）+ 每文件 sha256 + generated_at + root + 反向索引，get_architecture/get_module/find_symbol 只加不减。新增四个单测（P15 32 项 / P14 15 项 / P13 13 项 / P11 16 项）+ 五段探针 probe_output_and_map.py（21 项）；test_outcome 按 P13 改判并补 caller 的 invalid（两向都在红）；行尾门禁第 9 组本轮抓到 arch.py/files.py 被翻成 LF 已按索引还原。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/端点/版本轴未动，TOOLS_MAP 顶层键未改，/profile 加 runtime、/encode 请求响应加字段、CycleReport 加 deliverables（进 FROZEN_REPORT_KEYS）。D30：VERSIONS 的 v1.22 早已是 16->18，本轮给仍写着 16→19 的 EVALUATION-TRANSPARENCY2-BACKEND §9 加勘误注（历史条目不重排）。契约目录只读；对侧仓库与集成工作区未写入。
 .env.example                              |  19 +
 .gitignore                                |   6 +
 CYCLE.md                                  |   2 +-
 README.md                                 |  14 +-
 core/coding_cycle.py                      | 128 ++++++-
 core/contract.py                          |   2 +
 core/cycle.py                             |   8 +
 core/pipeline.py                          |  71 +++-
 core/runtime.py                           | 593 ++++++++++++++++++++++++++++++
 core/symbol_index.py                      | 210 +++++++++++
 docs/ARCHITECTURE.md                      |   2 +-
 docs/CHANGELOG.md                         |  75 ++++
 docs/EVALUATION-OUTPUT-CONTRACT.md        | 365 ++++++++++++++++++
 docs/EVALUATION-TRANSPARENCY2-BACKEND.md  |   8 +
 docs/FRONTEND_CONTRACT.md                 |  16 +
 docs/MODULES.md                           | 282 +++++++++-----
 docs/OPERATIONS.md                        | 130 ++++---
 docs/PENDING_DECISIONS.md                 |  31 ++
 main.py                                   |  49 ++-
 tests/README.md                           |   5 +
 tests/diagnostics/probe_output_and_map.py | 204 ++++++++++
 tests/unit/test_arch_map.py               | 157 ++++++++
 tests/unit/test_criterion_ownership.py    | 144 ++++++++
 tests/unit/test_deliverables.py           | 197 ++++++++++
 tests/unit/test_doc_consistency.py        |   6 +-
 tests/unit/test_outcome.py                |  39 +-
 tests/unit/test_project_root.py           | 189 ++++++++++
 tools/arch.py                             | 257 ++++++++++---
 tools/code_checks.py                      |  23 +-
 tools/files.py                            |  84 +++--
 tools/verify.py                           |  24 +-
 31 files changed, 3068 insertions(+), 272 deletions(-)
```

---

## v1.27.1 — 2026-10-03 15:46

**改动**：C4 勘误（OUTPUT-CONTRACT 评估文档）：§3.1 的 git diff --stat 是提交前快照，与备份点 cd1891b 有三处差异，已按机械输出为准写明 —— ① .gitignore 实际 6 行（快照后补了 .tmp/ 两行）；② docs/MODULES.md 实际 282 行（快照后才改版本戳 §40->§41）；③ 口径差异：快照是 24 个已跟踪文件，备份点是 32 个文件（含 core/runtime.py、四个新单测、探针、本评估文档与 VERSIONS.md）。这条本身就是 C4『改动清单与实际一致』的自纠：交出去核对的数字必须对，对不上时以机械输出为准并明写差异。

**备份点**：本条目所在的提交（提交信息以 `v1.27.1:` 开头）

**定位命令**：`git log --oneline --grep "^v1.27.1:"`

**验证**：
- 全量单测 PASS (46/46)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 35 个 · 测试文件 46 个

**本次提交的文件**：
```
80e2e8d v1.27.1: C4 勘误（OUTPUT-CONTRACT 评估文档）：§3.1 的 git diff --stat 是提交前快照，与备份点 cd1891b 有三处差异，已按机械输出为准写明 —— ① .gitignore 实际 6 行（快照后补了 .tmp/ 两行）；② docs/MODULES.md 实际 282 行（快照后才改版本戳 §40->§41）；③ 口径差异：快照是 24 个已跟踪文件，备份点是 32 个文件（含 core/runtime.py、四个新单测、探针、本评估文档与 VERSIONS.md）。这条本身就是 C4『改动清单与实际一致』的自纠：交出去核对的数字必须对，对不上时以机械输出为准并明写差异。
 docs/EVALUATION-OUTPUT-CONTRACT.md | 18 +++++++++++++++++-
 1 file changed, 17 insertions(+), 1 deletion(-)
```

---

## v1.28 — 2026-10-03 19:24

**改动**：P17 pass_evidence（round_id R-ecc61d8543）：pass 必须带机械证据。① 新增 core/evidence.py —— build_evidence 按强→弱取三类证据（executed{command,exit_code,expect_exit,criterion_source} / artifacts[{path,sha256,size}] 必须在输出根内 / static_declared{reason} 理由必须可复核），pass_allowed 硬判据，describe 契约面；② 执行记录留痕：SharedMemory.set_verify 增 exit_code/expect_exit（None 不冒充 0），来源 CheckPipeline.run_verify -> check_and_run 的真实 parsed.exit_code，orchestrator/skill_runner 两个调用点接线，CycleReport.verify 与 verify 事件都带 exit_code；③ pass 出口接门禁（core/coding_cycle.py 产物对账之后、打检查点之前）：checked_by==model 且无 evidence_kind 不得记 pass，结局 invalid/unsubstantiated-pass（core/outcome.py 新种类，不默认 fail），且不落检查点；④ 报告/事件/接口：CycleReport.evidence 进 FROZEN_REPORT_KEYS，cycle_end 加 checked_by/evidence_kind/evidence，/encode 请求加 static_reason、响应加 evidence，/profile 加 pass_evidence；workspace 里的产物不算证据但逐条记 excluded_artifacts(out-of-output-root/missing-hash) 不静默。反空洞（机械输出已贴评估文档 §4.1）：探针走生产路径真实子进程 => phase=record outcome=pass evidence_kind=executed exit_code=0；抽掉 exit_code => 同一个 pass 翻成 phase=failed outcome=invalid kind=unsubstantiated-pass 且 commit 为空，恢复回 pass。验证：新增 tests/unit/test_pass_evidence.py 30/30、tests/diagnostics/probe_pass_evidence.py 13/13、全量单测 47/47、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/端点/版本轴未动；契约版本不升（纯加性）。边界：D39 拆解关卡默认关闭本轮 DISPATCH 未指派且需用户批准 => 不动（DECOMPOSE_GATE_DEFAULT 保持 warn）；P16 多语言/P12 不做；D30 事件计数经机械复查仍 18。测试夹具 test_deliverables/test_cycle_manifest 的假编排器补 exit_code（忠实复刻真实编排器，非放宽判据）。

**备份点**：本条目所在的提交（提交信息以 `v1.28:` 开头）

**定位命令**：`git log --oneline --grep "^v1.28:"`

**验证**：
- 全量单测 PASS (47/47)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 36 个 · 测试文件 47 个

**本次提交的文件**：
```
50f7d4c v1.28: P17 pass_evidence（round_id R-ecc61d8543）：pass 必须带机械证据。① 新增 core/evidence.py —— build_evidence 按强→弱取三类证据（executed{command,exit_code,expect_exit,criterion_source} / artifacts[{path,sha256,size}] 必须在输出根内 / static_declared{reason} 理由必须可复核），pass_allowed 硬判据，describe 契约面；② 执行记录留痕：SharedMemory.set_verify 增 exit_code/expect_exit（None 不冒充 0），来源 CheckPipeline.run_verify -> check_and_run 的真实 parsed.exit_code，orchestrator/skill_runner 两个调用点接线，CycleReport.verify 与 verify 事件都带 exit_code；③ pass 出口接门禁（core/coding_cycle.py 产物对账之后、打检查点之前）：checked_by==model 且无 evidence_kind 不得记 pass，结局 invalid/unsubstantiated-pass（core/outcome.py 新种类，不默认 fail），且不落检查点；④ 报告/事件/接口：CycleReport.evidence 进 FROZEN_REPORT_KEYS，cycle_end 加 checked_by/evidence_kind/evidence，/encode 请求加 static_reason、响应加 evidence，/profile 加 pass_evidence；workspace 里的产物不算证据但逐条记 excluded_artifacts(out-of-output-root/missing-hash) 不静默。反空洞（机械输出已贴评估文档 §4.1）：探针走生产路径真实子进程 => phase=record outcome=pass evidence_kind=executed exit_code=0；抽掉 exit_code => 同一个 pass 翻成 phase=failed outcome=invalid kind=unsubstantiated-pass 且 commit 为空，恢复回 pass。验证：新增 tests/unit/test_pass_evidence.py 30/30、tests/diagnostics/probe_pass_evidence.py 13/13、全量单测 47/47、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/端点/版本轴未动；契约版本不升（纯加性）。边界：D39 拆解关卡默认关闭本轮 DISPATCH 未指派且需用户批准 => 不动（DECOMPOSE_GATE_DEFAULT 保持 warn）；P16 多语言/P12 不做；D30 事件计数经机械复查仍 18。测试夹具 test_deliverables/test_cycle_manifest 的假编排器补 exit_code（忠实复刻真实编排器，非放宽判据）。
 CYCLE.md                                 |   2 +-
 README.md                                |   3 +-
 core/coding_cycle.py                     |  63 +++++-
 core/contract.py                         |  22 ++-
 core/cycle.py                            |   9 +
 core/evidence.py                         | 258 ++++++++++++++++++++++++
 core/memory.py                           |   9 +
 core/orchestrator.py                     |   5 +
 core/outcome.py                          |   7 +
 core/skill_runner.py                     |   3 +
 docs/ARCHITECTURE.md                     |   2 +-
 docs/CHANGELOG.md                        |  73 +++++++
 docs/EVALUATION-PASS-EVIDENCE.md         | 327 +++++++++++++++++++++++++++++++
 docs/MODULES.md                          |  55 +++++-
 docs/OPERATIONS.md                       |  27 ++-
 main.py                                  |  14 ++
 tests/README.md                          |   2 +
 tests/diagnostics/probe_pass_evidence.py | 250 +++++++++++++++++++++++
 tests/unit/test_cycle_manifest.py        |   4 +
 tests/unit/test_deliverables.py          |   5 +-
 tests/unit/test_pass_evidence.py         | 276 ++++++++++++++++++++++++++
 21 files changed, 1403 insertions(+), 13 deletions(-)
```

---

## v1.29 — 2026-10-04 00:31

**改动**：P18 拆解关卡出厂默认由 warn 升到 block（round_id R-58068c34ba；用户 2026-10-03 裁决 D39）。① core/coding_cycle.py::DECOMPOSE_GATE_DEFAULT = block（DECOMPOSE_GATE 环境变量保留 off/warn/block 以便灰度）；② 拦下理由补逐条证据（从 principles[verdict=violated] 抽 evidence 拼进 report.error；decompose_review 事件照旧带 violated + principles[].evidence）；③ block 默认暴露并修掉一处交互：core/skill_runner.py::render_task_description 样板文本「目标与参数」撞 P3 并列词判据 ⇒ 每次技能重放都会被拦，改顿号「目标、参数」（语义不变）；④ 验收双向（tests/unit/test_decompose_review.py [V4]，不设任何环境变量）：不合规（含并列词「并」）⇒ phase=failed outcome=fail kind=decomposition-violation 且 error 写明 P3 + 逐条证据；合规 ⇒ phase=record outcome=pass，事件 passed=True applied=True；环境变量 off/warn/block 仍可覆盖、非法值回落 block。8 个测试其他机制的夹具被新默认拦下，按三类适配（如实记录在 CHANGELOG §43.4 与评估文档 §3）：5 个修夹具使其合规（criterion_ownership/pass_evidence/deliverables 补 expected_output；verify_vacuous 描述去并列词；transparency 第二轮不再点名 mod.py 以免 P4），2 个夹具本身必须不合规故显式 DECOMPOSE_GATE=off（cycle_manifest 多符号单文件测 manifest；reuse_scope §5 app.py 必须同时交付 app/ping 测 P7b），1 个是产品样板措辞修正（skills）。验证：全量单测 47/47、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/CycleReport/Snapshot/端点/版本轴未动，decompose_review payload 键未增，.interface_contract/ 只读未动；D30 经机械复查无新漂移，顺带修 MODULES §28 门禁项数 19→33 与 OPERATIONS §4.17 两处历史控制字符损坏。

**备份点**：本条目所在的提交（提交信息以 `v1.29:` 开头）

**定位命令**：`git log --oneline --grep "^v1.29:"`

**验证**：
- 全量单测 PASS (47/47)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 36 个 · 测试文件 47 个

**本次提交的文件**：
```
b23dfad v1.29: P18 拆解关卡出厂默认由 warn 升到 block（round_id R-58068c34ba；用户 2026-10-03 裁决 D39）。① core/coding_cycle.py::DECOMPOSE_GATE_DEFAULT = block（DECOMPOSE_GATE 环境变量保留 off/warn/block 以便灰度）；② 拦下理由补逐条证据（从 principles[verdict=violated] 抽 evidence 拼进 report.error；decompose_review 事件照旧带 violated + principles[].evidence）；③ block 默认暴露并修掉一处交互：core/skill_runner.py::render_task_description 样板文本「目标与参数」撞 P3 并列词判据 ⇒ 每次技能重放都会被拦，改顿号「目标、参数」（语义不变）；④ 验收双向（tests/unit/test_decompose_review.py [V4]，不设任何环境变量）：不合规（含并列词「并」）⇒ phase=failed outcome=fail kind=decomposition-violation 且 error 写明 P3 + 逐条证据；合规 ⇒ phase=record outcome=pass，事件 passed=True applied=True；环境变量 off/warn/block 仍可覆盖、非法值回落 block。8 个测试其他机制的夹具被新默认拦下，按三类适配（如实记录在 CHANGELOG §43.4 与评估文档 §3）：5 个修夹具使其合规（criterion_ownership/pass_evidence/deliverables 补 expected_output；verify_vacuous 描述去并列词；transparency 第二轮不再点名 mod.py 以免 P4），2 个夹具本身必须不合规故显式 DECOMPOSE_GATE=off（cycle_manifest 多符号单文件测 manifest；reuse_scope §5 app.py 必须同时交付 app/ping 测 P7b），1 个是产品样板措辞修正（skills）。验证：全量单测 47/47、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/CycleReport/Snapshot/端点/版本轴未动，decompose_review payload 键未增，.interface_contract/ 只读未动；D30 经机械复查无新漂移，顺带修 MODULES §28 门禁项数 19→33 与 OPERATIONS §4.17 两处历史控制字符损坏。
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/coding_cycle.py                    |  36 +++-
 core/skill_runner.py                    |   2 +-
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  62 ++++++
 docs/EVALUATION-DECOMPOSE-GATE-BLOCK.md | 336 ++++++++++++++++++++++++++++++++
 docs/MODULES.md                         |  11 +-
 docs/OPERATIONS.md                      |  10 +-
 docs/PENDING_DECISIONS.md               |  23 +--
 tests/unit/test_artifact_binding.py     |  12 +-
 tests/unit/test_criterion_ownership.py  |   3 +-
 tests/unit/test_cycle_manifest.py       |  10 +-
 tests/unit/test_decompose_review.py     |  88 ++++++++-
 tests/unit/test_deliverables.py         |   3 +-
 tests/unit/test_pass_evidence.py        |   2 +-
 tests/unit/test_reuse_scope.py          |   6 +
 tests/unit/test_transparency.py         |   5 +-
 tests/unit/test_verify_vacuous.py       |   4 +-
 19 files changed, 574 insertions(+), 46 deletions(-)
```

---

## v1.30 — 2026-10-04 14:00

**改动**：P19 推理模型 reasoning_content 协议 + P20 关卡分档 + D43 假换冒烟（round_id R-5bfd0ff2e5）。★ P19 方向性分歧：工单表 1 写『剥掉 reasoning_content』，但统筹方实测错误原文与 DeepSeek 官方《Thinking Mode》都说『带 tools 的请求必须回灌』（不回灌才 400），本仓库旧代码在适配层就丢了该字段 ⇒ 任何推理模型都撞。本轮按协议正确实现：core/llm.py 新增唯一判定点 request_messages()（带 tools 回灌 / 不带剥掉）+ AGENT_REASONING_REPLAY=auto/never/always 灰度（never 即工单字面行为）；chat() 把 reasoning_content 作为事实带回并累计用量（含 reasoning_tokens）；core/worker.py 新增 _assistant_message() 把上一轮 reasoning 原样带进 assistant 消息（三处分支）；CycleReport.model_usage（aggregate_usage 汇总，进 FROZEN_REPORT_KEYS）让『预算被思考吃掉』不再被误读成模型不行。P20 修正 P18：DECOMPOSE_GATE_DEFAULT 由 block 退回 warn 止血（实测 B1-A 误否决：V2 由 pass 变 fail），并要求分档 —— _review_decomposition 的否决条件由 not passed 改为 violated，undecidable（判不了）只记录、不计入否决。D43 假换冒烟：同一模型换名 ⇒ resolve_profiles()（/profile 数据源）与 Worker 路径都走通。反空洞（机械输出见评估文档 §4）：测试内假端点按 DeepSeek 规则验收，带 tools 且 assistant 缺 reasoning_content 就抛官方 400 原文 ⇒ 不回灌必复现、回灌走通；P20 [V5] 只有 undecidable ⇒ 放行 / 有 violated ⇒ 拦下（双向）；D43 关掉回灌 ⇒ 同一路径复现 400。验证：新增 test_reasoning_protocol.py 16/16、test_model_swap.py 8/8；test_decompose_review.py 重写 [V4]+新增 [V5]+报告用量 32/32；全量 49/49、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/Snapshot/Event/端点/版本轴未动，CycleReport 加性加 model_usage，decompose_review payload 键未增。★ 未做真实推理端点实跑（无端点/密钥，会写 workspace），已如实列在评估文档。★ 请统筹方裁决 P19 方向（维持协议正确 vs 改 AGENT_REASONING_REPLAY=never）。D30 机械复查无新漂移；P20 默认值变化已同步 MODULES §28/OPERATIONS §4.17/PENDING C11，并把 4 个测试里『P18 起默认 block』的陈旧注释改成与实现一致。

**备份点**：本条目所在的提交（提交信息以 `v1.30:` 开头）

**定位命令**：`git log --oneline --grep "^v1.30:"`

**验证**：
- 全量单测 PASS (49/49)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 36 个 · 测试文件 49 个

**本次提交的文件**：
```
a7ef862 v1.30: P19 推理模型 reasoning_content 协议 + P20 关卡分档 + D43 假换冒烟（round_id R-5bfd0ff2e5）。★ P19 方向性分歧：工单表 1 写『剥掉 reasoning_content』，但统筹方实测错误原文与 DeepSeek 官方《Thinking Mode》都说『带 tools 的请求必须回灌』（不回灌才 400），本仓库旧代码在适配层就丢了该字段 ⇒ 任何推理模型都撞。本轮按协议正确实现：core/llm.py 新增唯一判定点 request_messages()（带 tools 回灌 / 不带剥掉）+ AGENT_REASONING_REPLAY=auto/never/always 灰度（never 即工单字面行为）；chat() 把 reasoning_content 作为事实带回并累计用量（含 reasoning_tokens）；core/worker.py 新增 _assistant_message() 把上一轮 reasoning 原样带进 assistant 消息（三处分支）；CycleReport.model_usage（aggregate_usage 汇总，进 FROZEN_REPORT_KEYS）让『预算被思考吃掉』不再被误读成模型不行。P20 修正 P18：DECOMPOSE_GATE_DEFAULT 由 block 退回 warn 止血（实测 B1-A 误否决：V2 由 pass 变 fail），并要求分档 —— _review_decomposition 的否决条件由 not passed 改为 violated，undecidable（判不了）只记录、不计入否决。D43 假换冒烟：同一模型换名 ⇒ resolve_profiles()（/profile 数据源）与 Worker 路径都走通。反空洞（机械输出见评估文档 §4）：测试内假端点按 DeepSeek 规则验收，带 tools 且 assistant 缺 reasoning_content 就抛官方 400 原文 ⇒ 不回灌必复现、回灌走通；P20 [V5] 只有 undecidable ⇒ 放行 / 有 violated ⇒ 拦下（双向）；D43 关掉回灌 ⇒ 同一路径复现 400。验证：新增 test_reasoning_protocol.py 16/16、test_model_swap.py 8/8；test_decompose_review.py 重写 [V4]+新增 [V5]+报告用量 32/32；全量 49/49、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4。契约面零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/Snapshot/Event/端点/版本轴未动，CycleReport 加性加 model_usage，decompose_review payload 键未增。★ 未做真实推理端点实跑（无端点/密钥，会写 workspace），已如实列在评估文档。★ 请统筹方裁决 P19 方向（维持协议正确 vs 改 AGENT_REASONING_REPLAY=never）。D30 机械复查无新漂移；P20 默认值变化已同步 MODULES §28/OPERATIONS §4.17/PENDING C11，并把 4 个测试里『P18 起默认 block』的陈旧注释改成与实现一致。
 CYCLE.md                              |   2 +-
 README.md                             |   5 +-
 core/coding_cycle.py                  |  56 ++++-
 core/contract.py                      |   2 +
 core/cycle.py                         |   9 +
 core/llm.py                           | 139 ++++++++++-
 core/worker.py                        |  40 +++-
 docs/ARCHITECTURE.md                  |   2 +-
 docs/CHANGELOG.md                     |  64 +++++
 docs/EVALUATION-REASONING-PROTOCOL.md | 436 ++++++++++++++++++++++++++++++++++
 docs/MODULES.md                       |  24 +-
 docs/OPERATIONS.md                    |  12 +-
 docs/PENDING_DECISIONS.md             |  25 +-
 tests/README.md                       |   4 +-
 tests/unit/test_artifact_binding.py   |   9 +-
 tests/unit/test_cycle_manifest.py     |   6 +-
 tests/unit/test_decompose_review.py   |  98 +++++---
 tests/unit/test_model_swap.py         | 155 ++++++++++++
 tests/unit/test_reasoning_protocol.py | 224 +++++++++++++++++
 tests/unit/test_reuse_scope.py        |   4 +-
 tests/unit/test_transparency.py       |   6 +-
 21 files changed, 1216 insertions(+), 106 deletions(-)
```

---

## v1.31 — 2026-10-05 18:20

**改动**：P21 / M1 —— **上下文链路调用算法（外部记忆库）的第一期：独立库只做存储与检索**（round_id R-c0c8ba72e3）。来源：用户 2026-10-03 提议（外部记忆链表 + 物理存储上下文的区域 + 按对话时间/关键词分区 + 单元平常不调用、调用分机制）+ 统筹方 DISPATCH ⓪「本轮的活只有 M1：存储与检索 + 独立根 + 越界拒绝，**不接模型**」与 WORK-ORDER【P21】的三期（M1/M2/M3，**不许跳级**）。★ 先交代本轮为什么只做这一件：ROUND.json 的 open_items 有 7 条，逐条对仓库事实核过去 —— D38（P17）v1.28 已交付、D39（P18）v1.29 交付且 v1.30 的 P20 已按工单退回 warn 并分档、D40（P19）v1.30 已交付且 WORK-ORDER 的 2026-10-05 更正条明写『已独立复核通过，保持 auto 不要改』、D41（P20）v1.30 已交付、D43 假换冒烟 v1.30 已交付、D37（P16 多语言）DISPATCH 逐字『现在别动』、D30 由 test_doc_invariants 第 8/10 组自带反向判据机械复查无新漂移 ⇒ 唯一没做过也没被推迟的就是 P21 M1（ROUND.json 的 [ ] 是载荷里的历史文本，不随交付回填，这正是本项目在治的 U- 类）。新增 core/context_store/ 五件：① units.py —— 单元结构（时间/关键词/**符号引用**/file:line/内容哈希）+ 内容寻址 id（sha256(source+LF+归一正文)[:16] ⇒ CRLF/LF 同 id、同 source 同内容幂等不重复）；② scope.py —— **独立根**（默认 D:\PythonProject\08-memory，在两侧仓库之外，判据是 os.path.normcase 前缀比较）+ **越界结构化拒绝** StoreScopeError（字段与 runtime.scope_error_result() 同形，但**刻意不 import core.runtime** —— M1 是独立库）：`..`/绝对路径/空路径/库根在仓库内一律拒；③ retrieval.py —— **两路召回**（关键词：显式关键词 > 正文子串 + idf；符号：unit.symbol_refs ∩ 查询符号，structure_lookup.via=find_symbol|get_module|get_architecture，**不新建关键词库**）+ 记分；calibrate() 给 missed/false_recalled/miss_rate/false_recall_rate 与候选阈值曲线；④ store.py —— ContextStore（write/read/list_units/recall/calibrate/archive/profile），索引 units.jsonl 一行一条、确定性排序、逐字节可复现；**全类没有删除方法**，淘汰只走 archive()（移入 archive/ + 索引留 status=archived/archived_at，read() 仍读得到原文 ⇒ 淘汰不抹证据）；⑤ __init__.py —— 包级 describe()。三条硬要求的落点：① 判据覆盖漏召/误召（探针实测 micro_recall=0.6、miss_rate=0.4、false_recall_rate=0.2，**不看调用成功**）；② 第二路召回真有牙（单测里有一个单元关键词与正文都没有查询词面、只有 symbol_refs 命中，关键词路召不回、符号路召回 ⇒ 摘掉符号路立刻红）；③ 阈值不许定死（recall() 没有 threshold 参数，用 inspect.signature 钉住；返回全部带分数候选；recommended_threshold 恒为 None）。★ 测试逃生口（放宽了就说放宽了）：本轮硬边界只许写本仓库，而 M1 要求库根在仓库之外 ⇒ 单测/探针用显式关键字 allow_inside_repos=True 在 .tmp/ 造临时库根，生产代码无一处传它，放宽事实印在 profile()["scope"]["outside_repos"]["relaxed"]，默认值仍是拒绝（三条仓库各试一次 + 环境变量指进仓库，四例全拒）。验证：新增 tests/unit/test_memory_store.py 71/71、tests/diagnostics/probe_memory_store.py 五段取证 exit 0；全量单测 50/50（新计数）、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4，全部 exit 0。契约面零改动、零破坏：事件仍 18 种、工具仍 18 个、PHASE_ORDER/CycleReport/Snapshot/Event/端点/版本轴/TOOLS_MAP 全未动 —— 本包没有被任何生产代码 import（AST 扫描：只有标准库 + 包内相对导入）、main.py 未引用、无工具注册 ⇒ 主链路行为逐字节不变（这正是约束 4『在跨模型对比结论出来之前不得进主链路』的机判形态）。★ 未做：M2/M3、真实阈值校准、结构索引的实调用（本轮只产出 structure_lookup 原料）、默认库根未创建（在本仓库之外，只做路径计算证明隔离），均如实列在评估文档 §4.8/§7。D30 机械复查无新漂移；五处版本戳同步至 CHANGELOG §45。

**备份点**：本条目所在的提交（提交信息以 `v1.31:` 开头）

**定位命令**：`git log --oneline --grep "^v1.31:"`

**验证**：
- 全量单测 PASS (50/50)
- 文档一致性 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 41 个 · 测试文件 50 个

**本次提交的文件**：
```
949330f v1.31: P21/M1 上下文链路调用算法（外部记忆库）—— 独立库只做存储与检索（round_id R-c0c8ba72e3）
 CYCLE.md                                |   2 +-
 README.md                               |   3 +-
 core/context_store/__init__.py          |  61 ++++
 core/context_store/retrieval.py         | 354 +++++++++++++++++++++
 core/context_store/scope.py             | 205 ++++++++++++
 core/context_store/store.py             | 328 ++++++++++++++++++++
 core/context_store/units.py             | 202 +++++++++++++
 docs/ARCHITECTURE.md                    |   2 +-
 docs/CHANGELOG.md                       |  89 ++++++
 docs/EVALUATION-MEMORY-M1.md            | 531 ++++++++++++++++++++++++++++++++
 docs/MODULES.md                         |  73 ++++-
 docs/OPERATIONS.md                      |   2 +-
 docs/VERSIONS.md                        |  18 ++
 tests/diagnostics/probe_memory_store.py | 229 ++++++++++++++
 tests/unit/test_memory_store.py         | 467 ++++++++++++++++++++++++++++
 15 files changed, 2560 insertions(+), 6 deletions(-)
```

> 本条目由本轮**手工追加**（`tests/backup.py` 需要 `--tag/--note` 参数），
> 格式与它写入的一致；**历史条目只增不改**。
> 提交后独立复核：在 commit `949330f` 之后重跑全量单测 **50/50**、
> 文档审查 **18/18**，均 exit 0（见 `docs/EVALUATION-MEMORY-M1.md` §4.8）。


## v1.32 — 2026-10-05 19:18

**改动**：P21 ★★ **调用分算法必须与模型无关**（`round_id R-d11562e8d6`）：`retrieval.score(unit, query_context) -> float` 唯一纯函数入口（不读时钟/环境/网络、不调模型、不改入参）+ `score_breakdown()` 四项构成 lexical/symbol/time_decay/custom **相加 == 总分**+ 时间衰减纯函数（`now` 显式，`half_life_days=None` 默认关闭、参数不许拍）+ 定制加权 `[{why,add,when}]` 显式配置（缺 why / 未知键 / 非法值一律 ValueError）+ `calibrate()` 记 config/samples/curve 三指纹 ⇒ 校准可复现+ `recall().basis = {scorer:'S-A', model:null, config_sha256}`（scorer 与 model 并列归因；S-A 标已实现、S-B/S-C 如实标 M2 对照臂未实现）；`STORE_VERSION` m1.1→m1.2。新增 `tests/unit/test_memory_scoring.py`（63 项）+ `tests/diagnostics/probe_memory_scoring.py`（六段）；4 条反空洞（偏航打分器/读时钟打分器/改一项构成/改一条标注 ⇒ 同一条判据立刻红）。契约面零改动（事件 18 / 工具 18 / 端点/阶段/版本轴未动，本包无生产消费方）。

**备份点**：本条目所在的提交（提交信息以 `v1.32:` 开头）

**定位命令**：`git log --oneline --grep "^v1.32:"`

**验证**：
- 全量单测 PASS (51/51)
- 文档一致性 PASS (35/35)
- 文档不变量 PASS (35/35)
- 文档审查 PASS (18/18)

**规模**：工具 18 个 · core 模块 36 个（`core/*.py`，与 `tests/backup.py` 同口径；含 `core/context_store/` 子包共 41 个 —— v1.31 条目写的是后者）· 测试文件 51 个

**本次提交的文件**：
```
dc154c4 v1.32: P21 ★★ 调用分算法必须与模型无关（round_id R-d11562e8d6）
 CYCLE.md                                  |   2 +-
 README.md                                 |   3 +-
 core/context_store/__init__.py            |  11 +-
 core/context_store/retrieval.py           | 428 ++++++++++++++++++++++++--
 core/context_store/store.py               |  24 +-
 docs/ARCHITECTURE.md                      |   2 +-
 docs/CHANGELOG.md                         |  68 +++++
 docs/EVALUATION-MEMORY-SCORING.md         | 488 ++++++++++++++++++++++++++++++
 docs/MODULES.md                           |  63 +++-
 docs/OPERATIONS.md                        |   2 +-
 tests/diagnostics/probe_memory_scoring.py | 336 ++++++++++++++++++++
 tests/unit/test_memory_scoring.py         | 473 +++++++++++++++++++++++++++++
 12 files changed, 1857 insertions(+), 43 deletions(-)
```

> 本条目由本轮**手工追加**（格式与 `tests/backup.py` 写入的一致；历史条目只增不改）。
> 提交后独立复核（备份点 `ab2842e` 之后重跑）见评估文档 `docs/EVALUATION-MEMORY-SCORING.md` §4.4：全量单测 51/51、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4，全部 exit 0；行尾门禁 `git ls-files --eol` 对本次改动的已跟踪文件**未翻行**。另：某一轮全量单测曾报 50/51（未复现、未捕获失败名），已如实记在该评估文档 §4.4。

---

## v1.33 — 2026-10-06 15:34

**改动**：P22-A **模型档位 + 可启用模式（类插件结构）**（`round_id R-5f49cfa62f`）：只做 A（解耦）—— 把模型差异收进**档位**（数据），协议路径统一在适配层裁决。① `core/model_profile.py` 新增 `ModelReasoning`（`is_reasoning_model` / `replay`(auto|never|always) / `counts_in_max_tokens`（预算语义，仅声明；换算属 B1）/ `max_thinking_chars`（0=关闭））+ `problems()`（声明自洽，会红）与 `modes()`；`ModelProfile` 加 `reasoning` / `match` / `fallback` / `fallback_to`，新增 `effective_reasoning_replay()` 与 `tier()`（P22-A 全字段可机读）。② 加一个模型 = 加一份档位、**代码零改动**：`_guess_profile_name` 改为按各档位自带的 `match` 片段选档（函数里**不再有任何具体模型名**），内置新增 `reasoner`（推理模型、ctx=65536、max_tokens=8192、match=deepseek-*）；`register_profile()` 仍是运行时注册入口，新增 `profile_names()` / `profile_source()`（builtin/registered/missing）；匹配不到 ⇒ `default` + `auto`，且 `fallback`/`fallback_to` 使回落**可见**（不静默、不取极端）。③ **上限默认值进档位**：`from_env` 未显式给 `_CONTEXT_WINDOW` 时用档位声明的 `limits`（此前一律按窗口重推，会把档位的 `max_tokens=8192` 丢掉），显式覆盖仍优先。④ `core/llm.py`：`effective_replay_policy(profile)` = ① 进程级 `AGENT_REASONING_REPLAY` → ② 档位声明 → ③ `auto`；`request_messages(messages, tools, profile=None)` 仍是**唯一判定点**（`profile=None` 时与 P19 逐字节一致）；思考上限在回灌处按 `max_thinking_chars` 截断（默认关闭，0 时不多造副本）；新增 `replay_contract_problems(profile)`（★ **声明 vs 实现**判据，会红）；`aggregate_usage(..., profile=None)` 增记 `policy_declared`/`model`/`thinking_counts_in_max_tokens`。⑤ 暴露面：`/profile` 新增 `model_tiers`，`models[*]` 新增 `tier` 与 `replay_contract_problems`；`core/coding_cycle.py::_attach_model_usage` 把生效档位带进 `model_usage`（否则「换档位」与「换模型」会被混读）。★ 反空洞（机械输出见评估文档 §4）：运行时注册一份带 `match` 的档位 ⇒ 自动选中并用假 DeepSeek 端点（缺回灌即抛官方 400）跑通一道题；请求体 sha256 双向 —— 推理模式关/开（auto 下）与 `cap=0` 都**回到同一个基线哈希** `c1b86b4b0565c787`，而 `replay=never` / `cap=2` / `AGENT_REASONING_REPLAY=never` **必变**，取消覆盖后回原哈希；`replay_contract_problems` 在真实实现下为空、把 `request_messages` 换成「一律剥掉」的坏实现 ⇒ **立刻非空**、换回 ⇒ 又为空；一键关回灌 ⇒ 同一个假端点复现官方 400。★ 边界：B（思考策略）本轮**不动**（DISPATCH 逐字）；思考上限截断**未对真实推理端点实跑**（无端点/密钥），仅在假端点与请求体上取证 —— 如实记在评估文档 §4「未验证的部分」。D30 经机械复查无新漂移。契约面零破坏：事件仍 18 种、工具仍 18 个、`PHASE_ORDER`/`CycleReport`（`model_usage` 只加键）/`Snapshot`/`Event`/端点/版本轴未动，`/profile` 改动均为加性。

**备份点**：本条目所在的提交（提交信息以 `v1.33:` 开头）

**定位命令**：`git log --oneline --grep "^v1.33:"`

**规模**：工具 18 个 · core 模块 36 个（`core/*.py`；含 `core/context_store/` 子包共 41 个）· `tests/unit/test_*.py` 52 个 + `tests/diagnostics/probe_*.py` 7 个

**本次提交的文件**：

```
34a4deb v1.33: P22-A 模型档位 + 可启用模式（类插件结构）（round_id R-5f49cfa62f）
 CYCLE.md                               |   2 +-
 README.md                              |   3 +-
 core/__init__.py                       |   6 +
 core/coding_cycle.py                   |  10 +-
 core/config.py                         |   8 +
 core/llm.py                            | 159 +++++++++--
 core/model_profile.py                  | 238 +++++++++++++++-
 docs/ARCHITECTURE.md                   |   7 +-
 docs/CHANGELOG.md                      |  55 ++++
 docs/EVALUATION-MODEL-TIERS.md         | 487 +++++++++++++++++++++++++++++++++
 docs/MODULES.md                        | 115 +++++++-
 docs/OPERATIONS.md                     |  64 ++++-
 main.py                                |  17 ++
 tests/diagnostics/probe_model_tiers.py | 306 +++++++++++++++++++++
 tests/unit/test_model_tiers.py         | 401 +++++++++++++++++++++++++++
 15 files changed, 1836 insertions(+), 42 deletions(-)
```

> 本条目由本轮**手工追加**（格式与 `tests/backup.py` 写入的一致；历史条目只增不改）。
> 提交后独立复核见评估文档 `docs/EVALUATION-MODEL-TIERS.md` §4.7：全量单测 52/52、文档一致性 35/35、文档不变量 35/35、文档审查 18/18、契约符合性 44/44、前端契约 25/25、套件卫生 4/4，全部 exit 0；行尾门禁 `git ls-files --eol` 对本次改动的已跟踪文件**未翻行**。

---
