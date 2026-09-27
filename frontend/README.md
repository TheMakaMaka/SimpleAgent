# SimpleAgent2_Cycle

> **同步至 CHANGELOG §31** —— 本文只描述**当前状态**；修复过程见 `docs/CHANGELOG.md`。

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

## ⚠ 工作方式：做出一版可行之后，先备份，再继续完善

**这是硬规矩，不是建议。**

这个项目根目录**没有 `.git`**（它是复制版，原仓库在别处迭代），所以改坏了没有
`git checkout` 可以救你。只要有一版跑通了，立刻留快照：

```powershell
.\scripts\doctor.py                        # 体检：一条命令查清哪里不对
.\scripts\doctor.py --triage               # 归因最近一次失败（不用人写报告）
.\scripts\backup.ps1 -Note "这一版做到了什么"   # 打快照（判据见下）
.\scripts\backup.ps1 -List                     # 看有哪些快照
.\scripts\backup.ps1 -Verify                   # 当前比最近一版改了什么
.\scripts\backup.ps1 -Restore -From <快照名>    # 回退（会先自动再备份一次）
```

什么算"可行"——**下面这些全过**：

| 检查 | 命令 |
|---|---|
| 单元测试全绿 | `python tests/run_unit.py` |
| 前端类型零错误 | `cd frontend && npm run typecheck` |
| 事件流端到端（需后端在跑） | `python tests/diagnostics/check_frontend_stream.py` |

**为什么必须成文**：不备份的话，"继续完善"和"把能跑的版本改坏"之间没有任何区别——
你既回不去，也说不清改坏了什么。而 `-Verify` 会告诉你这一版相对上一个节点动了
哪些文件，比事后翻记忆可靠。

细节与恢复清单见 `docs/OPERATIONS.md` §11。

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

> **`.env` 会自动加载**（`backend/main.py` 在读取任何 `ORCH_*`/`WORKER_*` 之前
> 调用 `load_dotenv()`）。优先级为「已导出的环境变量 > `.env` > 内置默认值」，
> 所以临时覆盖可以直接导出变量：
>
> ```powershell
> $env:ORCH_MODEL="qwen2.5:7b"
> ```
>
> ⚠️ **测试与诊断脚本不走 `backend/main.py`**，因此**不会**加载 `.env`——
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
| `POST /encode` | **主入口**：一轮编码流程，含强制校验与检查点（阻塞，跑完才返回） |
| `POST /run` | 旧流程：只跑主循环+子循环，无强制校验、无检查点（保留用于对比） |
| `GET /profile` | 查看生效的模型接入参数与启动自检结果 |
| `GET /` | 存活检查 |
| `GET /app` | **Vue 执行可视化前端**（需已构建 `frontend/dist`，见下节） |

---

## Vue 前端：实时执行可视化

`/encode` 是**阻塞**的——一轮 cycle 动辄 60~300 秒，期间什么都看不到。
要"跟踪进度"，前提是「一次运行」先成为可寻址、可订阅的对象，于是有了 `/api/*`
这一层异步接口和配套的 Vue 前端。

### 起前端

```powershell
.\scripts/run.ps1          # 需要时自动构建前端，然后起服务
```

或者手动：

```bash
cd frontend
npm install
npm run build          # 产物落到 frontend/dist
```

回到仓库根目录起服务，然后打开 **http://127.0.0.1:8000/app**。

> `frontend/dist` 不存在时 **`/app` 不会被注册**，其余接口一切照常——
> 前端是可选视图，不该成为后端起不来的原因。

开发模式（改前端代码即时热更，API 由 Vite 代理到 8000）：

```bash
cd frontend && npm run dev     # http://127.0.0.1:5173
```

### 它长什么样

![执行可视化](docs/images/frontend.png)

> 截图是**演示运行**的产物：点界面上的「演示运行」即可复现，不调用模型。

三列布局，六阶段流水线是主角：

| 区域 | 内容 |
|---|---|
| **执行流水线** | `PLAN → WRITE → MANIFEST → CHECK → VERIFY → RECORD`；当前阶段带旋转光环，完成画勾，失败变红抖动；连接线随推进流动 |
| **尝试轨迹** | 每次尝试的成败、耗时、是否被回退（`↺`）；重试时整条流水线扫光重置 |
| **实时事件流** | 逐条推进的事件，可按阶段 / 工具 / 模型 / 异常过滤；贴底自动跟随，上翻自动暂停 |
| **任务与子循环** | 主模型拆出的任务、各任务用掉的步数、主模型的推理原文 |
| **门禁结果** | MANIFEST 的声明-实际差异、CHECK 的语法/lint 逐文件结论、VERIFY 的命令与输出 |
| **产物与工具调用** | 本轮写出的文件（点击直接看落盘内容）、最近的工具调用 |
| **运行概览 / 历史** | 尝试数、轮次、步数、工具调用、产物、回退、耗时；历史运行可点开回放 |

