# 模块与接口参考

> **同步至 CHANGELOG §34** —— 本文只描述**当前状态**；修复过程见 `CHANGELOG.md`。
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
- [20. core/decisions.py + core/notify.py](#20-coredecisionspy--corenotifypy远程人工决策) — 远程人工决策
- [21. core/compress.py](#21-corecompresspy结构化上下文压缩) — 结构化上下文压缩
- [22. core/vision.py](#22-corevisionpy多模态接口已预留未启用) — 多模态接口
- [23. core/contract.py](#23-corecontractpy上游前端兼容契约) — 上游→前端兼容契约
- [24. core/identity.py](#24-coreidentitypy代码身份) — 代码身份（跑的是哪一份上游）

---

## 1. `core/model_profile.py`

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
| `orchestrator_prompt_chars` | `6000` | 编排器 prompt 字符预算（由窗口推导） |

```python
ModelLimits.from_context_window(context_window: int, **overrides) -> ModelLimits
```

推导规则（`cw = max(2048, int(context_window))`）：

| 输出 | 公式 |
|---|---|
| `max_tokens` | `min(cw // 2, 4096)` |
| `rounds, steps, attempts` | `cw<=8192` → `15, 15, 2`；`cw<=32768` → `20, 20, 3`；否则 `30, 25, 3` |
| `tool_result_chars` | `max(800, min(cw // 6, 8000))` |
| `orchestrator_prompt_chars` | `max(2000, min(cw // 6, 24000))` |

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

## 2. `core/llm.py`

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

## 3. `core/config.py`

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

已登记角色：

| 角色 | 环境前缀 | 未配置时 |
|---|---|---|
| `orchestrator` | `ORCH` | 用内置默认档位（ollama + qwen2.5:7b） |
| `worker` | `WORKER` | **继承 orchestrator**（唯一的有意继承） |
| `reviewer` | `REVIEW` | 未启用（抛 `RoleNotConfigured`） |
| `package_optimizer` | `PKGOPT` | 未启用 |
| `vision` | `VISION` | 未启用（多模态，独立角色不继承） |

判定规则：

| 情形 | 行为 |
|---|---|
| 角色声明了 `inherits_from` | 继承（**只有 `worker` → `orchestrator`**） |
| 角色声明了 `has_builtin_default` | 用内置默认档位 |
| 都没有 | 抛 `RoleNotConfigured` |

关键区分：**「未配置」≠「未启用」**。`orchestrator` 有内置默认
（ollama + qwen2.5:7b），未配置但仍可用；`reviewer` 没有默认，
未配置就是未启用，**绝不静默继承编排器模型**（否则表现为"以为请了审查员，
实际还是同一个模型在审自己"，且不报错）。

`main.resolve_profiles()` 只解析 `orchestrator` / `worker` 两个必需角色。
`GET /profile` 的 `roles` 字段如实展示每个角色的 `available` / `source`，
未启用的显示 `available: false, model: null`。

**新增角色**时在 `ROLES` 里登记即可——`resolve_role` 对未登记的角色名会明确报错。

---

## 4. `core/cycle.py`

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

## 5. `core/coding_cycle.py`

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
| `_structured_context()` | 从事件流压缩出结构化事实块 → `(text, source)`；异常一律返回空 |
| `_emit_snapshot(cycle_id, goal)` | cycle 结束时压缩并落盘快照 |

`cycle_id` 格式：`cy_YYYYmmdd_HHMMSS_ffffff`。

**扩展点**：审查阶段若要插入，位置需在 `run` 内显式添加，
推荐 VERIFY 后 / RECORD 前（见 `CYCLE.md` §10.2）。

---

## 6. `core/orchestrator.py`

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
    verify_skipped: str = ""        # "没执行"的原因（空串=正常）；见 §24

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

**属性 `context_provider`**（默认 `None`）：由调用方注入的无参可调用对象，
返回 `str` 或 `(text, source)`。`_decide` 在**每轮决策前**调用它刷新
`SharedMemory` 的结构化上下文；provider 抛异常只打印一行日志并清空该段，
**不影响主循环**。`CodingCycle._setup_orchestrator` 会把它设为
`_structured_context`（见 §5、§21）。

内部方法：

| 方法 | 作用 |
|---|---|
| `_files_to_verify(memory, prior_files, declared_files)` | 声明 > 产物 > prior（语义修正见 §24/§33） |
| `_deliverables(memory, declared_files)` | ★ 本轮**可被判据引用**的交付物 = 声明 ∪ `write_file` 产物（**不含** prior） |
| `_verify_references(command, deliverables)` | ★ 命令引用了哪些交付物（路径/文件名/词干；词干匹配先剥字符串字面量） |
| `_model_verify_admissible(raw_verify, deliverables)` | ★ 自拟判据的**可采性下限**：须引用交付物，且本轮得有交付物 |
| `_verify_fingerprint(verify_command, files)` | `sha1(command + "\|" + sorted(files))[:16]` |
| `_verify_detail(vr)` | 从验证结果提取一句可读明细 |
| `_decide(memory)` | 刷新结构化上下文 → 构造 prompt → `chat_json` → 过滤幻觉工具名 |
| `_refresh_structured_context(memory)` | 调 `context_provider`；异常吞掉并清空（旁路） |
| `_parse_tasks(raw_tasks)` | 转 `Task` 列表 |
| `_should_skip(memory, task)` | 指纹去重；成功过或失败达上限则跳过 |

关键行为：
- `caller_verify = bool(self.verify_command)`——调用方的验收标准权威，
  仅在未提供时才采纳模型自拟的 `verify`；**自拟的那条还要过可采性下限**
  （`VERIFY-VACUOUS`，见 §24），不合格就**不采纳**（并记进
  `memory.verify_rejections`），而不是当没判据也判通过。
- 验证通过时**立即**返回，`answer` 形如 `"验证命令通过，目标达成（第 N 轮）"`。
- 达到轮次上限时，若 `memory.verified_passed()` 仍返回 `ok=True`。
- `set_verify(..., source=...)` 记录判据来源（`caller` / `model`），随
  `report.verify.source` 与 `verify` 事件暴露；**只作事实，不参与判定**。

---

## 7. `core/worker.py`

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
| `_dbg(path_suffix, content)` | 写 `workspace/_debug/` 调试快照 |

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

## 8. `core/pipeline.py`

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
{"passed": bool, "checked": bool, "status": "passed" | "failed" | "skipped",
 "skipped_reason": str | None,
 "steps": [{"tool", "file", "passed", "parsed", ["status"]}],
 "blocking_file": str | None}
```

`run_check` 行为：
- 无 `.py` 改动 → `passed=True` **且 `checked=False` / `status="skipped"`**
  且 `skipped_reason="本次 cycle 没有产生 .py 文件改动"`。
  ★ 三者必须同时看：`passed=True` 只说明"没拦你"，`status="skipped"`
  才说明**静态检查根本没跑**（`VERIFY-VACUOUS` 建议 4 —— 实测这条曾被读成绿灯）。
  该结论同时进 `CycleReport.check`。
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

## 9. `core/manifest.py`

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
                   strict_extra_files: bool = False,
                   base_dir: str | None = None) -> Manifest
def architecture_view(index: dict[str, ModuleEntry] | None = None) -> dict
```

violation 种类与严重度：

| severity | kind | 触发条件 |
|---|---|---|
| `error` | `declared-missing` | 声明的文件**既不在索引、也不在磁盘上** |
| `error` | `declared-broken` | 文件存在但 `syntax_ok` 为假 |
| `error` | `symbol-missing` | 缺声明的符号（模块级符号或类方法名均可） |
| `warning` | `dangling-import` | 本地模块间 import 不存在的模块 |
| `warning` | `imports-missing-declared-module` | 导入了「本次声明要产出但不存在」的模块 |
| `warning` | `unexpected-file` | 仅在 `strict_extra_files=True` 时产出（默认不产出） |
| `warning` | `not-indexed` | 声明的 `.py` 存在，但不在可扫描的模块索引里（在 `_`/`.` 开头目录） |
| `warning` | `symbols-unverifiable` | 声明的**非 `.py`** 交付物带了 `symbols`（符号无法校验） |

**判定顺序（`declared-missing` 的判据，实测修过）**：声明文件先查**符号索引**
（`.py` 走结构校验：语法、符号、悬空导入），**不在索引里就查磁盘**
（`_disk_fact()`：存在性 + size + sha1）。两处都没有才判 `declared-missing`。

> ⚠️ 加"查磁盘"这一步之前，**任何非 Python 交付物都必然被判 `declared-missing`** ——
> 因为索引只收 `.py`。症状是"只能跑样例需求"（阶梯样本全产 `.py`），
> 用户一要 txt 文档就 100% 失败。见 `docs/CHANGELOG.md` §29.1。

行为要点：
- `declared` 为空时 `checked=False`，**不做判定**（避免把"模型没声明"误判成失败）。
- 符号可用集合 = 模块级符号名 ∪ 类方法名（`sig.split("(")[0]`）。
- 查索引时先按归一化路径，再兜底尝试 `workspace/{path}`；
  查磁盘时用 `base_dir`（默认 `symbol_index.WORKSPACE_DIR`），拒绝 `..` 逃逸。
- 非 `.py` 交付物被记进 `actual`（带 `kind="file"` / `size` / `sha1`），
  所以"交付事实"里能看见它。
- 签名只作为信息，**不参与判定**。

`architecture_view` 返回 `{modules, totals, note}`，其中每个 module 含
`path`、`module`、`role_hint`（恒为空串，设计注记未实现）、`exports`
（`{name, kind, signature}`）、`depends_on`、`lines`、`sha1`。

---

## 10. `core/symbol_index.py`

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

## 11. `core/checkpoint.py`

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

## 12. `core/memory.py`

**职责**：全局状态。主循环唯一持有；Worker 只拿只读快照。

**依赖**：`.task`。

```python
@dataclass
class MemoryRecord:
    task: Task
    result: TaskResult

class SharedMemory:
    def __init__(self, goal: str)
    # 属性：goal, records, artifacts{}, facts[], verify_state, _verified_fingerprint,
    #       verify_untrusted, verify_rejections[], _fp_count,
    #       structured_context, structured_source

    def record(self, task, result) -> None
    def add_fact(self, fact: str) -> None            # (未被工作流调用)
    def count_fingerprint(self, task) -> int         # (未被工作流调用)

    def set_verify(self, passed: bool, detail: str, command: str,
                   fingerprint: str, source: str = "caller") -> None
    def reject_verify(self, raw_verify: dict, why: str) -> None   # ★ VERIFY-VACUOUS
    def already_verified_at(self, fingerprint: str) -> bool
    def verified_passed(self) -> bool

    def set_structured_context(self, text: str, source: str = "") -> None
    def summary_for_orchestrator(self, char_budget: int | None = None,
                                 max_records: int | None = None) -> str
    def prompt_chars(self) -> int                    # 诊断：渲染一次的实际字符数
    def context_for_worker(self, task: Task) -> str
```

`verify_state` 的键：`passed` / `detail` / `command` / `source`
（`source ∈ {caller, model}` —— 判据来源；技能里烘焙的命令算 `caller`，
因为它不是模型自拟的）。

`verify_untrusted` 与 `verify_rejections` 的分工（`VERIFY-VACUOUS`）：
前者是**当下**"为什么没在验证"（供 cycle 的错误文案直接引用，验证跑起来后清空），
后者是**只增不减的审计流水**（每条自带"不合格，已拒绝采纳"，
由 cycle 发成 `verify_skipped` 事件）。为什么不能只留最后一条：
实测那一轮里模型先给坏判据被拒、换一版好判据才通过 ——
成功时若把留痕清掉，事后就看不出"这次为什么多跑了两轮"。

`summary_for_orchestrator` 输出顺序（**按优先级填充，不是按条数截断**）：

```
【验证结论】            ← 优先级 0，永不省略；通过则要求 status=done
目标
【结构化上下文】        ← 有快照时；独立上限 max(200, min(budget//3, 1500))
失败任务（不要原样重试）  ← 末 5 条
关键事实                ← `facts` 末 8 条（该字段目前恒空，见下）
已有产物
已完成任务（倒序）       ← 预算内尽量多填，省略时写明省略条数
…（因 prompt 预算不足，省略了 N 条任务记录）   ← 兜底提示
```

**为什么验证结论在最前**：它决定主循环下一步（通过就 done、未通过就修）。
旧实现放最后且按条数截断，一旦超预算最该看到的信息反而先丢。
`schema_version` / 预算来源见 §21。

`set_structured_context` 由编排器在**每轮决策前**写入（内容来自
`core/compress.py` 的快照渲染）；存字符串而不是 `Snapshot` 对象，
所以本模块不依赖 `.compress`。空串表示"无可用快照"，渲染时整段不输出。

`context_for_worker` 解析 `task.context_refs`：优先按 artifact key 找
（`kind=="file"` 只给路径不展开内容），否则按 task_id 找，都没有则输出
`<missing ref='...'/>`。

> `facts` 机制目前未被接线：`add_fact` 无调用方，所以 `facts` 恒为空，
> `summary_for_orchestrator` 里的「关键事实」段是死代码。
> 注意它与 `compress` 的 facts **不是一回事**：后者是压缩产物（见 §21），
> 前者是运行期内存字段。属计划中的"结构化上下文压缩"能力的一部分。

---

## 13. `core/context.py`

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

## 14. `core/prompts.py`

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

## 15. `core/task.py`

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

## 16. `tools/registry.py`

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

**扩展点**：新增工具只需写 `@register(...)` 并在 `tools/__init__.py`
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

> `list_workspace`（`code_checks.py`）的跳过策略与 `core.symbol_index._SKIP_DIRS`
> **共用同一份常量**（`.git` / `.venv` / `node_modules` / `_tmp` / `_debug` /
> `__pycache__`），并额外跳过 `.` 开头的目录与文件。
> 返回体含 `total` / `listed` / `truncated` / `skipped_dir_names` ——
> **截断要明说，"看不见"≠"不存在"**。
> 实测事故：它原来只过滤 `_` 开头的目录，把 `.git/` 里 **249 个文件**倒给了模型，
> 模型照单全收写进了交付物（`docs/CHANGELOG.md` §29.3）。

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
"无 tool_calls 的纯文本"来判定（`core/worker.py` 情况 3）。

## 18. `storage/session.py`

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

存储文件：`sessions/{safe_session_id}.json`，结构 `{"runs": [...], "created_at": ...}`，
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

`core/pipeline.py`、`core/symbol_index.py`、`core/checkpoint.py`、
`tools/python_exec.py`、`tools/verify.py`、`tools/files.py`。

而 `core/worker.py` 用的是**相对路径** `"workspace/_debug"`。

**影响**：当前一致（都依赖 CWD 为仓库根目录），但没有单一来源。
若进程从别处启动，`worker.py` 的调试目录会与其它模块不一致。
多数测试脚本已改为从 `tests/_bootstrap.py` 取 `WORKSPACE`，但生产代码还没统一。

### #2 `facts` 机制未接线

`SharedMemory.add_fact` 与 `count_fingerprint` **无任何调用方**。
因此 `facts` 恒为空列表，`summary_for_orchestrator` 里的「关键事实」段永不输出。

注意它与 `core/compress.py` 的 `facts` **不是一回事**：
后者是压缩产物（带 confidence 分级），前者是运行期内存字段。

### #3 `manifest.to_prompt()` 未被工作流使用

`Manifest.to_prompt()` 有实现，但只有测试调用它。工作流侧走的是
`CodingCycle._manifest_error_text()`（自建格式）。

**影响**：两处格式化逻辑并存，改一处不会同步另一处。

### #4 预留但未接线的字段（有意保留）

| 字段 | 说明 |
|---|---|
| `ModelCoupling.error_prefixes` / `matches_error_prefix()` | 工作流只依赖结构化协议；保留是为了将来某模型确需文本兜底时有地方放补偿 |
| `CheckPipeline.verify_timeout` | 实际超时来自 `tools/verify.py` / `python_exec.py` 的 `TIMEOUT_SECONDS`（60s）；保留以便将来统一收归预算 |

两者都已在代码注释里注明是预留，不会给人"改了有效"的错觉。

### #5 `get_weather` 是占位实现

`tools/basic.py` 恒返回 `f"{city} 当前晴朗，温度 22°C"`，不产生任何网络请求。

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

## 20. core/decisions.py + core/notify.py（远程人工决策）

**职责**：关键节点挂起 → 推送到手机 → 人工作答 → 流程继续。
**只读历史/写决策队列，不参与执行**（不能改变 cycle 的成败判定）。

### 20.1 两个决策类型

只在**程序无法自行判定**的地方停；确定性事实（清单缺失、语法错误）不打扰人。

| 类型 | 触发 | 超时默认动作 | 为什么是这个默认 |
|---|---|---|---|
| `repeated_failure` | 验证连续失败达阈值 | `stop` | 停止而不是空转烧预算 |
| `risky_rollback` | 回退会覆盖已有文件之前 | `abort` | 不覆盖已有文件 |

**超时 fail-safe**：没人作答时**不能默认放行**。`abort` / `stop` 都是保守动作。

### 20.2 三个 on_decision 模式

| 模式 | 行为 |
|---|---|
| `auto` | 命中决策点直接用保守默认动作，不推送不等待（默认，等价旧行为） |
| `notify` | 落盘并推送，但不等待 |
| `wait` | 落盘并推送，**阻塞等待**人工作答 |

### 20.3 投递通道（
otify.py）

**任何 IM 都只需「发一条带链接的消息」** —— 交互式审批在网页里，
所以不受各平台 bot 能力差异影响。

| 通道 | 说明 |
|---|---|
| `console` | 默认。打到 stdout，不发网络请求（永远可用） |
| `dingtalk` | 钉钉群自定义机器人 webhook（个人可用、免费） |
| `webhook` | 通用（企业微信 / Slack / 自建中转） |

**未配置时退化为 console，绝不阻塞流程**；推送失败时**不等待**
（推不出去就没人会作答，等待只会让流程挂死）。

### 20.4 审批页

`web/decisions.py` 提供手机端页面（`GET /decisions`）。
渲染结构化上下文（目标 / 失败原因 / 清单问题 / 涉及文件），
这是聊天消息做不到的。设 `AGENT_APPROVAL_TOKEN` 后要求 `?t=<token>`。

### 20.5 跨进程作答

`_wait_for_answer` 用**文件轮询**而非内存 Future，
使「CLI 跑 cycle + Web 服务接收作答」两个进程能协作成立。

---

## 21. `core/compress.py`（结构化上下文压缩）

**职责**：把只增不改的事件流（JSONL）**派生**成带可信度标注的结构化视图。
**纯函数**：同样输入必得同样输出，随时可重算，不经过模型。

**依赖**：`storage.store.Event`。

```python
SCHEMA_VERSION = "1.0"

@dataclass
class Fact:        text, source, confidence, cycle_id, seq
@dataclass
class FileFact:    path, role, symbols[], status(declared|exists|missing), sha1, source
@dataclass
class FailureFact: what, reason, reason_hash, count, cycle_id, source, avoid
@dataclass
class Snapshot:
    cycle_id, goal, schema_version, status, facts[], files[], failures[],
    attempts, verify_command, commit
    def verified_facts(self) -> list[Fact]
    def to_dict(self) -> dict
    def to_prompt(self, max_facts: int = 12) -> str

def reduce_cycle(events, cycle_id) -> Snapshot        # 纯函数
def reduce_all(events, limit_cycles=20) -> dict[str, Snapshot]
def cross_cycle_failures(snapshots, min_count=2) -> list[dict]
```

**核心纪律**：压缩的输入只能是被程序校验过的工具结果，**不能是模型的自由摘要**。
第一轮试过"让模型做前后文压缩"，幻觉率太高——等于新增一个幻觉源并把错误固化。

**可信度只有三档**，由 `_SOURCE_CONFIDENCE` 决定，未登记来源一律降级为 `assumed`：

| confidence | 来源 | 能当判据吗 |
|---|---|---|
| `verified` | `verify` / `manifest` / `syntax` / `lint` | 能（程序实测） |
| `declared` | `plan`（含任务的 `expected_output`） | 不能（是意图，不是现实） |
| `assumed` | `task_output`（模型自述）、未登记来源 | 不能 |

`to_prompt()` 把三档**分段呈现**（已实测确认 / 计划声明 / 模型自述），
让模型一眼看出哪些能信；`assumed` 段明确写"未经校验，不可作为判据"。

**消费方**：`CodingCycle._structured_context()` 每轮决策前调用
`reduce_cycle` + `cross_cycle_failures`，渲染后经
`Orchestrator.context_provider` 注入 `SharedMemory`（见 §12、§5）。

**派生视图的意义**：原始事件永不改写，快照可从事件重算 ——
"丢信息"因此是可回滚的，而不是不可逆的。

---

## 22. `core/vision.py`（多模态接口，已预留未启用）

**职责**：把图片变成给模型的结构化描述。**独立角色**，不复用 worker ——
图像模型与代码模型通常不是同一个，且不该强制 worker 支持图像。

```python
@dataclass
class ImageInput:  path, url, data_uri, detail="auto", label
class VisionError(ModelCapabilityError)
def image_roots() -> tuple[str, ...]                # 白名单根目录
def build_vision_message(prompt, images, client=None) -> dict
def ensure_vision_capable(client, images) -> None   # 能力校验，不满足即抛
async def describe_image(prompt, images, client=None, system="")
def describe() -> dict                              # 诊断用
```

**当前状态**：接口完整、有测试，但 `VISION_*` 未配置 → 角色**未启用**
（`core/config.py` 里 `vision` 无 `has_builtin_default`、无 `inherits_from`）。
`ensure_vision_capable` 会显式报错，**不会**静默降级成纯文本。

**纪律**：图片解析失败必须显式失败，绝不静默丢图；`detail` 只在
profile 声明支持时才下发（`ModelCapabilities.supports_image_detail`）。
本地图片根目录由 `VISION_IMAGE_ROOTS` 限定（默认 `assets` / `workspace`）。

---

## 23. `core/contract.py`（上游→前端兼容契约）

**职责**：把"前端会扫上游的哪些面"**声明**出来，并用**与前端同款的技术**
（AST 扫 `_emit` 字面量）扫自己，任何不一致都点名。
**只读**：不改任何东西，不参与执行。

**依赖**：`ast`、`os`、`dataclasses`；实际值延迟 import（`core.cycle` /
`core.compress` / `tools.registry` / `storage.store`），避免 import 环。

```python
CONTRACT_VERSION = "1.1"      # 破坏性改动才升（1.0→1.1：decision_opened payload 键改名）
EMIT_SOURCES = ("core/coding_cycle.py",)
EMIT_COMMON_KEYS = ("goal",)  # _emit 签名统一带上，不算 payload 键
RECORD_FIELDS = (...)         # 前端扁平化时 payload 能覆盖的记录字段（门禁逐条扫）
PAYLOAD_SHARED_KEYS = {...}   # 故意共用的公共键（goal / attempt），必须写明理由

FACT_SOURCES: dict[str, str]                  # 前端扫的四处上游来源
EVENTS: dict[str, EventSpec]                  # 事件词表（当前 13 种）
FROZEN_REPORT_KEYS / FROZEN_SNAPSHOT_KEYS / FROZEN_EVENT_FIELDS
FROZEN_TOOL_INFO_KEYS / FROZEN_PHASES         # 冻结面：只增不减

@dataclass(frozen=True)
class EventSpec:  kind, payload, status="active", since, note

def scan_emit_sites() -> dict[str, dict]  # kind -> {payload, sites, files}
def audit() -> dict                       # 声明 vs 实际（每项机器可判定）
def capabilities() -> dict[str, dict]      # 能力声明（能推导的一律推导）
def describe() -> dict                     # 给 bridge / /profile 的紧凑视图

# ---- 责任划分：对不上时**谁去改**（词表经统筹契约统一）----
OWNER_OPS / OWNER_BACKEND / OWNER_FRONTEND / OWNER_BOTH
OWNER_ORDER: tuple[str, ...]                # 判定顺序：ops 优先
SEV_BREAKING / SEV_DEGRADED / SEV_INFO
VERDICTS: tuple[str, ...]                   # 6 个结论（含 ops-action）
OPS_FACT_RULES: dict[str, str]              # 运行态事实名 → code

@dataclass(frozen=True)
class IssueRule:  code, owner, severity, why, action
ISSUE_RULES: dict[str, IssueRule]           # 23 条规则；code 稳定，可被日志/工单引用
PEER_FIELDS: dict[str, str]                 # 前端对账时应提交的字段

@dataclass
class Issue:  code, detail, evidence

def upstream_issues(a=None) -> list[Issue]                 # 上游自查（全是后端责任）
def peer_issues(peer, a=None, routes=None) -> list[Issue]  # 与前端自述对账
def compare(peer=None, routes=None) -> dict                # 责任划分报告
def contract_emitted() -> set[str]                         # 实际会发的事件（AST 扫的）
```

**为什么需要这一层**：前端对上"认不出就降级显示"，所以上游的破坏性改动
**不会让前端报错**——只会让它静默少显示东西。本模块把"改契约"变成
一个需要**显式编辑**的动作（改 `EVENTS`），而不是顺手就改了。

**`audit()` 的字段**（全部机器可判定，故可作门禁）：

| 字段 | 含义 |
|---|---|
| `nonliteral_kinds` | `_emit(变量, ...)` 的调用点 → 前端 AST **扫不到** |
| `emit_sources_ok` | `_emit` 是否只在声明的文件里调用（单一口径） |
| `undeclared_events` | 发了但没声明 → 词表被改了却没说 |
| `dead_events` | 声明 active 但不再发 → 前端的 `dead_calibrations` |
| `deprecated_still_emitted` | 标了废弃却还在发（最坑：前端同时看到新旧两套） |
| `payload_drift` | 声明过的 payload 键被删/改名 |
| `removed_*` | 冻结面里消失的阶段 / 字段 / 工具条目键 |
| `ok` | 以上全过 |

**责任划分（`ISSUE_RULES`，23 条）**：一条原则 —— **事实源在哪一侧，责任就在哪一侧**。
归属词表（4 个值）与结论词表（6 个值）经**统筹契约**统一：
本仓库原有 3 个归属（缺 `ops`）、5 个结论（缺 `ops-action`），本轮补齐；
21 条既有规则的归属与级别**一条都没有改判**。

| owner | 含义 |
|---|---|
| `ops` | 环境/运行态（服务没起、前端没构建、配置坏）—— 与双方契约无关。**判定顺序优先** |
| `backend` | 上游发出/声明的东西与自己的代码不符 → 本仓库改 |
| `frontend` | 上游已声明并正常发出，前端不认识 → 前端改 |
| `both` | 上游**单方面判不出来**的（如事件历史归属、版本号无法比较）→ 需协商 |

`severity` 三档：`breaking`（前端会真看不到/画错）/ `degraded`（有兜底但要修）/
`info`（additive 新增，可不处理）。**`info` 不参与 `verdict`**——
否则"新增"又变成"每次都要两边同步改"。

`compare()` 的 `verdict`（6 个）：`ok` / `ops-action` / `backend-action` /
`frontend-action` / `need-negotiation` / `multi-action`。
**先判 `ops`** —— 服务不可达/前端没构建时，后面一切结论都不成立。

**运行态（`O-` 两条）**：`service_down` / `frontend_not_built` 这类事实
**上游在服务活着时观测不到**（自己的不可达不可自证），所以事实由看得见环境的一侧
上报（`POST /contract/check` 的可选 `ops` 字段），而 **code 与归属由本表定义**。
它**与那 8 项声明并列**（`client_report_schema.canonical_fields` 现共 **10 项**）：
类别上那 8 项是"前端按什么写死的"**声明**，`ops` 是运行态**观测**；
但既然是同一个上报体，就同属这套字段。契约的 `canonical_fields` 与本侧
`PEER_FIELDS` **必须相等** —— 由 `tests/unit/test_contract_conformance.py` 每次跑测试时核对。

**`OPS_STALE_BY_TRANSPORT`：经同步通道上报时不可能是"当前值"的事实。**

判据是传输层事实 —— `POST /contract/check` 能成功送达就证明上游可达，
所以随请求报上来的 `service_down=true` 只能是"**上次已知状态**"。
它**照常出现在 `ops` 栏（信息不丢）但不驱动 `verdict`**：
`ops` 优先的前提是"服务不可达时后面一切不成立"，而请求成功把这个前提证伪了。
报告新增顶层 `warnings: []`（additive）把这条矛盾明说出来。

真·服务不可达只可能在前端本地被发现（那时它发不出这个请求），
所以在这条通道上排除它**不会漏掉真实故障**；
`frontend_not_built` 与可达性不矛盾，照旧驱动 `ops-action`。

**暴露给前端的几个口**：

| 接口 | 用途 |
|---|---|
| `GET /profile` 的 `contract` 段 | `describe()` + `audit()` + **`responsibility` 规则表** + `owner_values` / `verdict_values` / `ops_fact_rules` / `ops_stale_by_transport` + **`authority`** + **`responsibility_count` / `responsibility_fingerprint`** + `peer_report_fields` |
| `GET /contract/check` | 上游自检（前端无需提交） |
| `POST /contract/check` | 完整对账 → 责任划分报告（前端运维机制调这个） |
| `python -m core.contract [--peer x.json]` | 服务没起来时也能查 |

**`AUTHORITY_SCOPE`（A1b）：本入口自述权威范围。**

架构清单 A1（用户已批准）决定**按职责切分**两个对账入口：
本入口管**跨侧归属**，`/api/audit` 管**本地自检**。两个入口都必须自述权威范围，
否则消费方无从判断该信谁。`id` / `role` / `covers` / `not_covers` /
`rule_source` / `counterpart` / `policy` 同时出现在 `/contract/check` 响应与
`/profile` 的 `contract` 段里（同一份 `AUTHORITY_SCOPE`，单一来源）。

**`responsibility_fingerprint()`：规则表的内容指纹（当前 `af6bfe2a`）。**

只覆盖 `code|owner|severity` 三元组，所以**改 `why`/`action` 文案不变，
增删规则或改归属/级别一定变**。用途：让引用本入口 code 的前端能判断
"规则表变了没有"。配合 `responsibility_count`（当前 23）一起发布。
契约已把它登记进 `response_contract.profile_additions`。

**`PHASE_UNKNOWN_DECISION_TREE` + `Issue.action_override`（契约 v1.0.7）。**

`P-phase-unknown` 默认 `both`/`degraded`，但契约定义了一棵**只锐化文案、不改 owner**
的方向判定树（`client_report_schema.phase_unknown_decision_tree`）：

| 情形 | `evidence.direction` | `action` 指向 |
|---|---|---|
| 未知阶段 ∈ `peer.bridge_gate_steps` | `bridge_gate_step` | 前端：上报 `phases` 时过滤 |
| ∈ `FROZEN_PHASES` 且 ∉ `PHASE_ORDER` | `upstream_removed_frozen_phase` | 后端：恢复该阶段 |
| 其余 | `undetermined` | 保持"先确认方向"，**不伪造方向** |

实现出口是 `Issue.action_override`（只改文案）与 `evidence.direction`（机器可读）；
**owner / severity 永远取自规则表**，不可逐条覆盖 —— 这条由测试守着。
上报字段相应新增 `bridge_gate_steps`（`PEER_FIELDS` 第 10 项）。

**门禁**：`tests/unit/test_frontend_contract.py`（25 项，契约不变量 +
`_emit` 撞名 / 撞记录字段两类门禁）+
`tests/unit/test_contract_attribution.py`（113 项，归因正确性 + 规则表无死条目 +
词表与统筹契约一致 + `service_down` 语义 + 未知阶段决策树）+
`tests/unit/test_contract_conformance.py`（43 项，直接读契约原文对账 +
A1 两入口归属一致性 + A1b 权威范围自述 + **HTTP 路径接线**）。
契约文档见 `docs/FRONTEND_CONTRACT.md`；变更评估见
`docs/EVALUATION-OPS-1.md`（`ops` 语义）、`docs/EVALUATION-ARCH-A1B.md`（A1b）、
`docs/EVALUATION-ARCH-D1.md`（未知阶段归因方向）、
`docs/EVALUATION-ARCH-D7.md`（传输断点 + 版本裁决）。

---

## 24. `core/identity.py`（代码身份）

**职责**：回答**"这一次运行加载的到底是哪一份上游代码"**。
**依赖**：`hashlib`、`os`（纯标准库，不 import 任何业务模块，避免环）。

```python
FINGERPRINT_GLOBS = ("core", "tools", "storage", "web")   # 参与指纹的目录
PACKAGE_DIR = <本模块所在目录>      # …/core
CODE_DIR = <上游 checkout 根>       # …/

def code_fingerprint(base_dir: str | None = None) -> str   # 8 位，对内容敏感
def describe() -> dict    # {code_dir, package_dir, fingerprint, module_files, note}
```

**为什么需要它**（`docs/CHANGELOG.md` §31）：用户反复失败而**修复没生效** ——
前端 `bridge/paths.py` 在 `AGENT_BACKEND_DIR` 未设时用 `<VueWeb>/backend` **自带副本**，
而当时的运行记录**没有任何字段**能回答"跑的是哪一份"，定位只能靠 traceback 恰好带路径。

**指纹的覆盖范围是刻意的**：只含**代码**（`core`/`tools`/`storage`/`web` + `main.py`），
不含文档/测试/产物 —— 指纹要回答"代码是哪一版"，改一行文档不该让它变。
已写成断言（`tests/unit/test_identity.py`：稳定 / 改一字节就变 / 加文档不变）。

**消费方**：
- 每次运行的第一个事件 `cycle_start` 记 `code_dir` + `code_fingerprint`（**事后可查**）；
- `GET /profile` 的 `code` 段（**当场可查**）；
- `tests/diagnostics/backend_dir_check.py` 拿它**并排比对**两份代码的指纹
  ——这就是统筹方 R4 要的"内容级判据"（原陈旧探针只查标记文件存在性，
  "标记齐全但内容陈旧"探不到）。

> ⚠️ 与 `cycle_start` 里的 `backend` 区分：那个是**检查点后端**（git/snapshot），
> **不是**代码来源。

**门禁**：`tests/unit/test_identity.py`（12 项）；
生产路径断言在 `tests/diagnostics/repro_user_goal.py`（真实 cycle 的记录里必须有身份，
且与当前代码一致）。

---
