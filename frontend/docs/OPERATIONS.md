# 运维与升级手册

> **同步至 CHANGELOG §36** —— 本文只描述**当前状态**；修复过程见 `CHANGELOG.md`。
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
- [10. Vue 执行可视化前端](#10-vue-执行可视化前端)
- [11. 备份纪律：做出一版可行之后，先备份，再继续完善](#11-备份纪律做出一版可行之后先备份再继续完善)

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

> ⚠️ **不设 `AGENT_BACKEND_DIR` 会拒绝启动**（架构清单 A2b）。
> 判据是"解析到的后端是不是仓库自带的 bundled 副本"——判**形态**不判**状态**。
> 想用自带副本（例如只想看界面）：`.\scripts\run.ps1 -AllowBundled`
> 或 `python -m bridge --allow-bundled`，或设 `AGENT_ALLOW_BUNDLED=1`。
> 该事实会写进 `/api/health` 的 `backend_bundled_override` —— **降级必须留痕**。
> 详见 `docs/DIAGNOSTICS.md` §7.5。

```bash
# 指向真上游（推荐；也是唯一能正常启动的默认形态）
$env:AGENT_BACKEND_DIR = "D:\PythonProject\SimpleAgent2_Cycle"

# 方式 A（推荐）：一键脚本，需要时先构建前端
.\scripts\run.ps1

# 方式 A2：等价的自带启动器（支持 --allow-bundled / --rebuild）
.venv\Scripts\python.exe -m bridge --port 8000

# 方式 B：手动。**入口是 bridge.app:app，不是 backend/main.py。**
# bridge 会在启动时把 CWD 切到 data/（运行根），所以要在**仓库根**执行。
.venv\Scripts\python.exe -m uvicorn bridge.app:app --app-dir . --host 127.0.0.1 --port 8000

# 只想跑上游、不要前端和事件流（调试上游时用）：
# cd backend && ..\.venv\Scripts\python.exe -m uvicorn main:app
```

启动日志里有一段**版本追溯**，可直接粘进版本记录：

```
[bridge]   后端目录      : D:\PythonProject\SimpleAgent2_Cycle
[bridge]   自带副本      : False
[bridge]   逃生舱        : False
[bridge]   core 模块     : 29 个
[bridge]   契约版本      : 1.0
[bridge]   前端 bundle   : index-CsUZBNxG.js      ← 你打开看到的是哪一版
```

或直接问探针：`GET /api/health` → `backend_dir` / `backend_is_bundled` /
`backend_bundled_override` / `backend_contract_version` / `frontend_asset`。

或直接 `python backend/main.py`（需自行补 uvicorn 启动逻辑；`backend/main.py` 只定义 `app`，
不含 `__main__` 入口）。

> **必须在仓库根目录启动**。`backend/core/pipeline.py`、`backend/core/symbol_index.py`、
> `backend/core/checkpoint.py`、`backend/tools/*.py` 都用 `os.path.abspath("workspace")`
> 或相对路径 `"workspace/..."` / `"sessions"`，从别处启动会指向错误目录。

### 1.3 验证服务与配置

```bash
# 1) 存活检查
curl http://127.0.0.1:8000/
# → {"status":"Coding Agent is running","endpoints":["/run","/encode","/profile"]}

# 2) 查看生效的模型接入参数（换模型后必查）
curl http://127.0.0.1:8000/profile
```

`/profile` 返回 `ORCH` 与 `WORKER` 两个角色的：
`profile`、`model`、`base_url`、`context_window`、`supports_tool_calls`、
`supports_json_mode`、`coupling`、`limits{...}`、`problems[]`。

`problems` 为空数组表示通过启动自检。

### 1.4 配置来源：`.env` 会自动加载

`backend/main.py` 启动时加载仓库根目录的 `.env`（在读取任何 `ORCH_*` / `WORKER_*`
之前执行）。`.env.example` 是模板，复制为 `.env` 即可生效。

```bash
copy .env.example .env
# 编辑 .env（放在**仓库根**），然后直接起服务
.\scripts\run.ps1
```

**两种方式都可用**，优先级为「已导出的环境变量 > `.env` 文件 > 内置默认值」：

```bash
# 方式 A：直接导出环境变量（适合临时覆盖）
$env:ORCH_MODEL="qwen2.5:7b"
.venv\Scripts\python.exe -m uvicorn bridge.app:app --app-dir . --port 8000

# 方式 B：写进 .env（推荐，持久）
```

> ⚠️ **测试与诊断脚本不走 `backend/main.py`**，因此**不会**加载 `.env`。
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

1. **路径前缀**。模型常写 `data/workspace/foo.py`，而索引键是 `foo.py`。
   代码已做归一化（`normalize_declared_path` 会剥掉 `data/workspace/`、
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
  "command": "import sum_1_to_100\nassert ... == 5050\nprint('PASS')"
}
```

> 注意：`CycleReport.verify` 在 `CodingCycle` 中是从
> `memory.verify_state` 重建的**精简三元组**，只有 `passed`/`detail`/`command`。
> 而 `CheckPipeline.run_verify()` 返回的是更完整的
> `{tool, passed, command, reason, parsed}`。

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
| `phase=failed`，`commit=null`，`rolled_back=true` | 全部尝试失败，已回退 |
| `success` 但 `error` 非空 | **不应发生**：成功路径会清空 `error` 与 `rolled_back` |

---

## 6. 如何新增一个工具

### 6.1 步骤

1. 选模块（新功能建议新建 `backend/tools/<name>.py`，或加入已有的同类模块）。
2. 用 `@register` 装饰异步函数。
3. 在 `backend/tools/__init__.py` **显式导入**该模块。

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
| 5 | **是否会被门禁使用**：只有 `check_syntax`、`run_lint`、`check_and_run` 参与门禁（由 `CheckPipeline` 按**名字硬编码**调用）。新工具默认只是模型可选，不参与成败判定。若要让新工具进门禁，需改 `backend/core/pipeline.py`。 |
| 6 | **避免与 `review_code` 职责重叠**。`review_code` 是**质量建议**（不决定成败）；若你的工具要产出判据，它应进 `CheckPipeline` 而**不是**注册成模型工具——否则模型可以绕过它。 |
| 7 | **路径安全**：写文件类工具请复用 `_safe_path` 的思路（见 `backend/tools/files.py`），并注意 `_PROTECTED = {".env","main.py","agent.py","pyproject.toml","requirements.txt"}` 是**受保护文件名**（比较的是 `basename`）。 |
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

- `run_levels.py` 会**清空 `data/workspace/`**（原有文件备份到
  `tests/output/_ws_backup` 并在结束时还原）。
- 结果写入 `tests/output/levels_result.json`，各级 CycleReport 在
  `tests/output/logs/`。
- 配套 `python tests/bench/analyze_levels.py` 做失败根因分类
  （需先跑过 `run_levels.py`）。
- 注意：`tests/README.md` 中的举例命令写的是 `python tests/run_unit.py`，
  与 `run_unit.py` 自身 docstring 一致。

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
| 3 | 清空或备份 `data/workspace/` | 避免历史产物干扰判断 |
| 4 | 记下当前能力基线（`2/8`，L1、L4 通过） | 用于判断改动是提升还是退化 |

### 8.2 改完必须确认

| # | 检查项 | 命令 / 方法 | 通过标准 |
|---|---|---|---|
| 1 | 单元测试无回归 | `python tests/run_unit.py` | 通过数与基线一致或更多 |
| 2 | **文档与代码一致** | `python tests/unit/test_doc_consistency.py` | 33/33 通过 |
| 3 | **文档版本戳已更新** | 看各文档顶部的 `同步至 CHANGELOG §N` | 与 `CHANGELOG` 最新条目一致 |
| 4 | 服务能起来 | `.\scripts\run.ps1` | 无异常退出 |
| 5 | 模型自检通过 | `curl /profile` | `problems` 均为 `[]` |
| 6 | 角色表状态符合预期 | `curl /profile` 的 `roles` | 必需角色 `available: true` |
| 7 | 检查点后端正常 | 看启动日志 `checkpoint 后端:` | 非 `none` |

> **第 2、3 项是文档漂移的防线**。改了代码或 CHANGELOG 后，
> 若忘了同步上游文档，这两项会失败——不必靠人回忆。
| 5 | 正向链路通 | `POST /encode` 跑单函数任务 | `phase=record`、`commit` 非空 |
| 6 | **反向门禁仍生效** | `python tests/diagnostics/gate_check.py` | `phase=failed`、`rolled_back=true` |
| 7 | 能力未退化 | `python tests/bench/run_levels.py` | 通过级别数 ≥ 基线 |

> 第 6 项最容易被忽略但最关键：**正向能跑通，不代表门禁还在拦**。
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
例如在 `data/workspace/.gitignore` 里加一行你自己的目录名。

---

## 10. Vue 执行可视化前端

### 10.1 启动

```powershell
.\scripts/run.ps1                 # 需要时自动构建前端，然后起服务
.\scripts/run.ps1 -Rebuild        # 强制重新构建
.\scripts/run.ps1 -SkipBuild      # 只起后端
```

打开 <http://127.0.0.1:8000/app>。手机看同一地址（把 `127.0.0.1` 换成本机局域网 IP）。

**`/app` 是可选路由**：`frontend/dist` 不存在时后端**不注册它**，其余接口一切照常。
判断挂没挂载看 `GET /` 的 `frontend.mounted`。

### 10.2 不用模型也能确认前端是好的

界面上点「演示运行」，或：

```bash
curl -X POST http://127.0.0.1:8000/api/runs -H "Content-Type: application/json" -d "{\"goal\":\"演示\",\"demo\":true}"
```

演示运行（`bridge/demo.py`）不发一次模型请求，但走**同一套事件词汇和同一个 SSE 通道**，
脚本里包含一次「manifest 失败 → 回退 → 重试 → 通过」。

### 10.3 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| 打开 `/app` 是 404 | 没构建前端 | `cd frontend && npm install && npm run build` |
| **界面像是旧的（改过的东西没生效）** | **`dist` 与 `src` 分了家** | `python scripts/freshness.py`；要修就 `--fix` 或 `cd frontend && npm run build`。**判据是重新构建后逐文件比，不看 mtime** |
| 顶栏「后端不可达」 | 服务没起 / 端口不对 | 见 §1.2；开发模式下看 Vite 代理的 `AGENT_BACKEND` |
| 页面进去但事件不动 | SSE 被中间层缓冲 | 直接访问 `/api/runs/{id}/stream` 看是否有流；确认没有反向代理在攒响应 |
| 「事件流中断」后自己恢复 | 正常：客户端带 `after=<seq>` 自动续订 | 持续不恢复时看后端日志是否有 500 |
| 进度条不动但后端在跑 | 该运行的事件流被写失败 | 存储是旁路，不影响 cycle；查 `data/storage_data/runs/<id>/events.jsonl` 是否存在 |
| `npm install` 报 `EPERM` | 沙箱/权限不允许派生带管道的子进程 | 换到允许的终端执行；或把 `--cache` 指到仓库内可写目录 |
| 改完 `.ps1` 一跑就语法错误 | 编辑工具去掉了 **UTF-8 BOM**，PS 5.1 按 GBK 解 | `python scripts/fix_bom.py`（幂等）→ `python tests/unit/test_ps1_encoding.py` |

### 10.3b 交付清单（每次交付前照做）

前三条是**门禁**，第 4 条是**原因**——**别只跑 typecheck 就当交付完了**：

| # | 命令 | 为什么 |
|---|---|---|
| 1 | `cd frontend && npm run build` | **交付物是 `dist/`**，不是 `src/` |
| 2 | `python scripts/freshness.py` | 复核"dist 就是当前源码构建的"，并打印产物哈希 |
| 3 | `python tests/run_unit.py` | 离线全量（含新鲜度门禁 `test_dist_freshness.py`） |
| 4 | —— | ⚠ `npm run typecheck` 会重新生成 `src/generated/expectations.ts`，**但不会重建 `dist/`** —— 这正是"改过的 ≠ 交付的"那个坑 |

`backup.ps1` 的 preflight 已经把第 2 条纳入：**dist 陈旧就不让备份通过**。

### 10.4 运行数据在哪

```
storage_data/runs/<run_id>/meta.json      运行终态、报告、摘要
storage_data/runs/<run_id>/events.jsonl   完整事件流（前端订阅的就是它）
```

`events.jsonl` 是**唯一真相**：界面上的历史回放就是把它重新喂进归约器。
进程重启后，之前标记为「正在跑」的运行会被改成 `cancelled`——
谎报「还在跑」比如实报错更糟。

### 10.5 升级时的额外回归项

```bash
python tests/unit/test_webui_runtime.py         # 离线：进度总线 + 运行管理器
python tests/diagnostics/check_frontend_stream.py  # 需后端在跑：SSE 端到端
cd frontend && npm run typecheck                   # 前端类型
```

**改了事件词表**（`bridge/progress.py` 的 `kind`）必须同时确认
`frontend/src/store/run.ts` 能处理它——未知 `kind` 会进事件流但不改状态，
不会让界面崩，但也不会显示新信息。

---

## 11. 备份纪律：做出一版可行之后，先备份，再继续完善

### 11.1 为什么这条不能省

**项目根目录没有 `.git`。** 它是复制版，原仓库在别处迭代，所以这里没有
`git checkout` / `git stash` 可用。改坏了就是改坏了。

「继续完善」和「把能跑的版本改坏」之间，唯一的区别就是**有没有上一个已知可用的节点**。

### 11.2 什么时候算「一版可行」

**下面三条全过**才算，缺一条都不算：

```bash
python tests/run_unit.py                            # 21/21，离线
cd frontend && npm run typecheck                       # 零错误
python tests/diagnostics/check_frontend_stream.py      # 17/17，需后端在 8000 端口跑着
```

如果这一版动了工作流本身（`backend/core/coding_cycle.py` / `orchestrator.py` / `pipeline.py`），
再加一条：`python tests/diagnostics/gate_check.py` 必须仍然拦住不可能的断言。

### 11.3 怎么用

```powershell
.\backup.ps1 -Note "这一版做到了什么"        # 打快照 + 验证 + 记进 VERSIONS.md
.\backup.ps1 -Label v2-重试动画 -Note "..."  # 带标签
.\backup.ps1 -SkipVerify                    # 跳过备份前验证（快，但不记验证结果）
.\backup.ps1 -List                          # 列出全部快照（新 → 旧）
.\backup.ps1 -Verify                        # 当前 vs 最近一版，看改了什么
.\backup.ps1 -Verify -From 20260925-234300  # 指定基准
.\backup.ps1 -Restore -From 20260925-234300 # 回退（会先自动再备份一次）
.\backup.ps1 -Restore -From v8 -Path docs/CHANGELOG.md   # 只退一个文件
.\backup.ps1 -ShowExcludes                  # 看排除清单
```

**`-Note` 别省。** 它写进快照的 `BACKUP.md`，也写进 `docs/VERSIONS.md`，
是给未来的你看的——"这版做到了什么"比时间戳有用得多。
留空时 `-List` 里就只有时间，等于没有线索。

**每次备份会自动做两件事**（`-SkipVerify` 可跳过第一件）：

1. **跑一遍离线验证**（单元测试 / 目录归属 / 前端类型），把结果记进 `docs/VERSIONS.md`。
   服务起着时还会跑端到端（`check_webui_stream.py`）；没起服务记"未跑"，不算失败。
2. **追加一条版本记录**到 `docs/VERSIONS.md`，含四样：
   标签与时间 · **改了什么**（对照上一版的机械 diff）· **验证结果** · **还原命令**。

> **验证不过**时：**仍然备份**，但记录里如实写"未通过"。
> 这与上游"验证不过拒绝备份"**刻意不同** —— 最需要备份的时候恰恰是东西坏掉的时候，
> 拒绝备份会让人失去唯一的退路。理由写在 `docs/VERSIONS.md` 的头部。
>
> `docs/VERSIONS.md` **只增不改**，不要手改（`tests/unit/test_versions.py` 钉住这一点）。

**`-Verify` 是"改动清单"的机械来源。** 本机没有 git，`git diff --stat` 用不了；
`-Verify` 按 SHA256 逐文件比，给出 `[改动] / [新增] / [删除]` 三张清单。
写变更评估文档时，"实际改了哪些文件"应当以它为准，而不是凭记忆列。
（实测价值：它抓到过一份手写清单**漏列了 6 个同步文档**。）

### 11.4 快照里有什么 / 没有什么

```
_backups/<时间戳>_<标签>/
  BACKUP.md        这一版做到了什么 + 目录构成 + 恢复方法
  manifest.json    每个文件的 sha256（-Verify 靠它做差异）
  files/           项目文件（保持原目录结构）
  undo-<时间戳>/   （仅在文件级回退后出现）被覆盖文件的**原**版本
```

| 不含 | 为什么 |
|---|---|
| `.venv/`、`frontend/node_modules/`、`.npm-cache/` | 依赖与缓存，可重建，体积数百 MB |
| `data/storage_data/`、`data/sessions/`、`tests/output/` | **运行态数据**；备份它会让每次快照都不相同，`-Verify` 就废了 |
| `data/workspace/` | 模型产出，且内含独立 git 仓库（回退机制用） |
| `.env` / `.env.local` | 含 API key，与仓库同样的保密要求 |
| `.interface_contract/` | **统筹方的只读镜像，不属于本仓库**（见下） |

`frontend/dist/` **在**快照里——它是构建产物，但带上它快照才开箱可跑。

`_backups/` 已加入 `.gitignore`：它是本地资产，每台机器各存各的。

> **`.interface_contract/` 为什么必须排除。** 它由统筹方按自己的节奏同步
> （内容会变、文件数会涨），留在快照里会让 `-Verify` 报出
> **不是本仓库发生的**新增/删除。备份的语义是"我的源码是什么样"，
> 混进别人的镜像这句话就不成立了。
> 上游仓库靠嵌套 `.gitignore`（内容 `*`）挡住它；本仓库不是 git 仓库，
> `.gitignore` 不生效，**只能靠排除清单**。
> `tests/unit/test_ps1_encoding.py` 钉住了这一条（从清单里删掉就红）。

### 11.5 回退

**整树回退**

```powershell
.\backup.ps1 -Restore -From 20260925-234300_v1-frontend-working
```

**文件级回退**（只退点名的文件，成本与风险按文件算）

```powershell
.\backup.ps1 -Restore -From v8 -Path bridge/audit.py
.\backup.ps1 -Restore -From v8 -Path docs/CHANGELOG.md -Path README.md
```

- 路径不在该快照里时**明确列出并跳过**，不静默忽略；
- 每个文件的当前处理结果会先打出来（`= 已一致` / `~ 会改动` / `+ 新增`）；
- 覆盖前把**被点名文件**的原版本存到 `_backups/<快照>/undo-<时间戳>/` ——
  **粒度回退配粒度的后悔药**（整仓自动快照对"只改了一个文档"太重）。

整树回退刻意做了两层保险：

1. **先自动给当前状态打一个快照**（`auto-before-restore`）——回退本身也可能后悔。
   这一步**永远执行**，`-Force` 也不跳过（只有 `-NoAutoBackup` 才跳，一般别用）。
2. 再要求输入 `yes` 确认。`-Force` 只跳过这一步确认。

回退后要做的：

| 步骤 | 命令 |
|---|---|
| 补依赖（`node_modules` 不在快照里） | `cd frontend && npm install`（仅在缺失时） |
| 重跑验证三件套 | 见 §11.2 |
| 重新起服务 | `.\scripts/run.ps1` |

> **文件级回退有一条限制**：跨模块的新增不能单独退。
> 例如 `bridge/contract_vocab.py` 被 `spec.py` / `audit.py` / `agent_api.py` import，
> 单独退一个文件会 import 失败——要退就连调用方一起退。

### 11.6 三个已知坑（都踩过）

1. **`.ps1` 必须是 UTF-8 带 BOM。**
   本机 `pwsh` 实际是 **Windows PowerShell 5.1**，它把无 BOM 的脚本按 ANSI(GBK) 读。
   中文注释会变乱码，更糟的是 here-string 会**跨行解析错位**，报出莫名其妙的
   `An empty pipe element is not allowed`。改这两个脚本后请确认文件编码。
   **现在有机械门禁**：`python tests/unit/test_ps1_encoding.py`
   （失败时会直接打印补 BOM 的命令）。这个坑踩过两次——第二次是
   **编辑工具按 UTF-8 无 BOM 写回**，把原有 BOM 静默丢掉了。

2. **PowerShell 函数要显式写 `param()`。**
   没有 `param()` 时 `New-Snapshot -Label "x"` 不会绑定参数，函数体会去读
   **脚本作用域**的同名变量——从别的函数里调用时它可能是空的，标签就悄悄丢了
   （实测自动快照全叫成了 `_snapshot`）。

3. **排除清单是唯一的排除机制。**
   本仓库不是 git 仓库，`.gitignore` **不生效**。新增"不该进快照"的目录时，
   必须同时改 `backup.ps1` 的 `$excludeDirs` ——否则它会静默进快照，
   并在之后的 `-Verify` 里制造噪声（`.interface_contract/` 就是这样混进去的）。

