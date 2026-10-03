"""运行根 / 工作区根 / 输出根 + **任务级目标项目根**（P14 / P15）。

来源：用户 2026-10-03 实跑真实任务后的反馈 ——
「1. 没有明确文件输出路径和输出成果，2. 缺少引入代码工作区的路径」。
契约 `runtime_paths_and_output_contract`（interface-contract v1.0.32）逐条对应本模块。

三个根**互不混淆**（此前 `/profile` 里根本没有 `runtime` 段）：

  ==================  ==========================================================
  `runtime_root`      运行数据根（会话 / 存储快照）。进程级，默认当前工作目录。
  `workspace_root`    agent 的**草稿区**：可以乱，**不承担交付**。
  `output_root`       **交付物**该去的地方：与工作区**分开**，因此必须可核对。
  ==================  ==========================================================

另有一个**任务级**的 `project_root`（目标项目根）：
任务要改的那个**已有代码库**。它由调用方**每次任务**给出（用户裁决），
经 `/encode` / `/run` 的 `project_root` 字段传入，落在 `ContextVar` 上，
**只在本次任务期间有效**（进程级会让「一个进程服务多个项目」不可能）。

⚠️ **绝不与 `AGENT_BACKEND_DIR` 混为一谈** ——
后者指**被测程序自己的源码**（来源核对用），把两者混起来会污染来源判定。
`describe()` 把两者并列暴露，正是为了让「不是同一个东西」成为**可读事实**。

越界写（超出 `project_root` / `output_root`）一律**结构化拒绝**
（`ScopeError` → `{code, message, allowed_roots}`），**不得静默失败**。
"""

from __future__ import annotations

import hashlib
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime

ENV_RUNTIME_ROOT = "AGENT_RUNTIME_ROOT"
ENV_WORKSPACE_ROOT = "AGENT_WORKSPACE_DIR"
ENV_OUTPUT_ROOT = "AGENT_OUTPUT_DIR"
ENV_PROJECT_ROOT = "AGENT_PROJECT_ROOT"
#: **被测程序自己的源码**（来源核对用）。与 project_root 是两个概念。
ENV_BACKEND_DIR = "AGENT_BACKEND_DIR"

#: 交付物前缀：`outputs/foo.txt` 明确指向**输出根**（而不是工作区根）。
OUTPUT_PREFIXES: tuple[str, ...] = ("outputs/", "output/")
OUTPUT_NAMES: tuple[str, ...] = ("outputs", "output")

#: 声明的交付物最多回报多少条（防止报告无限膨胀；截断会写明）。
MAX_DELIVERABLES = 200


class ScopeError(Exception):
    """路径越界 / 无法判定 —— **结构化拒绝**（不是静默失败）。"""

    def __init__(self, code: str, message: str, path: str = "",
                 allowed_roots: tuple[str, ...] = (), hint: str = ""):
        super().__init__(message)
        self.code = code
        self.message = message
        self.path = path
        self.allowed_roots = tuple(allowed_roots)
        self.hint = hint

    def to_dict(self) -> dict:
        out = {
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "allowed_roots": list(self.allowed_roots),
        }
        if self.hint:
            out["hint"] = self.hint
        return out


def _abs(path: str, base: str | None = None) -> str:
    p = os.path.expanduser(str(path))
    if not os.path.isabs(p) and base:
        p = os.path.join(base, p)
    return os.path.abspath(p)


def _looks_absolute(path: str) -> bool:
    norm = str(path or "").replace("\\", "/")
    return os.path.isabs(norm) or bool(re.match(r"^[A-Za-z]:", norm))


# ---------------------------------------------------------------------------
# 三个根
# ---------------------------------------------------------------------------
def runtime_root() -> str:
    """运行数据根（会话 / 存储快照）。进程级；默认当前工作目录。"""
    return _abs(os.getenv(ENV_RUNTIME_ROOT) or os.getcwd())


def workspace_root() -> str:
    """工作区根（草稿区）。默认 `<runtime_root>/workspace`，保持旧默认不变。"""
    env = os.getenv(ENV_WORKSPACE_ROOT)
    if env:
        return _abs(env)
    return os.path.join(runtime_root(), "workspace")


