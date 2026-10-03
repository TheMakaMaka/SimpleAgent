# 修复记录（CHANGELOG）

**本文件只记「修复过程」，不是当前状态的来源。**
当前状态请查 `README.md`、`docs/ARCHITECTURE.md`、`docs/MODULES.md`、
`docs/OPERATIONS.md`——**上游文档只描述现状，不含"已修复"条目**。

这条分工是刻意的，因为早期版本写反了：本文件曾声称"以本文件为最新状态"，
结果上游文档里残留的旧描述与这里互相矛盾，而**读文档的人不会先来看 CHANGELOG**。

因此约定：

| 文件 | 记什么 |
|---|---|
| 上游文档（README / ARCHITECTURE / MODULES / OPERATIONS） | **只有当前状态**。"已知限制"里只列**尚未修复**的 |
| 本文件 | 修复的**过程、原因、验证方式**；修复完成后从上游删掉对应条目 |

每条修复都必须能指出一个**可复现的验证命令**。没有验证方式的不写入。

---

## 1. `fetch_url` 内网拦截失效（安全项）—— ✅ 已修复

**发现**：`backend/tools/net.py` 中

```python
try:
    ip = ipaddress.ip_address(host)
    if ip.is_private or ip.is_loopback or ...:
        raise ValueError("禁止访问内网地址")   # ← 这个 raise
except ValueError:
    pass                                       # ← 被这里吞掉
```

`ipaddress` 对**域名**抛 `ValueError`（正常），但**私有 IP** 也抛 `ValueError`。
两者共用一个 `except`，导致安全判断被自己的异常处理吞掉。

**实测（修复前）**：`127.0.0.1` / `10.0.0.5` / `169.254.169.254` 全部 **ALLOWED**，
只有 `localhost` 靠另一行的显式判断侥幸拦住。

**修复**：`try` 只包住 `ipaddress.ip_address(host)` 这一步，把「不是 IP 字面量」
与「是私有 IP」两种 `ValueError` 分开处理。同时补齐 `.localhost` 后缀、
末尾点号、`0.0.0.0`、IPv6 回环/link-local、组播等情形。

**验证**：`python tests/unit/test_net_guard.py` —— 20 个用例全过，含 6 项关键回归。

**残余风险（未修）**：DNS rebinding / TOCTOU——域名在校验时解析为公网、
请求时被重新解析到内网，本层拦不住。彻底防护需在传输层做 peer-IP 校验。
**暴露到公网前必须补上。**

---

## 2. `PHASE_ORDER` 定义了但零消费方 —— ✅ 已修复

**发现**：`backend/core/cycle.py` 定义 `PHASE_ORDER` 并注释「CHECK 未通过时不允许进入
VERIFY」，但全仓库唯一引用就是定义处。实际阶段推进是 `CodingCycle.run` 里
硬编码的——**注释宣称的约束不由它保证，改这个常量不会生效**。

声明了却不兑现的约束，比不写更危险。

**修复**：`CycleReport.enter()` 现在调用 `is_valid_transition()`：
- 除 `FAILED` 外，阶段必须沿 `PHASE_ORDER` **恰好前进一步**，不得跳跃或倒退
- `FAILED` 可从任意阶段进入，之后只能重新回到 `PLAN`
- 已在 `PLAN` 时重复进入 `PLAN` 视为重启本轮（多次重试会走到这里）
- 非法推直抛 `ValueError`，带明确的合法顺序提示

顺带修正了 `CodingCycle.run` 的阶段顺序：manifest 阻塞时原先会
`PLAN → CHECK` 跳级，现在统一为 `PLAN → WRITE → (manifest) → CHECK`。

**验证**：`python tests/unit/test_phase_order.py` —— 8 项全过，
含「越级被拦」「跳过 CHECK 被拦」「倒退被拦」「多次重试不误报」。

---

## 3. 一批配置项「存了不用」—— ✅ 已处理

**发现**：以下字段在代码里可读可写、却没有消费方，会给人「可调」错觉：

| 字段 | 原状态 | 处理 |
|---|---|---|
| `ModelLimits.debug_head_chars` | 推导出但无人读取 | **删除** |
| `ModelLimits.verify_output_chars` | 推导出但无人读取 | **删除** |
| `ModelCoupling.error_prefixes` / `matches_error_prefix()` | 仅测试引用 | **保留并注明为预留**（见 `model_profile.py` 注释） |
| `CheckPipeline.verify_timeout` | 存了不用 | **保留并注明**：实际超时来自 `backend/tools/verify.py` 的 `TIMEOUT_SECONDS` |
| `VerifyCommand.expect_exit` | 死参数 | **接线**：现传入 `check_and_run(expect_exit=...)`，支持「期望非零退出」的验收 |
| `check_manifest(strict_extra_files)` | 默认 False 从未覆盖 → `unexpected-file` 是死分支 | **接线**：`CheckPipeline.run_manifest()` 默认 `True`，声明外的多余 .py 会列为 warning |

**验证**：
- `python tests/unit/test_adapter.py`（预算推导不再包含已删字段）
- `python tests/unit/test_manifest.py`（manifest 判定）
- `python tests/unit/test_cycle_manifest.py`（manifest 接入 CHECK 阶段）

---

## 4. `.env` 不自动加载 —— ✅ 已修复

**发现**：`.env.example` 存在、`python-dotenv` 已安装，但全仓库无 `load_dotenv()`
调用。照抄模板后配置**不生效**，且没有任何提示——运维极易踩。

**修复**：`backend/main.py` 启动时加载仓库根目录的 `.env`（在读取任何 `ORCH_*`/`WORKER_*`
之前执行）。未安装 `python-dotenv` 时静默降级为「只用环境变量」。

> 注意：测试与诊断脚本**不走** `backend/main.py`，它们仍通过环境变量或内置默认值配置。
> 需要给它们配 `.env` 时，请在 shell 里导出变量。

**验证**：`python -c "import main"` 无异常；写入 `.env` 后
`GET /profile` 应反映其中的配置。

---

## 5. `CYCLE.md` 章节编号重复 —— ✅ 已修复

**发现**：出现两个 `## 9`（「尚未完成」与「文件清单」），后续章节与
交叉引用（§9.2、§10.3、§11）全部错位。

**修复**：重排为 §1–§12，并同步修正子章节编号与全部「见 §X」引用。

**验证**：`Select-String -Path CYCLE.md -Pattern '^#{2,3} \d'` 应无重号；
所有「见 §X」都能在标题中找到对应。

---

## 6. `context_window` 被静默抬升 —— ✅ 已修复

**发现**：`ModelProfile.__post_init__` 会把用户配置的 `context_window`
抬高到至少 `max_tokens`，但**不告知**。结果是 `/profile` 显示的值与
`.env` 里配的值不一致，排查时容易怀疑人生。

**修复**：抬升时在 stderr 打印一行说明（配置值 → 实际值 → 原因），
保留自动修正行为但让它可见。

**验证**：设置 `ORCH_CONTEXT_WINDOW=1024` 启动，应看到提示行。

---

## 7. git 回退后端未真正接管 —— ✅ 已修复

**发现**：系统装了 git（2.55.0），但 `CheckpointManager` 仍选中 `snapshot`。
排查出**两个独立原因**：

**(a) 进程 PATH 未刷新。** Git 安装只更新注册表，已打开的终端/进程看不到
`C:\Program Files\Git\cmd`，于是 `shutil.which("git")` 返回 None。
`_run_git` 捕获 `FileNotFoundError` 后静默降级，界面上看不出任何异常。

**修复**：新增 `resolve_git()`，按「PATH → 常见安装目录」顺序定位并缓存结果；
POSIX 与 Windows 路径都覆盖。`/profile` 的 `checkpoint_backend.git` 会显示
`executable` / `from_path` / `note`，明确告知是否走了回退路径。

**(b) Git 的 dubious ownership 防护。** 仓库属主与当前进程用户不一致时，
Git ≥ 2.35.2（CVE-2022-24765 的修复）会**拒绝所有操作**：

```
fatal: detected dubious ownership in repository at '.../workspace'
```

**修复**：`_run_git` 统一加命令行级 `-c safe.directory=<cwd>`。
选它而不是 `git config --global --add safe.directory`，是因为后者会**污染用户全局
配置**；命令行级只影响本次调用。

**附带修复**：`commit()` / `_has_changes()` 原先吞掉 git 的 stderr 直接返回
`None`/`False`，导致回退机制「看起来启用了其实没工作」。现在失败时打印 stderr。
`commit()` 还补上了「仓库尚无任何提交」时用 `--allow-empty` 建初始提交。

**验证**：`python tests/unit/test_git_backend.py` —— 11 项全过，含
真实提交历史、回退后 HEAD 与工作区状态、`_tmp/_debug` 未被追踪、无改动提交幂等。

**端到端**：`python tests/bench/run_levels.py 1 1` 返回真实 SHA，
`data/workspace` 里可读到 `[cycle …] baseline` 与 `[cycle …] 创建 add.py` 两条提交。

> ⚠️ 测试里**不要裸调 git**。Git 的 ownership 防护会让裸调用失败，
> 而 backend 已放行——裸调会得到与真实行为不符的假失败。
> 请复用 `core.checkpoint._run_git`。

---

## 8. `run_lint` 永远 skipped（ruff 装了也不生效）—— ✅ 已修复

**发现**：装了 ruff 后 `run_lint` 仍返回 `skipped: "ruff not installed"`。
根因与 §7 的 git 问题**同源**：`shutil.which("ruff")` 在**当前进程 PATH** 里找不到，
而 ruff 装在 venv 的 `Scripts/` 目录下——服务/IDE/CI 进程都可能如此。

**修复**：新增 `resolve_ruff()`，按「当前解释器同目录 → PATH → 常见安装位置」定位。
优先查解释器同目录是有意的：ruff 通常就装在跑它的那个环境里。

**验证**：

```
python -c "from tools.code_checks import resolve_ruff; print(resolve_ruff())"
# → D:\...\.venv\Scripts\ruff.exe
```

对有问题的代码应报出真实 issue（实测 `I001` + 两个 `F401`），干净代码返回 `ok: true`。
端到端事件流里能看到 `lint status=passed`（此前恒为 `skipped`）。

> 这说明 CHECK 阶段现在是**语法 + lint 双门禁**，lint 不再是空转。

---

## 9. 新增存储层与结构化压缩 —— ✅ 已落地

**目标**：为「上下文压缩」「架构跟踪角色」提供原料，同时避免把压缩交给模型
自由生成（那会新增幻觉源，并把错误固化）。

**新增文件**：

| 文件 | 职责 |
|---|---|
| `backend/storage/store.py` | `Storage` Protocol + `FileStorage`（JSONL 事件 + JSON 快照） |
| `backend/core/compress.py` | `reduce_cycle` / `reduce_all` / `cross_cycle_failures` |

**核心纪律（写在 `backend/core/compress.py` 模块 docstring 里）**：

> 压缩的输入只能是被程序校验过的结果，不能是模型的自由摘要。

每个事实带 `source`（可回溯到哪条事件）与 `confidence`：

| confidence | 来源 | 能否作判据 |
|---|---|---|
| `verified` | verify 退出码 / manifest 文件与符号实测 / syntax / lint | 能 |
| `declared` | 计划声明（意图，不是现实） | 否 |
| `assumed` | 模型自述（任务 output 摘要） | **绝不能** |

未登记的来源一律兜底为 `assumed`——**安全默认**。

**可替换性已验证**：测试里用一个 `MemoryStorage` 替换文件实现，
`isinstance(ms, Storage)` 成立，且两种实现产出的压缩结果**逐字段一致**
（证明压缩与存储形态无关，将来接数据库只需换实现）。

**存储是旁路**：`CodingCycle._emit` 内兜住所有异常——存储写失败**绝不能**
让 cycle 失败。

---

## 10. 远程人工决策 —— ✅ 已落地

**需求**：决策流不必一直盯着，可以从手机输入决策并继续。

### 先说的实话：QQ/微信走不通

| 通道 | 双向 bot 能力 | 结论 |
|---|---|---|
| 个人微信 | 官方**无** API；第三方方案基于逆向/hook，**违反用户协议**、封号风险高 | ❌ |
| 个人 QQ | 官方 bot 平台需企业/组织资质审核 | ❌ |
| 企业微信 | 有正规 API，但需企业/组织才能注册 | ⚠️ |
| **钉钉** | 群自定义机器人 webhook，**个人可用、免费** | ✅ 唯一能正规落地 |

### 绕开限制：推送通知 + 链接跳转审批

交互式审批放在**网页**里，IM 只负责「发一条带链接的消息」：

```
验证连续失败 2 次
  → 钉钉推送：「⚠ 需要你决策… [👉 点击查看并决策]」
  → 手机点开审批页（渲染结构化上下文 + 按钮）
  → 点「再试一次」→ 决策写入队列 → cycle 继续
```

好处是**不绑定任何平台**：新平台只需实现 `backend/core/notify.py` 的一个 `Notifier`。
审批页还能直接渲染已有的结构化快照（计划声明 / 验证失败细节 / 清单问题），
这是聊天消息做不到的。

### 分层

| 层 | 文件 | 职责 |
|---|---|---|
| 决策层 | `backend/core/decisions.py` | 与通道无关：数据模型、状态机、持久化、超时策略 |
| 投递层 | `backend/core/notify.py` | 可插拔：Console / DingTalk / Webhook(企业微信·Slack) |
| 审批页 | `backend/web/decisions.py` | 手机端交互（无外部依赖，离线可用） |

### 决策点只设两处

| 位置 | 触发 | 为什么值得停 |
|---|---|---|
| `repeated_failure` | 验证连续失败达阈值 | 「模型能力不够」的信号，需要人拍板 |
| `risky_rollback` | 回退会覆盖已有文件前 | 回退会丢改动，属有风险动作 |

**程序能判定的确定性事实（清单缺失、语法错误）不会打扰你**——那是客观事实，
不该占用人的注意力。

### 超时 fail-safe

| 决策类型 | 超时默认 | 理由 |
|---|---|---|
| `risky_rollback` | `abort` | 不覆盖已有文件 |
| `repeated_failure` | `stop` | 停止而不是空转烧预算 |

### 关键设计：跨进程作答

`_wait_for_answer` 用**文件轮询**而非内存 `Future`，使
「CLI 跑 cycle + Web 服务接收作答」两个进程能协作成立。
**推送失败时不等待**——推不出去就没人会作答，等待只会挂死。

### 验证

| 测试 | 项数 | 覆盖 |
|---|---|---|
| `tests/unit/test_decisions.py` | 30 | 生命周期、非法作答拦截、超时 fail-safe、通道退化、**跨实例作答→恢复** |
| `tests/unit/test_approval_web.py` | 23 | 页面渲染、结构化上下文、按钮、非法选项 400、404、令牌 403/200 |

最关键一项：后台线程用**另一个 `DecisionManager` 实例**作答，
主线程阻塞等待后正确恢复并采用人的选择（实测等待 2.0s）。

### 安全

- 默认无鉴权，适合局域网自用；设 `AGENT_APPROVAL_TOKEN` 后接口要求 `?t=<token>`
- webhook 与 token 只从环境变量读，**已加入 `.gitignore`**（`data/storage_data/`、`.env`）
- 作答只接受选项列表内的值，防止前端被绕过时注入任意动作

### 已知限制

- **手机需能访问审批页**。局域网内可直接用；出门在外需内网穿透（cloudflared/ngrok）
- **`on_decision=wait` 会阻塞一个请求线程**。个人自用可接受；要做成生产级
  需把 cycle 改为后台任务 + 真正的持久化状态恢复（当前依赖进程存活）
- 钉钉通道**只验证了加签 URL 生成与载荷构造，未实测真实推送**（无真实 webhook）

---

**尚未修复（明确记录）**：

| 项 | 说明 |
|---|---|
| **DNS rebinding** | 见 §1 残余风险。需传输层 peer-IP 校验 |
| **`facts` 机制未接线** | `SharedMemory.add_fact` 仍无调用方。注意它与 `compress` 的 facts **不是一回事**：后者是压缩产物，前者是运行期内存字段 |
| **压缩快照尚未回流进 prompt** | `Snapshot.to_prompt()` 已可用且有测试，但 `CodingCycle` 还没把它注入编排器/执行器上下文。这是下一步 |
| **数据库实现未落地** | 按计划只留 Protocol；已验证抽象可替换，真接数据库时另做 |
| **`manifest.to_prompt()` 未被工作流使用** | `CodingCycle` 自建了重试提示格式，两处逻辑并存，可考虑统一 |
| **`get_weather` 是占位实现** | 恒返回「晴朗 22°C」，却注册为模型可见工具 |
| **工具全量下发** | 16 个工具无过滤地下发给子循环，`tool_hint` 无强制力。计划中的插件化会补 `stage`/`visible_to` |
| **上下文按条数截断** | `summary_for_orchestrator` 仍按条数截断；结构化快照已就绪但未接入 |
| **子任务串行执行** | 多任务延迟线性叠加，未在计划中 |

---

## 11. 反思分析器（自我反思的第一步）—— ✅ 已落地

**需求**：让 agent 具备"自我反思、分析问题"的能力，代替人的一部分职责
（发现反复出现的问题、建议改什么）。

### 为什么先做"程序统计版"

反思的质量上限由**原料**决定。若让模型"回顾刚才发生了什么"，它会基于
**自己的记忆**反思——而模型对自身行为的记忆极不可靠。本项目实测：
模型声称建了 3 个文件，实际只建了 1 个（L8）。

所以第一版**完全不用模型**：从事件流与 `Snapshot` 做统计，产出结构化模式 + 证据。

### 核心纪律：只用 verified 事实

每个检测器**只读程序校验过的结果**（verify / syntax / lint / manifest / rollback）。
模型自述（`confidence=assumed`）唯一被引用的地方是 `detect_false_claims`，
且只用于**指出矛盾**。这是从构造上杜绝幻觉，而不是靠提示词约束。

### 六个检测器

| 检测器 | 发现什么 | 置信度 |
|---|---|---|
| `repeated_failure` | 同一 `reason_hash` 跨 cycle 反复出现 → 系统性 | high（≥3 cycle） |
| `false_claim` | **模型声称成功但验证未通过** | high |
| `failure_cluster` | 失败集中在同一文件 | medium |
| `retry_hotspot` | 尝试次数高仍未通过 | medium |
| `manifest_gap` | 交付清单缺口重复出现 | medium |
| `budget_exhaustion` | 命中轮次/步数上限 | medium |

### 边界（刻意设计）

- **只产出建议，绝不自动应用**。「建议」与「执行修改」分离是关键：
  一个会自己改自己 prompt 的 agent，最大风险不是改坏，而是**改得看不出好坏**。
- **不参与成败判定**：不影响 `phase`，只影响人（或下一次规划）看到什么。
- 每条模式**必须带证据**，指向具体事件（`cycle#seq`）。解析不出位置时只显示
  cycle —— **不渲染成 `#0`**，那看起来像精确位置，实际是编的。

### 对外接口

| 入口 | 用途 |
|---|---|
| `GET /reflect?limit_cycles=20` | 结构化 patterns + 可直接读的 markdown |
| 工具 `reflect_on_history` | 模型可在规划前自查历史模式（共 17 个工具） |
| `core.reflect.reflect(events)` | 纯函数，供测试与离线分析 |

### 验证

`tests/unit/test_reflect.py` **23/23**：六个检测器各自命中、假成功标为 high、
每条模式都有证据、不采信模型自述、空输入不崩、全成功时不误报、
**单检测器崩溃被隔离**（不会让整份反思为空）。

### 真实数据端到端验证

跑 L1（成功）+ L2（失败）后，对真实事件流反思：

```text
cycles: 2 | patterns: 1 | by_confidence: high=1, medium=0, low=0

模型声称成功，但验证未通过   [high]
  出现次数：5（涉及 1 个 cycle）
  证据：cy_20260925_213201#19, ...#11, ...#12, ...#13
```

**它自主发现了我们最早人肉才找到的那个致命缺陷**：L2 里模型声称成功 5 次、
验证始终没过。现在由程序自动量化，不需要人看日志。

### 下一步（未做，需确认）

- **受控迭代**：反思产出 `ImprovementProposal` → 应用 → 跑基准 → 对比基线 →
  保留或回滚。护栏：每次只改一项，且必须证明"改后比改前好"。**当前刻意未实现**。
- **模型参与的反思**：两阶段（统计筛候选 → 模型归因），能发现语义模式，
  但引入幻觉风险，需先定证据约束。
- **跨 session 视角**：目前只分析本地 `data/storage_data`。

---

## 12. 技能：稳定流程封装成固定调用链路 —— ✅ 已落地

**需求**：某类代码生成流程已经稳定，把它打包成固定调用链路，不必每次让模型重新规划。

### 核心洞察：技能就是「预先烘焙的计划」

`CodingCycle.run()` 只要求 orchestrator 有 `run(goal)` 并返回 `OrchestratorResult`。
所以固定链路**不需要新增旁路**——实现同一个接口（`SkillRunner`），
就能复用全部既有机制：manifest 校验、语法/lint 门禁、验证回流、回退、
事件存储、人工决策。

这比另写一条执行路径安全得多：**功能不会因为走"快捷通道"而绕过门禁**。

```
普通流程：模型 PLAN（1 次 LLM） → 模型执行（N 次 LLM）
技能重放：读技能（0 次 LLM）   → 模型执行（N 次 LLM）
```

省掉的是**规划那一步**，不是执行。执行仍由模型按参数生成代码，因此仍需实测。

### 数据结构

| 层 | 作用 |
|---|---|
| `SkillParameter` | 变化的部分（函数名、文件名…） |
| `SkillFile` | 产出契约：路径模板 + 必须有符号 |
| `Skill` | 整条链路：文件 + 验证模板 + 参数 + 参考实现 |
| `SkillStore` | 落盘、检索、使用统计 |

占位符 `{name}` 可出现在**目标、文件路径、符号名、验证命令**里；
`validate()` 会拦住"用了未声明的参数"这类坏定义。

### 三条纪律

1. **只有验证通过的 cycle 才能被提升** —— `promote_from_report()` 强制检查
   `phase == "record"` + verify 通过 + 有声明清单。未验证的流程不是"稳定流程"，
   封装它等于**批量复制不确定性**。
2. **重放仍过全部门禁** —— 技能记录的是"曾经成功过"，不是"永远正确"。
   实测：少写文件 → 判失败；验证不过 → 判失败。
3. **参考实现不作为直接复制产物** —— 任务说明里明确写"参数已变化，不要照抄"。

### 技能是资产，不是遥测

默认落在 `data/storage_data/skills/`，但性质与其它 `data/storage_data/` 内容不同：
其它是运行遥测（可随时删），技能**需要备份与版本管理**。

因此 `.gitignore` 对它做了例外。这里踩了个坑：
**`!storage_data/skills/` 单独写不生效**（父目录被排除后 git 不会进入它），
而 `!storage_data/` 又会把 snapshots 一并放进来。正确写法是三步：

```gitignore
!storage_data/          # 先重新包含父目录
storage_data/*          # 再排除其余内容
!storage_data/skills/   # 最后放行技能目录
```

已加验证：技能入库、`snapshots/` 与 `events.jsonl` 仍被忽略、`.env` 仍被挡住。

### 对外接口

| 入口 | 用途 |
|---|---|
| `GET /skills` | 列出技能（含 uses/successes 成功率、problems 校验结果） |
| `POST /skills/{id}/replay` | 按固定链路重放，**仍走完整门禁**，结束后回写统计 |
| `core.skills.promote_from_report()` | 从成功 cycle 提升（带闸门） |
| `core.skill_runner.SkillRunner` | 作为 Orchestrator 的替代实现 |

### 验证

`tests/unit/test_skills.py` **46/46**：

- 技能定义校验（未声明参数 / 缺 verify / 无产出文件 / 缺必填参数，全部拦截）
- 模板渲染（路径、符号、验证命令；未知占位符保留原样）
- **与 CodingCycle 集成**：正向通过全部门禁；少写文件被判失败；验证不过被判失败
- 提升闸门：未通过 / verify 失败 / 无清单 / 缺参数声明，四种情况全部拒绝
- 参考实现 `example` **从磁盘读取**（worker 的 file artifact 只存路径不存内容）
- 使用统计回写（`describe()` 显示成功率）

### 尚未做

- **自动参数识别**：单次运行无法知道"哪些部分可变"，目前参数由调用方命名。
  要做需对比多次成功运行、diff 出变化点。
- **技能失效检测**：代码演进后旧技能可能过时，尚无检测。
- **技能推荐**：目前靠人指定 skill_id，还没做"根据目标自动匹配已有技能"。

---

## 13. 封装优化角色：形态指纹 + 参数识别 + 审核闸门 + 副本机制 —— ✅ 已落地

**需求**："自动参数识别考虑从外部加个角色，专门封装优化的"；
"可以先建立副本，不影响元项目"；"要加个审核机制，怎么算可封装复用"。

### 它是离线分析器，不是运行时角色

| | 运行时角色（编排器/执行器/审查员） | 本角色 |
|---|---|---|
| 作用于 | **活着的 cycle** | **已完成的历史** |
| 输出 | 影响当前执行 | 产出可复用资产 |
| 风险 | 可能污染流程 | 只读历史，**天然安全** |

"先建副本"这条原则正好落在这里：它**不碰运行中的流程**，
只读 `data/storage_data`、只写候选与副本区。

### 四层结构

| 层 | 文件 | 职责 |
|---|---|---|
| 形态指纹 | `backend/core/shape.py` | 判断两次运行是否「同一类任务」 |
| 候选分析 | `backend/core/package.py` | 变化点识别 + 打分 |
| 审核与副本 | `backend/core/promote.py` | 程序判据审核 + 隔离安装 |
| 落点 | `data/storage_data/skill_candidates/`、`skill_staging/` | 候选区 / 副本区（与正式库分开） |

