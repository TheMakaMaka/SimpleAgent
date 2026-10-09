# SimpleAgent2_Cycle

> **同步至 CHANGELOG §47** —— 本文只描述**当前状态**；修复过程见 `docs/CHANGELOG.md`。

**一个面向自动编码的标准工作流 —— 模型可替换，不是某个模型的定制产物。**

主模型拆解任务、子模型执行、**程序强制校验**、失败可回退。

判断"是否标准工作流"的标准很具体：**换模型只应改配置，不应改工作流代码。**
为此项目把「机制」留在工作流层，把「数字与策略」全部收进适配层。

---

## 它做什么

给它一个目标，它会：

1. **规划** —— 主模型把目标拆成可执行的具体任务（PLAN）
2. **写码** —— 子模型调用工具落盘实现（WRITE）
3. **核对交付** —— 程序对照「声明的文件清单」与「实际产出」（MANIFEST）
4. **静态检查** —— 程序跑语法检查（CHECK）
5. **机器验证** —— 程序执行验收命令，**以退出码为唯一判据**（VERIFY）
6. **记录/回退** —— 通过则打检查点，失败则回退后重试（RECORD）

关键点：**"完成"由程序判定，不由模型自称。** 第 5 步是唯一的成败判据——
模型说"我完成了"不算数，验收命令退出码为 0 才算。

---

## 快速开始

### 1. 环境

实测环境：**Python 3.10.11**。

本仓库自带 `.venv/`，可直接用。若要重建，只需 6 个包
（`.venv` 里另有大量无关重型包，不必照搬）：

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install openai fastapi uvicorn httpx pydantic
```

| 包 | 实测版本 |
|---|---|
| `openai` | 2.44.0 |
| `fastapi` | 0.115.12 |
| `uvicorn` | 0.34.3 |
| `httpx` | 0.28.1 |
| `pydantic` | 2.11.5 |

### 2. 模型服务

默认连本地 Ollama：`http://localhost:11434/v1`，模型 `qwen2.5:7b`。

```bash
ollama pull qwen2.5:7b
ollama serve
```

### 3. 配置

```bash
cp .env.example .env
# 编辑 .env，填模型地址与预算；main.py 启动时会自动加载它
```

> **`.env` 会自动加载**（`main.py` 在读取任何 `ORCH_*`/`WORKER_*` 之前
> 调用 `load_dotenv()`）。优先级为「已导出的环境变量 > `.env` > 内置默认值」，
> 所以临时覆盖可以直接导出变量：
>
> ```powershell
> $env:ORCH_MODEL="qwen2.5:7b"
> ```
>
> ⚠️ **测试与诊断脚本不走 `main.py`**，因此**不会**加载 `.env`——
> 需要给它们配配置时请在 shell 里导出。
>
> `.env` 含 API key，**已加入 `.gitignore`，不要提交**。

### 4. 起服务

**必须在仓库根目录执行**（多处路径依赖 CWD）：

```bash
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

### 5. 验证 + 跑第一个任务

```bash
# 存活检查
curl http://127.0.0.1:8000/

# 确认模型接入参数（换模型后必查，problems 应为空数组）
curl http://127.0.0.1:8000/profile