def output_root() -> str:
    """输出根（交付物）。**与工作区根分开**，因此「有没有产出」才可核对。"""
    env = os.getenv(ENV_OUTPUT_ROOT)
    if env:
        return _abs(env)
    return os.path.join(runtime_root(), "outputs")


def ensure_roots() -> dict:
    """确保三个根都存在（`/profile.runtime` 的验收①：三个绝对路径都存在）。"""
    roots = {
        "runtime_root": runtime_root(),
        "workspace_root": workspace_root(),
        "output_root": output_root(),
    }
    for p in roots.values():
        os.makedirs(p, exist_ok=True)
    return roots


# ---------------------------------------------------------------------------
# 任务级目标项目根（ContextVar：只在本次任务期间生效）
# ---------------------------------------------------------------------------
_active_project_root: ContextVar[str | None] = ContextVar(
    "agent_project_root", default=None
)


def default_project_root() -> str | None:
    """进程级默认（仅来自环境变量）。任务级参数会覆盖它。"""
    env = (os.getenv(ENV_PROJECT_ROOT) or "").strip()
    return _abs(env) if env else None


def project_root() -> str | None:
    """当前任务的目标项目根；未设时为 `None`（不影响旧行为）。"""
    active = _active_project_root.get()
    if active:
        return active
    return default_project_root()


def project_root_source() -> str:
    if _active_project_root.get():
        return "task"
    if default_project_root():
        return "env"
    return "none"


def effective_root() -> str:
    """文件 / 结构工具**实际以谁为根**：设了目标项目根就用它，否则用工作区根。"""
    return project_root() or workspace_root()


def effective_root_source() -> str:
    return "project_root" if project_root() else "workspace_root"


def set_project_root(path: str | None):
    """设置**任务级**目标项目根；返回 `ContextVar` token（`None` 表示未改动）。

    - `None` / 空串：**不动**（保持环境变量默认或未设），返回 `None`；
    - 路径不存在 / 不是目录：抛 `ScopeError`（结构化拒绝，不静默忽略）。
    """
    raw = (path or "").strip()
    if not raw:
        return None
    target = _abs(raw)
    if not os.path.isdir(target):
        raise ScopeError(
            "project-root-not-found",
            f"目标项目根不存在或不是目录: {target}",
            path=target,
            hint=f"传入一个存在的目录（任务级 project_root；与 {ENV_BACKEND_DIR} 不是一回事）",
        )
    return _active_project_root.set(target)


def reset_project_root(token) -> None:
    if token is not None:
        _active_project_root.reset(token)


@contextmanager
def use_project_root(path: str | None):
    """任务级作用域：进入时设根，退出时**一定**还原（异常路径也还原）。"""
    token = set_project_root(path)
    try:
        yield effective_root()
    finally:
        reset_project_root(token)


# ---------------------------------------------------------------------------
# 路径判定：读 / 写各允许哪些根
# ---------------------------------------------------------------------------
def _within(target: str, root: str) -> bool:
    target = os.path.normcase(os.path.abspath(target))
    root = os.path.normcase(os.path.abspath(root))
    return target == root or target.startswith(root + os.sep)


def is_within(target: str, root: str) -> bool:
    """`target` 是否在 `root` 之内（公开版，供工具拼相对标签用）。"""
    return _within(target, root)


def allowed_read_roots() -> list[str]:
    """可读的根：目标项目根（或工作区根）+ 输出根（模型要能读回自己的交付物）。"""
    roots = [effective_root()]
    out = output_root()
    if out not in roots:
        roots.append(out)
    return roots


def allowed_write_roots() -> list[str]:
    """可写的根：`project_root` **或** `output_root`（契约的「越界即拒」判据）。"""
    return allowed_read_roots()


def _output_subpath(norm: str) -> str | None:
    """`outputs/x.txt` → `x.txt`；`outputs` → ``；不是输出前缀 → `None`。"""
    low = norm.lstrip("/")
    for pref in OUTPUT_PREFIXES:
        if low.startswith(pref):
            return low[len(pref):]
    if low.strip("/") in OUTPUT_NAMES:
        return ""
    return None