### 关键难点：单次运行识别不出参数

"哪些部分是变量"只有对比**多次同类运行**才知道。单次运行看起来一切固定——
那正是过拟合的来源。所以必须先分组（形态指纹）再 diff（变化点）。

### 形态指纹踩了两次坑（值得记）

指纹的松弛程度极其难调，我改了三次才对：

| 版本 | 做法 | 结果 |
|---|---|---|
| v1 | 抹标识符 + 抹数字 | `fib(10)==55` 与 `factorial(5)==120` 骨架相同 ✓，但**没处理 `[3,1,2]`**，同类因方括号被拆开 ✗ |
| v2 | 只抹标识符、**保留字面量** | 结构区分度上来了，但 `fib(10)==55` 与 `factorial(5)==120` 又分到不同组 ✗ |
| v3 | 标识符→`ID`，字面量→`<int>`/`<str>` | 两者都对 ✓ |

**结论：结构签名要对具体值不敏感，参数提取才用具体值。两级分工。**
另外 v3 顺带修正了一个隐蔽 bug：子串替换会把 `import fib` 与
`assert fib.fib(...)` 里的 `fib` 变成 `{p1}.{p1}`（实为两个不同变量），
改成**词法级重建**后消失。

### 审核闸门是程序判据

| 检查 | 拦截什么 |
|---|---|
| 证据量 ≥ 2 次成功 | 单次运行的过拟合 |
| 分数 ≥ 0.7 | 证据不足（**2 次成功不足以过关**——区分不出"固定形态"与"碰巧相似"） |
| 验证模板完整 | 缺了就无法判定重放成败 |
| 识别出 ≥1 个变量 | 常量流程谈不上复用 |
| 参数已命名 | 自动名 `p1` 没有语义，不能入库 |
| 参数名不重复 | |
| 转成的技能定义自洽 | 残留未替换占位符等 |
| ID 不与正式库冲突 | |

`auto_rename_map()` 按 kind 给出**弱语义建议**（path→filename、symbol→func、
字面量→expected_int），但明确标注"命名可能不准，需人工确认"——
自动命名在一般情形下不可解，本模块不假装能猜对。

### 副本机制（落实"不影响主项目"）

```
候选 --审核闸门--> 副本区 --重放实测--> 正式库
                       └─ 失败则丢弃，正式库不受影响
```

`promote_staging_to_live(proven=...)` 的 `proven` **必须来自真实重放结果**，
不能凭审核分数推断——审核只能筛掉明显不合格的，**不能证明它能跑通**。

### 真实数据验证（暴露了一个典型形态）

对历史运行分析后产出 3 个候选，其中：

```
变量: []
理由: 证据充分：4 次成功运行
      未识别出变量：可能是常量流程，复用价值有限
```

**这是过拟合的教科书形态**：之前测试反复用同一个目标（`实现 add`），
路径/符号/验证命令零变化。审核闸门会拦住它（`识别出至少一个变量` 失败）——
这正说明闸门在起作用，而不是形同虚设。

### 对外接口

| 入口 | 用途 |
|---|---|
| `GET /candidates?analyze_now=1` | 列出候选（含分数、变量、弱语义建议名）。**只读** |
| `POST /candidates/{id}/install` | 审核并装进**副本区**；未过审返回 400 并列出拦截点 |
| `POST /candidates/{id}/promote` | 副本提升到正式库（需 `proven=true`） |

### 验证

`tests/unit/test_package.py` **42/42**：

- 形态指纹：同类归组、异类分开、失败的不参与、列表入参与标量入参分开
- 变化点识别：抽出外壳、多变化段不硬凑、单元素拒绝归纳
- 打分：证据越多分越高、缺模板显著扣分、2 次不达阈值 / 3 次达阈值
- 审核闸门：未命名 / 重名 / ID 冲突 / 单次运行，全部拦截
- **副本机制**：审核通过只进副本、未实测不许提升、实测后提升、丢弃不影响正式库

### 尚未做

- **跨 session 分析**：目前只读本地 `data/storage_data`
- **技能失效检测**：代码演进后旧技能可能过时
- **自动命名**：目前只给弱语义建议，仍需人工确认（这点是刻意的）

---

## 14. 文档漂移治理 + 三项设计修正 —— ✅ 已落地

外部评审发现三类问题，逐条处理如下。

### 14.1 原则错误：CHANGELOG 曾被当成"最新状态来源"

**问题**：本文件开头写过"以本文件为最新状态"。但**读文档的人不会先看 CHANGELOG** ——
结果上游文档里的旧描述与本文件互相矛盾，产生多处硬冲突。

**修复**：把约定反过来。

| 文件 | 记什么 |
|---|---|
| 上游（README / ARCHITECTURE / MODULES / OPERATIONS） | **只有当前状态**。"已知限制"只列**尚未修复**的 |
| 本文件 | 修复的**过程、原因、验证方式**；修完即从上游删掉对应条目 |

已清理的具体矛盾：

| 矛盾 | 修法 |
|---|---|
| `ARCHITECTURE` §4.0 / `OPERATIONS` §9 说回退走 snapshot，实际已是 git | 改为"优先 git，不可用才退化"，并指向 `/profile` 查询 |
| `OPERATIONS` §1.4 说 `.env` 不会自动加载，实际 `backend/main.py` 已 `load_dotenv()` | 重写该节；并补充"测试/诊断脚本不走 main.py，故不加载 .env" |
| `MODULES` §4 标 `PHASE_ORDER (未使用)`，同文件 §19 说已修复 | 改为"不是文档性常量"，补充强制校验说明 |
| `MODULES` §19 标题是"不一致清单"，内容大量是"✅ 已修复" | 重写为**只列当前未修**的清单 |
| `MODULES` §19 还列着 `debug_head_chars` / `verify_output_chars` | 这两字段**代码里已删除**，从文档移除 |
| `MODULES` §17 引用（实际清单在 §19） | 修正编号 |
| `README` / `OPERATIONS` 的"已修复"条目 | 从上游删除，改由本文件承载 |

### 14.2 `resolve_profile` 的两角色假设 —— ✅ 改成显式角色表

**问题**：加 `REVIEW` 角色时会**静默继承编排器模型**，表现为
"以为请了专业审查员，实际还是同一个模型在审自己"，**且不报错**。

**修复**：`backend/core/config.py` 引入显式 `ROLES` 表。未配置的三种走向必须明确：

| 情形 | 行为 |
|---|---|
| 角色表声明了 `inherits_from` | 继承（**只有 worker→orchestrator 这一对**） |
| 角色声明了 `has_builtin_default` | 用内置默认档位（orchestrator/worker） |
| 都没有 | 抛 `RoleNotConfigured`（reviewer / package_optimizer） |

关键区分：**"未配置"≠"未启用"**。orchestrator 有内置默认（ollama+qwen2.5:7b），
它未配置但仍然可用；reviewer 没有默认，未配置就是未启用。

`GET /profile` 的 `roles` 字段如实展示每个角色的 `available` / `source`，
未启用的显示 `available: false, model: null`，**不会伪装成已就绪**。

### 14.3 工具全量下发 —— ✅ 改为 profile 过滤（**不删工具**）

**问题**：17 个工具无过滤下发，`tool_hint` 只是提示文本、无强制力。

**修复**：`backend/tools/registry.py` 的 `register()` 新增 `profiles` 声明；
Worker 按 profile 取 `tool_schemas(profile)`。

| profile | 工具数 | 内容 |
|---|---|---|
| `coding` | 14 | run_python / write_file / check_syntax / review_code / 架构视图 / 反思 … |
| `general` | 4 | get_weather / calculate / fetch_url / get_system_info |

**种子工具全部保留注册**（它们代表未来通用 agent 的能力），
只是在编码 profile 下**不下发**——模型看不到，就不存在"选错"。
比 `tool_hint` 提示硬得多。

编排器的候选工具列表也按同一 profile 过滤，避免建议一个子循环拿不到的工具。

### 14.4 `rollback()` 清除未跟踪文件 —— ✅ 加警告

**问题**：`GitBackend.rollback()` 的 `git clean -fd` 会删掉 workspace 里
**所有未跟踪文件**，包括人手动放进去的，且**无任何提示**。

**修复**：执行前先跑 `git clean -nd`（dry-run）列出将被删除的文件并打印警告。

```
[rollback] 警告：将清除 2 个未跟踪文件（手动放进 workspace 的文件也会被删）: my_notes.md, scratch.py
```

**同时确认了一个容易误解的点**：`clean -fd` 不加 `-x`，**不会删被忽略的文件**。
所以 `_tmp/` `_debug/` 是安全的。已实测：回退后 `_tmp/ignored.txt` 仍然存在。

### 验证

| 测试 | 项数 | 覆盖 |
|---|---|---|
| `tests/unit/test_roles.py` | 14 | 未配置即未启用、只配 ORCH 时 worker 继承而 reviewer 拒绝、显式配置优先、未知角色报错 |
| `tests/unit/test_tool_profiles.py` | 21 | 种子工具仍注册、按 profile 隐藏、Worker 下发集合、编排器视图一致 |

全量 **18/18**；真实 E2E（L1）仍通过，日志可见"已隐藏种子工具"。

---

## 15. 文档漂移第二轮：从"人肉同步"改为"可执行检查" —— ✅ 已落地

第二轮评审又发现四处矛盾。**根因不是某次漏改，而是同步机制本身靠人肉** ——
改了 CHANGELOG 忘了改 MODULES/OPERATIONS，下一轮还会漂。

### 15.1 四处新矛盾（全部修正）

| 项 | 上轮只同步到 | 未同步处 | 修法 |
|---|---|---|---|
| git 后端 | ARCHITECTURE §7.1 | OPERATIONS §4.5 仍写"未安装 git" | **整节改为陈述当前行为**（择优 + 退化 + 查 `/profile`），不再描述环境快照 |
| 角色 fallback | CHANGELOG §14.2 | MODULES §3、OPERATIONS §9 | 改为描述显式角色表与三条走向 |
| 工具数量/profile | CHANGELOG §14.3 | MODULES §17（写 16）、README 项目结构 | §17 **按 profile 分组重写**；README/ARCHITECTURE 数量改为 17 |
| rollback 警告 | ARCHITECTURE §7.1.1 | MODULES §19 #6、OPERATIONS §9.1 仍写"没有警告" | 改为描述 dry-run 警告行为 |

顺带发现并修正的额外漂移：

- `MODULES` §17 漏列 `reflect_on_history`（这才是"16"的真正原因）
- `README` / `OPERATIONS` 的项目结构说"16 个工具"
- `ARCHITECTURE` 里 **8 处 CYCLE.md 交叉引用编号过期**（§9.2→§10.2、§10→§11 等）
- `MODULES` 引用本文档不存在的 §4.1

### 15.2 关键原则修正：上游不留"时间痕迹"

评审给的建议很对，已采纳：**上游文档不再写"曾经是问题"的痕迹**。

反例（修正前）：`OPERATIONS §4.5` 整节在讲"为什么显示 snapshot"，
一旦环境变化（比如装上 git），这节立刻过期。

正例（修正后）：陈述**当前选择行为**——
"git 可用时选用 git，不可用退化为 snapshot；查实际后端见 `/profile`"。
这样无论环境怎么变，描述都成立。

同样地，`MODULES §19` 与 `OPERATIONS §9` 的清单**只列当前仍存在的**，
已修的直接删掉，不留"✅ 已修复"墓碑。

### 15.3 机制修正：把一致性变成可执行检查

新增 `tests/unit/test_doc_consistency.py`（**33 项**），把"可机械验证的一致性"
变成测试。它覆盖六类高频漂移：

| 检查 | 抓什么 |
|---|---|
| 工具数量/分组 | 文档写的数字 == `len(TOOLS_MAP)` 与实际 profile 分组 |
| 工具清单覆盖 | `MODULES §17` 必须列出全部工具名 |
| 已删除符号 | 上游文档不得把 `debug_head_chars` 等**当现有字段**引用（说明"已删除"的提及允许） |
| 过时措辞 | 黑名单短语（`未安装 git` / `不会自动加载` / `是文档性常量` …） |
| § 交叉引用 | 每个 `§X.Y` 必须在**全部文档的标题**里有对应（引用可跨文档） |
| 未修清单 | 条目标题里不得有"已修复"墓碑；引用的项目路径必须存在 |
| **版本戳** | 各上游文档声明的 `同步至 CHANGELOG §N` == CHANGELOG 最新条目号 |

**版本戳**是评审建议的最后一条，采纳了：四份上游文档 + `CYCLE.md` 顶部都标了
`> 同步至 CHANGELOG §14`。下次改动不同步时，这个数字会立刻暴露。

> 写这个检查器时也踩了它自己的坑，都已修：
> ① 正则漏了字母子编号（`4.0` / `7.1.1`）；
> ② 把代码块里的 `# 注释` 当成标题；
> ③ 误以为 `§X` 只能引用同文档章节 —— 实际可跨文档（`CYCLE.md` §9.2）。
> 这些误报本身说明：**检查器也要能被信任，否则它只会制造噪音。**

### 15.4 这一批处理后仍未解决的

- **语义漂移**检查不了：检查器只能抓机械可验证的部分
  （数量、符号、措辞、引用、版本戳）。描述与实现"意思不一致"仍需人工审。
- **版本戳需要人记得改**：现在它能**暴露**未同步，但不能自动同步。

---

## 16. 文档审查纳入 agent 能力范围 —— ✅ 已落地

**需求**："我的 agent 也要把文档审查纳入范围"。

### 16.1 先分清两个层次（这决定谁来审）

| 层次 | 例子 | 谁能判 |
|---|---|---|
| **机械一致性** | 工具数是 16 还是 18；`§9.2` 是否存在；符号是否已被删除 | **程序**——可验证，**可作门禁** |
| **语义准确性** | "这段关于分层的描述是否成立"；"这个解释是否误导" | **模型**——只能建议，**不能裁决** |

这与 `CYCLE.md` §8「门禁 vs 建议」是同一条纪律，也承接 §2.2：
**验收标准不能由被考核方定义**。所以文档审查也分层落地——
机械层进测试与工具，语义层留作后续的审查角色（建议性）。

### 16.2 一个必须先解决的集成障碍：子循环读不到文档

实测确认：

```
read_file("docs/MODULES.md")   -> 被映射到 workspace/docs/MODULES.md（不存在）
read_file("../docs/MODULES.md") -> 被路径防护拒绝
```

`backend/tools/files.py` 把访问限制在 `data/workspace/`——那是**代码生成沙箱**，边界是对的。
**不该为了审文档而放宽它。**

解法是**另开一扇只读窗**（`backend/core/doc_access.py`）：

| 约束 | 做法 |
|---|---|
| 只读 | 只提供 `read()`，**没有写路径** |
| 显式白名单 | 默认 `README.md` / `CYCLE.md` / `docs`，可用 `DOC_REVIEW_ROOTS` 覆盖 |
| 拒绝穿越 | 绝对路径、盘符、任何 `..` 一律拒绝 |
| 大小上限 | 256 KB，**超限直接拒绝而非静默截断**（截断会让审查漏内容） |

### 16.3 检查逻辑只写一份

`backend/core/doc_review.py` 是**共享判据**：`tests/unit/test_doc_review.py` 与
模型可调用的工具**调同一套代码**。若各写一份，两处必然分叉——
那正是本项目一直在治理的漂移。

五项机械检查：代码块语法、`import` 引用、`模块.符号` 引用、
§ 交叉引用、`/profile` 字段名。

### 16.4 新工具 `review_document`（第 18 个）

| 能力 | 说明 |
|---|---|
| 列表模式 | 不传 `path` 时列出可审查的文档 |
| 审查模式 | 传 `path` 返回 `{passed, checks, failures}`，每条带**证据**（行号/符号） |
| 定位 | **建议性**，不参与 cycle 成败判定；但机械部分结论可信 |

实测能精确抓到三类问题（用故意写坏的文档验证）：

```
[NG] python 代码块语法合法   ↳ L3: invalid syntax
[NG] import 指向真实符号     ↳ core.config.this_symbol_does_not_exist
[NG] 「模块.符号」引用存在    ↳ core.config.also_missing
                              ↳ tools.registry.nope_nope
```

### 16.5 检查器缺口：这次是被自己抓到的

加完 `review_document` 后，`test_doc_consistency.py` **立刻报错**：

```
FAIL  README.md: 写了「17 个工具」，实际 18
FAIL  MODULES 未列出的工具: ['review_document']
FAIL  coding: 文档写 14，实际 15
```

这正是上一轮建它的目的——**不用靠人记得同步**。

但它也暴露了自己的缺口：只抓"数字"，没抓"结构声明"。
于是补了两项：

- README 项目结构里声明的路径必须存在
- **真实存在的顶层包必须在 README 结构里出现**

补完立刻抓到 README **漏了 `bridge/`**（手机端审批页所在目录）。

### 16.6 验证

| 测试 | 项数 |
|---|---|
| `tests/unit/test_doc_review.py` | 12 |
| `tests/unit/test_doc_consistency.py` | 35（新增 2 项结构检查） |

全量 **20/20**。

### 16.7 尚未做

- **语义审查未接入**：机械层已进工具与测试；"表述是否准确"仍需模型判读，
  属建议层。这正好是 `CYCLE.md` §11 规划的审查角色的职责。
- **文档写权限未开放**：`doc_access` 是只读窗口，模型不能改文档。
  若将来要让它"自动修文档"，需要单独的、可回退的写路径——
  并按 §11.3 的纪律确保它**不能自己决定改得对不对**。

---

## 17. Vue 执行可视化前端（实时事件流）—— ✅ 已落地

**需求**："这个项目作为 Agent 后端，用 Vue 做一个前端……想让这个 Vue 有动态执行的
效果，方便跟踪进度。"

### 17.1 先解决结构性问题：`/encode` 是阻塞的

`POST /encode` 要等一整轮 cycle 跑完（实测 L1 约 5~60s，失败用例 60~300s）才返回。
**进度可视化的前提不是画得好，而是「运行」先成为一个可寻址、可订阅的对象。**
否则前端只能盯着一个转圈图标。

所以新增一层运行管理器（`bridge/runner.py`）：

| 决策 | 理由 |
|---|---|
| 运行跑在**独立线程 + 独立事件循环** | `on_decision=wait` 内部用 `time.sleep` 阻塞，放进 FastAPI 的循环会把整个服务卡死 |
| 事件流落成**每个运行一个 JSONL 文件** | 浏览器刷新 / 断线重连 / 换设备都要能补齐历史；内存队列做不到 |
| `POST /api/runs` 立刻返回 `run_id` | 前端拿到 id 再去订阅，接口语义干净 |
| 取消是**协作式**的 | 模型调用没法从外部打断；取消在下一个进度播报点生效，最坏延迟 ≈ 一次模型调用 |

### 17.2 进度事件总线：ContextVar 而不是全局单例

`bridge/progress.py` 用 ContextVar 持有接收器：

- 同一进程可能**并发跑多个 cycle**，全局单例会让进度串台；
  ContextVar 在 Task 创建时复制，天然隔离。
- **没绑定接收器时是纯 no-op**——与 storage 事件同样的旁路纪律：
  进度坏掉绝不能影响 cycle 成败。
- `emit_progress` 吞掉订阅者的 `Exception`，但**放行 `RunCancelled`**。
  取消信号刻意继承 `BaseException`：工作流层到处都有 `except Exception` 兜底，
  是 `Exception` 就会被吞掉，取消永远不生效。

### 17.3 埋点：把「正在做什么」变成可观测量

| 层 | 新增事件 |
|---|---|
| `CodingCycle` | `run_start` / `baseline` / `attempt_start` / `retry` / `phase` / `rollback` |
| `Orchestrator` | `round_start` / `orchestrator_decision` / `task_start` / `task_done` / `verify_probe` |
| `Worker` | `worker_step` / `model_reply` / `tool_call` / `tool_result` |

`CodingCycle.run()` 新增可选参数 `cycle_id`，让 Web 层能把「一次运行」与
「一条 cycle」对齐，前端按同一个 id 订阅。

阶段推进的播报统一走新的 `CodingCycle._enter()`：推进合法性仍由
`CycleReport.enter()` 把关，这里只负责把它**变成一条可观测量**。

**这些埋点全部是旁路**：不绑定接收器时行为与改造前完全一致，
现有 20 个单测原样通过。

### 17.4 前端：Vue 3 + Vite + TypeScript

`frontend/`，无 UI 框架（自绘 CSS），零运行时外部依赖（局域网离线可用）。

| 关键取舍 | 理由 |
|---|---|
| **事件 → 状态的翻译集中在 `store/run.ts`** | 实时流与历史回放共用同一段归约器代码；组件保持纯粹，不解析事件 |
| SSE 用 **fetch 流自己解析**，不用 `EventSource` | 后端用具名事件，`EventSource` 必须逐个 `addEventListener`，词表一扩展就漏事件；且它不能带 `after` 参数续订 |
| 演示运行（`bridge/demo.py`）**复用同一套事件词汇** | 没模型也能看全流程；验证的是真链路，不是只在演示里成立的旁路 |
| 回放历史时用**事件自带时间**而非 `Date.now()` | 否则「耗时」会显示成「从事件发生到现在过了多久」（实测显示 75.2s / 67.2s 而非真实的 7.0s / 8.0s） |

### 17.5 踩到的两个坑（都已修）

1. **`RunManager.list` 覆盖了内置 `list`**：`def events(...) -> list[dict]` 在类体内求值，
   此时 `list` 已是方法 → `TypeError: 'function' object is not subscriptable`。
   改名 `list_runs`。
2. **任务 id 在每次尝试里复用**（都是 `t1` / `t2`…）：`task_done` 原先命中的是
   **上一轮**的同名任务，本轮任务永远挂在「进行中」。改为命中最近一次出现的那个。

### 17.6 验证

| 测试 | 项数 | 需要 |
|---|---|---|
| `tests/unit/test_webui_runtime.py` | 38 | 离线，不启服务 |
| `tests/diagnostics/check_frontend_stream.py` | 17 | 需后端在跑（SSE 端到端） |

`check_frontend_stream.py` 走的是**浏览器同一条路**：`POST /api/runs` 不阻塞
（实测 4ms）、SSE 逐条推进、服务端主动 close、按 `seq` 断线续传不重不漏。

前端另有 `npx vue-tsc --noEmit` 零错误，产物 124 KB（gzip 47 KB）。

### 17.7 尚未做

- **只有一个"当前运行"的视图**：后端支持并发运行，前端一次只订阅一个。
- **运行间对比未做**：`data/storage_data/runs/*/meta.json` 已有足够字段做趋势图，
  但没做——那属于 `CYCLE.md` §11.4 规划的跨周期角色。
- **取消的最坏延迟是一次模型调用**：要更细的粒度需要在 `LLMClient` 层做可中断请求。

---

## 18. 备份纪律与 `scripts/backup.ps1` —— ✅ 已落地

**需求**："做出一版可行之后要先备份再继续考虑完善。"

### 18.1 为什么这条在这里是硬需求

**项目根目录没有 `.git`。** 它是复制版，原仓库在别处迭代。所以这里没有
`git checkout` / `git stash`，改坏了就是改坏了——
"继续完善"和"把能跑的版本改坏"之间只差**有没有上一个已知可用的节点**。

### 18.2 判据必须是可执行的，不能是"感觉能跑"

「一版可行」= 三条命令全过：

| 检查 | 命令 |
|---|---|
| 单元测试 | `python tests/run_unit.py` |
| 前端类型 | `cd frontend && npm run typecheck` |
| 事件流端到端 | `python tests/diagnostics/check_frontend_stream.py` |

动了工作流层再加 `python tests/diagnostics/gate_check.py`。

### 18.3 `scripts/backup.ps1` 的设计取舍

| 决策 | 理由 |
|---|---|
| **文件级快照**，不是 git | 没有 `.git` 可用；且副本要能整包搬走 |
| 快照带**每文件 sha256** | `-Verify` 才能回答"相对上个节点改了什么"，而不是靠记忆 |
| **排除运行态数据**（`data/storage_data/`、`data/sessions/`、`tests/output/`） | 备份它会让每次快照都不相同，`-Verify` 立刻失去意义 |
| **包含** `frontend/dist/` | 它是构建产物，但带上它快照才开箱可跑 |
| 回退**先自动再备份一次当前状态** | 回退本身也可能后悔；这一步 `-Force` 也**不**跳过 |
| `-Force` 只跳过交互确认 | 把"留退路"和"别烦我"绑在同一个开关上是错的 |

### 18.4 实测的三个坑

改这个脚本时踩到三个与流程无关、但会让人白花时间的问题：

1. **本机 `pwsh` 其实是 Windows PowerShell 5.1**（`$PSVersionTable` 实测 5.1.26100）。
   它把**无 BOM** 的 `.ps1` 按 ANSI(GBK) 读：中文变乱码，更糟的是 here-string
   **跨行解析错位**，报出一串莫名其妙的 `An empty pipe element is not allowed`。
   修法：脚本存为 **UTF-8 带 BOM**。

2. **函数没写 `param()` 时参数不会绑定**：
   `New-Snapshot -Label "x"` 会去读**脚本作用域**的同名 `$Label`，
   从别的函数里调用时它是空的 → 自动快照的标签悄悄丢了（全叫成 `_snapshot`）。
   修法：显式 `param([string]$Label = "", [string]$Note = "")`。

3. `by_top_dir` 在内存里是 **Hashtable**、从 JSON 读回来是 **PSCustomObject**。
   对 Hashtable 直接取 `.PSObject.Properties` 会枚举到 `Count` / `Keys` / `Values`
   这些**哈希表自身**的属性——生成的 `BACKUP.md` 目录表里赫然列着 `Keys/` 和 `Values/`。
   修法：`Get-TopDirPairs` 归一化两种形态。