# 跑一轮编码任务
curl -X POST http://127.0.0.1:8000/encode -H "Content-Type: application/json" -d "{\"goal\": \"在 workspace 下创建 add.py，实现 add(a, b) 返回两数之和\", \"verify_command\": \"import add\nassert add.add(2, 3) == 5\nprint(\\\"PASS\\\")\"}"
```

**接口一览**：

| 接口 | 说明 |
|---|---|
| `POST /encode` | **主入口**：一轮编码流程，含强制校验与检查点；可带任务级 `project_root` 与 `deliverables` |
| `POST /run` | 旧流程：只跑主循环+子循环，无强制校验、无检查点（保留用于对比）；可带任务级 `project_root` |
| `GET /profile` | 查看生效的模型接入参数与启动自检结果；`runtime` 段给出**运行根 / 工作区根 / 输出根**三个绝对路径 |
| `GET /` | 存活检查 |

---

## 文档导航

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| `CYCLE.md` | 一轮编码流程的**契约**：五阶段门禁、验证回流、回退纪律、不可动摇的三条纪律 | 想理解"为什么这么设计" |
| `docs/ARCHITECTURE.md` | **架构**：分层图与职责边界、完整数据流、三类校验的区分 | 要改架构或判断某逻辑该放哪层 |
| `docs/MODULES.md` | **模块与接口参考**：逐模块签名、工具清单表、文档与代码不一致清单 | 查具体函数/参数/返回值 |
| `docs/OPERATIONS.md` | **运维手册**：启动、接入新模型、故障排查、CycleReport 判读、升级回归清单 | 日常运维、排查故障、升级前后 |
| `docs/FRONTEND_CONTRACT.md` | **上游→前端兼容契约**：前端扫哪四处上游事实、只增不减规则、破坏性改动怎么做 | **改上游前先看这里**（否则前端会静默少显示） |
| `docs/EVALUATION-OPS-1.md` | **变更评估**（按统筹方模板九节 + C1–C8 自检）：`ops.service_down` 通道语义 | 要审这次契约语义变更时 |
| `docs/EVALUATION-ARCH-A1B.md` | **变更评估**：架构清单 A1b —— `/contract/check` 自述权威范围 + 两入口归属一致性 | 要审架构级 A1 的后端侧时 |
| `docs/EVALUATION-ARCH-D1.md` | **变更评估**：`P-phase-unknown` 改判 `both`/`degraded`（归因方向修正） | 要审"看到未知阶段该怪谁"时 |
| `docs/EVALUATION-ARCH-D7.md` | **变更评估**：D7 传输断点（`bridge_gate_steps` 被静默丢弃）+ `CONTRACT_VERSION` 升 `1.1` + D10/D5 两条新门禁 | 要审"声明了但没接上"这类失效时 |
| `docs/EVALUATION-FIX-VERIFY-WIRING.md` | **变更评估**：一个 `if` 决定了两个能力是否存在 —— 不带 `verify_command` 的真实目标**从不执行验证** | 要审"验证到底跑没跑"时 |
| `docs/EVALUATION-VERIFY-VACUOUS.md` | **变更评估**：自拟验收可以**恒真** —— `print('PASS')` 让"没做"也判成功（含"关掉开关必定复现"的反向证明） | 要审"验证到底有没有意义"时 |
| `docs/EVALUATION-TRANSPARENCY-BACKEND.md` | **变更评估**：**判据不得静默换弱**（换掉已失败的判据必须给理由）+ 自拟判据必须**调用**交付物 + 决策依据/判据演化/收尾自述与**交叉核对** | 要审"那次 `passed` 是怎么来的、还会不会再发生"时 |
| `docs/EVALUATION-TRANSPARENCY2-BACKEND.md` | **变更评估**：**结局四值**（`pass`/`fail`/`abstain`/`invalid` —— 没有 `invalid` 会把"判据写错"记成"模型不行"）+ 两条**有否决权**的机械关卡（复用性 P2 / 拆解合规 P3）+ 架构事实层 P4 | 要审"这台仪表的读数算不算数"时 |
| `docs/EVALUATION-TRANSPARENCY3-BACKEND.md` | **变更评估**：**判词必须描述产物**（P6：验前记内容哈希 + 清字节码缓存 + 对不上即 `invalid`）+ 符号表收模块级赋值（P7）+ 审查模式显式（P8） | 要审"这次判读的到底是不是那份产物"时 |
| `docs/EVALUATION-REUSE-SYMBOL-SCOPE.md` | **变更评估**：复用层符号反查的**名字撞车**（`app = Flask(...)` 撞 `app.py` ⇒ 正确代码被硬否决、模型还被带着去反思它）—— 修好且**不许靠关检查来修** | 要审"这条 blocking 是真错还是误判"时 |
| `docs/EVALUATION-TOOLCALL-NORM.md` | **变更评估**（P9）：工具调用**规范化**（18 个工具封闭 + 别名表 + 未知键结构化拒绝）+ 工具产出**检验**（信封 / 旧字符串仍可读）；含反空洞机械输出 | 要审"两次同义调用是不是同一个形状"时 |
| `docs/EVALUATION-ENVELOPE-WIRING.md` | **变更评估**（P9 追加验收 ③ / D33 后半）：**产出检验真的接到工具上**（`audit().envelope_tools` 非空 + 摘掉登记立刻变红），以及 D30 文档计数漂移的收口 | 要审"机制是接上了还是只建好了"时 |
| `docs/EVALUATION-OUTPUT-CONTRACT.md` | **变更评估**（P14/P15/P13/P11）：三个绝对根 + **任务级目标项目根** + **交付物对账**；verify 归因看判据来源；结构地图的覆盖率/新鲜度/范围/反向索引 | 要审"东西写哪、交付了什么、这次读数算不算数"时 |
| `docs/EVALUATION-PASS-EVIDENCE.md` | **变更评估**（P17）：**pass 必须带机械证据**（`checked_by` + `evidence_kind`：`executed`/`artifacts`/`static_declared`）；没有执行记录 ⇒ 不得记 pass | 要审"这个 pass 是靠什么通过的、换模型后读数还可比吗"时 |
| `docs/EVALUATION-DECOMPOSE-GATE-BLOCK.md` | **变更评估**（P18）：拆解关卡出厂默认曾从 `warn` 升到 `block`（**已由 P20 修正回 `warn` + `undecidable` 分档**，见下一行） | 要审"边界是建议还是门禁"时 |
| `docs/EVALUATION-REASONING-PROTOCOL.md` | **变更评估**（P19/P20/D43）：推理模型 `reasoning_content` 协议（**带 `tools` 必须回灌** —— 与工单字面相反，附官方 400 原文与反空洞）；拆解关卡退回 `warn` + `undecidable` 分档；**假换**冒烟走通换模型路径 | 要审"换模型这条路本身能不能走通、关卡会不会误否决"时 |
| `docs/EVALUATION-MEMORY-M1.md` | **变更评估**（P21 / M1）：**外部记忆库**的独立库（`core/context_store/`）—— 存储与检索 + **独立根** + 越界拒绝 + **归档非删除**；两路召回（关键词 / 结构符号）+ 漏召/误召读数；**只记分不决策、不接模型** | 要审"记忆层会不会把上下文限制换成看不见的检索错误"时 |
| `docs/EVALUATION-MEMORY-SCORING.md` | **变更评估**（P21 ★★）：**调用分算法必须与模型无关** —— `score(unit, query_context)` 唯一纯函数入口、四项构成相加 == 总分（时间衰减默认关闭）、定制加权显式配置（非法即拒）、校准三指纹可复现；**S-A 已实现 / S-B、S-C 如实标未实现** | 要审「记忆层的调用分会不会随模型变、换 scorer 会不会被误读成换模型」时 |
| `docs/EVALUATION-MODEL-TIERS.md` | **变更评估**（P22-A）：**模型档位 + 可启用模式（类插件结构）** —— 加一个推理模型 = **加一份档位、代码零改动**；档位缺失回落 `default`+`auto`（不是极端，且`fallback` 可见）；每个开关关掉 = 基线**同哈希**；`replay_contract_problems` 把「声明 vs 实现」变成**会红**的判据 | 要审「换模型要不要改代码、读数会不会把换档位读成换能力」时 |
| `能力评估报告.md` | **能力边界实测**：8 级难度阶梯结果、失败根因分类 | 想知道"它现在能干什么" |
| `docs/CHANGELOG.md` | **修复记录**：已验证的修复 + 可复现验证命令 + 尚未修复清单 | **排查某问题是否已修时先看这里** |
| `docs/VERSIONS.md` | **备份点记录**：每个版本的 commit、改了什么、验证结果、**精确回退命令** | 要回退到某个已验证状态时 |
| `docs/PENDING_DECISIONS.md` | **待确认清单**：只有项目所有者能定的事项（外部资源/策略/排期），含建议与默认行为 | 要拍板或想知道"卡在哪"时 |
| `docs/PUSH_TO_GITHUB.md` | **推送指引**：需要填哪些信息、提交前自检、token 安全 | 要传到 GitHub 时 |
| `tests/README.md` | **测试说明**：单测/基准/诊断三类怎么跑 | 改代码前后 |
| `.env.example` | 模型接入配置模板，含全部变量与推导说明 | 接新模型时 |

---

## 当前能力边界（如实说明）

**通过率 2/8。** 8 级难度阶梯实测（`qwen2.5:7b`）：

| 级别 | 任务 | 结果 | 耗时 |
|---|---|---|---|
| L1 | 单文件 / 单函数 | ✅ PASS | 4.6~9.5s |
| L2 | 单文件 / 控制流 + 边界 | ❌ FAIL | 62.2s |
| L3 | 单文件 / 递归 + 输入校验 | ❌ FAIL | 148.8s |
| L4 | 单文件 / 类 + 异常语义 | ✅ PASS | 5.4s |
| L5 | 多文件 / 跨模块 + 算法 | ❌ FAIL | 300.7s |
| L6 | 单文件 / 文本解析 + 聚合 | ❌ FAIL | 55.8s |
| L7 | 单文件 / 文件 IO + JSON | ❌ FAIL | 161.2s |
| L8 | 多文件 / 大程序 | ❌ FAIL | 172.4s |

**一句话结论**：

> 能自动、可靠地完成 **"写一个自包含的、无外部契约的纯函数文件"**。
> 一旦涉及 **异常语义 / 返回 vs 打印的区分 / 多文件协作 / 文件 I/O**，
> `qwen2.5:7b` 会在 2~6 个任务内耗尽重试预算并回退。

**一个重要的正面结论**：门禁与回退**完全正常**。6 次失败全部被正确判为
`phase=failed` + `rolled_back=true`，**没有一次把错误结果当成功交付**。

> **数据时效说明**：上表测于「验证结论回流」改造之后，但**早于**
> 「文件清单 manifest」的接入与路径归一化修复。manifest 的目的是让
> 多文件任务的失败被更早、更精确地发现（而非提升通过率），
> 所以通过率**预计不变**，但 L5/L7/L8 的失败原因会更精确。
> 详细实测结论与失败根因分类见 `能力评估报告.md`。

**失败分两类，不要混淆**：

| 类型 | 级别 | 性质 | 应对 |
|---|---|---|---|
| 模型能力类 | L2、L3、L6 | 规格已写清，模型仍按直觉实现 | 换更强模型；不适合在工作流里打补丁 |
| 架构缺口类 | L5、L7、L8 | 曾经没有"本轮该产出哪些文件"的显式模型 | 已由 manifest 机制解决（`CYCLE.md` §9） |

---

## 已知限制

**本表只列「当前仍存在」的限制。** 已修复项不在此处——修复过程与验证方式见
`docs/CHANGELOG.md`。上游文档只描述现状，避免"还没修"与"修了但文档没更新"混淆。

| # | 限制 | 影响 | 处理 |
|---|---|---|---|
| 1 | **数据库实现未落地** | 事件与快照落本地 `storage_data/` | 按计划只留 `Storage` Protocol；抽象可替换性已验证 |
| 2 | **快照回流的预算仍偏保守** | 结构化上下文段上限为 prompt 预算的 1/3（且 ≤1500 字符），长任务仍可能被截断 | 段内会写明"已截断"；需要更多就调 `ORCH_*` 或换更大上下文窗口 |
| 3 | **回退会清除未跟踪文件** | `git clean -fd` 会删掉你手动放进 workspace 的文件（执行前有警告列出清单） | 往 workspace 放文件前确认已被忽略。见 `docs/OPERATIONS.md` §9.1 |
| 4 | **`resolve_profile` 是两角色假设** | 加 REVIEW 角色会**静默继承 ORCH**（"以为请了审查员，其实是同一个模型审自己"），不报错 | 开启 REVIEW 前必须先改成显式角色表 |
| 5 | **`resolve_profile` 的 fallback 仍是两角色语义** | 准备启用 REVIEW 等新角色时，`fallback` 会静默顶替 | 新角色请改用 `resolve_role()`（显式角色表，未配置即"未启用"）。见 `docs/MODULES.md` §3 |
| 6 | **子任务串行执行** | 多任务延迟线性叠加 | 未在计划中 |
| 7 | `fetch_url` 的 **DNS rebinding 风险未消除** | 域名在请求时被解析到内网时拦不住；IP 字面量与 `localhost` 已拦截 | 需传输层 peer-IP 校验 |
| 8 | **前端实例默认加载它自带的 `backend/` 副本**（`AGENT_BACKEND_DIR` 未设时走兜底） | 上游的修复**一行都不会生效**，症状与"根本没修"逐字相同——已实际发生过一次（见 `docs/CHANGELOG.md §31`） | 在前端仓库根建 `.env` 写 `AGENT_BACKEND_DIR=D:\PythonProject\SimpleAgent2_Cycle`；用 `tests/diagnostics/backend_dir_check.py` 当场比对两份代码指纹 |

> **回退后端当前是 git**（实测 git 2.55.0，提交/回退/历史均正常）。
> 若 `GET /profile` 的 `checkpoint_backend.selected` 显示 `snapshot`，
> 说明 git 不可执行，已退化为文件快照兜底。

---

## 项目结构

```
main.py              FastAPI 入口：/run、/encode、/profile
core/                工作流层 + 适配层
  ├─ coding_cycle.py   一轮流程编排（PLAN→WRITE→MANIFEST→CHECK→VERIFY→RECORD）
  ├─ orchestrator.py   主循环：拆解任务 + 验证回流
  ├─ worker.py         子循环：用工具完成单个任务
  ├─ pipeline.py       门禁：manifest / check / verify 调度
  ├─ manifest.py       交付契约：声明 vs 实际
  ├─ symbol_index.py   结构事实：AST 扫描符号与依赖（+ 覆盖率账目 / 新鲜度 / 反向索引）
  ├─ runtime.py        三个根（运行/工作区/输出）+ 任务级目标项目根 + 交付物对账
  ├─ checkpoint.py     回退：git / snapshot 双后端
  ├─ memory.py         全局状态 + 验证结论回流
  ├─ model_profile.py  模型接入标准参数入口（适配层）
  ├─ llm.py            OpenAI 兼容客户端 + JSON 容错（适配层）
  └─ ...