### 事件从哪来

```
CodingCycle ─┐
Orchestrator ├─ emit_progress() ─→ RunManager ─→ storage_data/runs/<id>/events.jsonl
Worker ──────┘   (ContextVar)        (独立线程)          │
                                                       ├─ GET /api/runs/{id}/stream   (SSE)
                                                       └─ GET /api/runs/{id}/events   (轮询/回放)
```

`bridge/progress.py` 的接收器挂在 ContextVar 上：**未绑定时是纯 no-op**，
所以工作流层加埋点不影响任何既有行为；并发跑多个 cycle 也不会串台。

### `/api/*` 接口

| 接口 | 说明 |
|---|---|
| `POST /api/runs` | 起一次运行，**立刻**返回 `run_id`（不阻塞） |
| `GET /api/runs` | 历史运行列表 |
| `GET /api/runs/{id}/stream` | **SSE 实时事件流**；带 `after=<seq>` 可断线续传 |
| `GET /api/runs/{id}/events` | 轮询式读取（SSE 不可用时的兜底，也用于回放） |
| `DELETE /api/runs/{id}` | 请求取消（协作式，下一个进度点生效） |
| `GET /api/workspace/file?path=` | 读 workspace 产物内容 |
| `GET /api/decisions` / `POST /api/decisions/{id}/answer` | 决策点的 JSON 形式，供界面内联作答 |
| `GET /api/health` / `GET /api/profile` | 顶栏用的后端与模型状态 |

### 端到端自检

需要后端已在 8000 端口运行：

```bash
python tests/diagnostics/check_frontend_stream.py
```

它验证的正是浏览器要走的那条路：`POST /api/runs` 不阻塞、SSE 逐条推进、
服务端主动 close、按 `seq` 断线续传不重不漏。离线部分见
`tests/unit/test_webui_runtime.py`（进度总线 + 运行管理器，38 项断言）。

---

## 文档导航

| 文档 | 内容 | 什么时候看 |
|---|---|---|
| `CYCLE.md` | 一轮编码流程的**契约**：五阶段门禁、验证回流、回退纪律、不可动摇的三条纪律 | 想理解"为什么这么设计" |
| `docs/ARCHITECTURE.md` | **架构**：分层图与职责边界、完整数据流、三类校验的区分 | 要改架构或判断某逻辑该放哪层 |
| `docs/MODULES.md` | **模块与接口参考**：逐模块签名、工具清单表、文档与代码不一致清单 | 查具体函数/参数/返回值 |
| `docs/OPERATIONS.md` | **运维手册**：启动、接入新模型、故障排查、CycleReport 判读、升级回归清单 | 日常运维、排查故障、升级前后 |
| `docs/VERSIONS.md` | **版本记录**：每次备份的「改了什么 / 验证结果 / 怎么退」，由 `backup.ps1` **自动追加** | 想知道某版改了什么、或要退回去 |
| `能力评估报告.md` | **能力边界实测**：8 级难度阶梯结果、失败根因分类 | 想知道"它现在能干什么" |
| `docs/CHANGELOG.md` | **修复记录**：已验证的修复 + 可复现验证命令 + 尚未修复清单 | **排查某问题是否已修时先看这里** |
| `docs/LAYOUT.md` | **目录归属与转移流程**：哪些覆盖、哪些千万别动 | **把上游最新版拿过来之前** |
| `docs/DIAGNOSTICS.md` | **体检与失败归因**：一条命令查清哪里不对、为什么失败 | **出问题的时候** |
| `docs/EVALUATION-WF1-WF6.md` | **变更评估**：接口契约对齐改了什么、影响面在哪、哪些没验（按 C1–C8 自查） | **与统筹方对账时** |
| `docs/EVALUATION-OPS-WARNINGS.md` | **变更评估**：契约 v1.0.5 的 `warnings` 消费方义务与 ops 裁定 | **与统筹方对账时** |
| `docs/EVALUATION-ARCH-A1A-A4.md` | **变更评估**：架构级 A1a/A2/A3/A4（入口切分、陈旧检测、版本记录） | **与统筹方对账时** |
| `docs/EVALUATION-ARCH-D2.md` | **变更评估**：契约 v1.0.7 两处裁定的落实（偏离撤销、级别统一） | **与统筹方对账时** |
| `docs/EVALUATION-D8-D9-D6.md` | **变更评估**：载荷键跨语言对齐（D8）、挂钩签名绑定（D9）、双入口对拍常驻化（D6） | **与统筹方对账时** |
| `docs/EVALUATION-ARCH-A2B.md` | **变更评估**：bundled 即拒绝启动（A2b）+ 版本追溯 | **与统筹方对账时** |
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
| 1 | **数据库实现未落地** | 事件与快照落本地 `data/storage_data/` | 按计划只留 `Storage` Protocol；抽象可替换性已验证 |
| 2 | **压缩快照尚未回流进 prompt** | `Snapshot.to_prompt()` 可用，但还没注入上下文 | 下一步；当前上下文仍按条数截断 |
| 3 | **回退会清除未跟踪文件** | `git clean -fd` 会删掉你手动放进 workspace 的文件（执行前有警告列出清单） | 往 workspace 放文件前确认已被忽略。见 `docs/OPERATIONS.md` §9.1 |
| 4 | **`resolve_profile` 是两角色假设** | 加 REVIEW 角色会**静默继承 ORCH**（"以为请了审查员，其实是同一个模型审自己"），不报错 | 开启 REVIEW 前必须先改成显式角色表 |
| 5 | **`resolve_profile` 的 fallback 仍是两角色语义** | 准备启用 REVIEW 等新角色时，`fallback` 会静默顶替 | 新角色请改用 `resolve_role()`（显式角色表，未配置即"未启用"）。见 `docs/MODULES.md` §3 |
| 6 | **子任务串行执行** | 多任务延迟线性叠加 | 未在计划中 |
| 7 | `fetch_url` 的 **DNS rebinding 风险未消除** | 域名在请求时被解析到内网时拦不住；IP 字面量与 `localhost` 已拦截 | 需传输层 peer-IP 校验 |