### 18.5 验证

回退路径做了完整的往返实测（不是"看起来对"）：

```
1. 打 v1 快照（127 文件 / 1.47 MB）
2. -Verify            → 与备份完全一致
3. 改 1 个文件 + 新增 1 个文件
4. -Verify            → [改动] core/progress.py  [新增] TEMP_SCRATCH.md
5. -Restore -Force    → 自动留 auto-before-restore 快照，然后覆盖
6. 核对               → 新增文件已消失、改动已还原
7. -Verify            → 与备份完全一致
8. python tests/run_unit.py → 21/21 仍全绿
```

### 18.6 尚未做

- **没有自动快照**：靠人记得跑 `.\backup.ps1`。做成改动前自动触发更容易，
  但也更容易堆出几十个无意义快照——先保持手动。
- **快照不压缩**：1.47 MB 无所谓；真要长期保留时再上 zip。
- **跨机器不可比**：快照是本地资产（`_backups/` 已 gitignore），
  不同机器各存各的，没有共享的"已知可用版本"。

---

## 19. 结构梳理：前后端分离 + 路径唯一来源 —— ✅ 已落地

**需求**："你现在项目结构看着有点乱，重新梳理成前后端的。"

### 19.1 先解决真正的地雷：路径是 CWD 相对的

看起来只是"挪目录"，但直接挪会**静默炸掉**：

```
backend/core/checkpoint.py    WORKSPACE_DIR = os.path.abspath("workspace")
backend/core/pipeline.py      同
backend/core/symbol_index.py  同
backend/core/decisions.py     DECISION_ROOT = os.path.abspath("storage_data/decisions")
backend/storage/store.py      STORAGE_ROOT = os.path.abspath("storage_data")
backend/storage/session.py    STORAGE_DIR = "sessions"
backend/tools/files.py        BASE_DIR = os.path.abspath("workspace")
... 共 18 处
```

`abspath("workspace")` 是 **CWD 相对**的。它不会报错，只会**在错误的位置
静默新建一套空目录**，然后表现为"文件丢了""验证找不到模块"这类间接症状。

服务"必须在仓库根启动"这条隐性约定，原先只靠 README 里一句提醒。
把 `main.py` 挪进 `backend/` 之后它立刻失效——**所以先修路径，再挪目录**。

### 19.2 新结构

```
backend/        ── 后端（Python）
  main.py           FastAPI 入口
  paths.py          ★ 路径唯一来源
  core/  tools/  storage/  server/
frontend/       ── 前端（Vue 3 + Vite）          ← 原 webui/
data/           ── 运行态（不入库）
  workspace/  storage_data/  sessions/
tests/  docs/  scripts/
```

三处改名，各有明确理由：

| 原 | 新 | 为什么 |
|---|---|---|
| `web/` | `bridge/` | `web/`（Python）和 `webui/`（Vue）名字太像，是人都会看错 |
| `webui/` | `frontend/` | 与 `backend/` 对称，一眼看出前后端 |
| `workspace/` `storage_data/` `sessions/` | `data/` 下 | 运行产物不该和源码并排躺在仓库根 |

### 19.3 `bridge/paths.py`：唯一来源

```python
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND_DIR)          # 由 __file__ 推导，与 CWD 无关

DATA_DIR      = _abs_env("AGENT_DATA_DIR",      ROOT/data)
WORKSPACE_DIR = _abs_env("AGENT_WORKSPACE_DIR", DATA_DIR/workspace)
STORAGE_DIR   = _abs_env("AGENT_STORAGE_DIR",   DATA_DIR/storage_data)
SESSIONS_DIR  = _abs_env("AGENT_SESSIONS_DIR",  DATA_DIR/sessions)
# 派生：RUNS_DIR / SNAPSHOTS_DIR / DECISIONS_DIR / SKILLS_DIR / ...
FRONTEND_DIST = ROOT/frontend/dist
ENV_FILE      = ROOT/.env       # 部署配置留在仓库根，不进 backend/
```

18 处 `os.path.abspath("...")` 全部换成 `from paths import ...`。
**现在从任何目录启动都指向同一套 `data/`**——实测在 `%TEMP%` 下导入，
`workspace` 仍是仓库的 `data/workspace`。

顺带补上两处同类的 `__file__` 推导：`backend/core/doc_access.py` 与
`backend/core/doc_review.py` 的 `project_root()` 原先假设自己躺在仓库根，
挪进 `backend/` 后会指到 `backend/`——那会让文档审查**扫描不到任何文档，
然后静默全部通过**。现在两者都返回 `paths.ROOT`。

### 19.4 一个必须一起改的功能点

`backend/core/doc_review.py` 的 `importable_modules()` 按包名扫描
`("core", "tools", "storage", "web")`。包挪到 `backend/` 下之后：

- 扫描根要变成 `<仓库根>/backend`；
- 包名 `web` → `server`。

漏改的话 `mods` 会是**空字典**，而 `check_module_refs` 的逻辑是
`if mod_name not in mods: continue` —— 于是**所有文档引用校验静默通过**。
这正是本项目最防的那种假阴性。

### 19.5 路径纪律写进了测试

新增 `tests/unit/test_paths.py`（28 项断言），钉住四件事：

1. 所有运行态常量都落在同一个 `data/` 下（没有漏网的散落位置）；
2. **换三个不同 CWD 导入，路径完全相同**（真·与 CWD 无关）；
3. 环境变量能覆盖（测试隔离与部署要靠它）；
4. **静态扫描 `backend/**.py`，禁止再出现 `os.path.abspath("workspace")` 式写法**
   （`paths.py` 自己是唯一豁免）。

`test_doc_consistency.py` 也加了一条「文档不得残留裸路径引用」：
`` `core/xxx.py` `` / `` `webui/` `` / `` `workspace/xxx` `` 一律 FAIL。
它当场就抓到了 README 里的一句话——说明这条检查是有效的，不是摆设。

### 19.6 验证

| 检查 | 结果 |
|---|---|
| `python tests/run_unit.py` | **22/22**（新增 `test_paths.py`） |
| `test_doc_consistency.py` | 38/38（新增 3 项裸路径检查） |
| `test_paths.py` | 28/28 |
| `check_webui_stream.py` | 17/17 |
| 前端构建 + `vue-tsc` | 零错误 |
| 真实模型运行 | 一轮通过 |

迁移用一次性脚本完成（共 207 处文档替换 + 30 处代码替换），
**每条替换都要求唯一命中，未命中即报错退出**，不做静默跳过。跑完即删。

### 19.7 尚未做

- **`backend/` 不是 Python 包**（没有 `__init__.py`），靠 `sys.path` 注入。
  够用；将来若要发布成 pip 包需要再调整。
- **`data/` 没有多项目分区**：所有运行共用一套数据目录。
- **迁移脚本已删**：它是一次性的，留着反而会被误跑——我已经因为重复执行
  一个非幂等脚本，把两处 import 弄成了重复行（已修）。

---

## 20. 前后端隔离：引入 `bridge/` 适配层 —— ✅ 已落地

**需求**："尽量的把后端和前端隔离的清晰点，这样我后续把最新版后端复制过来的时候
你也可以直接考虑前端迁移。"

### 20.1 上一版留下的隐患（这次才看清）

§17/§19 把集成代码写进了上游文件里：

```
backend/core/coding_cycle.py    +emit_progress +_enter +cycle_id 参数
backend/core/orchestrator.py    +5 处 emit_progress
backend/core/worker.py          +4 处 emit_progress +_preview_args
backend/main.py                 +/api 路由 +SPA 挂载
backend/paths.py                +18 处 from paths import
```

功能都对，但**用户的工作流是「把最新版后端复制过来覆盖 `backend/`」**——
这一次复制会把上面全部内容抹掉，而且是**静默**的：服务照常起得来，
只是没有 `/api/*`、没有事件流，前端直接死。

**这不是"以后再说"的问题，是下一次复制就发生的问题。**

### 20.2 目标：`backend/` 必须是可整包替换的纯上游

新分工：

```
backend/    上游代码，一行不改，可整包替换
bridge/     ★ 适配层：上游与前端之间唯一的粘合处
frontend/   Vue，只跟 bridge 说话
data/       运行态
```

于是**先做了一件有风险但必须做的事：把上游改回去**。
`revert_backend.py` / `revert_backend2.py` 共 56 处精确反向替换，
每处都要求唯一命中。验证靠原作者那 20 个单测——撤错了它们会红。

> 实测确实抓到两个手工错误：① `doc_review.importable_modules` 的 `def` 行
> 被吃掉了（`SyntaxError`）；② `main.py` 的 `_approval_base_url()` 整个丢失
> （`NameError`，`/profile` 直接 500）。**测试网兜住了这两处。**

### 20.3 事件改为运行时挂钩，不再写进上游

关键洞察：**挑上游本来就存在的"汇聚点"，而不是挑"我方便的地方"**。

| 上游挂钩点 | 一次覆盖 | 为什么它是汇聚点 |
|---|---|---|
| `CodingCycle._emit` | plan / task_result / manifest / syntax / lint / verify / cycle_end / decision_* 等 **11 个** | 上游所有 cycle 级事件都从这一个方法出去 |
| `CycleReport.enter` | phase（+ 派生 attempt_start / retry） | 阶段推进的唯一出口 |
| `CodingCycle.run` | run_start + 周期上下文 | 一轮流程的唯一入口 |
| `CodingCycle._new_file_artifacts` | files | 交付文件的唯一计算处 |
| `CheckpointManager.commit / rollback` | baseline / rollback | 检查点的唯一出口 |
| `Orchestrator._decide` | round_start / orchestrator_decision | 每轮决策的唯一入口 |
| `Worker.run` | task_start / task_done | 单个任务的唯一入口 |
| `LLMClient.chat` | worker_step / model_reply | 所有模型调用的唯一出口 |
| `Worker._invoke` | tool_call / tool_result | 所有工具调用的唯一出口 |
| `CheckPipeline.run_verify` | verify_probe | 循环内验证的唯一出口 |

**成果：事件流一个不少**——SSE 端到端 17/17，与改上游埋点时的输出一致。

挂钩的两条纪律：

- 每个包装都走 `_safe()` 兜异常：**进度是旁路，坏掉不能拖垮 cycle**。
  唯一放行 `RunCancelled`（继承 `BaseException` 就是为了穿过去）。
- `CodingCycle._emit` 的包装**有条件**：检测到 `_enter`（说明这份后源自带埋点）
  就跳过 cycle 级挂钩，避免同一条事件播报两次。

### 20.4 路径：切 CWD，而不是改 18 个常量

上游的路径全是 CWD 相对的（`abspath("workspace")`）。
`bridge/bootstrap.py` 启动时把**进程 CWD 切到 `data/`**，它们就全部落位——
**一行上游代码都不用改**。

为什么不用"逐个改常量"：上游还有**函数内部**算路径的地方
（`tools/code_checks.list_workspace()` 里的 `abspath("workspace")`），
逐个打补丁一定会漏，而且上游新增一处我们也看不见。切 CWD 是一刀切的。

代价：这条是**隐式**的，坏了不报错。所以补了 `paths.stray_dirs()`——
仓库根一旦冒出 `workspace/` / `storage_data/` / `sessions/` 就说明有路径没被覆盖住，
契约自检会把它报出来。

### 20.5 三把新锁

| 测试 | 项数 | 守什么 |
|---|---|---|
| `tests/unit/test_isolation.py` | 33 | 上游里**没有** bridge 的东西；运行根在任意 CWD 下都生效；仓库根不被污染；契约自检**真的能报错**（含负向测试）；挂钩幂等且不改变上游行为 |
| `tests/unit/test_event_contract.py` | 12 | 前端词表 == 后端词表。扫三处事件源（上游 `_emit` / hooks / runner），AST 跨行解析 |
| `scripts/adopt-backend.ps1` | — | 复制新后端进来之后跑一次：契约自检 + 打印每个挂钩点的**实际签名** |

`test_event_contract.py` 上线当天就抓到两件事：

1. **`plan` / `task_result` / `decision_notified`** —— 上游会发、前端没 `case`
   （§17 起就有的老账，一直没人发现）。现在补上了 case，时间线不再出现裸 kind。
2. **挂钩漏了 `attempt_start` / `retry`** —— 这是**本次迁移引入的真实回归**：
   改上游埋点时这两个事件写在 `CodingCycle.run` 里，换成挂钩后忘了补，
   前端的「尝试轨迹」会永远停在第一次。测试当场报红。

> 第 2 条正是我上一轮说的"缺一把锁"的实例：没有这个测试，
> 这个回归会以"面板看着有点怪"的形式活到很久以后。

### 20.6 验证

| 检查 | 结果 |
|---|---|
| `python tests/run_unit.py` | **23/23** |
| `test_isolation.py` | 33/33 |
| `test_event_contract.py` | 12/12 |
| `test_doc_consistency.py` | 38/38 |
| `check_webui_stream.py`（SSE 端到端） | 17/17 |
| 真实模型运行 | 一轮通过，37 个事件、24 种 kind |
| 仓库根 | 无 `workspace/` `storage_data/` `sessions/` |
| `.\scripts\run.ps1`（入口 `bridge.app:app`） | `/app` 200，上游 `/profile` 正常 |

### 20.7 尚未做

- **路径依赖 CWD 是隐式的**：靠 `stray_dirs()` 事后发现。要更硬的话，
  可以在启动时遍历上游模块、把可疑的 `abspath("...")` 结果对一遍——
  但那会引入"上游新增模块要登记"的维护面，暂时不值。
- **契约自检不阻止启动**：缺接口只警告。理由是"上游少一个挂钩点，
  前端少一块信息而已，不该让服务起不来"。要不要改严，取决于你更怕哪种。
- **挂钩依赖 `_emit` 这类私有方法**：如果上游把它们重构成别的名字，
  自检会报红，但得人工找新的汇聚点。

## 21. 低定制高拓展：标定方案（`/api/spec`）—— ✅ 已落地

**需求**："前端最好设计成低定制高拓展性的，能做变量调整就做变量，而不是定义静态地址，
或者说给后端提供一个标定的前端方案……前端预留接口。"

### 21.1 之前的"低定制"是假的

阶段名、事件词表、工具中文名、状态色、轮询间隔、示例任务——
**全写死在前端代码里**。后端加一个阶段，前端得改 `STAGE_DEFS`；
后端加一个事件，前端得补 `case`；后端改个端点路径，前端得改 `client.ts`。

§20.5 那个 `test_event_contract` 抓到的 `plan` / `task_result` / `decision_notified`
漏翻译，就是这个模式的必然结果：**两边各手写一份，只能靠人记得同步**。

### 21.2 反过来：后端声明，前端照单渲染

```
bridge/spec.py  ──GET /api/spec──▶  frontend
   声明事实与标定                     不含任何后端事实
```

**三层分清楚**，这是整个方案的核心：

| 层 | 内容 | 能不能改 |
|---|---|---|
| **事实** | 有哪些阶段 / 事件 / 工具 / 端点 | ❌ **从代码扫出来**——改了就和代码说谎 |
| **标定** | 中文名、色调、面板、可调参数 | ✅ 可改，也可被 `spec.override.json` 覆盖 |
| **渲染** | 怎么画 | ✅ 前端自由，但不许含后端事实 |

事实的来源：

| 事实 | 扫描来源 |
|---|---|
| 阶段 | 上游 `core.cycle.PHASE_ORDER` |
| 门禁步骤 | 标定的 `gate_after`（声明插在哪个阶段之后） |
| 事件 | AST 扫三处：上游 `_emit` / `bridge/hooks.py` / `bridge/runner.py` |
| 工具 | 上游 `tools.registry.TOOLS_MAP` |
| 端点 | bridge 自己的表（它就是权威） |

### 21.3 预留接口：后端加东西，前端自动跟上

| 后端做了什么 | 前端 |
|---|---|
| `PHASE_ORDER` 加一个阶段 | 流水线自动多一个节点 |
| 加一个事件 | 按标定 label/tone 渲染；没标定就自动生成可读名字 |
| 加一个工具 | 工具面板显示它 |
| 改端点路径 | 跟着走 |
| 改轮询间隔 / 示例 / 面板开关 | 从 `spec.ui` 拿，**连重新构建都不用** |

**认不出的一律降级，不报错不空白**：

- 未知阶段 → 运行时补节点 + 通用图标（一个加号，一眼看出"前端没见过"）
- 未知事件 → 自动 label + 从 payload 自动挑可读字段
- 未知图标名 → 通用图标
- 未知状态 → 原始字符串
- **标定端点拿不到 → 用前端内置 `DEFAULT_SPEC`，界面照常可用**

> 崩了比显示不出来严重得多——所以这里全部选"降级可见"。

### 21.4 前端不再写死的东西

| 原先写死在 | 现在来自 |
|---|---|
| `store/run.ts` 的 `STAGE_DEFS`（6 个阶段） | `spec.pipeline.stages` |
| `store/run.ts` 的 `TONE` 表（28 个 kind） | `spec.events[kind].tone` |
| `store/run.ts` 的 `MAX_TIMELINE/MAX_TOOLCALLS` | `config.limits`（`spec.ui.limits` 可覆盖） |
| `PipelineFlow.vue` 的 6 个图标 | `spec.pipeline.stages[].icon` |
| `TaskPanel.vue` 的 `toolLabel`（9 个工具） | `spec.tools[].label` |
| `RunHistory.vue` 的 `statusTone/statusText` | `spec.statuses` |
| `LaunchPanel.vue` 的 `EXAMPLES` | `spec.ui.examples` |
| `App.vue` 的 `12000/6000/2500` | `config.poll.*` |
| `sse.ts` 的 `700/40` | `config.stream.*` |
| `client.ts` 的 `/api/...` 字面量 | `spec.endpoints` |
| `types.ts` 的 `Phase` 联合类型 | 放开成 `string`（阶段数由后端定） |

配置优先级：**内置默认 → `VITE_*` 环境变量 → 后端 `spec.ui`**（后者运行期生效）。

### 21.5 三把锁

新增 `tests/unit/test_spec.py`（26 项）：

1. **事实 == 代码现状**：阶段集合与顺序 == `PHASE_ORDER`；事件集合 == AST 扫描结果；
   工具集合 == `TOOLS_MAP`；
2. **没有漏标 / 没有死标**：`uncalibrated_events` 与 `dead_calibrations` 都为空；
   tone 全部是前端认识的取值；
3. **端点双向一致**：标定里声明的 `/api/*` 全部真的注册在 app 上，
   且 app 上注册的 `/api/*` 全部进了标定；
4. **前端兜底不许漂**（最重要）：`frontend/src/api/spec.ts` 的 `DEFAULT_SPEC`
   必须覆盖全部端点 key、阶段 id、阶段图标、状态、可调参数 key。
   这是**跨语言**一致性，没有类型系统帮忙，只能靠测试。

外加一条负向测试：**override 能改标定，但改不了事实**。

### 21.6 实测抓到的 bug

`test_spec.py` 上线即抓到：`pipeline_stages()` 读的是模块级 `CALIBRATION`，
而不是合并过覆盖文件的标定——结果是 **`spec.override.json` 改的阶段中文名不生效**，
而且不报错。改成 `pipeline_stages(cal)`。

这个 bug 的价值在于：它**只会在用户第一次真的去改标定时才暴露**，
表现是"我明明改了，怎么没用"——典型的静默失效。

### 21.7 验证

| 检查 | 结果 |
|---|---|
| `python tests/run_unit.py` | **24/24**（新增 `test_spec.py`） |
| `test_spec.py` | 26/26 |
| `test_event_contract.py` | 12/12 |
| `check_webui_stream.py` | 17/17 |
| 前端类型 + 构建 | 零错误，130 KB（gzip 49 KB） |
| 界面实测 | 阶段图标/中文名/状态/示例全部来自标定，无裸 kind |
| `GET /api/spec` | 33 事件全部标定、13 端点、18 工具、5 段可调参数 |

### 21.8 尚未做

- **没有前端设置面板**：改标定仍要编辑 JSON。加界面要引入"设置存哪儿、
  谁有权限"的新问题，先不做。
- **图标库内置**：标定只能选名字（`route`/`pencil`/…），不能传 SVG。
- **`failure_phase` 仍是 `failed`**：标定里留了键，但改成别的值没意义——
  它是上游 `CyclePhase` 的一部分。
- **`spec_version` 没有兼容性协商**：现在是 `1.0`，前端没有"版本太新就拒用"的逻辑。
  真要长期演进的话得补。

## 22. 指过去而不是搬过来 + 失败归因（`doctor`）—— ✅ 已落地

**需求**："其实没必要把文件转移过来，因为后端只是个服务，但是问题是如果出问题的
审查机制，我希望你来做，而不是我给你处理报告。"

### 22.1 前半句直接打中了我的设计缺陷

`bridge/paths.py` 里 `BACKEND_DIR` 写死成 `<仓库>/backend`——**逼着用户把上游代码
搬进仓库**。而用户的工作流是"上游在别处迭代，我这边跟着走"。

现在：

```powershell
$env:AGENT_BACKEND_DIR = "D:\upstream\SimpleAgent2_Cycle\backend"
```

**指过去，不复制。** 上游代码留在原地，不存在"覆盖掉什么"的风险——
也就不需要 §19/§20 那一整套"改坏了怎么办"的心理负担。
仓库自带的 `backend/` 降级为**开箱可跑的兜底**。

### 22.2 但"后端只是个服务"有个硬约束，必须说清楚

**bridge 的进度事件靠运行时挂钩**（§20.3）。挂钩要求上游代码在**本进程内**
可 import。所以"纯远端 HTTP 服务"和"丰富的实时进度"是**冲突**的：

| 方案 | 前端能力 |
|---|---|
| 同进程 + `AGENT_BACKEND_DIR` 指过去 | **完整**（全量事件） |
| 同进程 + 代码复制进 `backend/` | 完整，但有复制动作 |
| 上游独立部署，bridge 当纯 HTTP 客户端 | **大幅降级**：只有 `/encode` 的最终返回，没有 round / task / tool 级过程 |

选了第一种，第三种如实写进 `docs/LAYOUT.md` §7 供权衡——**不假装它能行**。

另加一条防御：`AGENT_BACKEND_DIR` 指错时**显式报错**而不是让后面的 import 抛
`ModuleNotFoundError`。"路径配错了"和"上游少了个模块"是两种完全不同的故障，
不能长得一样。

### 22.3 后半句：审查机制归程序，不归人的报告

出问题时人的自然反应是"收集信息 → 整理成报告 → 交给别人判断"。
这个来回本身就是瓶颈，**而且整理过程会丢信息**。

现在是一条命令：

```powershell
python scripts\doctor.py              # 分节报告 + 结论
python scripts\doctor.py --json       # 机器读（Agent 用的就是它）
python scripts\doctor.py --triage     # 归因最近一次失败
```

两条设计原则：

- **服务挂了也要能跑**——体检最需要它的时候，恰恰是服务起不来的时候。
  所以除"服务"一节外全部离线自检。
- **每条结论都带证据**——没证据的判断等于猜，猜错会把人引向错误的修法。

七节：引导 / 环境 / 路径与隔离 / 上游契约 / 标定自洽 / 服务 / 历史与归因。
有 FAIL 即返回非零，可直接进回归清单。

### 22.4 归因的口径必须跟项目一致

新增 `bridge/triage.py`（纯函数，可离线测）。类别沿用项目自己的定义
（`CYCLE.md` §12）：

| 类别 | 含义 | 应对 |
|---|---|---|
| 模型能力类 | 规格已写清，模型没做到 | 换模型；**不在工作流里打补丁** |
| 架构缺口类 | 系统缺少某个**显式模型** | 补机制 |
| 预算耗尽 | 轮次/步数/重试用完 | 调 `ModelLimits` |
| 环境问题 | 依赖/路径/服务 | 与模型和工作流无关 |
| 验收标准问题 | 验收命令自身有毛病 | 检查调用方给的 `verify` |

**边界踩错过一次，而且是 doctor 自己抓到的**：

第一次跑体检，它对一次真实失败给出的归因是「架构缺口类 — 声明的交付件没真正产出」，
证据却是 `declared-broken: SyntaxError`。**这是错的**——manifest 本身就是为补那个
架构缺口做的；`manifest` 已执行但内容不合格，属于**模型能力类**（模型写坏了），
不是系统缺机制。只有 `checked=False`（压根没有交付声明）才是架构缺口。

口径写进 `bridge/triage.py` 的 docstring，并由 `test_triage.py`（35 项）钉住。

### 22.5 顺带发现的真实历史 bug

归因那次失败时，它读出第二条：

```
环境问题 — 运行期异常
TypeError: CodingCycle._emit() got multiple values for argument 'kind'
```

来自 §20 改造过程中的一个**瞬时状态**（那会儿 `run_20260926_002100` 是 error）。
已确认现在不可复现（SSE 端到端 17/17、真实运行通过）。
**如果没有归因，这条只会以"某次运行莫名其妙 error"的形式沉在历史里。**

### 22.6 三处顺带的收尾

- `bridge/spec.py` 新增 `frontend_event_kinds()` / `event_contract()`：
  跨语言词表核对从测试里提出来，**测试与体检共用同一份判据**（原来只有测试会做）。
- `scripts/doctor.py` 自己也有过一个 bug：第一版忘了先 `bootstrap.install()`，
  结果 `core` 全部 import 不到、报了一屏假失败。**是它自己跑出来暴露的。**
- 归因收尾逻辑：已有具体证据时不再叠一条"未归类"（那是噪音，实测让输出难读）。

### 22.7 验证

| 检查 | 结果 |
|---|---|
| `python tests/run_unit.py` | **25/25**（新增 `test_triage.py`） |
| `test_triage.py` | 35/35 |
| `python scripts/doctor.py` | `WARN`（0 失败 / 2 提示），七节全绿 |
| `doctor.py --triage` | 正确归因历史失败，含证据与应对 |
| `check_webui_stream.py` | 17/17（确认历史 bug 不可复现） |