tools/               18 个工具，按 profile 过滤下发（registry.py 为注册表）
storage/             会话与事件落盘（sessions/、storage_data/）
web/                 手机端审批页（远程人工决策）
tests/               单测 / 能力基准 / 诊断，见 tests/README.md
workspace/           模型产出的代码（草稿区，运行产物）；交付物的**输出根**是 outputs/
docs/                架构、模块、运维文档
```

---

## 不可动摇的三条纪律

改动本项目前请先读这三条，完整论述见 `CYCLE.md`：

| # | 纪律 | 为什么 |
|---|---|---|
| 1 | **验收标准不可被模型改写** | 验收标准由被考核方定义，整个校验层就失去意义 |
| 2 | **结构事实不许模型改** | 否则模型会读着自己写的过时文档，更确信一切正常 |
| 3 | **审查角色不得有自由否决权** | 否则等价于纪律 1 换个形式重来 |

> 纪律 1 是**踩过的坑**：早期实现里模型每轮都能用自己的 `verify` 覆盖调用方
> 指定的验收命令。模型曾把断言改写成
> `assert isinstance(factorial(-1), ValueError)` —— 一个**永远不可能成立**的
> 断言，导致实现正确也判失败。修正前的所有通过率数据都不可参考。
> 详见 `CYCLE.md` §2.2。
