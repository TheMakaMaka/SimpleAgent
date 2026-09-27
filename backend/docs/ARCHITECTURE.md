# 架构说明

> **同步至 CHANGELOG §34** —— 本文只描述**当前状态**；修复过程见 `CHANGELOG.md`。
>
> 本文说明**分层与为什么这么分**。流程契约细节见 `CYCLE.md`；
> 逐模块签名见 `docs/MODULES.md`；运维操作见 `docs/OPERATIONS.md`。

## 1. 项目定位

**标准工作流，模型可替换。** 这不是某个模型的定制产物。

判断标准很具体：换一个模型接入时，**只应改配置，不应改工作流代码**。
为此项目把「机制」和「策略/数字」严格切开，见 §3。

## 2. 分层图

```
┌─────────────────────────────────────────────────────────────┐
│ 入口层        main.py                                       │
│   POST /run（旧流程，无强制校验）                            │
│   POST /encode（一轮编码流程，有强制校验）                   │
│   GET  /profile（查看生效的模型接入参数）                    │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│ 工作流层（模型无关，不得含任何模型特判）                      │
│                                                             │
│   coding_cycle.py  一轮流程的编排与阶段推进                  │
│   cycle.py         阶段枚举与 CycleReport 契约               │
│   orchestrator.py  主循环：拆解任务 + 验证回流               │
│   worker.py        子循环：用工具完成单个任务                │
│   pipeline.py      门禁：manifest / check / verify 调度       │
│   manifest.py      交付契约：声明 vs 实际                    │
│   symbol_index.py  结构事实：AST 扫描出符号与依赖            │
│   checkpoint.py    回退：git / snapshot 双后端               │
│   memory.py        全局状态 + 验证结论回流                   │
│   context.py       跨层传参（ContextVar）                    │
│   prompts.py       提示词模板                                │
│   task.py          Task / TaskResult / Artifact              │
└───────────────────────────┬─────────────────────────────────┘
                            │ 只依赖结构化协议
┌───────────────────────────▼─────────────────────────────────┐
│ 适配层（可整体替换）                                         │
│   model_profile.py  标准参数入口：标识/能力/预算/耦合         │
│   llm.py            OpenAI 兼容客户端 + JSON 容错            │
│   config.py         角色解析（ORCH / WORKER）                │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│ 工具层（模型可调用）                                         │
│   tools/registry.py  @register 装饰器注册表                  │
│   tools/*.py         18 个工具，按 profile 过滤，见 MODULES 工具清单表 │
└─────────────────────────────────────────────────────────────┘

旁路：storage/session.py（会话落盘）  tests/（单测/基准/诊断）
```

## 3. 职责边界：为什么这么分

核心原则一句话：**机制留在工作流层，数字与策略进适配层。**

| 层 | 放什么 | 不放什么 | 换模型的代价 |
|---|---|---|---|
| 工作流层 | 调度、门禁、状态流转、回退 | 模型名、预算数字、模型措辞习惯 | **零改动** |
| 适配层 | 接入信息、能力声明、预算推导、模型特有补偿 | 流程控制逻辑 | 改配置或换档位 |
| 工具层 | 确定性能力（跑代码、查结构、审查） | 模型相关的容错 | 复用 |

**为什么必须这样切**：一旦把「为了让某个模型跑通」的补丁写进工作流，
换模型后这些补丁就从"帮助"变成"负担"——它们会对新模型误命中，或者成为永不被触发的死代码。
这类代码不会报错，只会静默劣化，是运维时最难查的故障。

所以所有模型自适应都被收拢到 `ModelCoupling`（`core/model_profile.py`），
它是一个**可以整体丢弃**的数据结构。新模型默认走 `DEFAULT_COUPLING`，
即**不做任何补偿**，只依赖结构化协议。

当前 `ModelCoupling` 的实际使用情况（已核对代码）：

| 字段 | 是否被消费 | 说明 |
|---|---|---|
| `plan_hints` | ✅ | `Worker.run` 经 `coupling.looks_like_plan()` 判断 |
| `repair_json` | ✅ | `LLMClient.chat_json` 传给 `extract_json(repair=...)` |
| `error_prefixes` | ❌ **未被消费** | `matches_error_prefix()` 无调用方，仅测试引用 |
| `notes` | ✅ | 仅用于 `/profile` 与 `describe()` 展示 |