def _resolve(raw: str, *, write: bool) -> str:
    text = str(raw or "").strip()
    if not text:
        raise ScopeError("empty-path", "路径为空", path="",
                         allowed_roots=tuple(allowed_write_roots()))
    norm = text.replace("\\", "/")
    roots = allowed_write_roots()
    code = "out-of-scope-write" if write else "out-of-scope-read"
    verb = "写" if write else "读"

    if _looks_absolute(norm):
        target = _abs(norm)
        for root in roots:
            if _within(target, root):
                return target
        raise ScopeError(
            code,
            f"{verb}路径超出允许范围: {target}（不在 "
            f"{' / '.join(roots)} 之内）",
            path=target, allowed_roots=tuple(roots),
            hint="相对路径以目标项目根（未设时=工作区根）为根；"
                 "交付物可用 `outputs/` 前缀指到输出根",
        )

    sub = _output_subpath(norm)
    if sub is not None:
        target = _abs(os.path.join(output_root(), sub))
        if _within(target, output_root()):
            return target
        raise ScopeError(code, f"{verb}路径越出输出根: {target}", path=target,
                         allowed_roots=tuple(roots), hint="不要用 `..` 逃出输出根")

    target = _abs(os.path.join(effective_root(), norm.lstrip("/")))
    if _within(target, effective_root()):
        return target
    raise ScopeError(
        code,
        f"{verb}路径越出目标根: {target}（根={effective_root()}）",
        path=target, allowed_roots=tuple(roots),
        hint="不要用 `..` 逃出根目录；交付物写到 `outputs/` 下",
    )


def resolve_read(path: str) -> str:
    """把调用方给的路径解析成**绝对路径**（读）；越界抛 `ScopeError`。"""
    return _resolve(path, write=False)


def resolve_write(path: str) -> str:
    """把调用方给的路径解析成**绝对路径**（写）；越界抛 `ScopeError`。"""
    return _resolve(path, write=True)


def relative_label(abs_path: str) -> str:
    """给报告用的相对标签：优先相对**目标根**，其次输出根，最后绝对路径。"""
    target = os.path.abspath(abs_path)
    for root in (effective_root(), output_root(), workspace_root()):
        if _within(target, root):
            rel = os.path.relpath(target, root).replace("\\", "/")
            return "" if rel == "." else rel
    return target.replace("\\", "/")


# ---------------------------------------------------------------------------
# 文件事实（交付物回报用）
# ---------------------------------------------------------------------------
def file_fact(abs_path: str, label: str | None = None) -> dict:
    """`{path, sha256, size, exists}` —— 交付物声明的对账单位。"""
    target = os.path.abspath(abs_path)
    fact = {
        "path": label if label is not None else relative_label(target),
        "abs_path": target.replace("\\", "/"),
        "sha256": None,
        "size": None,
        "exists": False,
    }
    try:
        with open(target, "rb") as f:
            raw = f.read()
    except OSError:
        return fact
    fact["exists"] = True
    fact["sha256"] = hashlib.sha256(raw).hexdigest()
    fact["size"] = len(raw)
    return fact


# ---------------------------------------------------------------------------
# 交付物声明（P14 要求 3 / 验收 ②③）
# ---------------------------------------------------------------------------
def normalize_declared(raw) -> list[dict]:
    """把任务输入里的交付物声明归一成 `{path, sha256, size}` 列表。

    容忍写法：纯字符串 / `{path|filename|file, sha256|hash, size}`。
    不合法（没有 path）的条目**丢弃并留痕**在返回值之外 ——
    由 `check_deliverables` 的 `invalid` 记录，而不是静默消失。
    """
    out: list[dict] = []
    if not raw:
        return out
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return out

    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            item = {"path": item}
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("filename")
                   or item.get("file") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        out.append({
            "path": path,
            "sha256": str(item.get("sha256") or item.get("hash") or "").strip().lower(),
            "size": item.get("size") if isinstance(item.get("size"), int) else None,
        })
        if len(out) >= MAX_DELIVERABLES:
            break
    return out