### 22.8 尚未做

- **归因只看单次运行**：没有"同一类失败反复出现"的跨运行趋势分析。
  那需要历史语料，属 `CYCLE.md` §11.4 规划的跨周期角色。
- **只诊断不治疗**：要自动修得先有回退与验证网（这个项目有），
  但"改哪儿"仍需判断。
- **`doctor --e2e` 会真跑流程**（约 20 秒并写 `data/`），默认不开。

## 23. 责任自审查：判「该改前端还是后端接口定义」—— ✅ 已落地

**需求**："在后端做一个测试或者方便运维调试的模块，等后端服务开起来，做一个责任
自审查机制，然后要么改前端，要么发后端接口定义问题。这样的话，就不需要考虑文件
转移问题了，只需要考虑服务和前端的兼容性。"

### 23.1 这一条把「文件转移」从根上消掉了

§22 让 bridge 能**指向上游**而不是复制它。但还有半个问题没解决：
服务是黑盒之后，出了不兼容**谁来判断该改哪边**？

答案必须是程序——因为服务的版本可能比前端新，也可能前端比服务新，
而两边都不该靠"翻对方的代码"来判断。所以：

```
POST /api/audit   ← 前端报上「我按什么写死的」
                  → 服务判「该谁改」
```

### 23.2 判定分界线：**声明**，而不是实现

服务是黑盒，前端唯一能依赖的就是它**声明**了什么。所以：

| 现象 | 归属 | 理由 |
|---|---|---|
| 服务**声明了** X，前端不认识 X | **前端** | 服务守约了；前端没跟上声明 |
| 服务**声明了** X，实际**不做** X | **后端接口定义** | 自相矛盾 |
| 服务声明了端点，实际没注册 | **后端接口定义** | 前端照声明调会 404 |
| 服务内容比前端多、`spec_version` 没变 | **后端接口定义** | 版本号的意义就是「变了要说话」 |
| 前端认得服务不声明的事件（孤儿） | **前端** | 死代码或客户端过时 |
| 前端按旧 spec 构建 | **前端** | 重新构建即可 |
| 服务不可达 / 前端没构建 | **运维** | 与双方契约无关 |

### 23.3 前端的「期望」必须生成，不能手写

前端启动时 POST 上自己的期望。这份期望由**构建期从源码扫出来**
（`frontend/scripts/gen-expectations.mjs` → `src/generated/expectations.ts`）：

| 期望 | 扫哪里 |
|---|---|
| `events` | `store/run.ts` 的 `case '...'` |
| `endpoints` | `api/*.ts` 的 `need('...')` / `endpoint('...')` |
| `stages` | `api/spec.ts` 的 `DEFAULT_SPEC` |

**为什么不手写**：手写的一定会漂；那时审查会给出**错误的责任判定**——
比不审查更糟，因为它会让人去修不该修的那一方。生成器扫不到东西就**直接报错退出**，
宁可构建失败，也不要产出一份假的期望。

生成挂进了 `dev` / `build` / `typecheck`，另有 `npm run check:expectations` 供测试用。

### 23.4 开发过程中被自己的审查抓到的三件事

这次实现过程本身就是这套机制的价值演示：

1. **`/api/audit` 自己没进端点声明** —— `GET /api/audit` 第一次跑就报了
   「1 个端点已注册但没进声明」。新加的端点忘了登记，是这类问题的原型。
2. **前端兜底 `DEFAULT_SPEC` 没跟上** —— `test_spec.py` 报
   「兜底覆盖全部端点 key `['audit']`」。跨语言一致性只能靠测试盯。
3. **生成器扫漏了** —— 它只扫 `need('...')`，而 `audit.ts` 用的是 `endpoint('audit')`，
   于是期望清单里少了这个端点——**而服务端会据此把"前端没用到"当成事实**。
   扫描范围已扩到 `api/*.ts` 并同时认两种写法。

### 23.5 归属可能不只一方——结论必须如实列全

早先的 `verdict` 按「后端 > 前端 > 运维」只报一个。结果：像
"服务加了事件但没升版本"这种**同时牵涉两边**的情况（后端流程有问题、前端也要跟上），
只报后端会把前端那一半藏起来——**而人往往只看结论**。

现在返回全部，例如 `backend+frontend`，文案是「需要改动：后端接口定义 + 前端」。

另有一条**方向**修正：客户端多了内容（孤儿）**不许**触发 `version_lying`。
方向搞反会让人去改后端，而后端本来是对的。`test_audit.py` 专门钉住这一条。

### 23.6 界面上就能看到

顶栏多了个徽标：`✓ 兼容` / `⚠ 契约` / `? 未审查`。点开是**分好归属**的清单：
每条写清「谁的」「什么问题」「怎么改」「证据是什么」。

拿不到结论时**不阻断界面**——只是没有徽标。

### 23.7 验证

| 检查 | 结果 |
|---|---|
| `python tests/run_unit.py` | **26/26**（新增 `test_audit.py`） |
| `test_audit.py` | 46/46（九个场景的归属断言） |
| `GET /api/audit`（服务自审） | `ok`，核对 9 项 |
| `POST /api/audit`（带前端期望） | `ok`，服务与前端一致 |
| 五个模拟场景 | 归属全部正确（含"不许诬告后端"） |
| 前端类型 + 构建 | 零错误 |
| `npm run check:expectations` | 最新（33 事件 / 6 阶段 / 12 端点） |

### 23.8 尚未做

- **`verdict` 不区分「谁先改」**：两边都要改时没有先后建议。
  实际上通常后端先改（前端基于声明适配），但没写进结论。
- **前端只在启动时审一次**：服务中途换了声明不会重审。加个手动刷新按钮很便宜。
- **期望不含字段级契约**：只比"事件名/端点名/阶段名"，
  不比每个事件的 payload 字段。字段改名仍会静默漏掉——那是下一层的契约。

---

## 24. 与 `.interface_contract` 对齐：词表、分区、以及两个被测试抓出来的真错 —— ✅ 已落地

**需求**："这个中间角色定义的东西不允许擅自变更，等我输出中间工作流给出的文档再操作文件"
→ 统筹方的契约（`1.0.2` / `1.0.3`）到位后，"**全部执行**"。

§23 的自审查是**自己定的规矩**。这一节做的是把它**换成契约的规矩**：
归属 4 值、严重度 3 档、结论 6 值，全部以 `.interface_contract/` 为准。

### 24.1 最重要的一条：`bridge/` 的问题算 **frontend**

契约 `boundary_definition`：边界 = **仓库的边界**。

```
backend  = SimpleAgent2_Cycle 仓库内的一切
frontend = SimpleAgent2_Cycle_VueWeb 仓库内的一切 —— bridge/ 与 frontend/ 同等
ops      = 环境与运行态
both     = 无法从事实源单方面判定，需人工协商
```

§23 里 `OWNERS["backend"]` 写着"改 `bridge/spec.py` 的声明"——**那是 frontend 的活**。
按边界，11 条 `backend.*` 判定里 **8 条改判为 frontend**（`contract_vocab.REATTRIBUTED`）。

**id 一律不改名**：契约的对账表按 `bridge_id` 索引，改名会把两套规则之间唯一的
链接弄断。于是 `backend.endpoint_missing` 这个 id 的归属是 **frontend** ——
前缀是历史遗留，真实归属查表（`owner_of()`），并在每条判定上带 `crosswalk_id`。

### 24.2 两个被新测试当场抓出来的**真错**

这一节最值得记的不是"实现了什么"，而是"**新测试立刻抓到了两个旧错**"。

**错一：`verdict_for` 的判定顺序反了。**

契约 `verdict_vocabulary.priority`：「**先判 ops**（服务不可达时后面一切都不成立）
→ 再按 owner 落到单侧/双侧」。而实现里写的是：

```python
if "both" in owners: return "need-negotiation"   # ← 先判了 both
if "ops"  in owners: return "ops-action"
```

后果不是"少一条提示"：一条 ops 问题会被 `both` 的 `need-negotiation` **盖住**，
而 ops-action 的下一步文案是"这一条修好之前后面都不成立" —— 被盖住就等于没人修环境。

`test_contract_vocab.py` 的 `{ops, backend, both} → ops-action` 当场红了。已改序。

**错二：`SPLIT` 哨兵用全等比较。**

契约 JSON 里这一格的实测值是 **`SPLIT(见 note)`**（带括号说明），
而镜像存的是 `SPLIT`。`owner_of()` 用 `== "SPLIT"` 判断，于是：

> 统筹方在括号里补一句说明 → 哨兵失效 → `owner_of()` 把 `SPLIT(见 note)`
> **当成真实归属返回** → 一条"需要拆开"的判定变成一条指向虚构归属的判定。

已改成**前缀**判断（`SPLIT_SENTINEL` / `is_split()`）。这个坑是测试跑出来的，不是想出来的。

### 24.3 端点分区：**先做少了，再补回来**

契约 `canonical_fields` 说 `upstream_endpoints` = 「前端要代理的**上游**端点」。
第一版的推导只从 `bridge/spec.py` 的 `ENDPOINTS` 反推 → 得到 **3** 条
（`/profile` `/reflect` `/decisions`，即 bridge 显式转发的那些）。

**这少了 4 条。** `frontend/vite.config.ts` 的 proxy 表把 **7** 条上游路径
**直接**代理给上游（`/skills` `/candidates` `/encode` `/run` 不走 bridge）。
统筹方的契约测试用的正是这张表，事实源标注为 `frontend/vite.config.ts`。

漏掉的后果是**静默的**：上游删了 `/skills`，前端少一块，
而**没有任何一条判定会指向上游**——因为前端从没说过它依赖 `/skills`。

现在分区取**并集**，两个事实源都读：

| 来源 | 内容 | 读法 |
|---|---|---|
| `UPSTREAM_ENDPOINT_MAP` | bridge 转发的 3 条（端点 key → 上游路径） | 代码常量 |
| `vite.config.ts` 的 proxy 表 | 前端直接代理的 7 条 | `partition.proxied_upstream()` |

前端那一侧同步改：`gen-expectations.mjs` 构建期扫 `vite.config.ts`，
产出 `EXPECTATIONS.proxied_upstream`；`buildReport()` 按它上报。

> 这条与缺口 G3 是**同型**的：G3 是把 bridge 自补的东西当上游的（多报），
> 这里是漏报前端真依赖的上游面（少报）。两个方向的错都不会让界面报错。

### 24.4 `ops` 字段：**接收，但不采信**

契约 `1.0.2` 新增第 9 个字段 `ops`（【观测】运行态事实），
但同一版记了一条 `ops_report_constraint`，状态 **AWAITING_SIDE_CONFIRMATION**：

> `ops.service_down` 经 `POST /contract/check` 上报是自相矛盾的 ——
> 能成功发出该请求就证明上游可达。而 `ops` **优先判定**，
> 一条陈旧的 `service_down` 会压掉其余全部结论。

工作单明示："在你开始上报 `ops` 之前，先看 `backend.md` 的对应章节"。

所以本仓库的处理是：`AuditRequest` **收下**这个字段（漏收会让上报被静默丢弃），
但只作为一条 **`info`** 如实报告（`frontend.ops_report_unconfirmed`），
**不参与 verdict**。语义未固化前不照着实现——那是 `CHANGE-PROCESS §6` 的纪律。
**前端当前不上报这个字段。**

### 24.5 G3 的测试：我和统筹方**独立得到同一个结论**

统筹方在契约 `CHANGELOG 1.0.3` 里修正了自己的一处判据：

> 我原来的断言是"把 6 个 stage 当 `phases` 上报时，上游不得把责任判给后端"。
> **这条断言是错的** —— 上游对不合规上报回 `P-phase-unknown` 是**正确行为**。

我在本轮独立读到同一个结论（记录在 `tests/unit/test_audit.py` §[6] 的注释里）：
`[H]` 测的是**上游的应答**，前端改完也转不了 PASS。两边各自发现，说明这是
**测试写错了**而不是实现错了。

改完后的 `[H]` 验证真实不变量：`upstream_phases` == 上游 5 个、
`bridge_gate_steps` 单独声明且含 `manifest`、不重叠、并集 == 全部 `stages`。

### 24.6 新增测试（把契约钉住，而不是靠记性）

| 文件 | 条数 | 钉什么 |
|---|---|---|
| `tests/unit/test_contract_vocab.py` | 57 | **直接读契约 JSON** 逐项比对词表 / 改判表 / 版本轴 |
| `tests/unit/test_partition.py` | 49 | 三条分区与契约 `observed` 快照比对；含"分区错了自检必须红"的反证 |
| `tests/unit/test_audit.py`（重写） | 92 | 新词表 + canonical 上报体 + 边界归属（含 `bridge/`→frontend 的改判） |
| `tests/unit/test_spec.py`（扩充） | 43 | 前端兜底 `DEFAULT_SPEC` 与服务端 / `vite.config.ts` **跨语言**一致 |
| `tests/diagnostics/check_contract_report.py` | 19 | 端到端：前端真会发的上报体 → `/api/audit` → 结论必须 `ok` |

第二项里的反证是刻意的：`check_against_contract()` 如果恒真，
"通过"就只是一个装饰。所以测试会**故意注入一份错分区**，断言它必须红。

### 24.7 报给统筹方的三条契约侧发现（本仓库不改契约）

`.interface_contract/` 是只读资产（README §3）。按 `CHANGE-PROCESS` §1，
契约侧的问题由统筹方改主本。以下三条已在本仓库记录，等统筹方裁决：

1. **`source_mapping` 那一行会复现 G3 的错误。**
   `client_report_schema.source_mapping.bridge_AuditRequest.endpoints`
   → `"-> upstream_endpoints"`。但 bridge 旧的 `endpoints` 是**它自己的** `/api/*`。
   字面照做 = 把 14 条 bridge 端点报成上游端点 = 11 条 `P-endpoint-missing(owner=backend)`。
   建议：像 `event_partition` / `phases_partition` 那样，补一节
   `endpoint_partition`，把「bridge 自己的」与「前端要代理的上游面」分开定义
   （后者的事实源是 `frontend/vite.config.ts`）。

2. **契约测试的镜像校验比 README 弱。**
   README §2 声明**7** 个载荷文件三处逐字节一致；
   但 `04-tests/cases/test_interface_contract.py` 的 `PAYLOAD` 只列了 **5** 个
   （缺 `CHANGE-PROCESS.md` / `EVALUATION-TEMPLATE.md`）。
   按 `1.0.1+proc` 自己的记录，`fingerprint.py` 的 `MIRROR_FILES` 已扩到 7 ——
   测试这一份没跟上，于是那两个文件的镜像一致性**实际没被校验**。

3. **`SPLIT(见 note)` 与散文里的 `SPLIT（按事件来源）` 不是同一个字符串。**
   机器消费方（本仓库的 `owner_of()`）得去猜括号。建议契约统一成裸 `SPLIT`，
   说明放进 `note`。本轮已用前缀判断容错，但**容错不该是消费方的义务**。

### 24.8 顺带修掉的一个真 bug：`doctor.py` 在 GBK 控制台上自崩

`doctor.py` 的报告里有 `✓` / `✗`，但没把自己的 stdout 钉成 UTF-8。
在 GBK 控制台上写到那一行就 `UnicodeEncodeError` ——

```
File "scripts/doctor.py", line 467, in main
    print(line)
UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 2
```

**这违反了它自己的设计原则**（文件开头第 3 条）：

> 3. **失败不抛异常，只标记 FAIL。** 体检自己崩了就没意义了。

而且它崩在**打印阶段**——前面所有检查都已跑完并得出结论，只是没印出来。
体检最需要它的时候（服务起不来、环境乱）恰恰最容易碰到非 UTF-8 控制台。

已加 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`
（`errors="replace"` 是兜底：老终端只退化显示，不中断体检）。

**验证**

```powershell
$PY scripts\doctor.py          # 现在跑到"结论：WARN"正常收尾
```

---

### 24.9 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量 | `python tests/run_unit.py` | **28/28**（新增 2 个测试文件） |
| 契约词表 | `python tests/unit/test_contract_vocab.py` | **57/57** |
| 三条分区 | `python tests/unit/test_partition.py` | **49/49** |
| 归属判定 | `python tests/unit/test_audit.py` | **92/92** |
| 标定自洽 | `python tests/unit/test_spec.py` | **43/43** |
| 端到端上报 | `python tests/diagnostics/check_contract_report.py` | **19/19**，`verdict=ok` `blocking=0` |
| **统筹方契约测试** | `test_interface_contract.py --backend 8210` | **29/29**（G1/G2/G3 全关） |
| 前端类型 | `npm run typecheck` | 零错误 |
| 前端构建 | `npm run build` | 56 模块，`dist/` 168 KB |
| 体检 | `python scripts/doctor.py` | 6 节 PASS / 1 节 WARN，正常收尾（不再自崩） |
| 生成物最新 | `npm run check:expectations` | 33 事件 / 6 阶段 / 13 端点 / 7 上游代理 |

实测 `/api/spec`（`AGENT_BACKEND_DIR` 指向真正上游）：

```
implements_contract_version = 1.0 [upstream]      ← 从上游读，不是抄常量
schema_version              = 1.0 [upstream]
pipeline.upstream_phases    = plan,write,check,verify,record
pipeline.bridge_gate_steps  = manifest
event_partition             = 12 + 21
endpoint_partition.upstream = /candidates,/decisions,/encode,/profile,/reflect,/run,/skills
```

### 24.10 尚未做

- **`verdict` 仍不区分「谁先改」**：`ops` 的优先级已按契约修好，
  但 backend 与 frontend 同时有问题时只给 `multi-action`，没有先后建议。
- **`ops` 通道未接**：等契约固化语义（见 §24.4）。
- **期望仍是名级**：不比 payload 字段。字段改名仍会静默漏掉。
- **`check_against_contract()` 多了两条可能偏严的规则**（"读不到 vite proxy 表"也算 issue）。
  它服务的是 `doctor` / 测试，不进 `verdict`，所以偏严是安全的副作用。

### 24.11 评估文档

按 `CHANGE-PROCESS` §3，本轮产出一份评估文档：
`docs/EVALUATION-WF1-WF6.md`（按 `EVALUATION-TEMPLATE.md` 的九节，
逐条对应 `C1`–`C8`）。它是给统筹方**验证可行性**用的，不是自评表。

---

## 25. 统筹方回执（契约 v1.0.4）：三条发现被采纳 + 补齐 C4/C8 + 一个真 bug —— ✅ 已落地

**来源**：统筹方的按侧指令 `DISPATCH.md`（本轮由 8 个文件涨到 9 个新增的那份），
生成于 2026-09-26 03:00，对应契约 **v1.0.4**。

### 25.1 评估文档的判定：「有条件通过」，条件已补齐

统筹方的判定：

> C1/C2/C3/C5/C6/C7 **满足**；C4/C8 **部分满足**，原因是本机无 git（正当理由，非隐瞒）。
> 条件是把"改动清单 vs 实际"与"文件级回退"在有 git 或**等价机械核对**后补齐。

**关键在"等价机械核对"这四个字** —— 我先前把"没有 git"当成了终点，
其实本仓库的备份工具**本来就有**这个能力：`-Verify` 按 SHA256 逐文件比对。

**C4 补齐**：拿改动前的基线快照机械核对改动清单。

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-015512_v7-responsibility-audit
# → [改动] 20 / [新增] 9 / [删除] 2，合计 31 个文件
```

顺带被它抓到一件事：评估文档 §3 的改动清单**漏列了 6 个同步文档**
（`README` / `CYCLE` / `ARCHITECTURE` / `MODULES` / `OPERATIONS` / `DIAGNOSTICS`）。
清单是手写的，机械核对不是——**这正是要机械核对的原因**。已补记。

**C8 补齐**：`backup.ps1` 新增**文件级回退** `-Restore -Path`。

先前只有整树恢复：改坏一个文档也要先删掉整份源码树。现在：

```powershell
.\scripts\backup.ps1 -Restore -From v7-responsibility-audit -Path bridge/audit.py
```

- 只覆盖点名的文件，不存在的路径**明确跳过并列出**（不静默）；
- 覆盖前把**被点名文件**的当前版本另存到 `_backups\<快照>\undo-<时间戳>\` ——
  **粒度回退配粒度的后悔药**（整仓自动快照对"只改了一个文档"太重）；
- 往返实测过（故意改坏 `data/README.md` 再退回，SHA256 精确还原）。

### 25.2 三条契约侧发现：全部被确认并修正

我按"只报告不擅改"提的三条，统筹方在 `v1.0.4` 全部改了：

| # | 我的报告 | 统筹方的处理 |
|---|---|---|
| 1 | `source_mapping` 的 `endpoints -> upstream_endpoints` 会**复现 G3 的错误** | 改为 `-> frontend_endpoints`，并**新增 `endpoint_partition` 一节**，写明 `upstream_endpoints` 的事实源是 `frontend/vite.config.ts` 去掉 `/api` |
| 2 | 契约测试的 `PAYLOAD` 只列 5 个，而 README 声明 7 个 → 那两个文件的镜像一致性**从未被校验** | 已改为 7 个（元组形式处理 `templates/`）。**修完立刻抓到统筹方自己未同步的改动** |
| 3 | `SPLIT(见 note)` 与散文 `SPLIT（按事件来源）` 不是同一字符串 | `unified_owner` 改为**裸 `SPLIT`**，说明移入 `note` |

第 1 条的评语值得原样记下来：

> **那是"拿对侧的事实源污染本侧归属"，和 G3 完全同型。你选对了，我写错了。**

**新增断言**：契约既已记下 `endpoint_partition` 的事实源，推导就必须与它逐条相同。
`test_partition.py` 现在直接读契约的 `three_sets` 对账（`upstream` == `observed` == 7 条），
`test_contract_vocab.py` 也钉住"哨兵值是裸 `SPLIT`"——一旦回退成带括号的形态就红，
而不是靠前缀容错悄悄盖过去。

### 25.3 一个真 bug：备份把统筹方的只读镜像一起打包了

统筹方核了我的新备份点，**两个都混进了他的目录**：

```
_backups\20260926-025148_v8-contract-alignment\files\.interface_contract\   ← 8 项
_backups\20260926-025203_v8.1-eval-doc\files\.interface_contract\           ← 8 项
```

**根因**：`backup.ps1` 用自己的排除清单，不是 gitignore；
`.interface_contract` 不在里面。上游那边被嵌套 `.gitignore`（内容 `*`）挡住了，
本仓库不是 git 仓库，`.gitignore` 不生效。

**为什么这要紧**（不只是洁癖）：

1. 备份的语义是"**我的**源码是什么样"，混进别人的镜像让这句话不成立；
2. 该目录的内容由统筹方按自己的节奏同步（本轮 8 → 9，新增 `DISPATCH.md`），
   留在备份里会让 `-Verify` 报出**不是本仓库发生的**新增/删除；
3. 更实际：下个备份会多一项，看起来像本仓库自己变了。

**已修**：排除清单加了 `".interface_contract"`。

**并且要把旧快照一起校正** —— 否则 `-Verify` 立刻会把这 8 个文件报成"[删除]"
（实测确认：加完排除后 `-Verify` 果然报了 8 条 `[删除]`）。
所以 v8 / v8.1 两个快照的 `manifest.json`（条目、`file_count`、`total_bytes`、
`by_top_dir`）、`files/` 下的文件树、以及 `BACKUP.md` 一并校正。
**这不是篡改历史**：那些文件本来就不属于本仓库，摘掉让 manifest **更**准确。
校正后 `-Verify` 只剩真实改动（1 个文件）。

### 25.4 又一个真 bug：`.ps1` 的 BOM 被编辑工具静默写掉

改 `backup.ps1` 加排除清单之后，脚本**直接跑不起来了**：

```
At D:\...\scripts\backup.ps1:60 char:1
+ }
+ ~
Unexpected token '}' in expression or statement.
...
+ | 椤?| 鍊?|
An empty pipe element is not allowed.
```

**根因**：本机是 **Windows PowerShell 5.1**，读**无 BOM** 的 `.ps1` 时按 ANSI/GBK 解码；
编辑工具按 UTF-8 **无 BOM** 写回，BOM 就没了。症状具有欺骗性——
报的是"语法错误"，看起来像代码写错了，而不是编码问题。

这个坑本轮之前已经踩过一次（初次写这三个脚本时）。**踩两次说明它需要机械门禁，
不是"下次注意"。** 所以新增 `tests/unit/test_ps1_encoding.py`：

- 每个 `.ps1` 必须有 UTF-8 BOM；
- 内容必须能按 UTF-8 解码；
- 含非 ASCII 的脚本必须同时满足上面两条；
- 顺带断言 `backup.ps1` 的排除清单里有 `.interface_contract`、
  且支持 `-Path` —— 把本轮的两项改动也钉住（删掉就红）；
- 失败时**直接打印修 BOM 的命令**，不让人去猜。

### 25.5 第三个真 bug：`§` 一个符号扛了两种约定

版本戳从 §24 升到 §25 之后，`test_doc_review.py` 立刻红了：

```
FAIL  无效引用 ['ARCHITECTURE.md: §25', 'CYCLE.md: §25', 'MODULES.md: §25',
                'OPERATIONS.md: §25', 'README.md: §25']