> `error_prefixes` 目前是**预留的补偿位**：设计意图是把「错误文本嗅探」从工作流
> 剥离出来，但实际上工作流已改为只信结构化判断 `is_error_result`，
> 所以这个字段没有消费方。详见 `docs/OPERATIONS.md` 的已知不一致清单。

## 4. 一轮编码流程的完整数据流

入口：`POST /encode` → `CodingCycle.run(goal, verify_command)`。

### 4.0 前置（attempt 循环之前，只做一次）

```
① CheckpointManager(prefer="git")
     → 择优选用后端：优先 git（本机已启用），不可用时退化为 snapshot
     → 调用 backend.init()
     → cycle.checkpoint.name ∈ {"git", "snapshot", "none"}
     → 实际后端可查 GET /profile 的 checkpoint_backend.selected
② 基线检查点：checkpoint.commit("[cycle {cycle_id}] baseline")
     → 得到 base_ref，作为所有回退的锚点
③ 若调用方传入 verify_command → _setup_orchestrator()
     → 写入 orchestrator.verify_command 与 orchestrator.pipeline
④ _snapshot_prior_files()
     → 记录 workspace 现有文件到 self._prior_files
```

### 4.1 每次 attempt 的六个环节

| # | 阶段 | 谁执行 | 输入 | 输出 | 门禁条件 | 不通过时 |
|---|---|---|---|---|---|---|
| 1 | PLAN | 模型（Orchestrator） | `goal`（首次）或 `_retry_goal()` 注入失败原因 | `OrchestratorResult{ok, answer, memory, verify_command, declared_files}` | 至少产出 1 条任务记录 | `phase=failed`，continue |
| 2 | **MANIFEST** | **程序** | 编排器声明的 `files` + workspace 实际 `.py` | `Manifest` | 无 `severity=error` 的 violation | 回退 + continue |
| 3 | CHECK | **程序** | 本次 `write_file` 产出的文件列表 | `steps[]` + `passed` | `check_syntax` 全部通过 | 回退 + continue |
| 4 | VERIFY | **程序** | `VerifyCommand` | 读取 `memory.verify_state` | `passed == True` | 回退 + continue |
| 5 | RECORD | **程序** | — | `report.commit` | — | — |
| 6 | FAILED | — | — | `report.error` | — | 进入下一次 attempt |

**顺序要点：MANIFEST 在 CHECK 之前。** 理由：如果该产出的文件压根不存在，
对它做语法检查没有意义；而且缺文件的症状是间接的（`ModuleNotFoundError`），
不如直接指出「计划要产出 X，但 X 不存在」。

### 4.2 PLAN 阶段的内部结构

PLAN 不是一个原子步骤，内部还有两层循环：

```
Orchestrator.run(attempt_goal)            ← 主循环，最多 max_rounds 轮
  for round_idx in range(max_rounds):
      decision = await self._decide(memory)          # 调 LLMClient.chat_json
      ├─ 采集 verify（仅当调用方未指定时采纳模型的）
      ├─ 采集 files（声明清单，后续轮次覆盖）
      ├─ status == "done"    → 返回 ok=True
      ├─ status == "blocked" → 返回 ok=False
      ├─ tasks = _parse_tasks(decision["tasks"])
      ├─ 指纹去重 _should_skip()（同描述成功过 / 失败达 max_same_task 次 → 跳过）
      └─ for task in executable:                      ← 串行执行
             result = await Worker.run(task, context)  ← 子循环，最多 max_steps 步
             memory.record(task, result)
      ↓
      ── 验证回流（见 §6）──
```

Worker 子循环内部按 4 种情况分支（`core/worker.py`）：

| 情况 | 触发条件 | 行为 |
|---|---|---|
| 1 | 返回了 `tool_calls` | 逐个执行工具，结果回灌；有错则 `error_count += 1` |
| 2 | 无 `tool_calls` 但 content 含代码块 | 自动包成 `run_python` 调用执行 |
| 3 | 纯文本且被耦合层判为"计划" | 提示"不要写计划，直接调用工具" |
| 4 | 空响应 | 连续 3 次则判失败（提示 `max_tokens` 可能不足） |

### 4.3 数据流全图