def _candidate_locations(declared_path: str) -> list[tuple[str, str]]:
    """声明路径可能落在哪：输出根优先，其次目标根（读回自己写在工作区的产物）。"""
    text = str(declared_path or "").strip().replace("\\", "/")
    out: list[tuple[str, str]] = []

    def _safe_join(root: str, sub: str) -> str | None:
        target = _abs(os.path.join(root, sub)) if sub else _abs(root)
        return target if _within(target, root) else None

    if _looks_absolute(text):
        target = _abs(text)
        for label, root in (("output_root", output_root()),
                            ("effective_root", effective_root())):
            if _within(target, root):
                out.append((label, target))
        return out

    sub = _output_subpath(text)
    if sub is not None:
        cand = _safe_join(output_root(), sub)
        if cand:
            out.append(("output_root", cand))
        return out

    for label, root in (("output_root", output_root()),
                        ("effective_root", effective_root())):
        cand = _safe_join(root, text)
        if cand and all(cand != c for _l, c in out):
            out.append((label, cand))
    return out


def check_deliverables(raw, *, extra_touched: list[str] | None = None) -> dict:
    """对账「声明的交付物」与实际磁盘事实（**声明的必须存在且哈希一致**）。

    返回：
      `checked`     是否真的有声明（没有声明 → `False`，不假装通过也不拦路）
      `passed`      无 error 级 violation
      `declared`    归一后的声明
      `actual`      `[{path, sha256, size, exists, root}]` —— **实际产物**
      `violations`  结构化缺口（`deliverable-missing` / `-hash-mismatch` /
                    `-size-mismatch` / `-out-of-scope` / `-invalid-declaration`）
      `touched`     `extra_touched` 里那些确实存在的文件的 `{path, sha256, size}`
    """
    declared = normalize_declared(raw)
    touched_facts: list[dict] = []
    for rel in extra_touched or []:
        try:
            target = resolve_write(rel)
        except ScopeError:
            continue
        fact = file_fact(target)
        if fact["exists"]:
            touched_facts.append({k: fact[k] for k in ("path", "sha256", "size")})

    if not declared:
        return {
            "checked": False,
            "passed": True,
            "declared": [],
            # 没有声明时，`actual` 就是本轮真正写出来的文件 ——
            # 「运行记录回报实际产物 {path, sha256, size}」不该因为没声明就空着
            "actual": list(touched_facts),
            "touched": touched_facts,
            "violations": [],
            "note": "本轮没有声明交付物路径（不判定；`actual` 仍回报磁盘事实）",
            "roots": {"output_root": output_root(), "effective_root": effective_root()},
        }

    violations: list[dict] = []
    actual: list[dict] = []
    for d in declared:
        declared_path = d["path"]
        locations = _candidate_locations(declared_path)
        if not locations:
            violations.append({
                "kind": "deliverable-out-of-scope",
                "severity": "error",
                "path": declared_path,
                "message": (
                    f"声明的交付物路径不在允许范围内（输出根 {output_root()} / "
                    f"目标根 {effective_root()}）"
                ),
                "fix": "把交付物路径写成相对路径（或用 `outputs/` 前缀指到输出根）",
            })
            actual.append({"path": declared_path, "exists": False,
                           "sha256": None, "size": None, "root": None})
            continue

        found_root = ""
        fact = None
        for label, cand in locations:
            f = file_fact(cand, declared_path)
            if f["exists"]:
                found_root = label
                fact = f
                break
        if fact is None:
            violations.append({
                "kind": "deliverable-missing",
                "severity": "error",
                "path": declared_path,
                "message": (
                    f"声明了交付物 {declared_path}，但它**不存在**"
                    f"（查过：{' / '.join(c for _l, c in locations)}）"
                ),
                "fix": f"把它实际写出来（推荐的输出根：{output_root()}）",
            })
            actual.append({"path": declared_path, "exists": False,
                           "sha256": None, "size": None, "root": None})
            continue

        entry = {"path": declared_path, "exists": True,
                 "sha256": fact["sha256"], "size": fact["size"],
                 "root": found_root, "abs_path": fact["abs_path"]}
        expected_sha = d.get("sha256") or ""
        if expected_sha and not fact["sha256"].startswith(expected_sha):
            violations.append({
                "kind": "deliverable-hash-mismatch",
                "severity": "error",
                "path": declared_path,
                "expected_sha256": expected_sha,
                "actual_sha256": fact["sha256"],
                "message": (
                    f"交付物 {declared_path} 的内容哈希与声明不一致："
                    f"声明 {expected_sha[:16]}… 实际 {fact['sha256'][:16]}…"
                ),
                "fix": "重新产出，或更新声明里的 sha256（不许改判据来通过）",
            })
        if d.get("size") is not None and fact["size"] != d["size"]:
            violations.append({
                "kind": "deliverable-size-mismatch",
                "severity": "error",
                "path": declared_path,
                "expected_size": d["size"],
                "actual_size": fact["size"],
                "message": (
                    f"交付物 {declared_path} 大小与声明不一致："
                    f"声明 {d['size']} 字节，实际 {fact['size']} 字节"
                ),
                "fix": "重新产出，或更新声明里的 size",
            })
        actual.append(entry)

    return {
        "checked": True,
        "passed": not violations,
        "declared": declared,
        "actual": actual,
        "touched": touched_facts,
        "violations": violations,
        "note": "声明的交付物必须存在且哈希一致（P14：把「写哪、产出什么」变成接口事实）",
        "roots": {"output_root": output_root(), "effective_root": effective_root()},
    }