```

**根因**：`§` 在本项目里有**两种互不相干的用法**——

| 用法 | 例子 | 指向 |
|---|---|---|
| 交叉引用 | `详见 CYCLE.md §2.2` | 那 5 份上游文档的章节 |
| 版本戳 | `同步至 CHANGELOG §25` | **CHANGELOG** 的条目号 |

而 `core.doc_review.check_section_refs` 只把前 5 份文档的标题当靶子
（CHANGELOG 不在它收到的 `texts` 里），于是版本戳的数字被当成"指向不明章节的引用"。

**为什么以前没暴露**：CHANGELOG 的节号**碰巧**和 `MODULES.md` 的模块号对齐 ——
§23↔`bridge/audit.py`、§24↔`bridge/contract_vocab.py`。
一旦某轮只改工具层、MODULES 没有同号章节，就红。
**这是两个约定靠同号巧合互相满足，不是真的有效。**

**修法**：在 `test_doc_review.py` 里把版本戳行**摘掉**再查交叉引用，
并**另立一条断言**专门校验版本戳（必须等于 CHANGELOG 的真实条目号）。
两种约定各查各的——比"再加一个同号的 MODULES 章节"更根本：
后者只是把巧合续了一轮。

> 这是本轮第三个"我改完之后被自己的门禁抓到"的问题
> （前两个：`.ps1` 的 BOM、备份混进外部目录）。
> 三次都不是实现错误，而是**门禁与实现之间有隐含假设**。
> 这类问题只有"改完就跑"才抓得到——所以回归基线那条命令不能省。

### 25.6 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量 | `python tests/run_unit.py` | **29/29**（新增 `test_ps1_encoding.py`） |
| `.ps1` 编码门禁 | `python tests/unit/test_ps1_encoding.py` | **12/12** |
| 契约词表（v1.0.4） | `python tests/unit/test_contract_vocab.py` | **57/57** |
| 三条分区（v1.0.4） | `python tests/unit/test_partition.py` | **55/55** |
| 排除清单生效 | `.\scripts\backup.ps1 -ShowExcludes` | 含 `.interface_contract` |
| 机械核对改动清单 | `.\scripts\backup.ps1 -Verify -From ...v7...` | 20 改动 / 9 新增 / 2 删除 |
| 文件级回退往返 | 改坏 `data/README.md` → `-Restore -Path` | SHA256 精确还原 |
| 旧快照噪声 | `.\scripts\backup.ps1 -Verify -From ...v8.1...` | 只剩 1 个真实改动，无伪 `[删除]` |
| 文档审查 | `python tests/unit/test_doc_review.py` | **23/23**（新增版本戳专项断言） |
| 文档一致性 | `python tests/unit/test_doc_consistency.py` | 38/38 |
| 统筹方契约测试 | `test_interface_contract.py --backend 8210` | **29/29** |

### 25.7 尚未做

- **`undo-*` 目录会累积**：每次文件级回退在快照目录下留一份原件。
  目前靠人清理；量大了应该加个 `-PruneUndo`。
- **`-Verify` 仍要全量算哈希**：170 个文件约 1–2 秒，可接受；
  再大就该上 mtime 短路。
- **仍无 git**：机械核对已能替代 `diff --stat`，但替代不了 `git log` 那种历史叙事。
  本项目靠 `docs/CHANGELOG.md` 承担那一层。

---

## 26. 契约 v1.0.5 `warnings`：消费方义务与 ops 裁定 —— ✅ 已落地

**来源**：统筹方指令 `DISPATCH.md`（2026-09-26 09:25），契约 **v1.0.5**。
本轮**唯一**的接口级待办。

### 26.1 后端把 ops 那条约束裁定了

我上轮写的是"`ops` 字段：**接收，但不采信**"，并把理由记成"语义待后端拍板"。
后端在 `EVALUATION-OPS-1.md` 里拍板了，结论与我的实现**同向但更精确**：

> **被传输层证伪的 ops 事实**（请求已成功送达，却报了 `service_down`）
> **不再驱动 verdict**，但仍出现在 `ops` 栏与新增的 `warnings` 里。

**我的处理从"不采信"升级为"按裁定分流"**，并且发现我原来的写法有个洞：

| 情形 | 上轮（我） | 本轮（按裁定） |
|---|---|---|
| 客户端报 `service_down` | 一条 `info` issue「未采信」 | **`warnings` + `ops` 栏**，不进 verdict |
| 客户端报 `frontend_not_built` 但本地有产物 | 同上一并算「未采信」 | **与本地观测矛盾 → `warning`**，不进 verdict |
| 服务侧观测到未构建 | `ops-action` | **不变**（契约实测举证：ops 优先未被削弱） |
| 未知事实名 | 忽略 | 忽略（additive 安全） |
| 报 `false` | —— | 不构成事实，不产生 warning |

### 26.2 ★ 一条**消费方义务**：只看 verdict 会漏掉它

裁定带来一条"你必须处理的路径"，后端自己在 §6 就点出来了：

> **只看 `verdict` 的消费方会看到 `ok`，从而看不到那条陈旧标志。**

统筹方把它写成了契约里的消费方义务
（`response_contract.warnings.consumer_obligation`）：

> 展示 verdict 的消费方**应当同时展示 warnings**。

**这条义务的落点在本仓库前端**（它展示 `/api/audit` 的 verdict）。
三处改动：

1. `bridge/audit.py` 的 `Audit` 新增 `warnings` 与 `ops_reported`，
   `to_dict()` 输出 `warnings: []` 与 `ops: {}`（additive）；`to_markdown()` 里
   **提示段排在分归属正文之前** —— 藏在末尾等于没展示；
2. `frontend/src/api/audit.ts` 取 `warnings`（缺失兜底 `[]`）与 `ops`，
   导出 `auditWarnings()` / `auditOps()`；
3. `frontend/src/components/TopBar.vue` 把提示渲染在阻塞项**之前**，
   **并且徽标本身就带条数**（`✓ 兼容 (1 提示)`）——
   否则用户不点开，那条义务就等于没履行。

### 26.3 另一条认知修正：判断环境问题不要只看 verdict

契约 `response_contract.priority_clarification` 澄清了一件容易搞错的事：

| 原来的假设 | 现在 |
|---|---|
| `verdict == "ops-action"` ⟸ `service_down` 报了 true | **不成立** —— 陈旧 `service_down` 判 `ok` + 一条 warning |
| `frontend_not_built` | **未变**，仍判 `ops-action` |

所以"环境问题横幅"的依据是 **`ops` 栏 / `warnings`**，不是 verdict。
这条已写进 `TopBar.vue` 的注释与 `DIAGNOSTICS.md`，并在界面上把 `ops` 栏显示出来。

契约还澄清了它与 `verdict_vocabulary.priority` 不冲突：
**收窄的是"什么算当前 ops 事实"（输入），不是优先级**。
举证是 `frontend_not_built` 仍判 `ops-action`（实测）。

### 26.4 实现时自己抓到的两件事

1. **`_relabel(code, ...)` 用错会把 ops 判成前端。**
   `_relabel` 查的是按 `bridge_id` 索引的 `REATTRIBUTED` 表；
   传契约 code（`O-frontend-not-built`）查不到，会落到默认归属 `frontend` ——
   **一条运维问题被标成前端要改**。已改成显式构造 `Issue(owner="ops")`。
2. **重复计一条事实。** 服务侧与客户端同时观测到 `frontend_not_built` 时，
   去重只查了 `audit.issues`，而服务侧那一条此刻还在局部列表 `ops_issues` 里没合并 ——
   于是同一条在 `responsibility` 里出现两次。已改成两边一起查。

3. **顺手删掉一个我自己加的、有害的参数。** 我先给 `run()` 加了
   `transport_reached: bool = True`，想表达"离线代别人上报"。
   但那个场景不存在，而该分支让 `service_down` 在 `transport_reached=False` 时
   **既不 warning 也不判** —— 静默丢弃。恒为真的开关只是制造缝隙，已删除。

### 26.5 新增/更新的断言

| 位置 | 钉什么 |
|---|---|
| `tests/unit/test_audit.py` §[9b] | 陈旧 `service_down` → `ok` + 恰好 1 条 warning + `ops` 栏保留；未构建仍 `ops-action`；矛盾观测 → warning；未知事实忽略；报 false 不成事实；**无重复 id**；markdown 提示段在正文之前 |
| `tests/unit/test_contract_vocab.py` §[9] | 契约 `response_contract` 的形状、**消费方义务的措辞**、`ops_stale_by_transport` == 实现常量；**跨语言**核对前端确实取了 `warnings` 且徽标带条数 |
| `tests/diagnostics/check_contract_report.py` §[4][5] | 端到端：真实上报体带 `ops` → `verdict=ok` + `warnings` + `ops` 栏；markdown 提示段 |

第 2 项里那条**跨语言核对**是刻意的：消费方义务要求"前端真的展示"，
光在后端产出 `warnings` 不算履约 —— 所以断言直接读前端的 `.ts` / `.vue`。

### 26.6 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量 | `python tests/run_unit.py` | **29/29** |
| 归属判定 | `python tests/unit/test_audit.py` | **107/107** |
| 契约词表 | `python tests/unit/test_contract_vocab.py` | **78/78** |
| 端到端上报 | `python tests/diagnostics/check_contract_report.py` | **29/29** |
| 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误 / 56 模块 |
| 统筹方契约测试 | `test_interface_contract.py --backend 8220` | **29/29** |

实测 `/api/audit`（带 `ops.service_down=true`）：

```
verdict = ok — 服务与前端兼容，无需改动
⚠ 客户端上报 service_down=true，但该请求已成功送达本服务 ——
  这条 ops 事实被传输层证伪（code=O-service-down），未参与判定。
ops 栏 = {'service_down': True}
blocking_count = 0
```

### 26.7 尚未做

- **界面未人眼看**：徽标带条数与提示段的**渲染**只过了 `vue-tsc` 与构建，
  没有人眼确认（与本项目一贯的"浏览器渲染未验"同一条覆盖缺口）。
- **`warnings` 未做历史留痕**：现在只反映"本次上报"。若运维想追
  "这条陈旧标志挂了多久"，需要把 `warnings` 存进事件流——那是新功能，不在本轮。
- **`ops` 栏仍是客户端单方面声明**：服务侧不校验它是否与真实环境一致，
  只能证伪"与本次请求矛盾"的那一类。

---

## 27. 架构级变更 A1a/A2/A3/A4（用户已批准 P1–P5）—— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-26 09:40）+ `ARCHITECTURE-CHECKLIST.md`，
契约 **v1.0.6**。用户原话：

> 「架构级别层面的按照你的想法执行吧，写在清单里，我都批准了」

清单把 P1–P5 映射成 A1–A5。**本仓库侧是 A1a + A2 + A3 + A4**（A5 是决定，无待办）。

### 27.1 A1a：两个对账入口按**职责**切分

决定是**切开**，不是合并也不是二选一：

| 入口 | 权威范围 | 明确**不**负责 |
|---|---|---|
| `POST /contract/check`（上游） | 跨侧对账 | 本地环境细节 |
| `POST /api/audit`（bridge） | 本地自检：声明 vs 实现 vs 环境 | **跨侧归属**（引用上游 code） |

**为什么不能合并**：`/api/audit` 看得见上游看不见的东西
（`frontend_not_built`、挂钩是否装上、bridge 自己的声明自洽性）。
硬合并会丢掉这些观测能力。

**"不再自行下结论"落到实处的三件事：**

1. **跨侧判定的 id 就是契约的 rule code**。自造的 `frontend.missing_upstream_events`
   之类全部改成 `P-event-unknown-to-frontend` 这样的契约 code；
   运行态的 `ops.service_down` 改成契约采纳的 `O-service-down`。
   **一个判定只有一个名字。**
2. `contract_vocab.owner_of()` **优先读契约 JSON**（`rule_crosswalk`），
   手写的镜像表降级为**离线回退**（镜像不在时的兜底），
   并由测试断言两者逐条一致。
3. 每条判定带 `code` 字段（契约的 `upstream_equivalent`）；
   空字符串表示**契约明确写「无」**，不是"忘了填"。

**响应自述权威范围**：`authority: "local-self-check"` + `authority_note`，
markdown 开头也写了。

**在线证明**（`check_contract_report.py` §[7]）：造一个前端漏认上游事件的不一致，
同时打两个入口 —— 上游回 `[frontend/degraded] P-event-unknown-to-frontend`，
本地回同一条同归属：

```
本地入口认出了这条不一致（漏 verify）   ['P-event-unknown-to-frontend']
★ 本地判定的 id 就是契约 code（不是自造名字）   P-event-unknown-to-frontend
     上游 verdict=frontend-action 命中 1 条
       [frontend/degraded] P-event-unknown-to-frontend
★★ 两个入口给出的 owner **一致**   本地=frontend 上游=frontend
```

**过程中抓到三处我自己判错的地方**（都是新测试/对账逼出来的）：

1. **契约版本方向没分。** 我原来把"前后端契约版本不一致"一律判 `frontend/degraded`。
   契约有**两条**规则且方向相反：落后 → `P-version-behind`（frontend, degraded）；
   **领先 → `P-version-ahead`（backend, breaking）**。
   不分方向会把"后端没跟上"判成"前端要改"。已按方向拆成三条
   （behind / ahead / unparsable）。
2. **"少给字段"的级别判重了。** 契约 `absence_policy` 明写字段全部可选，
   少给只降精度 → `P-missing-field`（frontend, **info**）。我原来判 `degraded`（阻塞）。
   已按契约改成 info。
3. **`_relabel` 传契约 code 会落到默认归属。** 那张表按 `bridge_id` 索引，
   传 `O-frontend-not-built` 查不到 → 落到默认 `frontend` →
   **把运维问题判成"前端要改"**。已改成显式构造 / 专用 `_cross()`。

**一处声明的偏离**（不静默照抄，也不静默改判）：
`P-phase-unknown` 契约判 `backend/breaking`，本模块判 `both/degraded`。
理由：前端新画一个阶段、与上游删了一个前端还在画的阶段，**现象完全一样**，
事实源判不出方向 —— 这正是 `boundary_definition` 里 `both` 的定义。
契约 `empirical_evidence.S2` 自己也把这条的归因称为"让后端去恢复一个它从未拥有的东西"。
记在 `audit.DEVIATIONS` 里，测试断言该集合**恰好**是这些（长不大），请统筹方裁决。

### 27.2 A2/A3：上游副本陈旧检测

**实测确认了统筹方给的事实**（不是照抄）：

```
bundled  core 模块 27 个
upstream core 模块 29 个
上游有、bundled 缺：core/contract.py, core/vision.py
两边都有但内容不同：9 个
```

缺 `core/contract.py` → **新契约机制整体静默不可用**，
而服务照常启动、界面照常显示。**不报错的失效最难查。**

新增 `bridge/staleness.py`（纯函数、按目录取参 —— 这样负向测试才写得了）+
三个出口：启动横幅警告 / `GET /api/health` 探针 / `doctor.py` 结论。

★ **A3 的判据也钉住了**：判据是 `paths.BACKEND_DIR`，**不是"import 到了 `core` 就算对"**
—— 仓库里两个同名 `core` 包，import 成功只说明 `sys.path` 里有它。
写进 `docs/LAYOUT.md` §7.1、`docs/ARCHITECTURE.md` §12、`docs/DIAGNOSTICS.md` §7.5，
并由 `test_staleness.py` 用"故意指向一份坏上游"的**负向测试**守住。

**严重度分两档**（这个区分是有意的）：

| 情形 | 级别 | 理由 |
|---|---|---|
| bundled 且落后 | `WARN` | 用自带副本是**正当选择**（开箱可跑是设计），修法只是一行环境变量。判 FAIL 会让默认配置**永远红着** —— 而"永远红着"的检查等于没有检查 |
| 外部却落后 | `FAIL` | 你明确指向了一份上游，它却缺必需模块 —— 那是配错了，不是选择 |

### 27.3 A4：`docs/VERSIONS.md`，由 `backup.ps1` 自动追加

先前"版本"只有一个**目录名**，记不下三件最要紧的事：
**改了什么 / 验证过了吗 / 怎么退回去**。上游有 `docs/VERSIONS.md` 且
"验证不过拒绝备份"，两侧可追溯性不对称。

**逻辑住在 `scripts/versions.py`（Python，可测），不埋在 PowerShell 字符串拼接里** ——
因为这个文件的纪律是**只增不改**，而一条会静默改写历史的 bug 比没有记录更糟
（它会让"这一版当时验过没有"变成编出来的）。`backup.ps1` 只负责算数据、调 CLI。

每次备份自动做两件事：

1. **跑一遍离线验证**（单元测试 / 目录布局 / 前端类型；服务起着时加端到端），
   结果写进记录；
2. **追加一条**，含四样：标签与时间 · **改了什么**（对照上一版的机械 diff）·
   **验证结果** · **还原命令**。

> **与上游刻意不同的一点**：验证不过时**仍然备份**，只在记录里如实写"未通过"。
> 理由：**最需要备份的时候恰恰是东西坏掉的时候**，拒绝备份会让人失去唯一的退路。
> 这个偏离写在 `docs/VERSIONS.md` 的头部，不是偷偷放宽。

**起点**：`v1`…`v9` 只在 `_backups/` 留有目录名，**不追溯补写** ——
凭记忆补出来的记录不是记录。`--SkipVerify` 可跳过验证。

### 27.4 新增/更新的测试

| 文件 | 条数 | 钉什么 |
|---|---|---|
| `tests/unit/test_staleness.py` | 34 | A2/A3；含**负向**：指向缺 `core/contract.py` 的目录 → 必须报落后 |
| `tests/unit/test_audit_authority.py` | 35 | A1a；权威自述 / id 即契约 code / 偏离集合长不大 / 双入口同归属（离线形式） |
| `tests/unit/test_versions.py` | 35 | A4；**只增不改**（旧条目逐字比对）/ 四样必填字段 / 缺失写"未记录" / 最新在上 |
| `tests/diagnostics/check_contract_report.py` | 41 | 端到端：health 探针 + 双入口 owner 一致（**在线**形式） |

`test_versions.py` 里那条"旧条目逐字未变"是刻意的最强形式：
不是"条数对了"，而是**每个旧条目的文本与之前逐字相同**。

### 27.5 备份前验证**自己**修了四处（都是真跑一次才暴露的）

A4 的价值在于"每次备份都真的验一遍"。**真跑第一次就崩了四次** ——
这四处的共同点是：**单元测试覆盖不到**，因为它们是 PowerShell 与子进程交互的坑。

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | `The expression after '&' produced an object that was not valid` | **`backup.ps1` 从来没有定义 `$python`** —— 我把它和 `run.ps1` 记混了，四处引用都在用 `$null` | 在脚本头定义（找不到 `.venv` 就回退到 PATH，且**不报错**：备份本身不依赖 Python） |
| 2 | 单测命令行报 `NativeCommandError` 后**整次备份终止** | 脚本级 `$ErrorActionPreference = "Stop"` + PowerShell 5.1 下把原生命令 stderr 用 `2>&1` 收进来会变成 ErrorRecord | `Invoke-Preflight` 内部局部放宽，返回前恢复 |
| 3 | 记录成「**单测 23/23**」（真实是 32/32） | 单个测试文件**自己也会打印** `通过 X/Y`；`[regex]::Match` 取的是**第一条** | 改成取**最后一条**汇总 |
| 4 | 记录成「改了什么 = `op_Addition` 方法不存在」 | `(管道A) + (管道B) + (管道C)`：管道为空时返回 `$null`，与数组相加在 5.1 下报错 | 改成显式 `List[string]` 逐条 `Add` |

外加第 5 处（属于 A2 的同类问题）：**`check_webui_stream.py` 没有钉住 stdout 编码**，
于是 `backup.ps1` 用 `2>&1 \| Out-String` 捕获它的输出时，UTF-8 的中文被按 GBK 解码
→ `通过 17/17` 变乱码 → 正则匹配不到 → 记录成"未识别输出"。
修法两处都做：预检局部设 `[Console]::OutputEncoding = UTF8`，
且脚本自己 `reconfigure(encoding="utf-8")`（**同一个坑在 `doctor.py` 上踩过一次**，
这是第二次 —— 说明"脚本要自己钉编码"这条该当成默认动作）。

> ★ 值得记的是**第 3、4 处的失败方式是诚实的**：它们没有静默写一个错数字，
> 而是把失败本身写进了记录（"未识别输出" / 那句 `op_Addition` 错误）。
> 这正是"只增不改 + 如实记录"的设计要的效果 ——
> **记录系统宁可说自己没测出来，也不能编一个看起来正常的数**。

### 27.6 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量 | `python tests/run_unit.py` | **31/31**（新增 2 个测试文件） |
| 陈旧检测 | `python tests/unit/test_staleness.py` | **34/34** |
| 入口切分 | `python tests/unit/test_audit_authority.py` | **35/35** |
| 版本记录 | `python tests/unit/test_versions.py` | **35/35** |
| 端到端 | `python tests/diagnostics/check_contract_report.py` | **41/41** |
| 体检 | `python scripts/doctor.py` | 结论含上游来源与陈旧项 |
| 统筹方契约测试 | `test_interface_contract.py --backend 8230` | 见 §27.6 |

### 27.7 尚未做 / 待统筹方裁决

- **`P-phase-unknown` 的归属**（§27.1 的声明偏离）—— 请裁决。
  若契约维持 `backend`，请说明"前端自造阶段"与"上游删阶段"如何区分；
  若改判 `both`，我这边不需要动代码（`DEVIATIONS` 里删一条即可）。
- **`U-dead-event` 的级别在契约内部不一致**：`rule_crosswalk` 的行里写 `breaking`，
  而 `upstream_only` 列的是 `degraded`。本模块取行里的值（breaking）。
  同一个 code 两个级别会让按 code 对账的消费方对不上 —— 建议契约统一。
- **`ops` 通道的 `warnings` 适用范围**（上一轮 §26 的疑问）仍未得到答复：
  义务约束的是**端点**还是**展示行为**。本轮按"展示行为"实现。
- **A4 的记录不含"验证不过就拒绝"**（刻意的偏离，见 §27.3）。

---

## 28. ARCH-D2：两处裁定落到代码（偏离撤销 + 级别统一）—— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-26 10:25），契约 **v1.0.7**。
本轮只有一项，且是**回执性质**的：上一轮我请裁决的两条都裁了。

### 28.1 `P-phase-unknown`：**我报的那条被采纳，偏离撤销**

裁定：

> `P-phase-unknown` **改判 `both` / `degraded`**（原 `backend` / `breaking`）。
> 你之前把它记进 `DEVIATIONS` —— **现在它不是偏离了，可以撤销那条**。

契约给出的理由与我报的一致（"前端自造了一个节点"与"上游删了一个阶段"现象相同，
事实源判不出方向），**并且补了一条我没说到的**：

> 真正的『上游删阶段』由 `U-removed-surface(backend,breaking)` 覆盖，
> **不因此丢失检测**。

这条补充很重要 —— 它说明改判**不会漏检**，我原来只论证了"归因方向"，
没论证"改判后有没有东西被漏掉"。**这是contract reasoning 比我严的地方**，记一笔。

**处理**：`DEVIATIONS` 清空。表**空着**本身也是断言（两侧判据一致）。

### 28.2 `U-dead-event`：缺陷真实，但**我指的位置偏了**

我上轮报的是"`U-dead-event` 在 `rule_crosswalk` 行里是 `breaking`，
而 `upstream_only` 里是 `degraded`"。统筹方的修正：

> 实际不一致在 `rule_crosswalk.upstream_only[U-dead-event]=degraded` 与
> `bridge_backend_prefixed[backend.dead_event]=breaking` 之间
> （后者 `upstream_equivalent` 正指向前者）。**已统一为 `degraded`。**

我指的是**同一行的两个字段**，实际是**两行之间**。结论一致（缺陷真实），
定位偏了 —— 记下来，因为"报得对但指得偏"在多人协作里会浪费对方一轮排查。

**处理**：`backend.dead_event` → `degraded`；`U-dead-event` 与 `bridge.dead_event`
的级别现在都从契约取（`severity_of("backend.dead_event")`），不再手写常量。

### 28.3 顺手把"两个判据"的根因去掉（本轮真正有价值的改动）

D2 只有两行值要改，但**这两行值之所以会漂，是因为它们被抄了一份**。
所以本轮不是"改两个常量"，而是**把跨侧规则也改成读契约**：

```
_cross(code) 的取值顺序：
    ① 契约 JSON（contract_vocab.upstream_rule）   ← 权威，新增
    ② DEVIATIONS                                  ← 声明偏离必须显式
    ③ UPSTREAM_RULES                              ← 离线回退（镜像不在时）