```
/encode {goal, verify_command, max_attempts}
   │
   ▼
CodingCycle ──baseline commit──▶ checkpoint 后端
   │
   ├─▶ Orchestrator.run(goal)
   │      │  system = ORCHESTRATOR_SYSTEM + 可用工具名列表
   │      │  user   = SharedMemory.summary_for_orchestrator()
   │      ▼
   │   LLMClient.chat_json()  ──▶ 模型
   │      │  extract_json(repair=coupling.repair_json)
   │      ▼
   │   decision{status, reasoning, files, tasks[], verify, final_answer}
   │      │
   │      ├─ files  ──▶ context.set_declared_files()  ──▶ MANIFEST 阶段读取
   │      ├─ verify ──▶ memory.verify_state（经 pipeline.run_verify）
   │      └─ tasks  ──▶ Worker.run(task, context)
   │                        │  tools = tool_schemas()（全量 16 个）
   │                        ▼
   │                     LLMClient.chat(tools=...) ──▶ 模型
   │                        │  tool_calls ──▶ TOOLS_MAP[name]["function"]
   │                        ▼
   │                     TaskResult{ok, output, artifacts, error, steps_used}
   │                        │
   │                        └─▶ SharedMemory.record()
   │                               └─ artifacts[kind=="file"] ──▶ touched_files
   │
   ├─▶ pipeline.run_manifest()   ──▶ Manifest{declared, actual, violations}
   ├─▶ pipeline.run_check(touched) ──▶ {passed, steps, blocking_file}
   ├─▶ report.verify ◀── memory.verify_state
   └─▶ 全通过 → checkpoint.commit() → report.commit
```

## 5. 三类校验的区分（最容易混淆的点）

项目里有**三套**看起来都在"检查代码"的东西，职责完全不同，**不可互相替代**：

| | ① 门禁 CheckPipeline | ② 建议 `review_code` | ③ manifest |
|---|---|---|---|
| 文件 | `core/pipeline.py` | `tools/quality.py` | `core/manifest.py` |
| 调度方 | **程序**，模型绕不过 | **模型**，自愿调用 | **程序** |
| 决定 cycle 成败 | ✅ 是 | ❌ 否 | ✅ 是（error 级） |
| 检查对象 | 本次产出的 `.py` 文件 | 模型交给它的任意代码 | 声明清单 vs 实际文件 |
| 检查内容 | `check_syntax` + `run_lint` | 语法 + lint + 静态质量 | 文件是否存在、符号是否存在 |
| 结果去向 | 回退 / 重试 / 判 `failed` | 作为上下文回灌给模型 | 回退 / 重试 / 判 `failed` |

**为什么不能合并**：

- 门禁若可被模型绕过就失去意义 → 所以门禁必须由程序调度。
- 审查若升级成门禁，就会把"风格建议"（如缺少返回注解、行超 120 字符）
  变成"成败判据"，会误杀大量本可通过的任务。
- manifest 判的是**交付事实**（文件/符号在不在），审查判的是**代码质量**，
  两者错一个层级：一个文件可以质量很差但确实存在。

②的返回体里明确带 `note: "这是建议性审查，不参与 cycle 成败判定"`，
避免模型误以为它能替代验证。

## 6. 验证结论回流机制

### 6.1 为什么需要

早期实现里验证只在编排循环**结束后**跑一次。结果是主循环在循环内部
**不知道目标有没有达成**，只能靠猜，于是反复制造"再运行一遍确认一下"的任务，
直到耗尽 `max_rounds`。

实测证据：同一个"运行并检查输出"的动作被重复 5 次；
两次尝试合计 17 个任务、109.2 秒，而有效工作只是写一个 6 行文件。

改造后同一任务：**1 个任务、6.6 秒**通过。

### 6.2 怎么工作

```
每轮任务执行完
   │
   ├─ files = _files_to_verify(memory, baseline_files)
   │     └─ 无文件产物则本轮不验证（没东西可验）
   │
   ├─ fp = _verify_fingerprint(verify_command, files)
   │     └─ = sha1(command + "|" + 排序后的文件列表)[:16]
   │
   ├─ if memory.already_verified_at(fp): 跳过
   │
   ├─ vr = await pipeline.run_verify(VerifyCommand(...))
   ├─ memory.set_verify(passed, detail, command, fingerprint)
   │
   └─ if vr.passed: 立刻 return ok=True（不再规划任何新任务）
```