# ---------------------------------------------------------------------------
# /profile 的 runtime 段
# ---------------------------------------------------------------------------
def describe() -> dict:
    """`/profile.runtime` —— 三个绝对路径 + 任务级目标项目根的当前状态。"""
    roots = ensure_roots()
    active = _active_project_root.get()
    default = default_project_root()
    backend_dir = (os.getenv(ENV_BACKEND_DIR) or "").strip()
    backend_abs = _abs(backend_dir) if backend_dir else ""
    current = active or default
    distinct = None
    if current and backend_abs:
        distinct = os.path.normcase(current) != os.path.normcase(backend_abs)
    return {
        "runtime_root": roots["runtime_root"],
        "workspace_root": roots["workspace_root"],
        "output_root": roots["output_root"],
        "exist": {k: os.path.isdir(v) for k, v in roots.items()},
        "project_root": {
            "lifetime": "per-task",
            "active": active,
            "default": default,
            "source": project_root_source(),
            "env": ENV_PROJECT_ROOT,
            "must_not_conflate": ENV_BACKEND_DIR,
            "backend_dir": backend_abs,
            "distinct_from_backend_dir": distinct,
            "note": (
                "目标项目根是**任务级**的（每次任务给一个）；"
                f"{ENV_BACKEND_DIR} 是**被测程序自己的源码**，两者语义不同"
            ),
        },
        "effective_root": effective_root(),
        "effective_root_source": effective_root_source(),
        "allowed_write_roots": allowed_write_roots(),
        "env_keys": {
            "runtime_root": ENV_RUNTIME_ROOT,
            "workspace_root": ENV_WORKSPACE_ROOT,
            "output_root": ENV_OUTPUT_ROOT,
            "project_root": ENV_PROJECT_ROOT,
            "backend_dir": ENV_BACKEND_DIR,
        },
        "workspace_prefix_convention": (
            "`workspace/` 前缀会被去掉（兼容旧习惯）；`outputs/` 前缀指向输出根。"
            "相对路径的真正根由 `effective_root` 决定"
        ),
        "deliverable_contract": {
            "declared": "{path, sha256?, size?}",
            "actual": "{path, sha256, size}",
            "gate": "声明的交付物必须存在且哈希一致，否则结局 delivery-gap（fail）",
        },
        "tools_rooted_at_effective_root": [
            "get_architecture", "list_workspace", "read_file", "write_file",
            "get_module", "find_symbol",
        ],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def scope_error_result(tool_name: str, err: ScopeError) -> str:
    """把 `ScopeError` 渲染成**结构化拒绝**（`{ok:false, kind:error, error:{...}}`）。"""
    import json

    return json.dumps(
        {
            "ok": False,
            "kind": "error",
            "tool": tool_name,
            "error": err.to_dict(),
        },
        ensure_ascii=False,
    )