```

新增 `contract_vocab.load_upstream_rules()` / `upstream_rule(code)`，
与既有的 `owner_of()` + `REATTRIBUTED` 回退是**同一个模式**。
并新增断言：**离线回退表必须与契约逐条一致** ——
`U-dead-event` 那种"同一底层状况两个级别"的漂移，从此会**当场红**。

> 这也是我在 `EVALUATION-ARCH-A1A-A4 §6-1` 里承认过的同一类问题的第二次修复：
> 第一次是版本方向（判据写死导致方向丢失），这次是规则值（判据抄一份导致漂移）。
> **凡是"契约定过的事"，本模块都不该再存第二个副本。**

### 28.4 另外两项主动询问也裁了（都不需要改代码）

| 我问的 | 裁定 | 本仓库现状 |
|---|---|---|
| `ops.warnings` 语义是否放宽 | **维持单一语义**（只放被传输层证伪的事实）——否则它退化成第二个 `info` 通道，多一个字段、少一个判据 | 已经就是这样，**无需改动** |
| id 改用契约 code 要不要加别名映射 | **不需要** —— A1a 的决定就是"同一件事只有一个判据"，加别名等于把两套判据养回来 | 没有加别名，**无需改动** |

### 28.6 端到端自检修了两处（都是"真跑一次"才暴露的）

D2 只有两行值要改，但我把端到端自检在**两种配置**下各跑了一遍，暴露两处：

**一、404 被当成"上游答了但没命中"。**
服务用自带副本时没有 `/contract/check`，FastAPI 回 404；而 404 的 body 是
合法 JSON（`{"detail":"Not Found"}`），`r.json()` 会"成功"解析出空 dict ——
于是被判成 `verdict=None 命中 0 条` → 记 **FAIL**。
**修法**：显式判 `status_code == 200`。

**二、把"按配置不可测"与"测了没过"分开。**
自带副本做不了跨侧对账，这是**配置事实**不是代码缺陷（缺什么已由陈旧检测报出）。
记成 FAIL 会让**默认配置永远红着**，而永远红着的检查等于没有检查
（与 §27.2 里 bundled→WARN / 外部→FAIL 是同一个判断）。
**修法**：新增 `skip()`，明确印 `SKIP` 并写明原因，不计入失败。

实测两种配置：

```
bundled（:8000）  → 通过 39/39 · SKIP 1
上游（:8240）     → 通过 41/41（含双入口 owner 一致）
```

### 28.7 一条**观察**（不是本仓库的缺陷，报给上游）

跑端到端时，指向上游的那个实例上 `POST /contract/check` **返回 500**：

```
File "backend/core/contract.py", line 805, in peer_issues
    out.append(Issue("P-missing-field", "前端未提交 contract_version",
NameError: name '_version_tuple' is not defined
```

**但同一个文件现在在磁盘上第 731 行就定义了 `_version_tuple`。**
重启实例（重新加载模块）后 `/contract/check` 恢复 200。

**判断：这是"模块被改过、运行中的实例还是旧版本"的瞬时状态**，
不是稳定缺陷 —— 大概率是上游当时正在编辑。

**为什么仍然要报**：如果它**不是**瞬时的，那是一条会让**所有**跨侧对账 500 的
严重缺陷，而现象只在"打接口时"才看得到（上游自己的离线测试可能覆盖不到
ModuleNotFound/NameError 这类只在特定代码路径触发的错）。
请上游确认它是否已随那次编辑一起修掉。

### 28.9 一条**没能复现**的观察：仓库根冒出一个空的 `workspace/`

本轮验证时 `test_isolation.py` 与 `layout.py --check` 同时红了，指向仓库根多了一个
`workspace/`（内容只有空目录 `_debug` / `_tmp`，创建时间 10:23:31）。

这正是隔离设计要防的事（上游路径是 CWD 相对的，CWD 一旦不是运行根就会落错地方），
**门禁按预期抓到了它**。

**但我复现不出来**，如实记下证据与排除过程：

| 排查 | 结果 |
|---|---|
| 删掉后逐个跑 `test_doc_review` / `test_isolation` / `test_staleness` / `doctor` / `run_unit` | 全部**干净**，一个都不造 |
| 当时运行的那个实例日志 | 运行根写的是 `...\sa2_d2_rt`，**是对的** |
| 那个运行根里 | 有 `workspace/`（含 `.git` / `_debug` / `_tmp`）—— 说明它**正常落位** |
| 用同样的 `Start-Process` 重跑一遍 | **干净**（`workspace/` 落在运行根，没落仓库根） |

所以那一次的具体触发条件**未知**。已把仓库根那份删掉，当前树干净。

**为什么不"猜一个原因然后写个修复"**：没有复现路径的"修复"无法验证，
写进 CHANGELOG 只会让下一个人以为它被治好了。
`_debug` / `_tmp` 是**上游**在 import 期建的子目录，所以那次确实是"有人在
CWD = 仓库根的情况下 import 了上游"——但**是哪一个进程**，我没能锁定。

**现有的防线（已生效）**：`tests/unit/test_isolation.py` 与 `scripts/layout.py --check`
都会当场红。这条留着继续观察。

### 28.10 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量 | `python tests/run_unit.py` | **32/32** |
| 契约词表（含新的回退表比对） | `python tests/unit/test_contract_vocab.py` | **86/86**（原 78，+8） |
| 入口切分 | `python tests/unit/test_audit_authority.py` | **34/34**（偏离表空） |
| 归属判定 | `python tests/unit/test_audit.py` | **107/107** |
| 实测取值 | 见下 | ✅ |

实测（`/api/audit` 的两条相关判定）：

```
P-phase-unknown → owner=both    sev=degraded     ← 契约 v1.0.7（原 backend/breaking）
bridge.dead_event → owner=frontend sev=degraded  ← 契约 v1.0.7（原 breaking）
DEVIATIONS: {}                                    ← 偏离撤销
```

### 28.11 尚未做

- **`severity_vocabulary` 与 `upstream_only` 的关系没有机械校验**：
  现在校验的是"回退表 == `upstream_only`"，但**没有**校验
  "`upstream_only` 里用的严重度都在 `severity_vocabulary.values` 里"。
  后者是契约内部一致性，属统筹方范围，本仓库只消费。
- **仍无 git**（与历轮同）。

---

## 29. D8（阻塞）+ D9 + D6：一条"从未跑通过"的路径 —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-26 12:10），契约 **v1.0.19**。

### 29.1 D8：`decision_opened` 的分支读错了字段

统筹方逐环核出的链条，我**逐环复现确认**（不是照抄）：

| 层 | 事实 | 我的核对 |
|---|---|---|
| `bridge/runner.py:78-83` | `record = {seq, ts, kind, **payload}` —— **payload 在后展开** | ✅ 读到源码 |
| 改名**前** | payload 的 `kind` **覆盖**记录的 `kind` → `ev.kind` = 决策种类 | ✅ 由展开顺序推出 |
| 改名**后** | 不再覆盖 → `ev.kind` = `'decision_opened'`（事件类型） | ✅ |
| `frontend/src/store/run.ts:717` | `kind: String(ev.kind \|\| '')` → **决策种类显示成事件名** | ✅ 改前确实如此 |

**修法**：第 717 行改读 `ev.decision_kind`。

**顺带发现一件统筹方没提的事**：那次改名**同时修好了上面的 `switch (kind)`**。
覆盖存在时 `ev.kind` 是决策种类（`repeated_failure`…），
所以 `case 'decision_opened'` **根本匹配不上** —— 这个分支此前是**死的**。
统筹方说"这条路径从未真正跑通过"，比它说的还多一层：不止上游发不出事件，
前端即使收到了也进不了这个分支。

**全类检查（我做了，不只改这一处）**：用 AST 扫上游 `core/coding_cycle.py` 的
**每一个** `_emit(...)` 调用，看还有没有别的 `kind=` 载荷键 ——
**0 处**。所以这不是"改一个地方"，而是"这一类只有这一个实例"。

### 29.2 D9：包装器镜像签名 —— 一次真实的 `status=error`

`bridge/hooks.py` 的 `_emit` 包装器原来写的是
`def _emit(self, kind, cycle_id, goal="", **payload)` —— 把上游签名**原样抄了一份**。
任何调用点写 `_emit("x", cid, kind="y")` 就会：
`TypeError: got multiple values for argument 'kind'` → **整轮 run status=error**。

上游已把自己的首参改名 `event_kind` 做二次防御，**但这份镜像不会跟着变** ——
镜像的本质就是"第二份判据"。改为 `inspect.signature(orig_emit).bind(...)`：
**问上游要签名**。

**改的过程中我自己踩了两个坑，都被新测试当场抓到：**

1. **`bind().arguments` 会把 `**payload` 收成嵌套字典**（挂在 `"payload"` 键下），
   不是摊平。不展开的话事件记录变成 `{seq, ts, kind, cycle_id, goal, payload:{...}}`
   —— 前端读的 `ev.decision_id` 成了 `undefined`，**而且不报错**（只是少显示）。
   修法：按 `param.kind is VAR_KEYWORD` 展开、丢掉 VAR_POSITIONAL。
2. **`emit_progress(kind, **payload)` 自己的首参就叫 `kind`** ——
   载荷里一旦有 `kind`，同一个撞名会在**这一层**再发生一次，
   而这次是被 `_safe(...)` **吞掉**的 → 事件**静默消失**。
   修法：把它的首参也改名 `event_kind`（与上游同一招）。

> 这两个坑都不是"想出来的"，是 `test_hooks_passthrough.py` 的**载荷断言**
> 逼出来的。**先写断言再验收**的价值就在这儿。

### 29.3 D6：把"双入口对拍"变成常驻测试

新增 `tests/unit/test_two_entrypoints.py`：**同进程**同时打 `/api/audit` 与
`/contract/check`，对拍 `code` / `owner` / `severity` / `verdict`。

实测（指向上游）：

```
本地 2 条 · 上游 3 条 · 共有 code 2 条
  P-event-unknown-to-frontend   本地=frontend/degraded  上游=frontend/degraded
  P-phase-unknown               本地=both/degraded      上游=both/degraded
★★ owner 逐条一致      ★★ severity 逐条一致
```

**verdict 允许不同**（本地=need-negotiation / 上游=multi-action）——
两侧覆盖面不同，本地还管"本地环境"项（钩子、构建产物、标定自洽），
那些是上游观测不到的。真正要比的是**共有 code 的 owner 集合**，那是一致的。

**按配置分流**：自带副本没有 `/contract/check` → **SKIP**（不是失败），
并写明原因与"想跑就设 `AGENT_BACKEND_DIR`"。与 `doctor.py` 的
bundled→WARN / 外部→FAIL 是同一条判断：**判 FAIL 会让默认配置永远红着**。

### 29.4 ★ 顺带修掉一个**测试基础设施**里的歧义（A3 的同型问题）

D6/D8 要读上游源码，这才发现 **`tests/_bootstrap.py` 把上游目录写死成
`<仓库>/backend`**，**不认 `AGENT_BACKEND_DIR`**。后果是静默的：

> 用户明明指了最新上游，而所有"扫源码"的测试
> （`test_event_contract.py` 扫 `_emit` 调用点、`test_doc_review.py` 扫文档…）
> **扫的还是仓库里那份旧副本** —— 测试全绿，但**验的不是你在用的那棵树**。

这正是架构项 A3 说的"两个同名 `core` 包的歧义"，只不过发生在**测试层**。
`_bootstrap` 的原注释还写着"由 `test_paths.py` 保证一致"—— 而那个文件早已不存在，
**没有任何东西在保证它**。

已修：`BACKEND` 改用与 `bridge/paths.py` **同一条判据**（`AGENT_BACKEND_DIR` 优先），
并新增断言把它与 `paths.BACKEND_DIR` 钉在一起（`test_isolation.py` §[6]）。

修完后，同一份测试在两种配置下给出**不同但都正确**的结果 —— 这本身就证明了修复有效：

| 配置 | `test_event_contract.py` |
|---|---|
| 指向上游 | **21/21**（真验到了"上游发的是 `decision_kind`"） |
| 自带副本 | 18/18 + **SKIP 1**（上游落后，那半边按配置验不了） |

**同时纠正两处测试判据**（它们本来把"生效上游"和"仓库自带副本"混为一谈）：

- "自带 `backend/` 里无 bridge 痕迹" —— 混进 bridge 东西只可能发生在**本仓库**，
  外部 checkout 不归这条管；改用显式的 `BUNDLED` 路径。
- "运行根在仓库内且叫 `data/`" —— 那是**默认布局**；设了 `AGENT_RUNTIME_ROOT`
  就不该用它判。隔离性由"跨 CWD 结果一致且落在运行根"那条守（它仍在跑）。

### 29.5 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 离线全量（buffered） | `python tests/run_unit.py` | **34/34** |
| 离线全量（指向上游） | 同上 + `AGENT_BACKEND_DIR` | **34/34** |
| 挂钩包装器 | `python tests/unit/test_hooks_passthrough.py` | **19/19** |
| 双入口对拍 | `python tests/unit/test_two_entrypoints.py` | **16/16**（指向上游） |
| 事件契约（含载荷键跨语言核对） | `python tests/unit/test_event_contract.py` | 21/21（上游）/ 18+SKIP（自带） |
| 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误 / 56 模块 |
| 统筹方契约测试 | `test_interface_contract.py --backend <port>` | 见 §29.6 |

### 29.6 尚未做

- **D8 的界面效果未人眼看**：改的是 reducer 的字段读取，已由
  `test_event_contract.py` §[6] 做**跨语言**核对（后端发 `decision_kind`
  ↔ 前端读 `ev.decision_kind`），但**渲染结果没人眼确认**（既有覆盖缺口同一条）。
- **D8 的完整链路未端到端跑**：要触发 `decision_opened` 得让模型连续失败两次
  并进入人工决策路径。当前证据是**源码/载荷层**的，不是"真跑出一轮"的。
  这是本轮最值得补的一项，但需要真实模型与较长时间。
- **`emit_progress` 的首参改名是行为收紧**：任何外部调用方若写
  `emit_progress(kind=...)` 会失效。已核对本仓库**无此写法**（全部位置传参）。

---

## 30. A2b：bundled 即**拒绝启动** —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-26 13:50）+ `ARCHITECTURE-CHECKLIST.md` 的 A2b 一节，
契约 **v1.0.22**。用户已批准（选 **(2) 启动即拒**，并要求**保证版本追溯性**）：

> 「按你推荐的来，保证版本追溯性就行，我希望下次我打开对应网页应用的版本是最新的」

### 30.1 为什么是"拒"而不是"更醒目的警告"

A2 当初的目标是「不删副本，但**让它无法被静默使用**」，四条验收标准**全部通过**。
然后真的出事了：

> 用户实例 `:8000` 以**无 `AGENT_BACKEND_DIR`** 的方式启动 → 走 bundled 副本；
> 从后端 v1.12 到 v1.14 约 **10 轮**里，上游所有修复**一条都没生效**，
> 而启动警告没人看见、探针字段没人去看。

**这不是"警告写得不醒目"，是"警告"这个手段本身不够 ——
「可见」被当成了「足够」，而它不够。** 所以换成"让误解不可能发生"。

### 30.2 判**形态**，不判**状态**

门禁是 `backend_is_bundled`，**不是** `backend_stale`：

> **"副本此刻恰好同步"是一个会过期的属性**，而这条规则要防的正是
> "你以为在跑上游、其实在跑副本"这种**误解**。

`stale` 仍然有用 —— 它用来在拒绝时说明"**落后在哪、有什么后果**"。
测试里专门用 `{**bundled, "stale": False}` 断言"即使不 stale 也照样拒"。

### 30.3 闸门放在 **import 期**（这是"端口不起来"的唯一办法）

uvicorn 的顺序是「先 import 应用 → 再绑定端口」。所以只要在 import 期退出，
**端口就不会被监听** —— 而验收标准要的正是这个，不是"起来了再关掉"。

代价是：**`import bridge.app` ≠ 启动服务**（测试要 in-process 拿 `app` 对象）。
代价怎么付：

- `tests/_bootstrap.py` 显式设 `AGENT_ALLOW_BUNDLED=1`，并写明
  "这里开的是**测试导入用**的逃生舱，不是'服务可以随便用副本'"；
- 真正的门禁由 `tests/unit/test_bundled_gate.py` 用**子进程**验证 ——
  它把该变量从子进程环境里**删掉**，断言拒绝真的发生。

### 30.4 逃生舱：**降级必须留痕**

`--allow-bundled`（或 `AGENT_ALLOW_BUNDLED=1`）可强制启动，但
`/api/health` 必须报 `backend_bundled_override: true`。

> 否则逃生舱会变成一条**新的静默通道**，把这次的事原样重演。

**为什么环境变量是主入口**：`uvicorn bridge.app:app --allow-bundled` 会在
uvicorn 自己的参数解析阶段就报错（它不认识这个 flag），根本轮不到我们看。
所以 flag 那条路要有**我们自己的**入口 —— 新增 `bridge/__main__.py`
（`python -m bridge --allow-bundled`），`scripts/run.ps1` 加 `-AllowBundled`。

**A2 的醒目警告没被丢掉**：它现在打在**逃生舱路径**上 ——
"用了逃生舱"恰恰是最需要看到"你在用副本、上游修复不生效、后果是什么"的时刻。
若不这样安排，那条警告会因默认路径变成"直接拒绝"而成为**死代码**。

### 30.5 版本追溯（用户明确要求）

启动日志与 `/api/health` **共用** `staleness.provenance()`（两处各拼一遍迟早分叉）：

| 字段 | 回答什么 |
|---|---|
| `backend_dir` | 用的哪份后端代码 |
| `backend_is_bundled` | 是不是仓库自带副本 |
| `backend_bundled_override` | **新增**：是否用了逃生舱 |
| `backend_stale` / `_reason` | 是否落后及**后果** |
| `backend_contract_version` | 跨侧唯一刻度 |
| `frontend_asset` | **新增**：**你打开看到的是哪一版** |

`frontend_asset` 从 `dist/index.html` **引用的那个 JS** 读，而不是"目录里最新的那个"
—— 两者在构建中断时会不一致，而用户问的是"**正在服务的**是哪一版"。

启动日志里的版本追溯段可直接粘进版本记录：

```
[bridge] ── 本次运行（版本追溯）────────────────────────────
[bridge]   后端目录      : D:\PythonProject\SimpleAgent2_Cycle
[bridge]   自带副本      : False
[bridge]   逃生舱        : False
[bridge]   陈旧          : False — 标记齐备，未发现落后
[bridge]   core 模块     : 29 个
[bridge]   契约版本      : 1.0
[bridge]   前端 bundle   : index-CsUZBNxG.js
```

### 30.6 拒绝长什么样（实测）

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
[拒绝启动] 解析到的后端是**仓库自带的 bundled 副本**。

  实际 backend_dir : D:\...\SimpleAgent2_Cycle_VueWeb\backend
  判定依据         : backend_is_bundled = True（判形态，不判状态）

  为什么这不可用：
    落后：缺 core/contract.py（契约机制）→ CONTRACT_VERSION / ISSUE_RULES /
    /contract/check 整体不可用，契约版本会静默退回 fallback；…

  怎么修（复制一条执行，然后重启）：
    PowerShell : $env:AGENT_BACKEND_DIR = "D:\PythonProject\SimpleAgent2_Cycle"
    cmd        : set AGENT_BACKEND_DIR=D:\PythonProject\SimpleAgent2_Cycle
    bash       : export AGENT_BACKEND_DIR=D:\PythonProject\SimpleAgent2_Cycle

  确实要用自带副本（例如只想看界面）：显式开逃生舱
    PowerShell : $env:AGENT_ALLOW_BUNDLED = '1'
    bash       : AGENT_ALLOW_BUNDLED=1 uvicorn bridge.app:app
    或         : python -m bridge --allow-bundled
    留痕字段：backend_bundled_override=true —— 降级必须留痕。
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

三件事齐全：**实际 `backend_dir`、带后果的理由、可复制的修复命令**。
修复命令里的路径**不编** —— 先看 `AGENT_UPSTREAM_DIR`，再看仓库同级目录里
真的有 `core/` 的那份，都没有才给明确的占位符。

### 30.7 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 门禁测试（含**子进程负向测试**） | `python tests/unit/test_bundled_gate.py` | **31/31**（bundled）/ **32/32**（指向上游） |
| 离线全量（bundled / 指向上游） | `python tests/run_unit.py` | **35/35** / **35/35** |
| 拒绝：退出码 | `uvicorn bridge.app:app`（无 `AGENT_BACKEND_DIR`） | **2** |
| 拒绝：端口 | 同上 | **未监听** |
| 逃生舱 | `python -m bridge --allow-bundled` | 起来了，`backend_bundled_override=true` |
| 正常路径 | 指向上游、无逃生舱 | 起来了，`override=false`、`is_bundled=false` |
| `frontend_asset` | `/api/health` | `index-CsUZBNxG.js` == `dist/index.html` 引用值 |

**负向测试是这一项的核心**（验收标准明写"一个只打警告的实现不得通过"）：
它**真的起一个进程**，断言退出码非 0 **且端口没被监听**。

### 30.8 一件顺带被门禁抓到的事（说明门禁在起作用）

改 `scripts/run.ps1`（加 `-AllowBundled`）之后，`test_ps1_encoding.py` 立刻红了
—— **编辑工具把 BOM 又写掉了**。这正是那个测试存在的理由（这个坑踩过两次）。
若不是它，脚本会在 PowerShell 5.1 下因中文注释变乱码而**报一堆看不懂的语法错误**。

### 30.9 尚未做 / 需要注意

- **⚠️ 行为变更，会影响现有启动方式**：以后**不设 `AGENT_BACKEND_DIR` 就起不来**。
  这是本项的目的，但第一次遇到时像"服务坏了" —— 拒绝信息里已给出修复命令与逃生舱。
- **`bridge.app` 现在不能"裸 import 就当服务"**：任何 in-process 使用者
  （测试、`doctor.py` 之类）都必须显式表明"我只是导入"。当前只有 `_bootstrap`
  这么做，并附了理由。
- **`--allow-bundled` 只在我方入口上有效**：`uvicorn ... --allow-bundled` 仍会因
  uvicorn 自己的参数解析而失败。环境变量 `AGENT_ALLOW_BUNDLED=1` 覆盖所有启动方式。
- **`frontend_asset` 只报 JS bundle**：不含 CSS/其它资源。够回答"哪一版"，
  但不是完整的构建指纹（若要完整，应报 `dist` 的哈希清单）。

---

## 31. 校准上游新事件 `verify_skipped`；并修掉"写死的期望值" —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-26 14:35），契约 **v1.0.23**。
本轮唯一红项：`/api/spec` 的 `diagnostics.uncalibrated_events = ["verify_skipped"]`。

### 31.1 这个事件是什么，为什么要认它

上游 `FIX-VERIFY-WIRING` **加性**新增（`core/contract.py:148`）：

```python
"verify_skipped": EventSpec("verify_skipped", ("reason", "command"), since="1.1")
```

它把「**有验证命令、却没有 pipeline，于是验证回流整块被跳过**」从**静默**
变成**显式事实** —— 因为静默跳过会让上层误诊成"缺少验证命令"，把定位带偏一整轮。
上游在 `coding_cycle.py:378` 与 `:382` 两处发它（后一处是"模型自拟判据被拒"）。

**我们的分区已经对了**（`/api/spec` 自动归到 upstream，13/21）——
缺的只是**校准**（label/tone/panel）。

**标定的选择**：

| 字段 | 值 | 理由 |
|---|---|---|
| `label` | `⚠ 验证被跳过` | 一眼看出这是"本该验、却没验" |
| `tone` | **`warn`** | 它是**跳过了一次安全检查**，不是通过；也**不是 `error`**（cycle 本身没失败） |
| `panel` | `gate` | 它属门禁那一段 |
| `detail` | `{reason}` | 跳过原因是最有价值的信息（上游给到 600 字） |

### 31.2 让运行视图**真的显示它**（不只是"认下来"）

只补 `case` 让它别退化成裸文本行，是**不够的** —— 这条恰恰最需要被看见。
所以：

- `store/run.ts` 新增 `case 'verify_skipped'`：时间线上一条 `warn` 条目，
  并把原因（含命令）收进 `state.verifySkipped`；
- `types.ts` 的 `RunState` 加 `verifySkipped: string[]`；
- `VerifyPanel.vue` 的 VERIFY 块加一个 **`跳过 N 次`** 徽标与列表 ——
  用琥珀色，与 violations 的红色（"出错"）区分开。
  **它既不是"通过"也不是"失败"，混进现有状态里就等于白做了。**

生成物随之 33 → **34 事件**（`npm run gen:expectations`）。

### 31.3 ★ 顺带修掉根因：**写死的期望值会把"契约更新"误报成"接口回归"**

改完之后 `test_partition.py` / `test_spec.py` / `test_audit.py` **三个测试红了**。
一查：**红的全是写死的常数**（`12` / `33` / `CONTRACT_RECORDED_*`），
不是分区逻辑 —— 上游按规矩加性加了一个事件，契约升到 `34 = 13 + 21`。

**这与统筹方本轮在同一份 `CHANGELOG` 里自陈的失误是同一个缺陷**
（他们原文：「我的契约测试写死了 12 / 21 / 33 …… **写死的期望值会把"契约更新"
误报成"接口回归"**」）。**我这边有同一个毛病。**

**修法与他们同构，且更彻底一点**：不是把常数从 12 改成 13，
而是让**常数的来源变成契约**：

```python
# bridge/partition.py
recorded_snapshot() -> {upstream_events, upstream_phases, total_events, source}
# 读 .interface_contract/interface-contract.json 的 event_partition.observed
# 与 phases_partition；读不到才回退 CONTRACT_FALLBACK_*（离线镜像不存在时用）
CONTRACT_RECORDED_* = recorded_snapshot()[...]     # 兼容旧名，模块加载时求值
```

这与 `contract_vocab.owner_of()` / `upstream_rule()` 是**同一个模式**（D2 那次的做法）：
**凡契约已经声明过的事，本模块不再存第二份副本。**

于是判据变成「**实测 == 契约声明**」：契约更新时测试自动跟随，
而实测与契约不一致**照样红**。

### 31.4 三个测试的判定也跟着改了（"上游落后"≠"逻辑错"）

修完根因后，剩下的红是**配置**造成的，不是缺陷：自带副本是旧的（少那个事件），
于是

| 现象 | 是缺陷吗 | 处理 |
|---|---|---|
| 推导 12 ≠ 契约 13 | **不是** —— 这是"你这份上游落后于契约"的**真信号** | 落后时 SKIP 该等式，但断言**差集恰好是契约新增的那一个**（不是别的漂移） |
| `dead_calibrations=["verify_skipped"]` | **不是** —— 标定表为契约的新上游备着 | 落后时 SKIP，并打印原因 |
| `verdict=backend-action`（`U-dead-event`） | **不是** —— 正是 `U-dead-event` 存在的意义 | 落后时不要求 `ok`，要求判定**解释得通** |

这正是我这几轮一直在用的那条：**按配置分流，别把"配置导致的不可测"记成失败**
（与 `doctor.py` 的 bundled→WARN / 外部→FAIL、`test_two_entrypoints` 的 SKIP 同一条判断）。

### 31.5 验证

**机械 diff（权威内容；本机无 git，用 `-Verify`）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-141024_v14-arch-a2b
```

```
[改动] 18
   ~ bridge\partition.py          ← 根因修复：快照改为从契约读
   ~ bridge\spec.py               ← 校准 verify_skipped
   ~ frontend\src\store\run.ts    ← case 'verify_skipped'
   ~ frontend\src\types.ts        ← RunState.verifySkipped
   ~ frontend\src\components\VerifyPanel.vue
   ~ frontend\src\generated\expectations.ts     ← 生成物（33 → 34 事件）
   ~ tests\unit\test_audit.py / test_event_contract.py /
     test_partition.py / test_spec.py           ← 期望值改为从契约读 + 按配置分流
   ~ README.md / CYCLE.md / docs\{ARCHITECTURE,CHANGELOG,MODULES,OPERATIONS,VERSIONS}.md
   ~ frontend\dist\index.html
[新增] 2
   + frontend\dist\assets\index-OwZY1JQb.css
   + frontend\dist\assets\index--XpunQ0C.js
[删除] 2
   - frontend\dist\assets\index-CsUZBNxG.js      ← 旧 bundle（前端改了 → 哈希变）
   - frontend\dist\assets\index-DiEIbo8g.css
```

| 检查 | 命令 | 结果 |
|---|---|---|
| **统筹方契约测试** | `test_interface_contract.py --backend 8260` | **32/32**（`no uncalibrated events` PASS） |
| `/api/spec` 诊断 | 直连 | `uncalibrated_events = []`、`dead_calibrations = []` |
| 事件分区 | 直连 | `13 + 21 = 34`（与契约一致） |
| 事件契约 | `python tests/unit/test_event_contract.py` | **29/29**（指向上游）/ 20/20（自带，含 SKIP） |
| 分区 | `python tests/unit/test_partition.py` | **59/59** / 55/55 |
| 归属判定 | `python tests/unit/test_audit.py` | **107/107** / 107/107 |
| 离线全量 | `python tests/run_unit.py` | **35/35** / **35/35** |
| 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误 / 56 模块，34 事件 |
| layout / doctor | — | exit 0 / exit 0 |

### 31.6 尚未做

- **界面渲染未人眼看**：`verify_skipped` 的徽标与列表只过了 `vue-tsc` 与构建。
  它要真出现需要**制造一次"跳过验证"**（缺 pipeline），本轮没有构造那个场景。
- **`verify_skipped` 的端到端未跑**：没有真跑出一轮含该事件的运行 ——
  证据停在"校准存在 + 归约器有 case + 契约测试通过"这一层。
- **本轮未交九节评估文档**：本轮是**校准**（不是接口改动），
  统筹方给的验收是单一条件（`uncalibrated_events` 为空），已附机械证据。
  但其中 §31.3 的**根因修复**是实质改动，若需要正式评估文档请说一声，我补。

---

## 32. TRANSPARENCY-UI：把「为什么」显示出来 —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-27 13:0x），契约 **v1.0.24**。
指令原文：**「本轮是显示层，不改判定逻辑。」**
验收方式是**打开界面**，用固定样例 `run_20260927_125647_5a3297` 逐条核，
并明确说：**「不要用'我们自己的测试过了'当作完成依据。」**

### 32.1 起因：一次 `passed` 的运行，判据换了一张考卷

样例的目标是「设计随机障碍物生成规则，**保证起始点与目标点至少可通**，
写蚁群算法，**连续测试验证**，**生成报告**」→ `status=passed`。而机械事实是：
没有连通性检查、`ant_colony.py:40` 用了 `np.random.choice` 却没 `import numpy`、
`test_ant_colony.py` **一次都没被执行**、工作区里**没有报告文件**。
模型全程 **0 次执行代码**（`tool_call` = `write_file`×5 + `read_file`×1）。

唯一被真跑过的是判据本身，而它是这样变的：

```
seq 35  (b) 生成障碍物 + 跑蚁群 + 检查报告              → 执行，passed=false
seq 56  (c) assert generate_obstacles                  → 执行，passed=true
seq 57  (a) assert obstacle_generator.generate_obstacles((10,10))  → 候选被拒
seq 74      (c) 被记录为交付判据                        source=model
```

**(c) 只证明"这个名字能 import 进来"**，它在 (b) 失败之后被换上来，**代码一行没改**。
而这件事在界面上完全看不见。

> ★ 注意本轮的**顺序纪律**：真实序号是 `(b)@35 → (c)@56 → 被拒的(a)@57 → 记录@74`，
> **不是**需求文档里为了讲故事而排的 (a)→(b)→(c)。界面**按 seq 原序显示**，
> 不重排、不改写因果 —— 一重排，"谁在谁之后"这件事就变成了编的。

### 32.2 三条纪律（这一轮真正的交付物）

1. **只显示事件流里真实存在的东西。** 后端没给的字段显示「后端未提供」，
   或用**实测替代物**顶上并**标明它是替代物**。编一个字，
   就等于把"判据换了看不见"换个地方再犯一次。
2. **推断必须标成推断。** 「上一条执行失败了」若是我按 seq 相邻读出来的，
   就写明"按序号相邻推断"；后端 B1 给出显式 `replaced_command`/`previous_passed`
   时**另起一行**并注明是后端给的。两种来源**不能同形**。
3. **缺席也要有归因。** 没有 `self_report` 时显示
   「本次运行没有收尾自述：该运行的结局词是旧词表 `passed`，后端 C1 交付前这类事件不会产生」。
   空白面板会被读成"模型没什么要说的"——那是最坏的一种误导。

### 32.3 四块视图

| 块 | 视图 | 数据 | 落在哪 |
|---|---|---|---|
| **A2** | 决策依据：每轮 `reasoning` + 「这一轮打算做什么」 | `orchestrator_decision` + `task_start` | `TransparencyPanel` tab 2 |
| **A3** | 模型回合原话：`task/step` → 说了什么 → 调了什么 → 结果 | `model_reply` + `tool_call` + `tool_result` | tab 3 |
| **B4** | 验收判据演化：命令 / 结果 / 采纳或拒绝 / 理由 | `verify_probe` + `verify_skipped` + `verify` | tab 1（**默认**） |
| **C3** | 收尾自述 + `fact_check` 矛盾 | `self_report`（后端 C1） | tab 4 |

- **B4 默认打开**：需求原话说它是"本次最该被看见的东西"，藏在第三个 tab 里等人去找 = 没做。
- **反面事实挂在标题栏**（不随 tab 隐藏）：`fact_check` 矛盾数、以及"本次没有自述"。
  需求原话是「放在最显眼处」「不是折叠在角落里」。
- **"被拒"与"失败"分开**：`rejected` 说的是"这张考卷不该用"，
  `failed` 说的是"用了，没考过"。混成一个词就看不出这次到底是"判据写错了"还是"模型没做到"。
- **"是否被最终记录"是另一根轴**（`adopted`），不压进执行结果里。

### 32.4 D3：结局四值 + 判据来源（指令第 5 节的追加项）

样例的 `report.verify.source = model` —— **这次是模型自己给自己判过的**。
界面现在把它显示在**结论旁**（`VerifyPanel` 的 VERIFY 格 + 透明化条标题栏）：

```
结局 pass（旧词表）   判据来自 模型自拟
```

`abstain`（模型声明做不到）/ `invalid`（任务或工装本身有问题）成为一等公民；
样例的结局词仍是**旧词表** `passed`，界面**如实标出这一点**并写明
"四值尚未交付，不能从这里读成'这次不是那两种'"。

### 32.5 ★ 机械验证：固定样例 → **真实归约器** → **真实 SSR 渲染**

以前前端只有 `vue-tsc` 与 `vite build`，**两者都不执行归约器、不渲染组件**。
本轮补上 `frontend/scripts/replay-check.mjs`（`npm run check:transparency`）：

1. 用 esbuild 把 `src/store/run.ts` **就地打包**（不复制逻辑），
   把固定样例的 77 条事件喂进去，断言四块视图的读数；
2. 用**同一份 vite 配置**做 SSR 构建，把 `TransparencyPanel.vue` 与
   `VerifyPanel.vue` 用 `vue/server-renderer` 渲染成 HTML，
   断言那几行字**真的在 HTML 里** —— "读数对、面板没显示"是最阴的失效。

`tests/unit/test_transparency_ui.py` 把它拉进门禁（缺 node 时按配置分流 SKIP）。
实测 **45/45**，四条验收各有独立断言。

> 它**不是**人眼验收的替代：排版、折叠、"看不看得懂"仍然只能由人判。

### 32.6 ★ 顺带修掉三处"界面对不上机械事实"

修这一轮的路上撞见的，都属于同一类毛病（**界面说了事实不支持的话**）：

1. **`bridge/hooks.py:74` 把长参数换成"前 6 行 + `…（共 275 字符）`"**，
   而旧的时间线摘要对**预览串**取 `.length` → 显示"写入 …（**235** 字符）"。
   真值 275 就写在同一个字符串里。改为优先读事件声明的真值（`store/args.ts`）。
2. **`TaskPanel.vue` 把编排器的理由标成「主模型推理」**，
   `run.ts` 的时间线标题写「**主模型**决策 → continue」。
   事件名就叫 `orchestrator_decision` —— **说错了人**。透明化的第一步是别把人认错。
3. **"什么都没干"的回合**（`t4` 第 3 步：无文字、无工具调用）与
   "只调工具"被渲染成同一句"（本轮无文字，直接调用工具）"。两者分开。

**必须记下的过程事故**：我用 PowerShell 5.1 的 `Get-Content -Raw` / `Set-Content`
往返改 `transparency.ts`，中文被读成 GBK 再写成 UTF-8 + BOM ——
**文件全毁，而 `vue-tsc` 与构建照样通过**。恢复靠重写整文件。
因此补了一个廉价门禁（`test_transparency_ui.py` 第 [5] 组）：
扫 `frontend/src/**/*.{ts,vue}` 的 **BOM** 与 **GBK 乱码特征**（全库命中 0，不误伤）。

### 32.7 ★ 中途发现：上游**已经实装**了后端那一半，但**换了事件名**

做到一半去核对上游，发现 `D:\PythonProject\SimpleAgent2_Cycle` **已经交付了**
`TRANSPARENCY-BACKEND`（A1 + B1 + C1 + C2），而且**刻意没有**用需求里建议的名字：

| 需求里的建议 | 上游实际发的 | 位置 |
|---|---|---|
| `orchestrator_decision`（补 `reasoning`/`intent`） | **`orchestrator_round`**（`reasoning` + `tasks`） | `core/contract.py:172`，`core/coding_cycle.py:394` |
| 替换类事件带 `replaced_command`/`previous_passed` | **`verify_criterion`**（`action` + `previous_command`/`previous_passed`/`reason`） | `core/contract.py:181`，`core/coding_cycle.py:407` |
| 加性事件 `self_report` + 报告字段 | **`self_report`**（含 `fact_check` 与 `fact_check.contradictions`） | `core/contract.py:189`，`core/coding_cycle.py:755` |

上游在 `core/contract.py:178-180` 写明了为什么避开 `orchestrator_decision`：
**那个 kind 由本仓库的 bridge 发（`bridge/hooks.py`），两个生产者发同一个 kind
会让审计无法判断哪条权威**。两边数据同源（同一个 `_decide` 返回值）。
**这个判断我认同**，所以界面**两个来源都认**（老运行只有 bridge 那条）。

**由此暴露的接口级缺口（附两处位置）**：

1. **契约主本落后于上游**：三个新事件在上游标的是 `since="1.2"`，而
   `core/contract.py:57` 的 `CONTRACT_VERSION` 仍写着 `"1.1"`；
   契约主本（`01-contract/interface-contract.json`，v1.0.24）里也没有它们
   —— 主本与镜像我核对过 SHA256，**逐字节一致**，所以不是镜像陈旧。
   实测（真上游，标定前）：`/api/spec` 报
   `uncalibrated_events=[orchestrator_round, self_report, verify_criterion]`。
2. **`verify_skipped` 的 `command` 恒为空**（那条被拒的判据只在 `reason` 文本里）：
   上游有**两个**发 `verify_skipped` 的地方 —— `core/coding_cycle.py:379`（未注入 pipeline）
   带 `command`，而 `:384`（**自拟判据被拒**）**硬编码 `command=""`**。
   固定样例里那条 `seq=57` 就是后者，所以它的命令只出现在 `reason` 里。
   界面因此显示"该事件未单独记录命令"，而不是去 `reason` 里猜一个命令出来。

**处理方式**（不放宽任何门禁）：

- 给三个事件**补 `/api/spec` 校准**（与 `verify_skipped` 那次同一动作）；
- **不写 `case`**，改为采集器用 `RECOGNIZED_KINDS` **声明**词表
  （声明就是 `HANDLERS` 的键，代码真的在用）；`test_event_contract.py` 的
  "前端认得的词"改判为 `case ∪ 声明`；
- 对"自带旧副本"那种配置，给三个名字一条**有到期条件的豁免**：
  逐名去**参考上游的 `core/contract.py`** 里核实 `EventSpec` 真的存在
  （核不到就 FAIL），并在契约同步后删除。

### 32.8 未做 / 依赖后端

- **D1（结局四值 `pass/fail/abstain/invalid`）没有交付**：上游
  `CONTRACT_VERSION` 仍是 `1.1`，全仓库 grep 不到 `abstain`/`invalid`。
  所以界面上"旧词表"提示是**如实的**，不是保守：现在的词表里确实
  **没有**"模型声明做不到"与"任务本身有问题"这两个位置。
- **C3 的自述文本只能是夹具**：`self_report` 由模型产生，我离线造不出真模型的话。
  所以 `tests/diagnostics/make_transparency_fixture.py` 用
  **上游自己的 `core.self_report.fact_check()`** 去核对一份明写的夹具自述
  （机械事实取自固定样例的 `meta.json`）—— "矛盾能不能被检出来"由**后端代码**
  判定，不由我判定。**真跑一次带 `self_report` 的运行仍然没有做。**
- **多 attempt 运行未构造**：判据列表是**一条按 seq 的平铺序列**（事件流本身的结构），
  跨 attempt 的"上一条失败"已被阻断（只在同一次尝试内陈述），但没有真实多 attempt 样例可验。
- **`relaxed` 结局没有位置**：`bridge/spec.py:305` 的状态词表里有 `relaxed`
  （人工放宽），它既不是 `pass` 也不是 `fail`。D1 的四值没有覆盖它 ——
  界面把它显示成"未产出结局"，**不替它归类**。

### 32.9 ★ 契约滞后：**按方向分流**，并让三处"永远是红的"检查回到可读状态

把上游拿出来真跑之后，**六个门禁红了**，红的全是同一件事：
`test_partition`（6 项）/ `test_audit`（1 项）/ `doctor`（2 项）都在说
「实测与契约不一致：**多** `orchestrator_round` / `self_report` / `verify_criterion`」。

**这不是实现错，方向是"契约主本落后于上游"**（见 §32.7）。
但"不一致就 FAIL"这条判据**分不出两个方向**：

| 现象 | 含义 | 该怎么判 |
|---|---|---|
| 契约有、实测**没有** | 上游**删了**它承诺过的东西 | **真回归** → FAIL |
| 实测有、契约**没有** | 上游**加性**新增，主本该跟上来 | **契约滞后** → 说清楚，不是实现错 |

只判第一个方向，第二种就会让门禁**永远红着** —— 而"永远红着"的检查等于没有检查
（`bridge/partition.py` 的模块注释与 `doctor.py` 的 bundled→WARN 是同一条纪律）。

**改法**：`bridge/partition.py` 新增 `CONTRACT_LAG_KINDS`（**逐个列名**，不是"凡是多出来的都放过"）：

- `check_against_contract()` 现在分开算 `extra` / `missing`：
  `missing` 或 `extra` 里**没登记**的 → 照旧 FAIL；
  已登记的滞后 → 记进 `contract_lag`，并且**总数期望值按「契约 + 滞后」比**。
- `/api/spec` 的 `diagnostics` 新增 `contract_lag` + `contract_lag_note` ——
  **必须显示出来**，否则"实测与契约不一致"没人看得见。
- `test_partition.py` / `test_audit.py` / `check_contract_report.py` 的期望值改为
  **从 `CONTRACT_LAG_KINDS` 推导**，不再写死 12/13/34（§31.3 的同一个教训，
  这次是镜像落后而不是我的常数落后）。
- 关键：**反向仍然会红**。实测负向：把 `invented_event` 塞进推导 →
  `★ 事件分区错了自检会红` 立刻报
  「多 `['invented_event']` 少 `[]`（另有已登记滞后 …）」。
- `doctor.py` 的「无死标定」与「前端无孤儿 case」在 **bundled** 配置下降级为
  `WARN` 并写明理由（标定为契约的新上游备着），指向真上游时照旧 `FAIL`。

### 32.10 ★ 顺手修掉的两件事（都是被门禁抓出来的）

1. **`/api/audit` 的"前端认得什么"少算 3 个**：
   `frontend/src/generated/expectations.ts` 与 `bridge/spec.frontend_event_kinds()`
   都只扫 `store/run.ts` 的 `case`，而本轮三个新事件由采集器的 `RECOGNIZED_KINDS` 声明。
   后果不是"少显示"，是**审查会说错话**（把"前端早就认得"报成"前端没跟上"）。
   两处都改成 `case ∪ 采集器声明`。
   实测（真上游，用真实 `expectations.ts` 驱动审计）：`verdict = ok`。
2. **从仓库根跑夹具脚本会在仓库根留下 `workspace/`**：
   `tests/diagnostics/make_transparency_fixture.py` 起初没切 CWD 就
   `import core`（上游的相对路径是 CWD 相对的，`core/__init__.py` 连带 import 的模块会建目录）。
   **`tests/unit/test_isolation.py` 当场地报了 `FAIL 仓库根无 workspace/`** ——
   这是本仓库第二次出现"来路不明的仓库根 `workspace/`"（上一次没能复现，
   现在有了机制解释）。修法是 import 前切到运行根（与 `tests/_bootstrap.py` 同一条判据）。
   顺带把两次的来源写进 `docs/DIAGNOSTICS.md` §8.3，免得下次再从零查。

### 32.11 验证（最终）

| 检查 | 命令 | 结果 |
|---|---|---|
| 透明化读数 + 新事件 + 夹具 + 真渲染 | `npm run check:transparency` | **66/66** |
| 前端单测（含编码门禁 + 夹具来源核对） | `python tests/unit/test_transparency_ui.py` | **50/50** |
| 事件词表门禁（自带副本 / 真上游） | `python tests/unit/test_event_contract.py` | **21/21** / **30/30** |
| 三条分区（自带副本 / 真上游） | `python tests/unit/test_partition.py` | **55/55** / **60/60** |
| 归属自审（自带副本 / 真上游） | `python tests/unit/test_audit.py` | **107/107** / **107/107** |
| 标定（自带副本 / 真上游） | `python tests/unit/test_spec.py` | **42/42** / **43/43** |
| 夹具可复现（后端 `fact_check` 重新生成） | `AGENT_UPSTREAM_DIR=… python tests/diagnostics/make_transparency_fixture.py` | **6/6** |
| 离线全量（两种配置） | `python tests/run_unit.py` | **36/36 文件，exit 0** |
| 体检（两种配置） | `python scripts/doctor.py` | **失败 0 项**（bundled WARN 10 提示 / 上游 WARN 6 提示） |
| 目录归属 | `python scripts/layout.py --check` | exit 0 |
| 前端类型 / 构建 | `npm run typecheck` · `npm run build` | 零错误 / 通过（期望 37 事件） |
| 备份前验证 | `.\scripts\backup.ps1 -Label v16-transparency-ui` | 单测 36/36 · layout 通过 · typecheck 零错误 · **端到端 17/17** |
| 机械核对改动清单 | `.\scripts\backup.ps1 -Verify -From 20260927-105719_v15-verify-skipped` | 见九节评估文档 §3 |

---

## 33. TRANSPARENCY2-UI：交付新鲜度、任务面板、结局四值、拆解合规 —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（2026-09-27，契约 **v1.0.25**）+ `WORK-ORDER.md` 的 **P1–P4**。
起因：`REVIEW-20260927-instability.md`（同一条指令两次运行，**14 个任务 vs 19 个**，判据与错误都不同）。

> ★ **先记一条：统筹方主动更正了自己的派单。** 上一轮他们把 A1
> （`orchestrator_decision` 补 `reasoning`）**派给了后端**，而那个 kind 是本仓库
> `bridge/` 发的（`bridge/hooks.py:307-310` 早就填了 `reasoning`）。
> 他们在契约里写了更正并说"**你们做对了**"。这条值得记下来：**派错侧是真实成本**
> （我这一轮为它多花了一整轮核对）。

### 33.1 【P1】🔴 `dist` 陈旧 —— 用户看到的不是交付的那一版

**统筹方实测**（`deploy-freshness.py`，重新构建后逐文件比对，不看 mtime）：

```
服务的 js        = index-BcJOtip4.js
当前源码重新构建 = index-BazGZyJn.js      ← FRESHNESS state = fail
```

**根因（两个时间点，已查明）**：

| 时刻 | 事件 |
|---|---|
| **13:43:17** | `dist/index.html` 被构建（当时的 `gen-expectations.mjs` 还是旧的） |
| **13:43:42** | 我把 `gen-expectations.mjs` 改成"前端词表 = `case` ∪ 采集器声明" |
| 13:49 / 13:52 | 两次备份的 preflight 只跑 `npm run typecheck`（它**只重新生成**
`src/generated/expectations.ts`），**没有重建 dist** |

于是交付物里的那份 JS **永远是 34 个事件**，而源码里已经是 37 个：
**改过的东西，不一定就是交付的东西。** 逐字节确认：旧产物里没有
`orchestrator_round` / `self_report` / `verify_criterion` 三个串，新产物里有。

**修法（三层，避免只靠"下次注意"）**：

1. **`scripts/freshness.py`**（新）：不看 mtime，**真的用当前源码构建到临时目录**，
   再逐文件比 `index.html` 引用的资源名与内容哈希 —— 与统筹方同一条判据，但离线可跑。
   `--fix` 直接重建；`--dist <dir>` 供负向测试。
2. **`tests/unit/test_dist_freshness.py`**（新，进全量门禁）：正向 `state=ok`；
   **负向**把 dist 里的 JS 追加一个字节 → 必须报「同名但内容不同」
   （这才是"门禁不是永远绿"的证据）。
3. **`backup.ps1` 的 preflight 增加"交付新鲜度"一项** —— 因为**根因就在这个函数里**：
   它跑 typecheck（会改生成物）却从不重建 dist，然后一起打快照，正好把两者分了家。
   现在 dist 陈旧就**不让备份通过**。

**交付产物哈希**（本版）：`index-Bu5N1N67.js` sha256:`d30297e6f3e7e769` ·
`index-yo24bi27.css` sha256:`f68c3a6352e41d3f`（`python scripts/freshness.py` 可复现）。

### 33.2 【P2】任务面板：任务一多就失去可视化价值

用户原话：「右上角的每一个任务状态，这个设计不错，但是**太多了就会压缩，也不会自动滚动**，
完全失去可视化价值。」**实测那两次运行是 14 与 19 个任务**（统筹方说 10/11，
按 `task_start` 数实际更多；`run_20260927_225939_f4daaa` 里 `t9` 还出现了**两次**）。

**统筹方猜的那一行是对的，但只说了一半。** 他们指出 `.task` 缺 `flex-shrink: 0`；
我去核实，机制确实如他们所说 —— 在有界高度的 flex 列里子项默认 `flex-shrink: 1`，
**先压缩、永不溢出**，所以 `overflow-y: auto` 永远不生效：**同一个机制解释了两句话**。

但只加 `flex-shrink` 还不够，另外三条要真做到：

| # | 要求 | 落点 |
|---|---|---|
| 1 | 不压缩 | `.task { flex: 0 0 auto }` + `min-height: 46px` |
| 2 | 可滚动 | `.tasks { max-height: 44vh }` + `.tasks__body { overflow-y: auto }` |
| 3 | 当前项自动在视野内（**手动滚过则不抢**） | `store/tasklist.ts` 的 `FollowMode` |
| 4 | 量大时降级可读 | `taskRows()` 折叠已完成，**当前项与失败项永远可见** |

**抽出纯函数**（`frontend/src/store/tasklist.ts`）是关键：`taskRows()` 的分组与
`shouldAutoFollow()`/`modeAfterScroll()` 的跟随决策都能**机械断言**，
不必靠人在浏览器里点。

**过程中被自己的断言抓住的两个坑**：

1. **任务 id 会重复**（实测 `t9` 出现两次）→ `:key` 只写 id 会让 Vue 复用错节点，
   而这类错误**只在运行时报 warning**，构建与类型检查都看不出来。key 改成带下标。
2. **"当前项永远可见"在运行结束时恰好失效**：跑完之后当前项状态也是 `done`，
   按状态分它就该进折叠区 —— 而那正是人回头看的时候。
   所以 `taskRows()` 增加 `keepIndex`：按**下标**把当前项钉住，不参与折叠。

### 33.3 【P3】结局四值 + 判据来源 + 审查独立性

契约 v1.0.25 之后，上游已经交付 `core/outcome.py`（`OUTCOMES = (pass, fail, abstain, invalid)`）
与 `build_verdict()`。所以这一轮我**不猜形状**，字段名照抄实现：

| 要显示 | 字段（照抄） | 位置 |
|---|---|---|
| 四值 | `outcome`（`+ outcome_kind`） | `core/outcome.py:89-104` |
| 判据来源 | `criterion_source`（caller/model）+ `criterion_trust` | 同上 |
| **是否独立** | `criterion_independent` | 同上（`core/outcome.py:102`） |

**通路做了两条，缺一不可**：

1. **`run_end` 事件带上这一组字段**（`bridge/runner.py` 的 `_verdict_of()`）——
   界面是事件驱动的，只放进报告就会出现"**实时看得到、回放看不到**"这种最难查的差异；
2. **报告那条路**（`GET /api/runs/{id}` 的 `run.report` → `store.ingestReportInfo()`）——
   **旧运行的事件里没有 verdict，只有报告里有**；拆解合规审查现在也只在报告里。

**三处刻意的"不猜"**：

- `criterion_independent` **缺失** → 显示「未给（判不了）」，**不是**「非独立」。
  `null` 与 `false` 是两件事：一个是"没给"，一个是"给了，且不独立"。
- 后端**没产出** verdict → 显示「后端没有产出结局四值」，**不拿 `run_end.status`
  硬套一个四值**（那等于替后端下一个它没下的判断）。兜底推导值另起一行、标明是推的。
- 结局词不在四值里 → 显示**原词** + `unknown`，不硬塞成 `fail`。

**踩过的一个真坑（已修，记下来）**：`readVerdict` 起初按"对象有没有键"判存在。
调用方若先拼一个固定键的壳（`{outcome: ev.outcome, …}`）再传进来，
`Object.keys` 一定是满的 → 返回一个 `raw=''` 的"verdict"，
**把「后端没产出」伪装成「产出了但认不出」**，旧运行的结局就这么被擦掉了。
现在判据是"**有键但全空 = 没有**"（`transparency.ts` 的 `readVerdict`）。

### 33.4 【P4】③ 拆解合规审查：`violated` 与 `undecidable` 分开

上游 `core/contract.py:207` 声明了 `decompose_review`（`since="1.3"`），
形状 `{principle, verdict: violated|ok|undecidable, evidence, checked_by, independent}`。
**但它还没有发出**（全仓 `_emit("decompose_review"…)` 一处都没有，只有 EventSpec + 报告键），
所以界面必须**两态都能显示**：有就逐条显示，没有就明说「后端尚未产出」——
**绝不画一个绿色的"审查通过"**。

三条硬规矩落到了代码里：

1. `undecidable` **与 `violated` 分两块**（颜色与措辞都不同：红「违反（要改）」/
   琥珀「判不了（审查范围不完整，既不是通过也不是违反）」）；
2. **`passed=true` 不足以**把这页画绿 —— 契约原话：「`passed` 只代表**机械条款**通过，
   `undecidable` 非空说明审查范围不完整，**不得**呈现为『审查通过』」；
3. 认不出的 `verdict` 值**留空**，**不归到 `ok`**。

顺带把上游另一个新事件 **`reuse`**（机械层复用性检查，**有否决权**）也标定 + 渲染了 ——
它是**真在发**的（`core/coding_cycle.py:507`），不认下 `/api/spec` 就会报未标定。

### 33.5 契约 v1.0.25 同步：`CONTRACT_LAG_KINDS` 到期，已验证删除

上一轮我登记的滞后项（`orchestrator_round` / `verify_criterion` / `self_report`）
**契约已经声明**（13 → 16，分区 34 → 37），所以那三个名字**按到期条件删掉了**。
这一轮上游又加了两个（`reuse` / `decompose_review`，都标 `since="1.3"`），
所以同一张表换成这两个名字 —— **机制不变，只是内容换了**。

### 33.6 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 透明化 + 新事件 + 夹具 + 真渲染（含 P2/P3/P4） | `npm run check:transparency` | **108/108** |
| 交付新鲜度（正向 + **负向**） | `python scripts/freshness.py` · `python tests/unit/test_dist_freshness.py` | `state=ok` · **6/6** |
| 前端单测 | `python tests/unit/test_transparency_ui.py` | 见 `docs/VERSIONS.md` 该版记录 |
| 离线全量（两种配置） | `python tests/run_unit.py` | **exit 0**（见评估文档 §4） |
| 事件词表（自带副本 / 真上游） | `python tests/unit/test_event_contract.py` | 见评估文档 §4 |
| 体检（两种配置） | `python scripts/doctor.py` | 失败 0 项 |
| 目录归属 | `python scripts/layout.py --check` | exit 0 |
| `.ps1` BOM（改完必跑） | `python scripts/fix_bom.py` · `python tests/unit/test_ps1_encoding.py` | 12/12 |
| 备份前验证 | `.\scripts\backup.ps1 -Label v17-transparency2-ui` | 见 `docs/VERSIONS.md` |
| 机械核对改动清单 | `.\scripts\backup.ps1 -Verify -From 20260927-134929_v16-transparency-ui` | 见九节评估文档 §3 |

---

## 34. 【P5 · 阻塞】挂钩包装器镜像签名 —— **系统跑不起来** —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md` 追加项（P5）。**症状**：

```
TypeError: install.<locals>._run_verify() takes 2 positional arguments but 3 were given
```

### 34.1 根因：D9 的教训**只学到了一处**

上游 v1.23 给 `run_verify` 加了一个**可选参数**（加性、向后兼容）：

| 位置 | 形态 |
|---|---|
| `D:\PythonProject\SimpleAgent2_Cycle\core\pipeline.py:361` | `async def run_verify(self, command: VerifyCommand, files: list[str] \| None = None)` |
| `D:\PythonProject\SimpleAgent2_Cycle\core\orchestrator.py:246` | `vr = await self.pipeline.run_verify(vc, files)` ← **两个位置参数** |
| `bridge/hooks.py:392`（旧） | `async def _run_verify(self, command):` ← **镜像了旧签名** |

于是**每一次运行在 ~6 秒内失败，验证整条链停摆**。而我们的单测**全绿** ——
因为这个包装器不在测试范围内。

**这正是 D9 的同类**：当时 `_emit` 包装器撞名（`got multiple values for argument 'kind'`），
改成"按上游真实签名绑定"才修好。**那个教训写进了注释，却没有推广到另外九个挂钩点。**

**审计结果（11 个挂钩点，9 个是镜像的）**：

| # | 挂钩点 | 旧写法 | 现在 |
|---|---|---|---|
| 1 | `CodingCycle._emit` | ✅ 已是透传（D9 修过） | 工厂 `make_emit_wrapper` |
| 2 | `CycleReport.enter` | ❌ `_enter(self, phase)` | 透传 |
| 3 | `CodingCycle.run` | ❌ `_run(self, goal, verify_command=None)` | 透传 |
| 4 | `CodingCycle._new_file_artifacts` | ❌ `(memory)` | 透传（staticmethod） |
| 5 | `CheckpointManager.commit` | ❌ `(self, label)` | 透传 |
| 6 | `CheckpointManager.rollback` | ❌ `(self, ref)` | 透传 |
| 7 | `Orchestrator._decide` | ❌ `(self, memory)` | 透传 |
| 8 | `Worker.run` | ❌ `(self, task, context)` | 透传 |
| 9 | `LLMClient.chat` | ❌ `(self, messages, tools=None, force_json=False)` | 透传 |
| 10 | `Worker._invoke` | ❌ `(self, name, arguments_json)` | 透传 |
| 11 | `CheckPipeline.run_verify` | ❌ `(self, command)` ← **本次炸的就是它** | 透传 |

### 34.2 修法：**一个工厂 + 一张名单**，不再手写十个签名

```python
HOOK_POINTS = ((模块:类, 属性名, 说明, 是否 staticmethod), ...)   # ★ 唯一名单

def bind_arguments(orig, args, kwargs) -> dict   # 按上游真实签名解出参数名（VAR_KEYWORD 展开）
def make_sync_hook(orig, around, *, label)       # 同步：around(named, call)
def make_async_hook(orig, around, *, label)      # 异步：async around(named, call) → await call()
def make_hook(orig, around, *, label)            # ★ 同步/异步用 iscoroutinefunction **问上游**
```

四条纪律（每条都是被真实事故逼出来的）：

1. **不镜像签名**：包装器就是 `(*args, **kwargs)`，原样 `orig(*args, **kwargs)`；
2. **同步/异步问上游**：`inspect.iscoroutinefunction(orig)` —— 手写这个判断就是又一份镜像；
3. **刻意不用 `functools.wraps`**：它会把 `__wrapped__` 指回原方法，于是
   `inspect.signature(包装器)` 会**报告上游签名**（看着像镜像），而实际能力是"什么都收"。
   外部工具（含统筹方的 `hook-compat.py`）按签名判断兼容性时，**看到的必须是真相**；
   所以工厂只手工复制 `__name__/__qualname__/__doc__`，并留
   `__bridge_hook__`（工厂印记）与 `__wrapped_orig__`（原方法）。
4. **`install()` 按名单遍历**，不再逐个手写赋值 —— 手写十处 = 十份会漂的镜像。

### 34.3 验收：真的跑一次，并走到 verify

新增 `tests/diagnostics/hook_verify_e2e.py`：把 **worker 换成桩**（直接写一个真文件，
不调模型），但 **Orchestrator / CheckPipeline / CodingCycle 全是真的** ——
也就是说**被 P5 打坏的那条链是真跑的**，只有"模型那一层"是桩。

实测（**真上游**）：

```
  本轮真跑到的挂钩点：8/8
  PASS  ★ 跑完没有异常（P5 形态会让它在 ~6 秒内抛 TypeError）
  PASS  ★ 走到了验证：发出 `verify_probe`
  PASS  ★ 验证真的执行了（`passed=true`）
  PASS  ★ 事件链完整：run_start → verify_probe → verify → cycle_end
  PASS  ★ `verify_probe` 带命令原文
  PASS  ★ 最终 phase 是 `record`（走完了 VERIFY 才可能到 RECORD）
通过 7/7
```

**自带旧副本配置下按配置分流 SKIP**（2/2）：那份副本的验证接线在
`FIX-VERIFY-WIRING` 之前，**本来就走不到 verify** —— 那是副本的问题，不是 bridge 的。
判据取自上游自己：v1.23+ 的 `run_verify` 才有 `files` 参数。

> **顺带一个实测确认**：这一跑把上一轮的后端事件也带出来了 ——
> `orchestrator_round` / `verify_criterion` / `decompose_review` / `reuse` / `self_report`
> 全部出现在事件流里，说明那些挂钩点不只是"装上了"，而是**真的在发**。

### 34.4 门禁：把"签名兼容"变成可执行的断言

新增 `tests/unit/test_hook_compat.py`（自带副本 18/18 · **真上游 21/21**）：

| # | 断言 |
|---|---|
| [1] | 名单 11 个 · 名单里的都装上了 · 没偷偷多挂 · 没有"有点没逻辑"的空壳 |
| [2] | 每个包装器的签名只许是「可选的 `self` + `*args` + `**kwargs`」（`self` 不算镜像） |
| [3] | 每个包装器**接得住上游真实参数**，**并且多加一个可选参数也接得住**（P5 的形态） |
| [4] | 同步/异步与上游一致（从上游读）· 每个包装器都带工厂印记 |
| [5] | 真回归：按上游形态真跑一次 `run_verify`，断言发出 `verify_probe` |
| [6] | **负向**：手写一个镜像包装器，上面的判据**必须**判它红 |

★ [3]/[6] 成对才有意义：[3] 让"上游加参数"这件事在**装钩子之前**就被发现；
[6] 证明这条判据不是永远绿。

### 34.5 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 挂钩点兼容（自带副本 / 真上游） | `python tests/unit/test_hook_compat.py` | **18/18** / **21/21** |
| 真跑一次走到 verify（真上游） | `AGENT_BACKEND_DIR=… python tests/diagnostics/hook_verify_e2e.py` | **7/7**（自带副本 2/2 + SKIP） |
| `_emit` 透传（D9 的原始防线） | `python tests/unit/test_hooks_passthrough.py` | 见全量 |
| 离线全量（两种配置） | `python tests/run_unit.py` | **37/37 文件，exit 0** |
| 体检 / 目录归属 / 新鲜度 | `doctor.py` · `layout.py --check` · `freshness.py` | 失败 0 项 · exit 0 · `state=ok` |

---

## 35. 【P5b · 阻塞】`NameError: name 'Worker' is not defined` —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（契约 v1.0.27）。**P5 修完 `TypeError` 之后，
错误换了一个，仍然是每次运行 ~6 秒必死**：

```
NameError: name 'Worker' is not defined
```

### 35.1 根因：函数内 import ≠ 模块全局

| 位置 | 改前 |
|---|---|
| `bridge/hooks.py:438`（`_around_invoke` 内） | `args = Worker._parse_args(arguments_json) or {}     # noqa: F821（install 时已 import）` |
| `bridge/hooks.py:500`（`install()` 内） | `from core.worker import Worker  # noqa: F401` ← **函数内局部 import** |

模块全局里**从来没有** `Worker`（实测 `hasattr(bridge.hooks,'Worker') → False`），
而 `_around_invoke` 查的就是模块全局 ⇒ 模型**第一次调用工具**的那一刻炸
（事件序 `task_start → worker_step → model_reply → error → run_end`），**一个文件都没写就结束**。

**★ 而 ruff 早就报了它**：`bridge/hooks.py:438:12: F821 Undefined name 'Worker'`
—— 被我自己写的那句 `# noqa: F821（install 时已 import）` 压掉了，**理由是错的**。

> **一句 noqa 能让门禁闭嘴，但改不了运行期的事实。**

### 35.2 为什么我的门禁全绿却漏了它（**比 bug 本身更值得记**）

| 门禁 | 为什么放过 |
|---|---|
| 全量单测 38/38 | `_around_invoke` 不在任何测试的调用路径上 |
| `test_hook_compat` [2]/[3] | 只验"**接得住签名**"（结构层），**没有真的调用它** |
| `hook_verify_e2e.py`（P5 那版） | **我把 worker 换成了桩** ⇒ `Worker.run`/`_invoke`/`LLMClient.chat` 三个挂钩点**被绕过**；我还把这件事**打印成"已声明的局限"**，而不是去关掉它 |
| `ruff` | **报了**，被 `# noqa` 压掉 |

> **两条教训，都落成了代码**：
> 1. **noqa 不能替代验证** ⇒ `ruff F821 --ignore-noqa` 成为常驻门禁（判据 G）；
>    另加一条**不依赖 ruff** 的等价判据：`dis` 扫挂钩体的 `LOAD_GLOBAL`。
> 2. **把缺口写进"局限"里，不等于评估过它** ⇒ harness 改成**不绕过任何挂钩点**
>    （只伪造最底层的模型 HTTP 客户端）。

### 35.3 修法（改前 → 改后）

```diff
- args = Worker._parse_args(arguments_json) or {}     # noqa: F821（install 时已 import）
+ # 走延迟函数（不是模块全局）；解析失败由 `_safe` 兜住 —— 挂钩自己的异常
+ # 绝不能让上游的工具调用失败（这是本模块第一条纪律）。
+ args = _safe(worker_cls()._parse_args, arguments_json) or {}
```

新增延迟取类（`bootstrap.install()` 之后才可 import 上游）：

```python
def worker_cls():
    from core.worker import Worker
    return Worker
```

并删掉 `install()` 里那句造成误解的局部 import 与我写的错误 `# noqa`。
**顺带把这次解析纳入 `_safe`** —— 挂钩自己的异常不许拖垮上游的工具调用。

### 35.4 ★★ 验收：真的跑一次任务 —— **`passed`**

在**临时实例**（指向真上游，真模型 `qwen2.5:7b`，端口 8300）上跑一次真实任务：

```
run_id  : run_20260928_212052_3d1143
status  : passed        phase: record
commit  : 4a1c68177d3a6ae04f1e5cc853dc79c6fe6ac686
touched : math_utils.py
verify  : passed=True  source=caller
```

完整事件序（挂钩点一个不少地真的走到了）：

```
queued → run_start → baseline → cycle_start → attempt_start → phase → round_start
→ orchestrator_decision → task_start → worker_step → model_reply → tool_call → tool_result
→ worker_step → model_reply → task_done → verify_probe → orchestrator_round → verify_criterion
→ plan → task_result → decompose_review → phase → files → manifest → phase → reuse
→ syntax → lint → phase → verify → phase → cycle_end → self_report → run_end
```

**这一次运行还顺手补掉了上一轮的两条"没有真实运行"**：

```
verdict          = {"outcome":"pass","outcome_kind":"verified","criterion_source":"caller",
                    "criterion_trust":"caller-authoritative","criterion_independent":true}
decompose_review = passed=False  violated=[P3]  undecidable=[P2,P5]  independent=False
reuse_checks     = {"checked":true,"passed":true,"blocking":[],"warnings":[]}
self_report      = ok=True  done=1
```

⇒ 四值 / 判据来源 / 独立性**都是真实运行产出的**（上一轮只能用后端函数造的夹具）；
**`reuse` 第一次有真实事件**。（该运行已复制进 `data/storage_data/runs/`，可在界面上打开。）

### 35.5 新增/加强的门禁

| 门禁 | 判据 |
|---|---|
| `test_hook_compat.py` **[6]** | 挂钩体**不许引用不存在的模块全局**：`dis` 扫 `LOAD_GLOBAL`/`LOAD_NAME`（**不依赖 ruff**）+ **负向**（假函数必须被扫出来） |
| `test_hook_compat.py` **[6] 判据 G** | `ruff check --select F821 --ignore-noqa bridge/` **零命中**；并**对照**不忽略压制也应为 0（证明没靠 noqa 遮） |
| `test_hook_compat.py` **[7]** | **生产路径冒烟**：装上挂钩之后真的调一次 `Worker._invoke`，断言发出 `tool_call`/`tool_result` |
| `hook_verify_e2e.py` | 改成**不绕过任何挂钩点**（只伪造最底层 `LLMClient._client`），并**逐点断言各自的事件真的出现** |

### 35.6 验证

| 检查 | 命令 | 结果 |
|---|---|---|
| 挂钩点兼容（自带副本 / 真上游） | `python tests/unit/test_hook_compat.py` | **25/25** / **28/28** |
| 判据 G | `.venv\Scripts\ruff.exe check --select F821 --ignore-noqa bridge/` | `All checks passed!` |
| 生产路径 e2e（离线，不绕过挂钩） | `AGENT_BACKEND_DIR=… python tests/diagnostics/hook_verify_e2e.py` | **10/10** |
| **真实运行**（真模型） | 临时实例 8300 + `POST /api/runs` | **`passed`**（`run_20260928_212052_3d1143`） |
| 离线全量（两种配置） | `python tests/run_unit.py` | 见 `docs/VERSIONS.md` 该版记录 |
| 体检 / 目录归属 / 新鲜度 | `doctor.py` · `layout.py --check` · `freshness.py` | 失败 0 项 · exit 0 · `state=ok` |

---

## 36. `_safe` 的契约：**它一个异常都没兜住** —— ✅ 已落地

**来源**：统筹方 `DISPATCH.md`（契约 v1.0.28）。本轮起因是**我自己的文档写了做不到的事**。

### 36.1 根因：`except BaseException: raise` 把 `except Exception` 变成死代码

```python
# bridge/hooks.py:48-55（改前）
def _safe(fn, *args, **kwargs):
    """挂钩内部一律走这里：进度出问题绝不能影响上游执行。"""
    try:
        return fn(*args, **kwargs)
    except BaseException:  # RunCancelled 要穿出去，见 progress.py
        raise              # ← 把**所有**异常都截走并重抛了
    except Exception:      # ← 永远走不到（死代码）
        return None
```

而模块抬头明确承诺：「**每个包装都兜住自己的异常，进度坏掉不能让 cycle 失败**」。
实测（判据 H）：`_safe(lambda: 1/0)` **抛出 `ZeroDivisionError`** —— **一个都没兜住**。

**为什么这不是"少挡一个异常"**：挂钩自身的任何 bug（`emit_progress` 撞上意外 payload、
`preview_args` 遇到没料到的类型）都会**杀掉用户的整轮运行**，
而用户看到的 `status=error` 与"模型做不出来"**长得一模一样** ⇒ **污染能力画像**
（那正是四值结局里 `invalid` 要解决的问题）。

★ **这是又一次 U- 类（声明 vs 实现不符），而方向是危险的**：
我的 `EVALUATION-HOOKS-PASSTHROUGH-2.md` §35.3 写着「解析失败由 `_safe` 兜住」——
**代码没有兜住**，那句话让人以为这一层已经被包住了。

### 36.2 同一类的第二处：**实参在进 `_safe` 之前求值**

```python
args = _safe(worker_cls()._parse_args, arguments_json)
#            ^^^^^^^^^^^^ 在 _safe **之外**求值 ⇒ 取类失败照样炸穿
```

统筹方点出了这一处。我接着**全量扫**了所有 `_safe(emit_progress, …)`：
凡**实参里带函数调用**的都在保护之外，最容易炸的有 5 处 ——
`preview_args(name, args)`、`command.label()`、`list(transitions)`、
`list(paths)`、`list(task.tool_hint)`。
⇒ 所以修法不是"把 `worker_cls()` 挪进去"，而是**让"构造 payload + 播报"整条都在保护内**。

### 36.3 修法

```diff
 def _safe(fn, *args, **kwargs):
     try:
         return fn(*args, **kwargs)
-    except BaseException:
+    except RunCancelled:
         raise
     except Exception:
         return None
```

新增两个内部函数，**把"求值"也包进来**：

```python
def parse_worker_args(arguments_json):
    """取 `Worker` 类并解析工具参数 —— **整条**都在 `_safe` 的保护范围内。"""
    return worker_cls()._parse_args(arguments_json)

def emit_safe(event_kind: str, build, *args):
    """播报一条事件，**payload 的构造也在保护范围内**。"""
    return _safe(lambda: emit_progress(event_kind, **build(*args)))
```

并把 5 处 emit 改成 `emit_safe(kind, _xxx_payload, …)`（payload 构造搬进内层函数）。

### 36.4 ★★ 验收：注入故障之后**整轮运行照样跑完**

`hook_verify_e2e.py` 新增 **[B] 故意注入异常**场景（monkeypatch `preview_args` 抛 `TypeError`）：

```
[B] 故意在挂钩里注入异常：**整轮运行必须照样跑完**
  phase=record · 异常=无
  PASS  ★★ 挂钩里的异常**没有**杀掉这一轮（cycle 跑完了）   None
  PASS  ★★ 而且它照样走到了 verify（坏掉的只是那一条事件）
  PASS  ★ 代价可见：`tool_call` 那一条事件确实**缺了**（不是静默假装成功）
  PASS  ★ 但流程本身照旧：run_start / task_start / cycle_end 都在
通过 12/12
```

改前这一注入会**杀掉整轮运行**（`status=error`，与"模型做不出来"同形）。

**同时验"修好 A 弄坏 B"的反面**（真实运行、真模型、重启后的实例）：

```
run_id  : run_20260928_221959_80417d
status  : passed        phase: record        touched: str_utils.py
verify  : passed=True   source=caller
verdict : {"outcome":"pass","criterion_source":"caller",
           "criterion_trust":"caller-authoritative","criterion_independent":true}
```

### 36.5 新增门禁

| 门禁 | 判据 |
|---|---|
| `test_hook_compat.py` **[8] 判据 H** | 行为：普通异常被吞（返回 `None`）/ 自定义异常被吞 / 正常值照旧透出 / **`RunCancelled` 仍穿出** / `KeyboardInterrupt` 穿出 |
| `test_hook_compat.py` **[8] 判据 I** | 结构：`_safe` 的**代码**（用 `ast` 摘掉 docstring 后）里没有 `except BaseException`、且确有 `except RunCancelled` + `except Exception` |
| `test_hook_compat.py` **[8] 负向** | 把**旧形态**喂给同一组行为判据，**必须判红** |
| `test_hook_compat.py` **[7] 修空洞断言** | 原来写的是 `check(…, True)` —— **硬编码 True 永远不会红**却计入 N/N（统筹方点出）；改成真的断言"没抛异常" |
| `hook_verify_e2e.py` **[B]** | 注入故障 ⇒ cycle 跑完 + 代价可见（事件缺一条） |

### 36.6 ★ 改这个写法**差点弄坏另一处**：两个 AST 扫描器只认旧写法

`emit_progress` 的"kind 在哪"有**两个**扫描器（`bridge/spec.py` 的 `_scan_calls()`
与 `test_event_contract.py` 的 `scan_kinds()`，后者决定 `/api/spec` 的事件分区）。
我改成 `emit_safe("kind", _build, …)` 之后，**两个都看不见那 5 个事件了**：

```
bridge 侧认到 0 个（改之前 21 个）· 总数 39 → 34
```

**它不报错、只是少认** —— 本仓库最怕的"静默少显示"。
**是我自己的三个门禁同时红抓到的**（`test_partition` / `test_spec` / `test_event_contract`）。

修法：两个扫描器都学会第三种写法；并新增判据 `test_hook_compat.py` **[9]**：
**hooks.py 里每一个 emit 调用点扫描器都必须认得**（当前 **16 ↔ 16**），
外加 5 个"最容易漏"的 kind 当金丝雀（`phase`/`files`/`task_start`/`tool_call`/`verify_probe`）。

### 36.7 验证

| 检查 | 自带副本 | 真上游 |
|---|---|---|
| `tests/unit/test_hook_compat.py` | **39/39** | **42/42** |
| `tests/diagnostics/hook_verify_e2e.py` | 分流 SKIP「走到 verify」 | **12/12** |
| `tests/run_unit.py` | **38/38 文件 exit 0** | **38/38 文件 exit 0** |
| `/api/spec` 事件分区 | —— | **18 + 21 = 39**（uncalibrated / dead 均空） |
| `ruff F821 --ignore-noqa bridge/` | `All checks passed!` | 同 |
| 真实运行（真模型） | —— | **`passed`**（`run_20260928_221959_80417d`） |

---

## 回归基线

任何改动后至少跑：

```bash
python tests/run_unit.py     # 离线，35 个测试文件
```

需要真实模型时再跑 `tests/bench/run_levels.py 1 1`（最快的一条正向路径）。
