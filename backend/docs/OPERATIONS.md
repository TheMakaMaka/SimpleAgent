# 运维与升级手册

> **同步至 CHANGELOG §34** —— 本文只描述**当前状态**；修复过程见 `CHANGELOG.md`。
>
> 面向日常运维、模型接入与升级回归。架构原理见 `docs/ARCHITECTURE.md`，
> 模块签名见 `docs/MODULES.md`，流程契约见 `CYCLE.md`。

## 目录

- [1. 环境要求与启动](#1-环境要求与启动)
- [2. 接入新模型的步骤清单](#2-接入新模型的步骤清单)
- [3. 预算推导表](#3-预算推导表)
- [4. 常见故障与排查](#4-常见故障与排查)
- [5. 如何看 CycleReport](#5-如何看-cyclereport)
- [6. 如何新增一个工具](#6-如何新增一个工具)
- [7. 测试怎么跑](#7-测试怎么跑)
- [8. 升级时的回归清单](#8-升级时的回归清单)
- [9. 已知不一致清单（速查）](#9-已知不一致清单速查)

---

## 1. 环境要求与启动

### 1.1 实测环境

| 项 | 实测值 |
|---|---|
| Python | **3.10.11** |
| 虚拟环境 | `.venv/`（已存在，直接用） |
| 模型服务 | Ollama `http://localhost:11434/v1` |
| 默认模型 | `qwen2.5:7b` |

关键依赖版本（实测）：

| 包 | 版本 | 用途 |
|---|---|---|
| `openai` | 2.44.0 | LLM 客户端（OpenAI 兼容协议） |
| `fastapi` | 0.115.12 | HTTP 服务 |
| `uvicorn` | 0.34.3 | ASGI 服务器 |
| `httpx` | 0.28.1 | `fetch_url` 工具 |
| `pydantic` | 2.11.5 | 请求/响应模型 |
| `python-dotenv` | 1.2.2 | 已安装（当前未被自动加载，见 §1.4） |
| `ruff` | 0.11.12 | 已安装但**可执行文件缺失**，见 §4.4 |

> ⚠️ `.venv` 里同时装着大量与本项目**无关**的重型包
> （`torch`、`transformers`、`gradio`、`jupyterlab`、`opencv-python`、
> `akshare`、`datasets`、`peft`、`accelerate`、`bitsandbytes` 等）。
> 本项目实际只依赖上表 6 个包。迁移到新机器时**不要**照搬整个 `.venv`，
> 按上表装即可。

### 1.2 启动服务

```bash
# 在仓库根目录执行（重要：多处路径依赖 CWD 为仓库根）
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

或直接 `python main.py`（需自行补 uvicorn 启动逻辑；`main.py` 只定义 `app`，
不含 `__main__` 入口）。

> **必须在仓库根目录启动**。`core/pipeline.py`、`core/symbol_index.py`、
> `core/checkpoint.py`、`tools/*.py` 都用 `os.path.abspath("workspace")`
> 或相对路径 `"workspace/..."` / `"sessions"`，从别处启动会指向错误目录。

### 1.3 验证服务与配置

```bash
# 1) 存活检查（endpoints 是**从真实路由推导**的，不会漂）
curl http://127.0.0.1:8000/
# → {"status":"Coding Agent is running","endpoints":["/","/candidates",...]}

# 2) 查看生效的模型接入参数（换模型后必查）
curl http://127.0.0.1:8000/profile

# 3) 上游→前端契约自检（改上游后必查，见 docs/FRONTEND_CONTRACT.md）
curl http://127.0.0.1:8000/contract/check
# → {"verdict":"ok", ...}；非 ok 时逐条给出【后端改】/【前端改】/【双方协商】

# 4) 与前端自述对账（前端运维机制调这个；这里手动试）
curl -X POST http://127.0.0.1:8000/contract/check -H "Content-Type: application/json" `
  -d '{\"contract_version\":\"1.0\",\"upstream_event_kinds\":[\"cycle_start\",\"plan\"]}'
# → {"verdict":"frontend-action","frontend":[{"code":"P-event-unknown-to-frontend",...}]}
```

`/profile` 返回 `ORCH` 与 `WORKER` 两个角色的：
`profile`、`model`、`base_url`、`context_window`、`supports_tool_calls`、
`supports_json_mode`、`coupling`、`limits{...}`、`problems[]`。

另有六个非模型段：`checkpoint_backend`（回退后端）、`decision_channel`
（远程审批通道）、`roles`（角色表，未配置即"未启用"）、`vision`（多模态诊断）、
**`contract`（契约概览 + `audit` 自检 + `responsibility` 责任划分规则表）**、
**`code`（代码身份：跑的是哪一份上游，见 §1.3.1）**。

`problems` 为空数组表示通过启动自检。

**启动时**：上游会自查一次契约，**只有不通过时才打印一行**
（`[contract] 上游契约自检未通过…`）。正常情况下启动日志里没有这一行——
"没有输出"就是好消息。

### 1.3.1 ★ 先确认"跑的是哪一份代码"

**这是排查一切"我改了但没生效"的第一步**（实测事故见 `docs/CHANGELOG.md` §31：
用户连续几次失败，而修复代码**一行都没被加载** —— 前端在用它自带的陈旧副本）。

```powershell
# ① 本进程自报的代码身份（/profile 的 code 段）
curl -s http://127.0.0.1:8000/profile | python -c "import json,sys; c=json.load(sys.stdin)['code']; print(c['code_dir'], c['fingerprint'])"

# ② 前端到底会加载哪一份（只读核对：逐文件 + 指纹比对）
.venv\Scripts\python.exe tests\diagnostics\backend_dir_check.py
```

`code` 段含 `code_dir` / `package_dir` / `fingerprint`（**上游代码内容的 8 位指纹**，
覆盖 `core`/`tools`/`storage`/`web` + `main.py`）/ `module_files`。
指纹**只看代码内容**：改文档或测试不会变，改代码一定变。

**每次运行的第一个事件 `cycle_start` 也记这两个字段**
（`code_dir` / `code_fingerprint`），所以**事后**也能回答"那次跑的是哪一份"——
不必再靠 traceback 恰好带了路径。

> ⚠️ `cycle_start` 里的 `backend` 是**检查点后端**（git/snapshot），
> **不是**代码来源。两者容易搞混，已在 `EVENTS["cycle_start"].note` 里点明。

### 1.4 配置来源：`.env` 会自动加载

`main.py` 启动时加载仓库根目录的 `.env`（在读取任何 `ORCH_*` / `WORKER_*`
之前执行）。`.env.example` 是模板，复制为 `.env` 即可生效。

```bash
copy .env.example .env
# 编辑 .env，然后直接起服务
.venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

**两种方式都可用**，优先级为「已导出的环境变量 > `.env` 文件 > 内置默认值」：

```bash
# 方式 A：直接导出环境变量（适合临时覆盖）
$env:ORCH_MODEL="qwen2.5:7b"
.venv\Scripts\python.exe -m uvicorn main:app --port 8000

# 方式 B：写进 .env（推荐，持久）
```

> ⚠️ **测试与诊断脚本不走 `main.py`**，因此**不会**加载 `.env`。
> 需要给它们配配置时，请在 shell 里导出环境变量，或直接用内置默认值。

`.env` 含 API key，**已加入 `.gitignore`，不要提交**。

### 1.5 检查点后端（启动时会打印）

```
[模型接入] ORCH: qwen | model=qwen2.5:7b | ctx=8192 | maxtok=4096 | ...
```

`CodingCycle` 启动时会打印：

```
########## CodingCycle cy_... 开始 (checkpoint 后端: snapshot) ##########
```

后端取值 `git` / `snapshot` / `none`。

---

## 2. 接入新模型的步骤清单

### 2.1 最小步骤（同厂商、换模型名）

```powershell
$env:ORCH_MODEL="qwen2.5-coder:7b"
$env:WORKER_MODEL="qwen2.5-coder:7b"    # 可省，则继承 ORCH
# 重新起服务
```

### 2.2 完整步骤

| # | 动作 | 说明 |
|---|---|---|
| 1 | 设 `{ROLE}_BASE_URL` | 接入地址。不回退到默认值时必须显式设 |
| 2 | 设 `{ROLE}_MODEL` | 模型名。用于匹配内置档位（含 `qwen` → qwen 档） |
| 3 | 设 `{ROLE}_API_KEY` | 本地 Ollama 用 `ollama` 占位即可 |
| 4 | 设 `{ROLE}_CONTEXT_WINDOW` | **只给这一个数字，其余预算自动推导**，见 §3 |
| 5 | 按需设 `{ROLE}_JSON_MODE` | 模型是否支持 `response_format={"type":"json_object"}` |
| 6 | 决定 `{ROLE}_COUPLING` | 新模型**建议先设 `default`**，见 §2.4 |
| 7 | 重启服务，查 `/profile` | 确认 `problems` 为空、`limits` 符合预期 |
| 8 | 跑一轮小任务 | 用 `/encode` 跑一个单函数任务确认链路通 |

**角色**：`ORCH`（编排器，需强 JSON 遵循）与 `WORKER`（执行器，需强代码能力）。
只配 `ORCH_*` 时 `WORKER_*` **继承** `ORCH_*` 的接入信息与预算
（由 `resolve_profile(prefix, fallback=orch)` 实现）。

### 2.3 全部可用环境变量

| 变量 | 作用 |
|---|---|
| `{ROLE}_MODEL` | 模型名 |
| `{ROLE}_BASE_URL` | 接入地址 |
| `{ROLE}_API_KEY` | API Key |
| `{ROLE}_PROFILE` | 指定内置档位名（`default` / `qwen`），覆盖按模型名的自动推断 |
| `{ROLE}_CONTEXT_WINDOW` | 上下文窗口（预算推导的输入） |
| `{ROLE}_COUPLING` | `default` / `qwen` / `none` |
| `{ROLE}_JSON_MODE` | 布尔：`1`/`true`/`yes`/`on` 为真 |
| `{ROLE}_TIMEOUT` | 请求超时（秒），默认 120 |
| `{ROLE}_MAX_TOKENS` | 覆盖单次生成上限 |
| `{ROLE}_MAX_ROUNDS` | 覆盖主循环轮次上限 |
| `{ROLE}_MAX_STEPS` | 覆盖子任务步数上限 |
| `{ROLE}_MAX_ATTEMPTS` | 覆盖 cycle 尝试次数 |
| `{ROLE}_MAX_ERRORS` | 覆盖连续工具报错上限 |
| `{ROLE}_MAX_SAME_TASK` | 覆盖同任务重复上限 |
| `{ROLE}_TEMPERATURE` | 覆盖采样温度 |
| `{ROLE}_TOOL_RESULT_CHARS` | 覆盖工具结果回灌截断长度 |

> `{ROLE}_DEBUG_HEAD_CHARS` / `_VERIFY_OUTPUT_CHARS` **不存在**，
> 对应的 `ModelLimits` 字段也已删除。

### 2.4 `COUPLING` 什么时候该设成 `default`

`COUPLING` 收纳的是"为了让某个模型跑通而写的补丁"。判断规则：

| 情况 | 建议 |
|---|---|
| 接入**新模型**（第一次跑） | 设 `default`（不做任何补偿），先看它的原生表现 |
| 出现"奇怪的重试行为"、明明该结束却反复规划 | 设 `default` 排除耦合干扰后再定位 |
| 用的是 qwen 系且表现正常 | 保持 `qwen`（默认按模型名自动选中） |
| 明确知道模型爱先写计划再调工具 | 设 `qwen` 或自定义档位 |

置为 `default` 后 `plan_hints` 为空元组 → `Worker` 不再识别计划句式；
`repair_json` 仍为 `True`（这是通用 JSON 容错，不属于模型特判）。

### 2.5 自定义档位（需要代码注册）

```python
from core import ModelProfile, register_profile, ModelLimits, ModelCoupling

register_profile(ModelProfile(
    name="my-model",
    model="my-model-v1",
    base_url="http://localhost:8000/v1",
    limits=ModelLimits.from_context_window(32768),
    coupling=ModelCoupling(),          # 空耦合 = 不补偿
))
```

注册后设 `{ROLE}_PROFILE=my-model` 即可引用。

---

## 3. 预算推导表

`ModelLimits.from_context_window(context_window)`，其中
`cw = max(2048, int(context_window))`：

| 输出项 | 公式 |
|---|---|
| `max_tokens` | `min(cw // 2, 4096)` |
| `max_rounds` / `max_steps` / `max_attempts` | `cw<=8192` → `15 / 15 / 2`；`cw<=32768` → `20 / 20 / 3`；`cw>32768` → `30 / 25 / 3` |
| `tool_result_chars` | `max(800, min(cw // 6, 8000))` |

**不随窗口变化**（保持 dataclass 默认值 `3` / `2` / `0.1`）：
`max_errors`、`max_same_task`、`temperature`。

### 各档实际取值

| `CONTEXT_WINDOW` | `max_tokens` | `rounds` | `steps` | `attempts` | `tool_result_chars` |
|---|---|---|---|---|---|
| 2048 | 1024 | 15 | 15 | 2 | 800 |
| 8192（默认） | **4096** | 15 | 15 | 2 | 1365 |
| 32768 | 4096 | 20 | 20 | 3 | 5461 |
| 131072 | 4096 | 30 | 25 | 3 | 8000 |

> **`max_tokens` 刻意封顶 4096。** 4096 是 `cw=8192` 下实测可用的值，
> 推导公式不允许在这一档回退（曾一度写成 `cw//4` 导致降到 2048，
> 会让截断更容易发生，已修正）。需要更大生成预算请**显式覆盖**
> `{ROLE}_MAX_TOKENS`。

任何一项都可被同名环境变量覆盖（见 §2.3），覆盖项优先于推导值。

---

## 4. 常见故障与排查

### 4.1 模型一直重复同一动作 / 空转到 `max_rounds`

**症状**：日志里同一个动作反复出现，最后 `达到主循环上限 N 轮，未能完成`。
实测历史：同一个"运行并检查输出"被重复 5 次，两次尝试合计 17 个任务、109.2 秒。

**排查顺序**：

1. **确认验证回流生效**。日志里应出现 `[验证回流] passed=... detail=...`。
   若完全没有这一行，说明 `verify_command` 没传到编排器，
   或 `Orchestrator.pipeline` 为 `None`。
2. **确认 verify 命令可判定**。查看 `/encode` 的 `verify_passed` 字段：
   - 若为 `null` 且 `error` 含 `缺少可机器判定的验证命令` → 调用方没传
     `verify_command` 且模型也没给出有效的 `verify`。
   - 若模型自拟的 verify 是自然语言（如 `"检查一下是否正确"`），
     `check_and_run` 会执行失败 → 判不通过。
3. **检查 verify 命令是否真的会失败**。实测踩过的坑：模型曾把断言改写成
   `assert isinstance(factorial(-1), ValueError)`——一个**永远不可能成立**的断言
   （`factorial(-1)` 抛异常，不会返回值供 `isinstance` 判断），
   导致实现正确也判失败。
   > 此问题已修：调用方给的 `verify_command` 现在是权威的，模型不可改写
   > （`CYCLE.md` §2.2）。

**正常表现**：改造后同一任务是 **1 个任务、6.6 秒**通过。

### 4.2 频繁空响应

**症状**：日志出现 `[FAIL] tN: 模型连续空响应，可能是生成被截断`
以及 `连续 3 次空响应，max_tokens 可能不足`。
实测 L4 曾出现连续 3 次空响应。

**处理**：

```powershell
$env:ORCH_MAX_TOKENS="8192"     # 或 WORKER_MAX_TOKENS
```

同时确认 `{ROLE}_CONTEXT_WINDOW` 不小于 `max_tokens`
（否则 `/profile` 的 `problems` 会报错并导致 `LLMClient` 构造失败）。

### 4.3 manifest 报 `declared-missing`

**症状**：

```
[manifest] checked=True passed=False declared=3 actual=2 violations=1
[manifest] 交付缺口: 交付清单不完整: 计划要产出 contacts.py，但文件不存在
```

**排查**：

1. **路径前缀**。模型常写 `workspace/foo.py`，而索引键是 `foo.py`。
   代码已做归一化（`normalize_declared_path` 会剥掉 `workspace/`、
   `./`、前导 `/`，并统一反斜杠）。若仍报缺失，检查是不是**真没写出**。
   > 实测踩过：未做归一化时，通过验证的产出被误判为"文件不存在"，
   > 白白烧掉整个重试预算。
2. **确认是"从来没写"还是"写到别处"**。用
   `POST /encode` 返回的 `touched_files` 对比 `declared`：
   - `touched_files` 里没有该文件 → 模型确实没写。
   - `touched_files` 里有但路径不同 → 路径不一致，属归一化未覆盖的形态。
3. 用架构工具直接查实际结构（对模型也可用）：

```
get_architecture()        → 全部模块总览
get_module("cli.py")      → 单模块符号表 + 反向依赖
find_symbol("run")        → 反查定义位置
```

或用 `list_workspace` 列实际文件。

**语义提醒**：`declared` 为空时 `checked=False`、**不做判定**。
所以 `manifest.passed=true` 有两种含义——"校验通过"或"没声明清单，跳过了"，
要看 `checked` 字段区分。

### 4.4 `run_lint` 永远返回 `skipped`

**症状**：CHECK 阶段日志里 lint 步骤 `status="skipped"`，返回体为
`{"ok": null, "issues": [], "skipped": "ruff not installed", ...}`。

**原因（已实测确认）**：`code_checks.py` 用 `shutil.which("ruff")` 探测，而：

```
pip list            → ruff 0.11.12 已安装
.venv\Scripts\ruff.exe  → 不存在
shutil.which("ruff")    → None
```

`ruff` 的 Python 包装装了，但**可执行文件缺失**。

**处理**：

```powershell
.venv\Scripts\python.exe -m pip install --force-reinstall ruff
# 确认：
.venv\Scripts\python.exe -c "import shutil; print(shutil.which('ruff'))"
```

**这不是 bug**：返回 `ok: null` + `skipped` 是**正确语义**——
表示"未执行"而非"通过"。早期版本返回 `ok: true` 会让模型误判为
lint 干净（假阴性），已修正。`WORKER_SYSTEM` 规则 8 也明确告诉模型
`ok: null` 不等于通过。

**影响**：在 ruff 装好之前，lint 这一层**没有实际把关能力**；
CHECK 阶段的阻塞门实际只有 `check_syntax`。

### 4.5 检查点后端的选择与退化

**当前行为**：`CheckpointManager(prefer="git")` 探活 `git --version`，
成功则用 `GitBackend`，失败则降级到 `FileSnapshotBackend`，
两者都不可用时为 `none`（会在启动时打印警告）。

```powershell
# 查实际生效的后端（权威来源，不要靠猜）
curl http://127.0.0.1:8000/profile | Select-String checkpoint_backend
```

| 后端 | 能力 | 缺失 |
|---|---|---|
| `git` | 完整：diff / log / 分支 / 精确回退 | — |
| `snapshot` | 文件级快照 + 文件清单，能回退 | **无 diff**、无分支 |
| `none` | 不回退 | 启动时有警告，改坏无法恢复 |

**若显示 `snapshot` 而你想用 git**：

```powershell
# 1. 确认 git 真的可执行
git --version
#    若提示找不到命令，但 git 其实已安装 —— 这是 PATH 未刷新，
#    core/checkpoint.py 的 resolve_git() 会自动回退到常见安装目录，无需你处理。

# 2. 若确实未安装
winget install --id Git.Git --exact --source winget
#    装完无需改代码：下次构造 CheckpointManager 时自动切换
```

> 注意：`resolve_git()` 会在 PATH 之外尝试常见安装目录
> （`C:\Program Files\Git\cmd\git.exe` 等），所以"PATH 里没有"不等于不可用。

**若显示 `none`**：两个后端都不可用，运行**无法回退**。

### 4.6 验证失败被回退——这是预期行为

**症状**：日志出现

```
[rollback] 已回退到 snap0005: True
```

且 `/encode` 返回 `rolled_back=true`、`commit=null`。

**这是设计行为，不是故障**。回退时机：

| 失败环节 | 是否回退 |
|---|---|
| MANIFEST 有 error 级 violation | ✅（若还有 attempt 余额） |
| CHECK 不通过 | ✅（若还有 attempt 余额） |
| VERIFY 不通过 | ✅（若还有 attempt 余额） |
| 已达 `max_attempts` | ❌ 不回退（最后一轮不再回退） |
| 全部通过 | ❌ 改为**打正式检查点** |

**语义**：失败路径不打正式检查点，所以 **`commit=null` 是"本 cycle 未通过"
的可靠标志**。回退后工作区恢复到失败前状态，避免错误实现被后续任务
当作"已有产物"继承。

**定位方法**：见 §5 逐字段解释，重点是 `error`、`verify.detail`、
`manifest.violations`、`check_steps`。

### 4.7 `/encode` 返回 500 且提示"模型接入校验失败"

**原因**：`ModelProfile.validate()` 返回非空 `problems`。三种可能：

| `problems` 内容 | 含义 |
|---|---|
| `模型 ... 声明不支持 tool_calls` | 档位的 `supports_tool_calls=False`，流程无法运行 |
| `max_tokens(...) >= context_window(...)` | 生成预算撑满上下文 |
| `context_window(...) 过小` | 小于 2048 |

**处理**：查 `/profile` 的 `limits` 与 `context_window`，
按 §3 调整 `{ROLE}_CONTEXT_WINDOW` 或显式覆盖 `{ROLE}_MAX_TOKENS`。

### 4.8 生成代码里出现 `write_file(...)` 这类调用

**症状**：模型产出的 `.py` 文件里直接调用 agent 工具名，例如：

```python
def save(path, data):
    write_file(path, data)      # ← write_file 是 agent 工具，不是可调用函数
```

**原因**：模型混淆了「agent 工具」与「普通 Python 函数」。
这是**模型能力问题**（实测出现在 L8），不是代码缺陷。

**缓解方向**：`WORKER_SYSTEM` 可增加一条明确区分；属计划中改进，
当前未处理。

### 4.9 prompt 里的「结构化上下文」段

**它是什么**：主循环每轮决策前，由 `CodingCycle._structured_context()` 从事件流
重算压缩快照（纯函数，不经过模型），渲染成 `【结构化上下文】` 段注入 prompt。

**怎么确认它在工作**：看事件流里同一 `cycle_id` 是否有 `plan` / `syntax` / `lint` /
`manifest` / `verify` 事件。只有 `cycle_start` 的第一轮不会有该段——
**这是正常的**，此时确实还没有任何实测事实，系统不会输出空壳段落。

**怎么判断它被截断**：段内会出现 `…（结构化上下文超出预算，已截断）`。
该段的预算是独立上限 `max(200, min(prompt预算//3, 1500))` 字符，
`prompt预算` 来自 `{ROLE}_CONTEXT_WINDOW`（见 §3）。

**它不会做的事**（出问题时的排查方向）：

| 现象 | 说明 |
|---|---|
| 验证结论不见了 | **不该发生**。验证结论优先级最高且永不省略，有专门测试守着。真出现请当 bug 报 |
| 段里出现模型自述 | 会单列为「模型自述（**未经校验，不可作为判据**）」，它不参与判定 |
| 取快照失败导致 cycle 失败 | **不该发生**。取快照任何环节异常都只降级为"无此段" + 一行日志 |

### 4.10 验证一段都没跑，或报"缺少可机器判定的验证命令"

**先分清两种情况**——它们的处置完全不同：

| 日志/响应 | 含义 | 处置 |
|---|---|---|
| `verify=null`，且日志有 `[验证回流] 跳过：主循环没有 pipeline（未注入）…` | **接线缺陷**：编排器没被注入检查流水线 | 报 bug，不要改需求 |
| `verify=null`，日志有 `verify_skipped`，`reason` 指向"没拟出验证命令" | **模型没给判据**：本轮真的没有可执行断言 | 属正常降级；改需求或改提示词让它给判据 |
| 报错文案是"已拟出验证命令但**未执行**…" | 命令有、执行链断了 | 报 bug |

**这两条曾经是同一个缺陷**：`CodingCycle` 里一个 `if verify_command is not None:`
把「注入检查流水线」和「注入结构化上下文」一起关掉了。用户真实需求从不显式传
`verify_command`，于是**验证整段不存在，还被误报成"缺少验证命令"**——
看起来像模型不给判据，实际是代码没接线。详见 `docs/EVALUATION-FIX-VERIFY-WIRING.md`。

**怎么确认当前这份代码已修复**：

```bash
python tests/unit/test_verify_wiring.py         # 断言：无 verify_command 也必须进 VERIFY
python tests/diagnostics/verify_wiring_http.py  # 同一条断言走 HTTP 路径（单测过≠线上过）
python tests/diagnostics/repro_user_goal.py     # 真实形态跑一轮，断言 report.verify 非 None
```

`repro_user_goal.py` 会打印 `code_fingerprint`——**同时**比对上一步 §1.3.1
确认它就是你改的那份代码。否则你验的是别人（或旧副本）的代码。

### 4.11 报「自拟判据不合格，已拒绝采纳」

**症状**：`error` 含

```
模型自拟的验收判据**不合格，已拒绝采纳**：本轮没有任何交付物（…）
```

且事件流里有 `verify_skipped`，`reason` 里带着**被拒命令的原文**。

**这是什么**：调用方没给 `verify_command` 时，验收标准由模型自己拟。
给它的下限是「**必须引用本轮交付物**」（`VERIFY-VACUOUS`）：

| 情况 | 判定 |
|---|---|
| 计划没声明文件、也没有 `write_file` 产物 | **不合格**（说不出"交付了什么"） |
| 命令没引用任何交付物（如 `print('PASS')`） | **不合格**（恒真，等于没有判据） |
| 引用了某个声明/产出的文件（路径、文件名、或模块词干） | 合格，照常执行 |

**为什么这么设计**：在这之前唯一的门槛是"非空且可执行"，于是
`print('PASS')` 让**什么都没做**也判成功（`declared=0` + `checked=False`
+ `steps=0` + `print('PASS')` → `phase=record`）。详见
`docs/EVALUATION-VERIFY-VACUOUS.md`。

**怎么处理**：

1. **首选**：这不是要你去改判据，是给模型的反馈 —— 下一轮它会拿到
   "请给出引用交付物的判据"，实测它会**真的把报告写出来**再断言它。
2. **目标本来就不产出文件**（如"算一个结果"）：要么让模型把结果落成文件
   （`result.txt` / 把代码存成 `.py`），要么由**调用方**给 `verify_command`
   —— 调用方的判据**不受这条例限制**（标准由调用方定，这是权威性）。
3. 若你确认判据是合理的却被拒，**报 bug 并附 `memory.verify_untrusted` 原文**
   —— 那说明下限写宽/写窄了，属于要改的代码而不是要绕过的门禁。

---

## 5. 如何看 `CycleReport`

`POST /encode` 的响应与日志里打印的 `CycleReport` 字段含义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `cycle_id` | `str` | 形如 `cy_20260925_174108_729484`（时间戳到微秒） |
| `goal` | `str` | 本次目标（重试时**不含**注入的失败提示） |
| `phase` | `str` | 最终阶段，见下表 |
| `transitions` | `list[str]` | 阶段推进轨迹。**重试会看到 `plan` 出现多次** |
| `attempts` | `int` | 实际尝试次数（≤ `max_attempts`） |
| `check_steps` | `list[dict]` | 每个文件的 `check_syntax` / `run_lint` 结果 |
| `manifest` | `dict \| None` | 完整 manifest，见下 |
| `verify` | `dict \| None` | 验证结论，见下 |
| `touched_files` | `list[str]` | 本次 `write_file` 产出的文件（相对 workspace） |
| `commit` | `str \| None` | 通过时的检查点引用；**`null` 表示未通过** |
| `rolled_back` | `bool` | 是否发生过回退 |
| `error` | `str \| None` | 失败原因；**成功时被清空为 `null`** |

### 5.1 `phase` 取值

| 值 | 含义 | 是否成功 |
|---|---|---|
| `record` | 走到最后一步：已打检查点 | ✅ **唯一成功标志** |
| `failed` | 未通过校验 | ❌ |
| `plan` / `write` / `check` / `verify` | 中间态（记录瞬时位置用，终态不会是这些） | — |

**判定成功的可靠方式**：`phase == "record"`。
`/encode` 的 `ok` 字段就是这个判断。

### 5.2 `manifest` 结构

```json
{
  "checked": true,
  "passed": false,
  "declared": [{"path": "storage.py", "role": "...", "symbols": ["save", "load"]}],
  "actual":   [{"path": "storage.py", "module": "storage", "symbols": [...],
                "local_deps": [], "sha1": "...", "lines": 12}],
  "violations": [{"severity": "error", "kind": "declared-missing",
                  "path": "contacts.py", "message": "...", "fix": "..."}],
  "note": ""
}
```

| 字段 | 要点 |
|---|---|
| `checked` | `false` = 模型没声明清单，**未做判定**（`passed` 此时恒为 `true`） |
| `passed` | `not blocking`，即无 `severity=="error"` 的 violation |
| `violations[].severity` | `error` 阻塞；`warning` **不阻塞** |

violation 种类见 `docs/MODULES.md` §9。

### 5.3 `verify` 结构

```json
{
  "passed": true,
  "detail": "PASS",
  "command": "import sum_1_to_100\nassert ... == 5050\nprint('PASS')",
  "source": "caller"
}
```

> 注意：`CycleReport.verify` 在 `CodingCycle` 中是从
> `memory.verify_state` 重建的**精简四元组**，只有
> `passed`/`detail`/`command`/`source`。
> 而 `CheckPipeline.run_verify()` 返回的是更完整的
> `{tool, passed, command, reason, parsed}`。
>
> **`source` 是判据来源**（`VERIFY-VACUOUS` 追加）：`caller` = 调用方给的权威判据，
> `model` = 模型自拟（已过可采性下限，见 §4.11）。它只作事实留痕，
> **判定只看退出码** —— 不要因为 `model` 就无视 `passed`。

`detail` 的构造（`Orchestrator._verify_detail`）：
- 通过 → `parsed.output` 或 `"验证通过"`
- 失败 → `"{error_type}: {message}"`（如 `AssertionError: 负数未抛 ValueError`）

### 5.4 典型判读

| 现象 | 结论 |
|---|---|
| `phase=record`，`commit=snap0006`，`rolled_back=false` | 一次通过 |
| `phase=record`，`attempts=2`，`transitions` 里 `plan` 出现两次 | 第一次失败回退后重试成功 |
| `phase=failed`，`manifest.passed=false` | 交付缺口（缺文件/缺符号） |
| `phase=failed`，`verify.passed=false`，`manifest.passed=true` | 交付齐了但功能不对 |
| `phase=failed`，`verify=null`，`error` 含 `缺少可机器判定的验证命令` | 没给可判定的验收标准 |
| `phase=failed`，`verify=null`，`error` 含 `不合格，已拒绝采纳` | 模型自拟的判据没引用任何交付物（见 §4.11） |
| `phase=record`，`verify.source=model` | 判据是模型自拟的（已过下限）；可信度低于 `caller`，但判定同样只看退出码 |
| `phase=record`，`check.status=skipped` | 本轮没有 `.py` 改动 → 静态检查**没跑**（不是"跑了并通过"） |
| `phase=failed`，`commit=null`，`rolled_back=true` | 全部尝试失败，已回退 |
| `success` 但 `error` 非空 | **不应发生**：成功路径会清空 `error` 与 `rolled_back` |

---

## 6. 如何新增一个工具

### 6.1 步骤

1. 选模块（新功能建议新建 `tools/<name>.py`，或加入已有的同类模块）。
2. 用 `@register` 装饰异步函数。
3. 在 `tools/__init__.py` **显式导入**该模块。

```python
# tools/mytool.py
from .registry import register

@register(
    name="my_tool",
    description="一句话说明用途与何时调用。模型只靠这句话决定用不用。",
    parameters={
        "type": "object",
        "properties": {
            "arg1": {"type": "string", "description": "参数说明"}
        },
        "required": ["arg1"],
    },
)
async def my_tool(arg1: str) -> str:
    return json.dumps({"ok": True, "result": ...}, ensure_ascii=False)
```

```python
# tools/__init__.py —— 必须加这一行，否则装饰器不执行、工具不会注册
from . import mytool   # noqa: F401
```

### 6.2 注意事项

| # | 事项 |
|---|---|
| 1 | **必须 async**。`registry.register` 的类型标注是 `Callable[..., Awaitable[str]]`，注册表调用方一律 `await`。 |
| 2 | **返回 `str`**。约定返回 JSON 字符串（`json.dumps(..., ensure_ascii=False)`）。 |
| 3 | **新工具请返回 `{"ok": bool, ...}`**。`is_error_result` 优先解析结构化 JSON：dict 且含 `"ok"` 键时取 `data["ok"] is False`。老式字符串 `"Error: ..."` 仍兼容，但属遗留协议。 |
| 4 | **`ok: null` 有明确语义**：表示"**未执行**"，不是"通过"。参考 `run_lint` 在 ruff 缺失时的返回。不要用 `ok: true` 表示跳过。 |
| 5 | **是否会被门禁使用**：只有 `check_syntax`、`run_lint`、`check_and_run` 参与门禁（由 `CheckPipeline` 按**名字硬编码**调用）。新工具默认只是模型可选，不参与成败判定。若要让新工具进门禁，需改 `core/pipeline.py`。 |
| 6 | **避免与 `review_code` 职责重叠**。`review_code` 是**质量建议**（不决定成败）；若你的工具要产出判据，它应进 `CheckPipeline` 而**不是**注册成模型工具——否则模型可以绕过它。 |
| 7 | **路径安全**：写文件类工具请复用 `_safe_path` 的思路（见 `tools/files.py`），并注意 `_PROTECTED = {".env","main.py","agent.py","pyproject.toml","requirements.txt"}` 是**受保护文件名**（比较的是 `basename`）。 |
| 8 | **必须声明 `profiles`**（`@register(..., profiles=("coding",))`）。工具按 profile 过滤后下发，未声明则默认 `("any",)` = 两个 profile 都暴露。**种子工具**（通用 agent 用）请标 `("general",)`，这样编码流程不会看到它，也就不存在"选错工具"。 |
| 9 | **同步更新 `docs/MODULES.md` 的工具清单表**。 |

### 6.3 验证新工具已注册

```bash
.venv\Scripts\python.exe -c "from tools import TOOLS_MAP; print(len(TOOLS_MAP)); print(list(TOOLS_MAP))"
```

---

## 7. 测试怎么跑

**所有命令都在仓库根目录执行。** 详见 `tests/README.md`，此处给决策口径。

```
tests/
├── run_unit.py          统一跑全部单元测试（离线，不需要模型）
├── _bootstrap.py        公共引导
├── unit/                纯逻辑断言，不调用模型
├── bench/               能力基准（难度阶梯），需要真实模型
├── diagnostics/         诊断与展示，需要真实模型
└── output/              运行产物（已 gitignore，可随时删）
```

### 三类测试什么时候跑

| 类别 | 命令 | 何时跑 | 耗时量级 |
|---|---|---|---|
| **单元测试** | `python tests/run_unit.py` | **每次改代码后必跑**。离线、确定性 | 秒级 |
| **能力基准** | `python tests/bench/run_levels.py [lo hi]` | 换模型、改提示词、改门禁逻辑后跑，对比通过率 | 分钟级（8 级实测累计约 900s+） |
| **诊断** | `python tests/diagnostics/*.py` | 排查具体问题、需要看完整流程日志时 | 单次分钟级 |

### 单独跑某个单测

```bash
python tests/run_unit.py                      # 全部
python tests/unit/test_manifest.py            # 单个（也可直接执行）
```

### 基准的注意事项

- `run_levels.py` 会**清空 `workspace/`**（原有文件备份到
  `tests/output/_ws_backup` 并在结束时还原）。
- 结果写入 `tests/output/levels_result.json`，各级 CycleReport 在
  `tests/output/logs/`。
- 配套 `python tests/bench/analyze_levels.py` 做失败根因分类
  （需先跑过 `run_levels.py`）。
- 注意：`tests/README.md` 中的举例命令写的是 `python tests/run_unit.py`，
  与 `run_unit.py` 自身 docstring 一致。
- **若 `python` 落到 Windows 应用商店别名**（`...\WindowsApps\python.exe`，
  执行即退 `9009`），请改用虚拟环境里的解释器：
  `.venv\Scripts\python.exe tests/run_unit.py`。此时命令**根本没跑起来**，
  上报的退出码不是测试结论 —— 排查前先确认解释器存在。

### 诊断脚本

| 脚本 | 用途 |
|---|---|
| `diagnostics/cycle_e2e.py` | 正向：跑一轮并打印 CycleReport |
| `diagnostics/gate_check.py` | 反向：注入不可能满足的断言，验证门禁会拦住 |
| `diagnostics/diag_level.py <N>` | 单级诊断：dump 实际产出代码 + 完整 verify 结果 |
| `diagnostics/run_with_full_log.py` | 完整流程日志 → `tests/output/full_cycle_log.txt` |

---

## 8. 升级时的回归清单

### 8.1 改动前

| # | 动作 | 为什么 |
|---|---|---|
| 1 | 确认 git 可用或至少 snapshot 后端可用 | 否则改坏无法回退 |
| 2 | `python tests/run_unit.py` 记录**基线通过数** | 对比改动后是否引入回归 |
| 3 | 清空或备份 `workspace/` | 避免历史产物干扰判断 |
| 4 | 记下当前能力基线（`2/8`，L1、L4 通过） | 用于判断改动是提升还是退化 |

### 8.2 改完必须确认

| # | 检查项 | 命令 / 方法 | 通过标准 |
|---|---|---|---|
| 1 | 单元测试无回归 | `python tests/run_unit.py` | 通过数与基线一致或更多 |
| 2 | **文档与代码一致** | `python tests/unit/test_doc_consistency.py` | 全部通过 |
| 3 | **文档版本戳已更新** | 看各文档顶部的 `同步至 CHANGELOG §N` | 与 `CHANGELOG` 最新条目一致 |
| 4 | **上游→前端契约未被破坏** | `python tests/unit/test_frontend_contract.py` | 全部通过，且 `/profile` 的 `contract.audit.ok` 为 `true` |
| 5 | 服务能起来 | `uvicorn main:app --port 8000` | 无异常退出 |
| 6 | 模型自检通过 | `curl /profile` | `problems` 均为 `[]` |
| 7 | 角色表状态符合预期 | `curl /profile` 的 `roles` | 必需角色 `available: true` |
| 8 | 检查点后端正常 | 看启动日志 `checkpoint 后端:` | 非 `none` |
| 9 | 正向链路通 | `POST /encode` 跑单函数任务 | `phase=record`、`commit` 非空 |
| 10 | **反向门禁仍生效** | `python tests/diagnostics/gate_check.py` | `phase=failed`、`rolled_back=true` |
| 11 | 能力未退化 | `python tests/bench/run_levels.py` | 通过级别数 ≥ 基线 |

> **第 2、3 项是文档漂移的防线**。改了代码或 CHANGELOG 后，
> 若忘了同步上游文档，这两项会失败——不必靠人回忆。

> **第 4 项是前端漂移的防线**。前端对上"认不出就降级显示"，
> 所以上游删事件/改 payload 键**不会让前端报错**，只会让它静默少显示。
> 改上游前请先看 `docs/FRONTEND_CONTRACT.md`。

> 第 10 项最容易被忽略但最关键：**正向能跑通，不代表门禁还在拦**。
> 历史教训——曾因模型可改写 `verify_command`，导致 L3 用
> `assert isinstance(factorial(-1), ValueError)` 这种永远不成立的断言"通过"，
> 通过率虚高，直到修正后才暴露出真实边界。

### 8.3 改配置类内容的额外确认

改动 `ModelLimits` 推导公式 / 默认值时：

| 检查 | 期望 |
|---|---|
| `cw=8192` 的 `max_tokens` | **必须仍为 4096**（实测可用值，不允许回退） |
| 任一档 `max_tokens < context_window` | 否则 `validate()` 报错，服务起不来 |
| `/profile` 的 `limits` 与本文 §3 表格 | 一致 |

### 8.4 改提示词时的额外确认

提示词对模型行为影响极大，且**没有自动化测试覆盖**。改后至少：

1. 跑 `tests/bench/run_levels.py 1 2` 确认 L1 仍通过。
2. 确认编排器仍输出 `files` 与 `verify` 字段
   （看 `tests/output/logs/L1.json` 里的 `manifest.checked`；
   若为 `false` 说明模型没给 `files`）。
3. 确认 `manifest.checked=true` 时 `declared` 非空。

---

## 9. 已知不一致清单（速查）

完整说明见 `docs/MODULES.md` §19。按运维影响排序：

> **本表只列「当前仍存在」的问题。** 已修复项不在此处（修复过程见
> `docs/CHANGELOG.md`）——上游文档只描述现状，否则无法判断某条是"还没修"
> 还是"修了但文档没更新"。

| # | 问题 | 运维影响 |
|---|---|---|
| 1 | **回退会 `git clean -fd`**，删掉未跟踪文件 | 手动放进 workspace 的文件会丢。见下方 §9.1 |
| 2 | `WORKSPACE_DIR` 在 6 处独立计算 + `worker.py` 用相对路径 | 必须从仓库根启动 |
| 3 | `facts` 机制未接线（`add_fact` 无调用方） | 编排器 prompt 的「关键事实」段永不输出 |
| 4 | `manifest.to_prompt()` 未被工作流使用（`CodingCycle` 自建格式） | 两处格式化逻辑并存 |
| 5 | `get_weather` 是占位实现（恒返回晴天 22°C） | 编码 profile 下不下发，不影响编码流程 |
| 6 | `resolve_profile` 的 fallback 仍是两角色语义 | **准备启用 REVIEW 角色时**要改用 `resolve_role()`，否则 `fallback` 会静默顶替 |

### 9.0 远程决策的类型与默认动作

只在两处会停下来等人：`repeated_failure`（验证连续失败达阈值）与
`risky_rollback`（回退会覆盖文件前）。**超时默认动作是保守的**：
前者 `stop`、后者 `abort` —— 没人管时不会自己往前冲。

推送通道未配置时退化为控制台输出，**不会阻塞流程**。

### 9.1 回退会清除未跟踪文件（务必知道）

`GitBackend.rollback()` = `git reset --hard <ref>` + `git clean -fd`。
后者会删掉 workspace 里**所有未被跟踪的文件**——包括你手动放进去的笔记、
临时脚本、下载的数据。

**执行前会先 dry-run 列出将被删除的文件并打印警告**：

```
[rollback] 警告：将清除 2 个未跟踪文件（手动放进 workspace 的文件也会被删）: my_notes.md, scratch.py
```

**一个容易误解的点**：`clean -fd` 不加 `-x`，所以**不会删被忽略的文件**。
`.gitignore` 覆盖的 `_tmp/` `_debug/` `__pycache__/` 是安全的（已实测）。

**建议做法**：往 workspace 里放手动文件前，确认它已被忽略，或放进 `_tmp/`。
例如在 `workspace/.gitignore` 里加一行你自己的目录名。