结论在下一轮 prompt 的**最末尾**渲染成「【验证结论】」段落
（`SharedMemory.summary_for_orchestrator`）——放最后是因为那是模型
下一步行动的直接依据。通过时明确命令它返回 `status=done`；
未通过时注入结构化错误（`error_type: message`）引导定向修复。

### 6.3 `verify_fingerprint` 的作用

指纹 **只与「验什么」有关、与历史任务无关**（命令 + 待验证文件），
所以主循环重复制造同一个验证任务时不会重复触发验证。

它同时缓解了 `_should_skip` 指纹去重失效的问题：实测中模型会把同一个动作
换一种措辞再提一次（"运行并检查输出" / "验证函数的结果" / …），
任务指纹认为它们是不同任务，但验证指纹会拦住重复验证。

### 6.4 `already_verified_at` 的双重条件

```python
return bool(self.verify_state) and self._verified_fingerprint == fingerprint
```

必须同时要求「指纹相同」**且**「本次已得出过结论」。后者用于区分
「本 attempt 内已验过」与「上一次 attempt 留下的陈旧结论」——
每个 attempt 会新建 `SharedMemory`，不应继承上一轮的验证结果。

## 7. 回退机制

### 7.1 双后端

`CheckpointManager(prefer="git")` 按优先级探活并选用第一个可用后端：

| 后端 | `name` | 可用条件 | 能力 |
|---|---|---|---|
| `GitBackend` | `"git"` | `git --version` 返回 0 | 完整：diff / log / 分支 / 精确回退 |
| `FileSnapshotBackend` | `"snapshot"` | 永远可用（兜底） | 文件级快照 + 文件清单，能回退，**无 diff** |

都没有时为 `"none"`，`CodingCycle` 会打印
`[警告] 无可用检查点后端，本次运行无法回退。`

**当前部署实际走 `git`**（实测 git 2.55.0，提交/回退/历史均正常）。
查询实际后端：`GET /profile` 的 `checkpoint_backend.selected`。

> 两个环境坑已在 `core/checkpoint.py` 处理，见 `docs/CHANGELOG.md` §7：
> ① Git 安装后**已打开的进程 PATH 不会刷新**，故 `resolve_git()` 会回退到常见安装目录；
> ② 仓库属主与当前用户不一致时 Git ≥2.35.2 会拒绝操作，
> `_run_git` 统一加 `-c safe.directory=<cwd>` 放行（不污染用户全局配置）。

### 7.1.1 回退的副作用（务必知道）

`GitBackend.rollback()` = `git reset --hard <ref>` + `git clean -fd`。
后半句会删掉 workspace 里**所有未跟踪文件**，包括手动放进去的。
执行前会先 dry-run 列出将被删除的文件并打印警告。

**注意 `clean -fd` 不加 `-x`，所以不会删被忽略的文件** ——
`.gitignore` 覆盖的 `_tmp/` `_debug/` 是安全的。已实测确认。

### 7.2 每 cycle 一个检查点

| 时机 | 动作 |
|---|---|
| cycle 开始 | `commit("[cycle {id}] baseline")` → `base_ref` |
| 校验失败且还有 attempt | `rollback(base_ref)`，置 `report.rolled_back = True` |
| 全部通过 | `commit("[cycle {id}] {goal[:60]} (attempt N)")` → `report.commit` |

失败路径**不打正式检查点**，所以 `report.commit is None` 是"本 cycle 未通过"的
可靠标志之一。

### 7.3 为什么 git 命令不能交给模型

两条纪律（`core/checkpoint.py` 模块头）：

1. **git 命令绝不出现在模型可见的工具里。** 工具清单里没有任何 git 工具。
   模型只能"申请检查点"（由程序在固定时机自动提交），
   具体命令由代码生成——模型对 `reset --hard` 的语义理解不可靠，
   用错就是不可恢复的数据丢失。
2. **后端可插拔**，回退能力不因环境缺失而消失。

补充实现细节：`GitBackend.init()` 会写入本地身份
（`user.name="SimpleAgent2 Bot"`、`user.email="agent@localhost"`、`core.autocrlf=false`），
不依赖全局 git config；若 workspace 下无 `.gitignore` 则生成一个，
内容为 `_tmp/` `_debug/` `__pycache__/` `*.pyc`。