> **回退后端当前是 git**（实测 git 2.55.0，提交/回退/历史均正常）。
> 若 `GET /profile` 的 `checkpoint_backend.selected` 显示 `snapshot`，
> 说明 git 不可执行，已退化为文件快照兜底。

---

## 项目结构

```
backend/                    ── 上游 Python 代码（**可以整包替换**）
  main.py                     FastAPI 入口：/run、/encode、/profile、/reflect、/decisions
  core/                       工作流层 + 适配层
    ├─ coding_cycle.py           一轮流程编排（PLAN→WRITE→MANIFEST→CHECK→VERIFY→RECORD）
    ├─ orchestrator.py           主循环：拆解任务 + 验证回流
    ├─ worker.py                 子循环：用工具完成单个任务
    ├─ pipeline.py               门禁：manifest / check / verify 调度
    ├─ manifest.py               交付契约：声明 vs 实际
    ├─ symbol_index.py           结构事实：AST 扫描符号与依赖
    ├─ checkpoint.py             回退：git / snapshot 双后端
    ├─ memory.py                 全局状态 + 验证结论回流
    ├─ model_profile.py          模型接入标准参数入口（适配层）
    ├─ llm.py                    OpenAI 兼容客户端 + JSON 容错（适配层）
    └─ ...
  tools/                      18 个工具，按 profile 过滤下发（registry.py 为注册表）
  storage/                    会话与事件落盘
  web/                        上游的接口层（decisions.py：手机端审批页）

bridge/                     ── ★ 适配层：上游与前端之间**唯一**的粘合处
  paths.py                    路径定义（运行根 = data/）
  bootstrap.py                 ① sys.path ② .env ③ 建目录 ④ **切 CWD 到 data/**
  hooks.py                     ★ 运行时包装上游的汇聚点，产出进度事件
  contract.py                  ★ 契约自检：上游接口变了就指名道姓报错
  app.py                       入口：上游 app + /api/* + /app
  agent_api.py                 REST + SSE 接口
  runner.py                    运行管理器：可订阅 / 可回放 / 可取消
  factory.py / actions.py      模型档位解析 + 参数转换
  demo.py                      演示运行：不调模型也跑出完整事件序列

frontend/                   ── 前端（Vue 3 + Vite），见 frontend/README.md
  src/                        store / api / components / composables
  dist/                       构建产物；不存在时 `/app` 不注册

data/                       ── 运行态（不入库），见 data/README.md
  workspace/                  模型产出的代码（内含独立 git 仓库，回退机制用）
  storage_data/               事件流 / 快照 / 决策 / 技能库
  sessions/                   每次 run 的完整记录

tests/                      单测 / 能力基准 / 诊断，见 tests/README.md
docs/                       架构、模块、运维文档
scripts/                    backup.ps1（打快照 / 看差异 / 回退）、run.ps1（构建并启动）
```

**三条结构纪律**：

1. **`backend/` 只放上游代码，一行都不改。** 你可以把最新版后端整包复制过来覆盖它。
2. **前端只跟 `bridge/` 说话**，不直接依赖 `backend/` 的内部结构。
3. **运行态一律写进 `data/`**：`bridge/bootstrap.py` 把进程 CWD 切到那儿，
   上游那些 CWD 相对的路径（`os.path.abspath("workspace")`）就自动落位 ——
   **不需要改上游一行代码**。

> 上游整包替换之后，跑 `.\scripts\adopt-backend.ps1`：它做契约自检，
> 把"新后端少了哪个接口、会导致前端少看到什么"直接列出来。

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
