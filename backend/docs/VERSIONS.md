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