`GitBackend.rollback()` 执行 `reset --hard <ref>` 后再 `clean -fd`。
⚠️ `clean -fd` 会删除未跟踪文件，这是有意为之（让回退彻底），
但意味着未提交的自建文件也会被清掉。

## 8. 不可动摇的三条纪律

从 `CYCLE.md` 提炼，完整论述见对应章节：

| # | 纪律 | 违反后果 | 出处 |
|---|---|---|---|
| 1 | **验收标准不可被模型改写** | 被考核方定义什么叫对，整个校验层失去意义 | `CYCLE.md` §2.2 |
| 2 | **结构事实不许模型改** | 模型读到自己的过时文档，更确信一切正常 | `CYCLE.md` §10.2 |
| 3 | **审查角色不得有自由否决权** | 换成"模型说不行就不行"，等价于纪律 1 换个形式重来 | `CYCLE.md` §11.3 |

纪律 1 的落地：`Orchestrator.run` 中 `caller_verify = bool(self.verify_command)`，
只有在调用方**没有**提供验收标准时才采纳模型自拟的 `verify`。
实测踩过的坑：模型曾把断言改写成
`assert isinstance(factorial(-1), ValueError)`——一个永远不可能成立的断言，
导致实现正确也判失败。

纪律 2 的落地：`symbol_index.py` 只用 AST 扫描产出结构事实，
明确不使用 grep 或正则匹配代码（避免把字符串里的内容误判为真实符号）。
设计注记（职责/扩展点）目前**尚未实现**，见 `CYCLE.md` §10.2 表格的"设计意图（后续）"列。

纪律 3 目前是**设计约束**，审查角色尚未实现，见 `CYCLE.md` §11。

## 9. 已实现 / 计划中

| 能力 | 状态 | 位置 |
|---|---|---|
| 一轮编码流程 + 五阶段门禁 | ✅ 已实现 | `core/coding_cycle.py`、`core/cycle.py` |
| 验证结论回流 | ✅ 已实现 | `core/orchestrator.py`、`core/memory.py` |
| 文件清单 manifest | ✅ 已实现 | `core/manifest.py`、`core/symbol_index.py` |
| 架构视图工具 | ✅ 已实现 | `tools/arch.py`（`get_architecture`/`get_module`/`find_symbol`） |
| 代码质量审查工具 | ✅ 已实现 | `tools/quality.py`（`review_code`） |
| 回退（git / snapshot） | ✅ 已实现 | `core/checkpoint.py` |
| 会话落盘 | ✅ 已实现 | `storage/session.py` |
| 模型接入标准参数入口 | ✅ 已实现 | `core/model_profile.py`、`core/config.py` |
| 工具插件化（`profiles` 过滤） | ✅ 已实现 | `tools/registry.py`（`coding` 15 / `general` 4） |
| 结构化上下文压缩（快照回流 prompt） | ✅ 已实现 | `core/compress.py`、`core/memory.py`、`CodingCycle._structured_context()` |
| 技能沉淀与回放 | ✅ 已实现 | `core/skills.py`、`core/skill_runner.py` |
| 候选包审计与晋升（含 staging 副本） | ✅ 已实现 | `core/package.py`、`core/promote.py`、`core/shape.py` |
| 远程人工决策（含手机审批页） | ✅ 已实现 | `core/decisions.py`、`core/notify.py`、`web/decisions.py` |
| 反思分析器（6 个检测器） | ✅ 已实现 | `core/reflect.py`、`tools/reflect.py` |
| 版本备份机制 | ✅ 已实现 | `tests/backup.py`、`docs/VERSIONS.md` |
| 上游→前端兼容契约（声明 + 自扫描） | ✅ 已实现 | `core/contract.py`、`docs/FRONTEND_CONTRACT.md` |
| 多模态接口（已预留，未启用） | ⚠️ 接口就绪 | `core/vision.py`、`core/model_profile.py` |
| 工具 `risk` / `stage` 声明 | ❌ 计划中 | 见 `CYCLE.md` §9 |
| 存储抽象 / 数据库接口 | ❌ 计划中（只留 Protocol） | 见 `CYCLE.md` §9 |
| 审查 / 架构跟踪角色（语义层） | ❌ 计划中 | 见 `CYCLE.md` §11 |
| 设计注记层 | ❌ 计划中 | 见 `CYCLE.md` §10.2 |
