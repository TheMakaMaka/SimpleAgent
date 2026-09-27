# 模块与接口参考

> **同步至 CHANGELOG §31** —— 本文只描述**当前状态**；修复过程见 `CHANGELOG.md`。
>
> 所有签名均从代码实际读出。标 `**(未使用)**` 或 `(预留)` 的表示
> 定义了但没有消费方——详见 §19 当前不一致清单。

## 目录

- [1. core/model_profile.py](#1-coremodel_profilepy) — 模型接入标准参数入口
- [2. core/llm.py](#2-corellmpy) — LLM 适配器
- [3. core/config.py](#3-coreconfigpy) — 角色解析
- [4. core/cycle.py](#4-corecyclepy) — 阶段与报告契约
- [5. core/coding_cycle.py](#5-corecoding_cyclepy) — 一轮流程编排
- [6. core/orchestrator.py](#6-coreorchestratorpy) — 主循环
- [7. core/worker.py](#7-coreworkerpy) — 子循环
- [8. core/pipeline.py](#8-corepipelinepy) — 门禁调度
- [9. core/manifest.py](#9-coremanifestpy) — 交付契约
- [10. core/symbol_index.py](#10-coresymbol_indexpy) — 结构事实
- [11. core/checkpoint.py](#11-corecheckpointpy) — 回退
- [12. core/memory.py](#12-corememorypy) — 全局状态
- [13. core/context.py](#13-corecontextpy) — 跨层传参
- [14. core/prompts.py](#14-corepromptspy) — 提示词
- [15. core/task.py](#15-coretaskpy) — 数据类
- [16. tools/registry.py](#16-toolsregistrypy) — 工具注册表
- [17. 工具清单表](#17-工具清单表)
- [18. storage/session.py](#18-storagesessionpy) — 会话落盘
- [19. 文档与代码不一致清单](#19-文档与代码不一致清单)
- [20. `bridge/` 与 `bridge/progress.py`](#20-bridge-与-bridgeprogresspy) — 适配层与实时事件流
- [21. `bridge/spec.py`](#21-bridgespecpy) — 标定方案
- [22. `bridge/triage.py`](#22-bridgetriagepy) — 失败归因
- [23. `bridge/audit.py`](#23-bridgeauditpy) — 责任自审查

---

## 1. `backend/core/model_profile.py`

**职责**：模型接入的**唯一**标准参数入口。所有"数字类"预算与模型特有补偿都集中在此。

**依赖**：仅标准库（`os`、`dataclasses`）。

### `ModelCapabilities`

流程对模型的能力声明，用于启动自检。

| 字段 | 默认 | 含义 |
|---|---|---|
| `supports_tool_calls: bool` | `True` | 是否支持 tool_calls（子任务执行强依赖） |
| `supports_json_mode: bool` | `False` | 是否支持 `response_format={"type":"json_object"}` |
| `supports_system_role: bool` | `True` | 是否支持 system role |
| `context_window: int` | `8192` | 上下文窗口 |

### `ModelLimits`

所有数字类参数的唯一入口。

| 字段 | 默认 | 含义 |
|---|---|---|
| `max_tokens` | `4096` | 单次生成上限 |
| `max_errors` | `3` | 连续工具报错上限 |
| `max_steps` | `15` | 单个子任务步数上限 |
| `max_rounds` | `15` | 主循环轮次上限 |
| `max_same_task` | `2` | 同一任务最多尝试次数 |
| `max_attempts` | `2` | 一个 cycle 最多尝试次数 |
| `temperature` | `0.1` | 采样温度 |
| `tool_result_chars` | `1500` | 工具结果回灌截断长度（字符） |

```python
ModelLimits.from_context_window(context_window: int, **overrides) -> ModelLimits
```

推导规则（`cw = max(2048, int(context_window))`）：

| 输出 | 公式 |
|---|---|
| `max_tokens` | `min(cw // 2, 4096)` |
| `rounds, steps, attempts` | `cw<=8192` → `15, 15, 2`；`cw<=32768` → `20, 20, 3`；否则 `30, 25, 3` |
| `tool_result_chars` | `max(800, min(cw // 6, 8000))` |

> `max_tokens` 刻意在 `cw=8192` 时保持 4096——这是实测可用的值，
> 推导公式不允许在这一档回退。需要更大生成预算请显式覆盖 `MAX_TOKENS`。

### `ModelCoupling`

模型特有补偿。**可整体丢弃**。

| 字段 | 默认 | 消费方 |
|---|---|---|
| `plan_hints: tuple[str, ...]` | `()` | `Worker.run` → `looks_like_plan()` |
| `repair_json: bool` | `True` | `LLMClient.chat_json` → `extract_json(repair=)` |
| `error_prefixes: tuple[str, ...]` | `()` | **(未使用)** |
| `notes: str` | `""` | `/profile`、`describe()` 展示 |

```python
def looks_like_plan(self, text: str) -> bool
def matches_error_prefix(self, text: str) -> bool   # (未使用)
```

内置常量：`DEFAULT_COUPLING`（全空，不做任何补偿）、
`QWEN_COUPLING`（`plan_hints=("我将","首先我","接下来我","我打算","计划如下")`，
`error_prefixes=("Error:","错误：","执行异常","失败：")`）。

### `ModelProfile`

```python
@dataclass
class ModelProfile:
    name: str = "default"
    base_url: str = "http://localhost:11434/v1"
    model: str = "qwen2.5:7b"
    api_key: str = "ollama"
    request_timeout: float = 120.0
    capabilities: ModelCapabilities
    limits: ModelLimits
    coupling: ModelCoupling
```

```python
ModelProfile.from_env(prefix: str = "LLM") -> ModelProfile
def validate(self, role: str = "LLM") -> list[str]   # 空列表 = 可用
def describe(self) -> str
```

`from_env` 读取的环境变量：`{prefix}_MODEL`、`_BASE_URL`、`_API_KEY`、
`_CONTEXT_WINDOW`、`_PROFILE`、`_COUPLING`、`_JSON_MODE`、`_TIMEOUT`，
以及预算覆盖 `_MAX_TOKENS` `_MAX_ROUNDS` `_MAX_STEPS` `_MAX_ATTEMPTS`
`_MAX_ERRORS` `_MAX_SAME_TASK` `_TEMPERATURE` `_TOOL_RESULT_CHARS`。

`__post_init__` 会把 `capabilities.context_window` 抬到至少
`limits.max_tokens`（见 §19 不一致 #6）。

模块级函数：`register_profile(profile)`、`get_profile(name)`。
内置档位表 `_BUILTIN_PROFILES` 含 `"default"` 与 `"qwen"`；
`_guess_profile_name(model)` 按模型名含 `"qwen"` 选中 qwen 档。

**扩展点**：新增模型只需 `register_profile()` 注册一个档位，
或用环境变量覆盖；**不需要改工作流代码**。

---

## 2. `backend/core/llm.py`

**职责**：LLM 适配层。请求构造、响应解包、JSON 容错、耦合补偿。

**依赖**：`openai.AsyncOpenAI`、`.model_profile`。

```python
class ModelCapabilityError(RuntimeError)

class LLMClient:
    def __init__(self, profile: ModelProfile | None = None)
        # profile 为 None 时用 ModelProfile() 默认值
        # validate() 有 problem 时抛 ModelCapabilityError
        # self.config = self.profile（向后兼容旧调用方）

    async def chat(messages: list[dict],
                   tools: list[dict] | None = None,
                   force_json: bool = False) -> dict
        # 返回 {"content", "tool_calls", "finish_reason"}

    async def chat_json(messages: list[dict]) -> dict
        # 解析失败时返回 {"_parse_failed": True, "_raw": <原文>}
```

行为要点：
- `temperature`、`max_tokens` 取自 `profile.limits`。
- 有 `tools` 时附加 `tool_choice="auto"`。
- **仅当** `capabilities.supports_json_mode` 为真时才发
  `response_format={"type":"json_object"}`，否则靠 prompt 约束。

```python
def extract_json(text: str, repair: bool = True) -> dict | None
def _first_balanced_object(text: str) -> str | None      # 私有
def _repair_json_text(raw: str) -> str                   # 私有
```

`extract_json` 流程：剥离 ```` ```json ```` 围栏 → 括号匹配取第一个完整对象
（正确处理字符串内括号与转义）→ `json.loads` → 失败且 `repair=True` 时
按 `_repair_json_text` 修复后重试。修复内容：去 `//` 行注释、去尾逗号。
失败返回 `None`，**不静默造数据**。

**扩展点**：换模型通常不需要改本文件，只改 `ModelProfile`。

---

## 3. `backend/core/config.py`

**职责**：角色解析。`ORCH` / `WORKER` 两类角色的档位来源。

**依赖**：`.model_profile`。

```python
LLMConfig = ModelProfile      # 向后兼容别名

# 显式角色表（推荐入口）
ROLES: dict[str, RoleSpec]    # orchestrator / worker / reviewer / package_optimizer

def resolve_role(role: str, *, required: bool | None = None,
                 resolved: dict[str, ModelProfile] | None = None) -> ModelProfile
def resolve_roles(*names: str) -> dict[str, ModelProfile | None]
def describe_roles() -> list[dict]
def role_available(role: str) -> bool

# 向后兼容（按 env 前缀解析，继承关系需调用方自己传 fallback）
def resolve_profile(prefix: str = "ORCH",
                    fallback: ModelProfile | None = None) -> ModelProfile
```

**角色表是显式设计**。未配置时的三条走向：

| 情形 | 行为 |
|---|---|
| 角色声明了 `inherits_from` | 继承（**只有 `worker` → `orchestrator`**） |
| 角色声明了 `has_builtin_default` | 用内置默认档位（orchestrator / worker） |
| 都没有 | 抛 `RoleNotConfigured`（reviewer / package_optimizer） |

关键区分：**「未配置」≠「未启用」**。`orchestrator` 有内置默认
（ollama + qwen2.5:7b），未配置但仍可用；`reviewer` 没有默认，
未配置就是未启用，**绝不静默继承编排器模型**（否则表现为"以为请了审查员，
实际还是同一个模型在审自己"，且不报错）。

`main.resolve_profiles()` 只解析 `orchestrator` / `worker` 两个必需角色。
`GET /profile` 的 `roles` 字段如实展示每个角色的 `available` / `source`，
未启用的显示 `available: false, model: null`。

**新增角色**时在 `ROLES` 里登记即可——`resolve_role` 对未登记的角色名会明确报错。

---

## 4. `backend/core/cycle.py`

**职责**：阶段枚举与 `CycleReport` 契约。**术语定义处**。

**依赖**：仅标准库。

术语（避免与主循环的 round 混淆）：

| 术语 | 含义 |
|---|---|
| Cycle | 从「规划」到「记录」的完整一遍，本模块的单位 |
| Orchestrator round | 主循环内部的一次拆解决策，属于 Cycle 内部细节 |
| Worker step | 子循环内部的一次工具调用，属于 Cycle 内部细节 |

```python
class CyclePhase(str, Enum):
    PLAN = "plan"; WRITE = "write"; CHECK = "check"
    VERIFY = "verify"; RECORD = "record"; FAILED = "failed"

PHASE_ORDER: tuple[CyclePhase, ...] = (PLAN, WRITE, CHECK, VERIFY, RECORD)

@dataclass(frozen=True)
class VerifyCommand:
    command: str
    reason: str = ""
    expect_exit: int = 0      # 期望退出码；run_verify 会传给 check_and_run
    def label(self) -> str
```

> `PHASE_ORDER` **不是**文档性常量：`CycleReport.enter()` 用它强制校验推进顺序，
> 非法推进（跳跃/倒退）直接抛 `ValueError`（见上文 `enter()` / `is_valid_transition()` 说明）。

```python
@dataclass
class CycleReport:
    cycle_id: str
    goal: str
    phase: CyclePhase = CyclePhase.PLAN
    transitions: list[str] = field(default_factory=list)
    attempts: int = 0
    check_steps: list[dict] = field(default_factory=list)
    manifest: dict | None = None
    verify: dict | None = None
    touched_files: list[str] = field(default_factory=list)
    commit: str | None = None
    rolled_back: bool = False
    error: str | None = None

    def enter(self, phase: CyclePhase) -> None   # 校验顺序后设 phase 并追加 transitions
    def is_valid_transition(self, phase: CyclePhase) -> bool
    def to_dict(self) -> dict
```

`enter()` **强制校验推进顺序**（依据 `PHASE_ORDER`）：
除 `FAILED` 外阶段必须恰好前进一步，不得跳跃或倒退；`FAILED` 可从任意阶段进入，
之后只能回到 `PLAN`。非法推进抛 `ValueError` 并给出合法顺序提示。
回归测试：`tests/unit/test_phase_order.py`。

---

## 5. `backend/core/coding_cycle.py`

**职责**：一轮编码流程的编排。把 PLAN → WRITE → MANIFEST → CHECK → VERIFY → RECORD
串成整体，并管理 attempt 循环、回退、重试提示注入。

**依赖**：`checkpoint`、`context`、`cycle`、`memory`、`orchestrator`、`pipeline`、`task`、`worker`。

```python
class CodingCycle:
    def __init__(self,
                 orchestrator: Orchestrator,
                 worker: Worker,
                 pipeline: CheckPipeline | None = None,
                 checkpoint_prefer: str = "git",
                 max_attempts: int = 2,
                 verbose: bool = True)

    async def run(self, goal: str,
                  verify_command: VerifyCommand | None = None
                  ) -> tuple[CycleReport, SharedMemory]
```

内部方法：

| 方法 | 作用 |
|---|---|
| `_setup_orchestrator(verify_command)` | 把 pipeline 与 verify_command 注入编排器，返回它 |
| `_snapshot_prior_files()` | 记录 workspace 现有文件到 `self._prior_files` |
| `_rollback(base_ref, report)` | 回退并置 `report.rolled_back` |
| `_new_file_artifacts(memory)` | 取 `kind=="file"` 的产物路径 |
| `_manifest_error_text(manifest)` | 把 error 级 violation 转成一句重试提示 |
| `_check_error_text(check)` | 取首个未通过步骤的明细 |
| `_retry_goal(goal, report)` | 重试时注入失败原因 / 涉及文件 / manifest 缺口 / 已回退标记 |

`cycle_id` 格式：`cy_YYYYmmdd_HHMMSS_ffffff`。

**扩展点**：审查阶段若要插入，位置需在 `run` 内显式添加，
推荐 VERIFY 后 / RECORD 前（见 `CYCLE.md` §10.2）。

---

## 6. `backend/core/orchestrator.py`

**职责**：主循环。拆解任务、指纹去重、串行调度子循环、**验证结论回流**。

**依赖**：`.llm`、`.memory`、`.prompts`、`.task`、`.worker`；运行时延迟导入 `.context` 与 `tools`。

```python
@dataclass
class OrchestratorResult:
    ok: bool
    answer: str
    memory: SharedMemory
    verify_command: Optional[dict] = None
    declared_files: Optional[list] = None

class Orchestrator:
    def __init__(self, llm: LLMClient, worker: Worker,
                 max_rounds: int | None = None,
                 max_same_task: int | None = None,
                 pipeline=None,
                 verify_command: Optional[dict] = None)
    async def run(self, goal: str) -> OrchestratorResult
```

`max_rounds` / `max_same_task` 为 `None` 时取 `llm.profile.limits` 的值
（分别回退到 15 / 2）。

内部方法：

| 方法 | 作用 |
|---|---|
| `_files_to_verify(memory, baseline_files)` | 有 cycle 级清单则用它，否则取 `write_file` 产物 |
| `_verify_fingerprint(verify_command, files)` | `sha1(command + "\|" + sorted(files))[:16]` |
| `_verify_detail(vr)` | 从验证结果提取一句可读明细 |
| `_decide(memory)` | 构造 prompt → `chat_json` → 过滤幻觉工具名 |
| `_parse_tasks(raw_tasks)` | 转 `Task` 列表 |
| `_should_skip(memory, task)` | 指纹去重；成功过或失败达上限则跳过 |

关键行为：
- `caller_verify = bool(self.verify_command)`——调用方的验收标准权威，
  仅在未提供时才采纳模型自拟的 `verify`。
- 验证通过时**立即**返回，`answer` 形如 `"验证命令通过，目标达成（第 N 轮）"`。
- 达到轮次上限时，若 `memory.verified_passed()` 仍返回 `ok=True`。

---

## 7. `backend/core/worker.py`

**职责**：子循环。用工具完成**单个**任务。

**依赖**：`.llm`、`.model_profile`、`.prompts`、`.task`、`tools`。

```python
class Worker:
    def __init__(self, llm: LLMClient,
                 limits: ModelLimits | None = None,
                 coupling: ModelCoupling | None = None)
    async def run(self, task: Task, context: str) -> TaskResult
```

模块级辅助函数：

| 函数 | 作用 |
|---|---|
| `_normalize_code(code)` | 归一化换行与行尾空白，用于重复提交判重 |
| `_code_hash(code)` | `hash(_normalize_code(code))` |
| `_clip(text, limit)` | 按预算截断回灌内容 |
| `_extract_code_block(text)` | 从 content 抽 ```` ```python ```` 代码块 |
| `_dbg(path_suffix, content)` | 写 `data/workspace/_debug/` 调试快照 |

内部方法：`_invoke(name, arguments_json)`、`_maybe_artifact(...)`、`_parse_args(arguments_json)`。

`_parse_args` 先 `json.loads`，失败后回退 `ast.literal_eval`（容忍 Python 字面量写法）。

产物生成规则（`_maybe_artifact`）：

| 条件 | 产生 Artifact |
|---|---|
| `run_python` 且非错误 | `kind="code"`，`key=f"{task_id}_code"` |
| `write_file` 且返回以 `OK:FILE\|` 开头 | `kind="file"`，`path` 为管道串第 2 段 |

**门槛**：`run` 用 `task.max_steps or self.limits.max_steps`
（`Task.max_steps` 默认 0 表示"用档位值"）。

---

## 8. `backend/core/pipeline.py`

**职责**：门禁。程序调度 manifest / check / verify，**不经模型决策**。

**依赖**：`.context`、`.cycle`、`.manifest`、`tools`。

```python
class CheckPipeline:
    def __init__(self, run_lint: bool = True, verify_timeout: float = 90.0)
        # verify_timeout 为预留参数：实际执行超时来自 tools/verify.py
        # 与 tools/python_exec.py 的 TIMEOUT_SECONDS（60s）。保留是为了将来
        # 把超时统一收归预算管理，避免现在两处各写一个值。

    @staticmethod
    def run_manifest() -> Manifest
    @staticmethod
    def _collect_python_files(touched: list[str]) -> list[str]

    async def run_check(self, touched: list[str]) -> dict[str, Any]
    async def run_verify(self, command: VerifyCommand) -> dict[str, Any]
```

`run_check` 返回：

```python
{"passed": bool, "skipped_reason": str | None,
 "steps": [{"tool", "file", "passed", "parsed", ["status"]}],
 "blocking_file": str | None}
```

`run_check` 行为：
- 无 `.py` 改动 → `passed=True` 且 `skipped_reason="本次 cycle 没有产生 .py 文件改动"`。
- 文件不存在 / 读取失败 → 直接判不通过，`blocking_file` 为该文件。
- `check_syntax` 为**阻塞门**，任一文件不过即整体不通过。
- `run_lint` 为**非阻塞**：`status ∈ {"passed","failed","skipped"}`，
  仅 `"failed"` 影响 `passed`。

`run_verify` 返回：

```python
{"tool": "check_and_run", "passed": bool, "command": str,
 "reason": str, "parsed": dict}
```

空命令直接判 `passed=False`。判据是 `check_and_run` 返回体里的 `ok`。

---

## 9. `backend/core/manifest.py`

**职责**：交付契约。对照「计划声明」与「实际文件」，产出可判定的 violation。

**依赖**：`.symbol_index`。

```python
BLOCKING_SEVERITIES = {"error"}

def normalize_declared_path(path: str) -> str
    # 去前导 "/"、循环去 "./"、剥掉 "workspace/" 前缀

@dataclass
class DeclaredFile:
    path: str
    role: str = ""
    symbols: list[str] = field(default_factory=list)
    @classmethod
    def from_raw(cls, raw) -> "DeclaredFile | None"
    # 接受 str 或 dict；dict 的 key 可为 path/filename/file、role/purpose、symbols/exports
    # symbols 为字符串时按逗号或空白切分

@dataclass
class Manifest:
    declared: list[DeclaredFile]
    actual: list[dict]
    violations: list[dict]
    checked: bool = False
    note: str = ""
    @property
    def blocking(self) -> list[dict]      # severity in BLOCKING_SEVERITIES
    @property
    def passed(self) -> bool              # not blocking
    def to_dict(self) -> dict
    def to_prompt(self, limit: int = 12) -> str   # 供模型阅读的紧凑陈述

def parse_declared(raw_files) -> list[DeclaredFile]
def check_manifest(declared: list[DeclaredFile],
                   index: dict[str, ModuleEntry] | None = None,
                   strict_extra_files: bool = False) -> Manifest
def architecture_view(index: dict[str, ModuleEntry] | None = None) -> dict
```

violation 种类与严重度：

| severity | kind | 触发条件 |
|---|---|---|
| `error` | `declared-missing` | 声明的文件在索引中不存在 |
| `error` | `declared-broken` | 文件存在但 `syntax_ok` 为假 |
| `error` | `symbol-missing` | 缺声明的符号（模块级符号或类方法名均可） |
| `warning` | `dangling-import` | 本地模块间 import 不存在的模块 |
| `warning` | `imports-missing-declared-module` | 导入了「本次声明要产出但不存在」的模块 |
| `warning` | `unexpected-file` | 仅在 `strict_extra_files=True` 时产出（默认不产出） |

行为要点：
- `declared` 为空时 `checked=False`，**不做判定**（避免把"模型没声明"误判成失败）。
- 符号可用集合 = 模块级符号名 ∪ 类方法名（`sig.split("(")[0]`）。
- 查索引时先按归一化路径，再兜底尝试 `data/workspace/{path}`。
- 签名只作为信息，**不参与判定**。

`architecture_view` 返回 `{modules, totals, note}`，其中每个 module 含
`path`、`module`、`role_hint`（恒为空串，设计注记未实现）、`exports`
（`{name, kind, signature}`）、`depends_on`、`lines`、`sha1`。

---

## 10. `backend/core/symbol_index.py`

**职责**：结构事实。用 AST 扫描 workspace，产出符号、签名、依赖。

**依赖**：`ast`、`hashlib`、`os`、`dataclasses`。

```python
WORKSPACE_DIR = os.path.abspath("workspace")
_SKIP_DIRS = {"_tmp", "_debug", "__pycache__", ".git", ".venv", "node_modules"}

@dataclass
class Symbol:
    name: str
    kind: str            # "function" | "async_function" | "class"
    signature: str       # "add(a, b)" / "Stack" / "run(args)"
    lineno: int
    methods: list[str] = field(default_factory=list)   # 仅 class
    def to_dict(self) -> dict

@dataclass
class ModuleEntry:
    path: str            # 相对 workspace，正斜杠
    module: str          # "pkg.mod"
    package: str         # "pkg"；顶层为空串
    symbols: list[Symbol]
    imports: list[str]   # 原始 import 目标
    local_deps: list[str]# 解析后指向本地模块的依赖
    sha1: str
    lines: int
    syntax_ok: bool = True
    error: str | None = None
    def symbol_names(self) -> set[str]
    def to_dict(self, include_code: bool = False) -> dict

def analyze_file(abs_path: str, rel_path: str) -> ModuleEntry
def build_index(base_dir: str | None = None) -> dict[str, ModuleEntry]
def find_symbol(index: dict[str, ModuleEntry], name: str) -> list[dict]
def dangling_imports(index: dict[str, ModuleEntry]) -> list[dict]
def summarize(index: dict[str, ModuleEntry]) -> dict     # (未被工具消费)
```

私有辅助：`_format_signature`、`_ModuleVisitor`、`_module_name_for`、
`_resolve_local`、`_local_packages`。

行为要点：
- 语法错误不抛异常，降级为 `syntax_ok=False` 并填 `error`。
- `_ModuleVisitor` **只收模块级符号与类方法**，不深入函数体
  （避免把嵌套函数当成模块符号）。
- `from . import a, b` 记录为 `.a` 与 `.b`（而非 `"."`），
  否则无法判断 a/b 是否存在。
- `_local_packages` 从**目录结构**推导（任何含 `.py` 的目录视为包），
  不依赖 `package` 字段——顶层包的 `package` 是空串，靠字段会漏掉。
- `dangling_imports` **刻意保守**：只报相对导入无法解析、
  以及顶层是本地包但成员不存在。裸的顶层名（如 `import numpy`）一律不报。
- 不使用 grep 或正则匹配代码（避免字符串内容被误判为真实符号）。

---

## 11. `backend/core/checkpoint.py`

**职责**：编码回退。每 cycle 一个检查点，git / snapshot 双后端。

**依赖**：`json`、`os`、`re`、`shutil`、`subprocess`、`dataclasses`、`datetime`、`typing.Protocol`。

```python
WORKSPACE_DIR = os.path.abspath("workspace")
SNAPSHOT_ROOT = os.path.abspath(os.path.join(os.path.dirname(WORKSPACE_DIR), ".checkpoints"))
_BOT_NAME = "SimpleAgent2 Bot"
_BOT_EMAIL = "agent@localhost"

@dataclass
class Checkpoint:
    ref: str
    label: str

def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[int, str, str]

class CheckpointBackend(Protocol):
    name: str
    def is_available(self) -> bool
    def init(self) -> None
    def commit(self, label: str) -> Checkpoint | None
    def rollback(self, ref: str) -> bool
    def current_ref(self) -> str | None
```

| 类 | `name` | 说明 |
|---|---|---|
| `GitBackend` | `"git"` | `init()` 写本地身份 + 生成 `.gitignore`；`commit()` 无变更时复用 HEAD；`rollback()` = `reset --hard` + `clean -fd` |
| `FileSnapshotBackend` | `"snapshot"` | 快照目录 `.checkpoints/snapNNNN` + `index.json`；`init()` 从索引恢复计数器，避免同进程第二个 cycle 覆盖 |
| `CheckpointManager` | `"git"`/`"snapshot"`/`"none"` | 按 `prefer` 择优探活并 `init()` |

```python
class CheckpointManager:
    def __init__(self, prefer: str = "git")
    @property
    def name(self) -> str
    def commit(self, label: str) -> Checkpoint | None
    def rollback(self, ref: str) -> bool
    def current_ref(self) -> str | None
```

`CheckpointManager` 的所有方法都吞异常并返回 `None`/`False`，
保证回退失败不会打断主流程。

`SNAPSHOT_ROOT` 刻意放在 workspace **之外**，避免快照把自己提交进仓库。

---

## 12. `backend/core/memory.py`

**职责**：全局状态。主循环唯一持有；Worker 只拿只读快照。

**依赖**：`.task`。

```python
@dataclass
class MemoryRecord:
    task: Task
    result: TaskResult

class SharedMemory:
    def __init__(self, goal: str)
    # 属性：goal, records, artifacts{}, facts[], verify_state, _verified_fingerprint, _fp_count

    def record(self, task, result) -> None
    def add_fact(self, fact: str) -> None            # (未被工作流调用)
    def count_fingerprint(self, task) -> int         # (未被工作流调用)

    def set_verify(self, passed: bool, detail: str, command: str, fingerprint: str) -> None
    def already_verified_at(self, fingerprint: str) -> bool
    def verified_passed(self) -> bool

    def summary_for_orchestrator(self, max_records: int = 12) -> str
    def context_for_worker(self, task: Task) -> str
```

`summary_for_orchestrator` 输出顺序：目标 → 关键事实（`facts` 非空时，
取末 8 条）→ 已有产物 → 最近 `max_records` 条任务 → 失败任务（末 5 条）
→ **【验证结论】（放最后）**。

`context_for_worker` 解析 `task.context_refs`：优先按 artifact key 找
（`kind=="file"` 只给路径不展开内容），否则按 task_id 找，都没有则输出
`<missing ref='...'/>`。

> `facts` 机制目前未被接线：`add_fact` 无调用方，所以 `facts` 恒为空，
> `summary_for_orchestrator` 里的「关键事实」段是死代码。属计划中的
> "结构化上下文压缩"能力的一部分。

---

## 13. `backend/core/context.py`

**职责**：用 `ContextVar` 跨层传参，避免"先建 orchestrator 再建 cycle"
的构造顺序循环依赖。

**依赖**：`contextvars`。

```python
def set_cycle_files(files: list[str]) -> Token
def get_cycle_files() -> list[str] | None
def reset_cycle_files(token) -> None

def set_declared_files(raw) -> object
def get_declared_files()
def reset_declared_files(token) -> None
```

两个 ContextVar 的默认值都是 `None`。`reset_*` 吞 `ValueError`/`LookupError`。

使用方：`CodingCycle.run` 设置、`Orchestrator.run` 读 `get_cycle_files()`、
`CheckPipeline.run_manifest` 读 `get_declared_files()`。

---

## 14. `backend/core/prompts.py`

**职责**：提示词模板。

**依赖**：无。

模块级常量：`ORCHESTRATOR_SYSTEM`、`WORKER_SYSTEM`。

```python
def build_worker_user_message(task, context: str) -> str
    # 产出 <task id='...'> 任务/期望产出/建议工具 </task> + <context>...</context>
```

`ORCHESTRATOR_SYSTEM` 的 12 条规则中，与门禁直接相关的：

| 规则 | 内容 |
|---|---|
| 4 | 读取输入末尾的「【验证结论】」；通过则必须 `status=done` 且 `tasks=[]` |
| 11 | 必须给出 `verify` 字段，用 `assert` 表达验收条件 |
| 12 | 必须给出 `files` 字段，列出**全部**产出文件与符号名；不产出文件则 `[]` |

`WORKER_SYSTEM` 的 10 条规则中，关键的：

| 规则 | 内容 |
|---|---|
| 6 | 验证代码能否跑通优先用 `check_and_run`，不要拆两步 |
| 8 | `run_lint` 返回 `ok: null` 表示**未执行**，不等于通过 |
| 9 | 写完 `.py` 可用 `review_code` 自查（**建议**，不决定成败） |
| 10 | 涉及多文件时用 `get_architecture` / `get_module` / `find_symbol`，不要逐个 `read_file` |

---

## 15. `backend/core/task.py`

**职责**：核心数据类。

**依赖**：`hashlib`、`dataclasses`、`typing`。

```python
ArtifactKind = Literal["code", "file", "data", "text"]

@dataclass
class Artifact:
    key: str
    kind: ArtifactKind
    content: Optional[str] = None
    path: Optional[str] = None
    meta: dict = field(default_factory=dict)
    def preview(self, n: int = 120) -> str

@dataclass
class Task:
    id: str
    description: str
    expected_output: str = ""
    tool_hint: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    max_steps: int = 0      # 0 = 用模型档位的 ModelLimits.max_steps
    def fingerprint(self) -> str      # sha1(description.strip().lower())[:12]

@dataclass
class TaskResult:
    task_id: str
    ok: bool
    output: str
    artifacts: list[Artifact] = field(default_factory=list)
    error: Optional[str] = None
    steps_used: int = 0
    def summary(self) -> str
```

`fingerprint` 基于**描述文本**，所以同语义不同措辞会被判为不同任务
（实测确认，见 `docs/ARCHITECTURE.md` §6.3）。

---

## 16. `backend/tools/registry.py`

**职责**：工具注册表。

**依赖**：`json`、`typing`。

```python
TOOLS_MAP: dict[str, dict] = {}

def register(name: str, description: str, parameters: dict)
    # 装饰器；把 {"function", "description", "parameters"} 写入 TOOLS_MAP

def tool_schemas() -> list[dict]
def err(msg: str) -> str                    # 返回 "Error: {msg}"
def truncate(text: str, limit: int = 4000) -> str
def is_error_result(result: str) -> bool
```

`is_error_result` 判定顺序：先尝试 `json.loads`，若是 dict 且含 `"ok"` 键，
返回 `data["ok"] is False`；否则回退字符串匹配
（`startswith("Error:")` 或含 `"错误："`）。

**扩展点**：新增工具只需写 `@register(...)` 并在 `backend/tools/__init__.py`
显式 `from . import <模块>`（否则装饰器不执行，工具不会注册）。
详见 `docs/OPERATIONS.md` §6。

---

## 17. 工具清单表

共 **18** 个工具，按 profile 分组。运行时核对方式：

```python
from tools import TOOLS_MAP
from tools.registry import describe_profiles
len(TOOLS_MAP)          # 18
describe_profiles()     # {'coding': [...15], 'general': [...4]}
```

`profiles` 由 `@register(..., profiles=(...))` 声明，Worker 按当前 profile
取 `tool_schemas(profile)`——**未声明的工具不下发**。

### coding profile（15 个）

编码流程使用。Worker 默认走这个 profile。

| 工具名 | 定义于 | 用途 | 参与门禁 |
|---|---|---|---|
| `run_python` | `python_exec.py` | 执行代码，超时 60s，输出上限 4000 字符 | ❌ |
| `check_and_run` | `verify.py` | 语法检查 + 执行合一，返回 `parsed_error` | ✅ VERIFY |
| `check_syntax` | `code_checks.py` | AST 语法检查 | ✅ CHECK（阻塞） |
| `run_lint` | `code_checks.py` | ruff lint（未装则 `ok:null` + `skipped`） | ✅ CHECK（非阻塞） |
| `write_file` | `files.py` | 写 workspace 文件；返回 `OK:FILE\|路径\|大小\|说明` | ❌ |
| `read_file` | `files.py` | 读 workspace 文件；>2000 字符返回预览 | ❌ |
| `list_workspace` | `code_checks.py` | 列出 workspace 文件 | ❌ |
| `parse_python_error` | `parse.py` | traceback → 结构化 `{error_type,message,category,frames}` | ❌ |
| `review_code` | `quality.py` | 代码质量审查（**建议性**，不决定成败） | ❌ |
| `get_architecture` | `arch.py` | 工程结构总览 | ❌ |
| `get_module` | `arch.py` | 单模块符号表 + 反向依赖 | ❌ |
| `find_symbol` | `arch.py` | 按名反查符号定义位置与签名 | ❌ |
| `reflect_on_history` | `reflect.py` | 跨 cycle 失败模式分析（只读，仅供参考） | ❌ |
| `review_document` | `docs.py` | 文档机械审查（代码块语法 / 引用存在性；只读） | ❌ |
| `get_system_info` | `basic.py` | 操作系统 / Python 版本 / 当前时间 | ❌ |

### general profile（4 个）

通用 agent 的种子工具。**在 coding profile 下不下发**，但保留注册——
它们代表未来通用 agent 的能力，不应因当前只做编码而删除。

| 工具名 | 定义于 | 用途 |
|---|---|---|
| `get_weather` | `basic.py` | 查询天气（占位实现，恒返回晴天 22°C） |
| `calculate` | `basic.py` | 安全算术（AST 求值） |
| `fetch_url` | `net.py` | 取网页文本前 3000 字符（内网拦截见 §19 #5） |
| `get_system_info` | `basic.py` | 同 coding profile（双 profile 声明） |

**注**：`WORKER_SYSTEM` 要求"必须通过工具调用完成任务"，
但项目**没有** `finish`/`submit` 类工具——任务完成由子循环检测到
"无 tool_calls 的纯文本"来判定（`backend/core/worker.py` 情况 3）。

## 18. `backend/storage/session.py`

**职责**：会话落盘。

**依赖**：`json`、`os`、`re`、`dataclasses.asdict`、`datetime`、`core.task`。

```python
STORAGE_DIR = "sessions"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

def _safe_id(session_id: str) -> str
    # 不匹配 _SAFE_ID 时退化为 sha256(session_id)[:16]

class RunStore:
    def __init__(self, session_id: str)
    def load(self) -> dict
    def append_run(self, goal: str, ok: bool, answer: str, records: list) -> None
    def _atomic_save(self, data: dict) -> None       # 写 .tmp 后 os.replace
    @staticmethod
    def _record_to_dict(record) -> dict
```

存储文件：`data/sessions/{safe_session_id}.json`，结构 `{"runs": [...], "created_at": ...}`，
每条 run 含 `goal`、`ok`、`answer`、`records[]`、`finished_at`。

`STORAGE_DIR = "sessions"` 是**相对路径**，依赖进程 CWD 为仓库根目录。

---

## 19. 当前不一致 / 未接线清单

**本清单只列「当前仍存在」的问题。** 已修复项不在此处——修复过程见
`docs/CHANGELOG.md`。这条分工刻意如此：上游文档只描述现状，
否则读者无法判断某条限制是"还没修"还是"修了但文档没更新"。

按影响排序。

### #1 `WORKSPACE_DIR` 在 6 处独立计算，无单一来源

以下模块各自算一份 workspace 绝对路径，取值都是 `os.path.abspath("workspace")`：

`backend/core/pipeline.py`、`backend/core/symbol_index.py`、`backend/core/checkpoint.py`、
`backend/tools/python_exec.py`、`backend/tools/verify.py`、`backend/tools/files.py`。

而 `backend/core/worker.py` 用的是**相对路径** `"workspace/_debug"`。

**影响**：当前一致（都依赖 CWD 为仓库根目录），但没有单一来源。
若进程从别处启动，`worker.py` 的调试目录会与其它模块不一致。
多数测试脚本已改为从 `tests/_bootstrap.py` 取 `WORKSPACE`，但生产代码还没统一。

### #2 `facts` 机制未接线

`SharedMemory.add_fact` 与 `count_fingerprint` **无任何调用方**。
因此 `facts` 恒为空列表，`summary_for_orchestrator` 里的「关键事实」段永不输出。

注意它与 `backend/core/compress.py` 的 `facts` **不是一回事**：
后者是压缩产物（带 confidence 分级），前者是运行期内存字段。

### #3 `manifest.to_prompt()` 未被工作流使用

`Manifest.to_prompt()` 有实现，但只有测试调用它。工作流侧走的是
`CodingCycle._manifest_error_text()`（自建格式）。

**影响**：两处格式化逻辑并存，改一处不会同步另一处。

### #4 预留但未接线的字段（有意保留）

| 字段 | 说明 |
|---|---|
| `ModelCoupling.error_prefixes` / `matches_error_prefix()` | 工作流只依赖结构化协议；保留是为了将来某模型确需文本兜底时有地方放补偿 |
| `CheckPipeline.verify_timeout` | 实际超时来自 `backend/tools/verify.py` / `python_exec.py` 的 `TIMEOUT_SECONDS`（60s）；保留以便将来统一收归预算 |

两者都已在代码注释里注明是预留，不会给人"改了有效"的错觉。

### #5 `get_weather` 是占位实现

`backend/tools/basic.py` 恒返回 `f"{city} 当前晴朗，温度 22°C"`，不产生任何网络请求。

**当前处置**：它属于「通用种子工具」（`get_weather` / `calculate` / `fetch_url` /
`get_system_info`），**不删除**；在 coding profile 下不下发（见 §17）。

### #6 回退会清除未跟踪文件

`GitBackend.rollback()` = `git reset --hard` + `git clean -fd`，
会删掉 workspace 里**所有未跟踪文件**，包括手动放进去的。

**当前行为**：执行前先 dry-run 列出将被删除的文件并打印警告；
`clean -fd` 不加 `-x`，所以 `.gitignore` 覆盖的 `_tmp/` `_debug/` **不会**被删。

**仍需注意**：未被忽略、又未被跟踪的文件（你手动放的笔记/脚本）会被清掉。
往 workspace 放文件前请确认它已被忽略。

---

## 20. `bridge/` 与 `bridge/progress.py`

前端（`frontend/`）要跟踪进度，先得有「可订阅的进度」。这一层就是它。

### 20.1 `bridge/progress.py` — 进度事件总线

```python
ProgressSink = Callable[[str, dict], None]
_sink: ContextVar[ProgressSink | None]      # 默认 None

class RunCancelled(BaseException): ...       # 刻意继承 BaseException

bind_progress(sink) -> Token
reset_progress(token) -> None
current_sink() -> ProgressSink | None
emit_progress(kind: str, **payload) -> None
```

| 约定 | 说明 |
|---|---|
| **无接收器时是纯 no-op** | 与 storage 事件同样的旁路纪律：进度坏掉不影响 cycle 成败 |
| 用 ContextVar 而非全局单例 | 同一进程可能并发跑多个 cycle，全局单例会串台 |
| 订阅者的 `Exception` 被吞掉 | 坏掉的订阅者不该拖垮流程 |
| `RunCancelled` **放行** | 它继承 `BaseException`，能穿过工作流层到处都有的 `except Exception` |

`RunCancelled` 的继承关系不是随手写的：这是**唯一**能干净中断一次模型调用的位置，
做成 `Exception` 就会被兜底吞掉，取消永远不生效。

### 20.2 事件从哪来：运行时挂钩，不改上游

**上游 `backend/` 里没有任何埋点。** 事件由 `bridge/hooks.py` 在启动时包装
上游的「汇聚点」产出——挑点的原则是「上游本来就把所有同类事件从这一个地方发出去」：

| 上游挂钩点 | 一次覆盖 |
|---|---|
| `CodingCycle._emit` | plan / task_result / manifest / syntax / lint / verify / cycle_end / decision_* 等 11 个 |
| `CycleReport.enter` | phase（+ 派生 attempt_start / retry） |
| `CodingCycle.run` | run_start + 周期上下文 |
| `CodingCycle._new_file_artifacts` | files |
| `CheckpointManager.commit / rollback` | baseline / rollback |
| `Orchestrator._decide` | round_start / orchestrator_decision |
| `Worker.run` | task_start / task_done |
| `LLMClient.chat` | worker_step / model_reply |
| `Worker._invoke` | tool_call / tool_result |
| `CheckPipeline.run_verify` | verify_probe |

两条纪律：每个包装都走 `_safe()` 兜异常（**进度是旁路，坏掉不能拖垮 cycle**）；
检测到上游自带埋点（`_enter`）就跳过 cycle 级挂钩，避免重复播报。

`CodingCycle.run(goal, verify_command=None)` 是**上游原样的签名**。
前端按 `run_id` 订阅；事件里同时带着上游生成的 `cycle_id`，两者不同名，按需关联。

### 20.3 `bridge/runner.py` — 运行管理器

```python
RUNS_ROOT = paths.RUNS_DIR      # = <运行根>/storage_data/runs
TERMINAL_STATUSES = {"passed", "failed", "relaxed", "cancelled", "error"}

class EventLog:                    # 一个运行一个 JSONL，seq 单调递增
    append(kind, **payload) -> dict
    read_all(after_seq=0) -> list[dict]
    tail(offset) -> tuple[list[dict], int]     # 字节偏移增量读

@dataclass
class RunInfo:                     # meta.json 的模型
    run_id, goal, status, created_at, started_at, finished_at,
    options, phase, attempts, touched_files, commit, rolled_back,
    error, answer, report, summary, event_count, demo
    .terminal -> bool

class RunManager:
    start(goal, verify_command=None, max_attempts=2, on_decision="auto",
          max_consecutive_failures=2, session_id="default",
          approval_base_url="", demo=False) -> RunInfo
    get(run_id) -> RunInfo | None
    require(run_id) -> RunInfo                      # 不存在抛 RunNotFound
    list_runs(limit=50) -> list[RunInfo]
    events(run_id, after_seq=0, limit=2000) -> list[dict]
    tail(run_id, offset) -> tuple[list[dict], int]
    cancel(run_id) -> tuple[bool, str]
    pending_decisions(run_id=None) -> list[dict]
    answer_decision(decision_id, value, by="frontend") -> tuple[bool, str]

run_manager() -> RunManager        # 进程内单例
```

磁盘布局：

```
storage_data/runs/<run_id>/meta.json      运行状态与最终报告
storage_data/runs/<run_id>/events.jsonl   追加型事件流（前端订阅的就是它）
```

| 设计决策 | 理由 |
|---|---|
| 跑在独立线程 + 独立事件循环 | `on_decision=wait` 内部 `time.sleep` 阻塞，放进 FastAPI 循环会把服务卡死 |
| 事件落文件而不是内存队列 | 刷新 / 重连 / 换设备都要能补齐历史 |
| 取消是协作式的 | 模型调用无法从外部打断；最坏延迟 ≈ 一次模型调用 |
| 进程重启后未完成的运行标为 `cancelled` | 谎报「还在跑」比报错更糟 |

**注意**：`list_runs` 不能叫 `list` —— 类体内 `def events(...) -> list[dict]`
会在定义时求值，方法名 `list` 会覆盖内置 `list` 并直接 `TypeError`。

### 20.4 `bridge/agent_api.py` — HTTP 接口

`APIRouter(prefix="/api")`，在 `backend/main.py` 里注册。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/runs` | 起一次运行，立刻返回 `run_id` |
| GET | `/api/runs` | 历史运行列表 |
| GET | `/api/runs/{id}` | 单次运行的 meta |
| DELETE | `/api/runs/{id}` | 请求取消 |
| GET | `/api/runs/{id}/events` | 轮询 / 回放 |
| GET | `/api/runs/{id}/stream` | **SSE**，`after=<seq>` 续订 |
| GET | `/api/workspace/file` | 读产物内容（路径做穿越防护） |
| GET | `/api/workspace/tree` | 产物清单 |
| GET/POST | `/api/decisions[...]` | 决策点的 JSON 形式 |
| GET | `/api/health`、`/api/profile`、`/api/insights`、`/api/reflect` | 只读状态与分析 |

用 SSE 而非 WebSocket：数据是**单向**的，SSE 原生支持重连与 `Last-Event-ID`，
不需要多维护一套握手与心跳。

### 20.5 其余 web 模块

| 文件 | 职责 |
|---|---|
| `bridge/factory.py` | `resolve_profiles()` / `build_orchestrator()` / `profile_snapshot()`。**不抛 HTTPException**——装配层不认识 Web 框架 |
| `bridge/actions.py` | `build_cycle(...)`：请求参数 → `CodingCycle`，与 `POST /encode` 同构 |
| `bridge/demo.py` | `run_demo_cycle(sink, run_id, goal)`：不发模型请求，按脚本播报**同一套事件词汇** |
| `backend/web/decisions.py` | 手机端审批页（服务端渲染，无外部依赖） |

`bridge/demo.py` 刻意复用真实事件词汇，所以它验证的是真链路，而不是一条只在演示里
成立的旁路——没模型时也能确认前端是好的。

### 20.6 `frontend/` — Vue 前端

Vue 3 + Vite + TypeScript，无 UI 框架、零运行时外部依赖。构建产物挂到 `/app`；
**产物不存在时不注册该路由**，后端照常可用。

| 文件 | 职责 |
|---|---|
| `frontend/src/store/run.ts` | **事件 → 界面状态**的唯一归约器（实时流与历史回放共用） |
| `frontend/src/api/sse.ts` | 基于 fetch 流的 SSE 解析与自动续订 |
| `frontend/src/components/PipelineFlow.vue` | 六阶段流水线动画 |
| `frontend/src/components/ActivityFeed.vue` | 实时事件流 |
| 其余组件 | 尝试轨迹 / 任务 / 门禁 / 产物 / 历史 / 决策条 |

细节见 `frontend/README.md`。

---

## 21. `bridge/spec.py` — 标定方案

**后端把「自己长什么样」声明出来，前端照单渲染。** 前端不含任何后端事实。
完整说明见 `bridge/SPEC.md`。

### 21.1 三层：事实 / 标定 / 渲染

| 层 | 内容 | 谁定 |
|---|---|---|
| **事实** | 有哪些阶段、事件、工具、端点 | **从代码扫**（不手写，所以不会漂） |
| **标定** | 中文名、色调、面板、可调参数 | `CALIBRATION` + `spec.override.json` |
| **渲染** | 怎么画 | `frontend/src/**` |

### 21.2 接口

```python
SPEC_VERSION = "1.0"
OVERRIDE_FILE = <仓库根>/spec.override.json

def event_kinds() -> dict[str, list[str]]   # AST 扫三处事件源
def pipeline_stages(cal) -> list[dict]      # 从上游 PHASE_ORDER 派生
def tool_catalog() -> list[dict]            # 从上游 TOOLS_MAP 派生
def load_calibration() -> tuple[dict, list[str]]   # 默认 + 覆盖文件
def build_spec() -> dict                    # 组装，给 GET /api/spec
```

`build_spec()` 的返回（前端只发这一个请求）：

```
spec_version, generated_at, runtime,
endpoints,                 # 13 个，前端不写死路径
pipeline.stages[]          # id / label / hint / icon / kind
statuses{}                 # label / tone / terminal
events{}                   # label / tone / panel / title? / detail? / sources / calibrated
tools[]                    # name / label / description / profiles
ui{}                       # poll / stream / limits / features / examples
diagnostics{}              # uncalibrated_events / dead_calibrations / errors
```

### 21.3 事实的来源（改了就红）

| 事实 | 来源 | 把守 |
|---|---|---|
| 阶段 | 上游 `core.cycle.PHASE_ORDER` | `test_spec.py` |
| 事件 | AST 扫 `_emit` / `hooks.emit_progress` / `runner.append` | `test_spec.py`、`test_event_contract.py` |
| 工具 | 上游 `tools.registry.TOOLS_MAP` | `test_spec.py` |
| 端点 | 本模块的 `ENDPOINTS` | `test_spec.py`（与真实路由**双向**核对） |

### 21.4 未标定 / 死标定

- **未标定的事件**：自动生成可读 label（`task_result` → `Task Result`），
  并出现在 `diagnostics.uncalibrated_events`。**降级可见，不是静默丢失。**
- **死标定**（标了但代码不发）：出现在 `diagnostics.dead_calibrations`，多半是上游删了事件。
- **未标中文名的工具**是允许的（种子/通用工具不出现在编码界面），前端回退成原名。

---

## 22. `bridge/triage.py` — 失败归因

**从事件流里读出「为什么失败」，而不是等人写报告。** 纯函数：不读文件、不联网、
不调模型，可离线测。完整说明见 `docs/DIAGNOSTICS.md`。

```python
CATEGORIES: dict[str, tuple[str, str]]   # 类别 → (中文名, 应对)

@dataclass
class Finding:          # 一条归因结论，**必须带 evidence**
    category, summary, evidence[], detail
    .label  -> str      # 中文类别名
    .action -> str      # 应对建议

@dataclass
class Triage:
    run_id, goal, status, attempts, rolled_back, failed_at
    findings: list[Finding]
    timeline: list[str]
    .primary -> Finding | None
    .to_dict() / .to_markdown()

def key_timeline(events, limit=40) -> list[str]      # 只留关键事件
def triage(run_id, events, *, max_attempts=0) -> Triage
```

### 22.1 类别口径（必须与项目一致）

| category | 含义 | 应对 |
|---|---|---|
| `model_capability` | 规格已写清，模型没做到 | 换模型；不在工作流里打补丁 |
| `architecture_gap` | 系统缺少某个**显式模型** | 补机制 |
| `budget` | 轮次 / 步数 / 重试耗尽 | 调 `ModelLimits` |
| `environment` | 依赖 / 路径 / 服务 | 与模型和工作流无关 |
| `verify_spec` | 验收命令自身有毛病 | 检查调用方给的 `verify` |
| `planning` | 主循环拆不出可执行任务 | 提示词或目标描述 |
| `cancelled` | 人工取消 | 不是失败 |
| `unknown` | 证据不足 | 看原始事件流 |

### 22.2 关键边界（踩过）

`manifest` **已执行但内容不合格**（文件没写、缺符号、语法错）→ `model_capability`。
因为 manifest 本身就是为补那个架构缺口做的。

只有 `manifest.checked == False`（压根没有交付声明）才是 `architecture_gap`。

> 早先这里把 `declared-broken` 归成架构缺口，会把人引向"去补机制"，
> 而真正的问题是模型写坏了代码。**是在一次真实失败运行上被 doctor 发现的。**

### 22.3 设计约束

- **每条结论必须带 `evidence`**：没证据的判断等于猜，猜错会把人引向错误的修法。
- **证据不足时明说**（`unknown`），不硬编一个结论。
- 已有具体证据时**不再叠**一条"未归类"——那是噪音。

---

## 23. `bridge/audit.py` — 责任自审查

**判「该改前端还是后端接口定义」**——服务是黑盒时的唯一可行判据。
**词汇表与归属规则以 `.interface_contract/` 为准**（见 §24），本模块只是它的执行者。
完整说明见 `docs/DIAGNOSTICS.md` §7。

```python
@dataclass
class Issue:
    id, owner, severity, title, detail, evidence[], fix, crosswalk_id
    .owner_label -> str          # 中文名，取自契约 OWNERS
    .blocking    -> bool         # severity != "info"

@dataclass
class Audit:
    spec_version, contract_version, contract_version_source,
    issues[], checked[], client_reported, client_legacy_shape
    warnings[], ops_reported{}    # 契约 response_contract（见 §23.4）
    .verdict      -> 契约 6 值之一：ok / ops-action / backend-action /
                     frontend-action / need-negotiation / multi-action
    .verdict_text -> 一句话（列出**全部**该动手的人）
    .by_owner() / .to_dict() / .to_markdown()

OPS_STALE_BY_TRANSPORT = frozenset({"O-service-down"})   # 不驱动 verdict 的 ops code
OPS_FACT_CODES = {"service_down": "O-service-down",
                  "frontend_not_built": "O-frontend-not-built"}

def backend_checks(spec, *, contract_report=None, hooks_report=None, routes=None)
def compat_checks(spec, client)      # client 用契约 canonical 字段名
def run(spec, client=None, *, ..., client_legacy_shape=False) -> Audit
```

### 23.1 判定分界线

**核心是「声明」，不是「实现」。** 服务是黑盒，前端只能依赖它声明了什么。

★ **架构清单 A1a：跨侧归属只有一个判据 —— 契约。** 本模块不再自行下结论：

| 判定类型 | id 长什么样 | 判据 |
|---|---|---|
| **跨侧**（契约定义过） | 契约的 rule code，如 `P-event-unknown-to-frontend` | **读契约 JSON** 的 `rule_crosswalk.upstream_only`（`contract_vocab.upstream_rule`）；`audit.UPSTREAM_RULES` 只是离线回退 |
| **历史遗留**（契约按 `bridge_id` 索引的 11 条） | 仍是 `backend.*` | `contract_vocab.owner_of()` → **优先读契约 JSON**，读不到才回退镜像表 |
| **本适配层自己**（契约没有） | `bridge.` 前缀 | 本模块自己决定 |
| 运行态 | `O-service-down` / `O-frontend-not-built` | 契约 `bridge_only_reclassified` 采纳的 code |

每条判定还带 `code` 字段（= 契约的 `upstream_equivalent`），空字符串表示
**契约明确写了「无」**，不是"忘了填"。

**声明的偏离**：`audit.DEVIATIONS` 列出"契约说一套、本模块按更好的判据判另一套"的地方，
每条必须写清理由。**当前为空** —— 唯一那条（`P-phase-unknown` 判 `both`）
已被契约 v1.0.7 采纳（由 `backend/breaking` 改判 `both/degraded`），偏离随之撤销。
测试断言该集合**恰好**是表里的那些，所以它既长不大、也不会悄悄留一条已生效的。
归属按契约 `boundary_definition`：**边界 = 仓库的边界**，
所以 `bridge/` 里的问题算 **`frontend`**。

| 现象 | 归属 | 严重度 |
|---|---|---|
| 服务声明了 X，前端不认识 | `frontend` | `degraded` |
| 服务声明了 X，实际不做（事实源在上游） | `backend` | `breaking` |
| 端点声明与注册不一致（声明在 bridge） | `frontend` | `breaking` |
| 上游端点被删（bridge 声称重暴露的没了） | `backend` | `breaking` |
| 前端认得服务不声明的事件（孤儿） | `both` | `degraded` |
| 前端画的阶段双方都没有 | `both` | `degraded` |
| 前端漏画上游阶段 | `frontend` | `degraded` |
| 契约版本没上报 / 对不上 | `frontend` | `degraded` |
| 服务多了端点（additive，前端还没用） | `frontend` | **`info`** |
| 服务不可达 / 前端没构建 | `ops` | `breaking` |

★ **`info` 不参与 `verdict`**（契约 `severity_vocabulary` 明规）。
否则"上游加了个端点"会被报成"有事要改"，低定制就退化成每次加东西都要两边同步。

### 23.2 三条设计约束

- **归属必须列全**：一次审查可能牵涉多方（`multi-action`）。
  只报一个会把另一半藏起来——而人往往只看结论。
- **`ops` 优先判定**（契约 `verdict_vocabulary.priority`）：环境没弄好，
  后面判什么都没意义。所以 `verdict_for()` 先看 `ops`，再看 `both`。
- **id 不许改名**：11 条 `backend.*` 判定按边界改判后**仍保留原 id**
  （契约对账表按 `bridge_id` 索引），真实归属查 `contract_vocab.owner_of()`，
  每条判定另带 `crosswalk_id` 指回原 id。
- **平铺上报不猜来源**：收到旧格式（`events`/`stages`/`endpoints`）时
  **不做兼容性比对**，只报一条 `info` —— 猜来源就是复现缺口 G2。

### 23.3 前端期望从哪来

**构建期从源码扫**（`frontend/scripts/gen-expectations.mjs`），不是手写——
手写的一定会漂，那时审查会给出错误的责任判定，比不审查更糟。

| 期望 | 扫哪里 |
|---|---|
| `events` | `store/run.ts` 的 `case '...'` |
| `endpoints` | `api/*.ts` 的 `need('...')` / `endpoint('...')` |
| `stages` | `api/spec.ts` 的 `DEFAULT_SPEC` |
| `proxied_upstream` | `vite.config.ts` 的 proxy 表 |

上报体用契约 `client_report_schema.canonical_fields` 的字段名，
**事件与阶段必须按来源分开**（缺口 G2/G3）：分区**判据来自服务**
（`/api/spec` 的 `event_partition` / `pipeline.upstream_phases`），
**成员来自生成物** —— 两边取交。

### 23.4 `warnings`：不参与 verdict，但**必须与它一起展示**

契约 v1.0.5 `response_contract` 定的分流规则。当前唯一的来源是
**被传输层证伪的 ops 事实**——请求已成功送达，却报了 `service_down`。

| 情形 | 落点 | 驱动 verdict？ |
|---|---|---|
| 客户端报 `service_down`（送达了） | **`warnings` + `ops` 栏** | ❌ 被传输层证伪 |
| 客户端报 `frontend_not_built`，但本地有产物 | **`warnings` + `ops` 栏** | ❌ 与本地观测矛盾 |
| 服务侧观测到未构建 | `ops-action` | ✅（契约实测举证） |
| 未知事实名 | 忽略 | —（additive 安全） |
| 报 `false` | 不构成事实 | — |

★ **消费方义务**（契约原文）：

> 展示 verdict 的消费方**应当同时展示 warnings**。

理由：这类事实不参与 verdict，所以**只看 verdict 会看到 `ok`，
从而看不到那条陈旧标志**。本仓库的履约点在
`frontend/src/components/TopBar.vue` —— 提示段渲染在阻塞项之前，
**徽标本身也带条数**（`✓ 兼容 (1 提示)`），否则不点开就等于没展示。

★ **判断环境问题不要只看 `verdict`**：自 v1.0.5 起，
`verdict == "ops-action"` **不再**等价于"报了 `service_down`"；
要看 `ops` 栏或 `warnings`。只有 `frontend_not_built` 仍判 `ops-action`。

### 23.5 验证

```powershell
$PY tests/unit/test_audit.py        # 107 项
$PY tests/unit/test_contract_vocab.py            # 78 项（含消费方义务的跨语言核对）
$PY tests/diagnostics/check_contract_report.py   # 29 项，端到端
```

---

## 24. `bridge/contract_vocab.py` + `bridge/partition.py` — 契约的镜像与推导

这两个模块让「谁该改」**不只是本仓库自己定的规矩**，
而是 `.interface_contract/` 那份契约的可执行副本。

### 24.1 `contract_vocab.py` — 契约词汇表的镜像

| 本模块 | 契约字段 |
|---|---|
| `OWNERS`（4 值） | `owner_vocabulary.values` |
| `SEVERITIES`（3 档） | `severity_vocabulary.values` |
| `VERDICTS`（6 值） | `verdict_vocabulary.values` |
| `REATTRIBUTED`（11 条） | `rule_crosswalk.bridge_backend_prefixed_reclassified` |
| `CONTRACT_FALLBACK_VERSION` | `version_axes.CONTRACT_VERSION.observed_value` |

```python
Owner    = Literal["backend", "frontend", "ops", "both"]
Severity = Literal["breaking", "degraded", "info"]
SEVERITY_LEGACY = {"fail": "breaking", "warn": "degraded"}
NON_BLOCKING_SEVERITIES = frozenset({"info"})   # 唯一不参与 verdict 的档

owner_of(bridge_id) -> str        # 查改判表；SPLIT 条目落默认值
severity_of(bridge_id) -> str
is_split(value) -> bool           # 前缀判断，容 `SPLIT(见 note)`
verdict_for(owners: set[str]) -> str   # ★ ops 优先，其次 both
```

**两条纪律**

- **它是镜像，不是契约。** `.interface_contract/` 是只读资产；
  要改词表就得统筹方改主本再同步。`tests/unit/test_contract_vocab.py`
  直接读契约 JSON 逐项比对，漂了就红。
- **`_source` 必须一起给。** `CONTRACT_VERSION` 由 **backend 拥有**，
  bridge 只有在读不到上游时才回退 —— 不标来源等于 bridge 冒充 backend 说话。

### 24.2 `partition.py` — 三条分区，全部**推导**

分区是「哪些东西属上游」的判据。硬编码一份名单一定会漂，而漂了以后
**归因会指错人**（契约记的三处缺口 G1/G2/G3 就是这么来的）。
所以全部从事实源推导，并用契约记录的观测值**校验**。

| 分区 | 事实源 | 产物 |
|---|---|---|
| 事件 | 各事件由谁发出（`spec.event_kinds()` 的 `upstream` 标记） | 12 上游 + 21 bridge = 33，不相交 |
| 阶段 | `stage.kind`（`phase` vs `gate`） | `upstream_phases`(5) / `bridge_gate_steps`([`manifest`]) |
| 端点 | bridge 转发的 3 条 ∪ `vite.config.ts` proxy 表的 7 条 | `upstream`(7) / `frontend`(14) |

```python
event_partition() -> {upstream[], frontend[], total, overlap[]}
phases_partition(stages) -> {upstream[], bridge_gate_steps[], other[], drawn[]}
endpoint_partition(endpoints) -> {upstream[], frontend[], mapped{}, proxied_upstream[]}
proxied_upstream() -> list[str]          # 读 vite.config.ts 的 proxy 表
upstream_routes() -> list[str]           # 上游真实路由（app.routes）
contract_version() -> (值, "upstream" | "fallback")
schema_version()   -> (值, "upstream" | "absent")
check_against_contract() -> {ok, issues[], ...}   # 拿契约快照校验推导结果
```

**为什么端点要取并集**：只看 bridge 转发的会漏掉 `/skills` `/candidates`
`/encode` `/run` —— 它们由 dev server **直接**代理给上游，不走 bridge。
漏报是**静默**的：上游删了它们时没有任何判定会指向上游。

### 24.3 验证

```powershell
$PY tests/unit/test_contract_vocab.py    # 78 项（逐条比对契约 JSON）
$PY tests/unit/test_partition.py         # 55 项（含"分区错了自检必须红"的反证）
$PY tests/unit/test_spec.py              # 43 项（兜底 spec 跨语言一致）
$PY tests/unit/test_audit_authority.py   # 35 项（对账入口按职责切分，见 §25）
```

---

## 25. 上游来源与陈旧检测：`bridge/staleness.py`

**让"你正在用一个过期的 `backend/`" 无法被静默使用。**

### 25.1 为什么需要它（实测）

`VueWeb/backend/` 自带一份副本，为了"开箱可跑"。但它**落后于上游**：

```
bundled  core 模块 27 个
upstream core 模块 29 个
两边都有但内容不同：9 个
```

自带副本比上游**少了两个模块**：core 包下的 contract.py 与 vision.py。
（这两个文件在自带副本里**不存在**，所以本文不把它们写成可点的路径引用 ——
那正是 `test_doc_consistency` 会拦下的"引用不存在的路径"。）

缺 contract.py 的后果最隐蔽：**新契约机制整体静默不可用**
（契约版本常量 / 规则表 / 上游对账端点），
而**服务照常启动、界面照常显示、没有任何一处报错**。

### 25.2 接口

```python
MARKERS = (("core/contract.py", "契约机制", "缺了会怎样"), …)

probe(backend_dir=None, reference_dir=None) -> dict
    # backend_dir / is_bundled / markers[] / missing_markers[]
    # core_module_count / contract_version / contract_version_readable
    # missing_vs_reference[] / stale / reasons[] / summary

startup_warning(result=None) -> str | None    # 返回文本而不直接 print（便于断言）
read_contract_version(backend_dir) -> str     # 读源码，不 import（不污染 sys.modules）
core_modules(backend_dir) -> list[str]
reference_dir_from_env() -> str               # AGENT_UPSTREAM_DIR
```

**判据是 `paths.BACKEND_DIR`**，不是"import 到了 `core` 就算对" ——
仓库里有两个同名 `core` 包，import 成功只说明 `sys.path` 里有它
（见 `docs/LAYOUT.md` §7）。

### 25.3 四个出口

| 出口 | 形态 |
|---|---|
| 启动期（**门禁**） | `bridge/app.py` 在 **import 期**判：bundled → **拒绝启动**（退出码 2，端口不监听） |
| 启动期（逃生舱路径） | 用了 `--allow-bundled` 时打 A2 的**醒目警告**（说明后果） |
| 探针 | `GET /api/health` → `backend_dir` / `backend_is_bundled` / `backend_stale` / `backend_stale_reason` / `backend_core_modules` / `backend_contract_version` / **`backend_bundled_override`** / **`frontend_asset`** |
| 体检 | `scripts/doctor.py` 的「路径与隔离」节纳入结论 |

**A2b：bundled 即拒绝启动**（判**形态**，不判状态）：

```python
REFUSAL_EXIT_CODE = 2
ALLOW_BUNDLED_ENV = "AGENT_ALLOW_BUNDLED"     # 主入口（对任何启动方式都有效）
ALLOW_BUNDLED_FLAG = "--allow-bundled"        # 需经 python -m bridge 解析

allow_bundled_requested(argv=None) -> bool
should_refuse(result=None, *, allow=None) -> bool   # 只看 is_bundled
refusal_message(result=None) -> str                 # backend_dir + 后果 + 修复命令
frontend_asset(dist_dir=None) -> str                # dist/index.html 引用的那个 JS
provenance(result=None, *, override=None, asset=None) -> dict
provenance_lines(prov) -> list[str]                 # 启动日志用
```

**为什么闸门必须在 import 期**：uvicorn 先 import 应用再绑定端口 ——
只有在那里退出才能保证**端口不被监听**（验收标准要的就是这个，
而不是"起来了再关掉"）。代价是 `import bridge.app ≠ 启动服务`，
所以测试用 `AGENT_ALLOW_BUNDLED=1` 显式表明"只是导入"，
而真正的门禁由 `tests/unit/test_bundled_gate.py` 用**子进程**验证。

**严重度分两档**（A2 保留，这个区分是有意的）：

| 情形 | 级别 | 理由 |
|---|---|---|
| bundled 且落后 | `WARN` | 用自带副本是**正当选择**（开箱可跑是设计），修法只是一行环境变量。判 FAIL 会让默认配置**永远红着**，而"永远红着"的检查等于没有检查 |
| 外部却落后 | `FAIL` | 你明确指向了一份上游，它却缺必需模块 —— 那是配错了，不是选择 |

### 25.4 验证

```powershell
$PY tests/unit/test_staleness.py     # 34 项（含负向：指向坏上游必须报落后）
$PY tests/unit/test_bundled_gate.py  # 31 项（含**子进程负向测试**：拒绝真的发生）
python scripts/doctor.py             # 「路径与隔离」节含该结论
```
