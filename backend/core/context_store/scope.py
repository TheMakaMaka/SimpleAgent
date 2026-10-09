"""记忆库的**独立根**与**越界拒绝**（P21 / M1 · 统筹方硬要求 5）。

统筹方 §P21 约束 5 逐字：

> **物理隔离**：库根独立（建议 `<work area>\\08-memory\\`），**绝不写进两侧仓库**、
> 也不进 `.interface_contract\\`；**越界即拒**（复用 P15 的 `ScopeError` / `scope_error_result`）。

三条落地：

  1. **默认根在两侧仓库之外** —— `default_root()` 给的是绝对路径，且
     `assert_outside_repos()` 会**机判**它不在任何一侧仓库里；
  2. **越界即拒** —— 写/读目标不在库根内 ⇒ `StoreScopeError`（结构化：`code` /
     `message` / `path` / `allowed_roots` / `hint`），**不静默失败**、也不"写到一个
     别的地方去"；
  3. **库根自己也不能在仓库里** —— 即使调用方用 `AGENT_CONTEXT_STORE_ROOT`
     指进仓库，也照样结构化拒绝（否则隔离就成了"默认值好看、一改就没"）。

★ 与 `core/runtime.py::ScopeError` 的关系：**同形不同类**。本模块**刻意不 import**
`core.runtime` —— M1 的验收前提是「独立库、独立测试、成型之后再谈接入」，
所以它不依赖主链路的任何东西。错误对象字段与 `scope_error_result()` 的输出
逐键对齐（`code` / `message` / `path` / `allowed_roots` / `hint`），
M3 接入时一行适配即可，**M1 不需要动主链路**。
"""

from __future__ import annotations

import os

#: 库根的覆盖开关（与 `core.runtime` 的 `AGENT_*` 命名一致）。
ENV_STORE_ROOT = "AGENT_CONTEXT_STORE_ROOT"

#: 两侧仓库的绝对路径（**硬边界**：库根绝不许落在它们里面）。
#: 由 `FORBIDDEN_ROOTS` 机判，判据是 `os.path.normcase` 后的前缀比较。
REPO_BACKEND = r"D:\PythonProject\SimpleAgent2_Cycle"
REPO_FRONTEND = r"D:\PythonProject\SimpleAgent2_Cycle_VueWeb"
REPO_INTEGRATION = r"D:\PythonProject\SimpleAgent2_Integration"

FORBIDDEN_ROOTS: tuple[str, ...] = (REPO_BACKEND, REPO_FRONTEND, REPO_INTEGRATION)

#: 默认库根：**统筹方建议的 `<work area>\\08-memory\\`**。
#: 它不在任何一侧仓库里（`FORBIDDEN_ROOTS` 三条都不匹配），这是隔离的**出厂事实**。
DEFAULT_ROOT = r"D:\PythonProject\08-memory"

#: 库内部布局（把"物理隔离"落成可读事实，而不是散在代码里的字符串）。
LAYOUT = {
    "units": "units.jsonl",      # 索引：一行一条单元（append-only）
    "archive": "archive",        # 归档层：淘汰 = 移入这里，不是删除
    "manifest": "manifest.json",  # 库的自我描述（根 / 版本 / 计数）
}


class StoreScopeError(Exception):
    """记忆库越界 / 无法判定 —— **结构化拒绝**（不是静默失败）。

    字段与 `core/runtime.py::ScopeError` 及 `scope_error_result()` 的输出逐键对齐，
    便于 M3 接入时直接复用主链路的错误信封**而不必改本模块**。
    """

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

    def to_result(self) -> dict:
        """结构化拒绝的**结果信封**（形状与 `scope_error_result` 一致）。"""
        return {"ok": False, "kind": "error", "error": self.to_dict()}


def _abs(path: str) -> str:
    return os.path.abspath(os.path.expanduser(str(path)))


def _norm(path: str) -> str:
    return os.path.normcase(_abs(path)).rstrip("\\/")


def within(target: str, root: str) -> bool:
    """`target` 是否在 `root` 之内（相等也算）。"""
    t, r = _norm(target), _norm(root)
    return t == r or t.startswith(r + os.sep)


def repo_of(path: str) -> str | None:
    """`path` 落在哪一侧仓库里（不在任何一侧 ⇒ `None`）。**机判，不靠约定。**"""
    for repo in FORBIDDEN_ROOTS:
        if within(path, repo):
            return repo
    return None


def default_root() -> str:
    """默认库根（`AGENT_CONTEXT_STORE_ROOT` 优先）。

    `DEFAULT_ROOT` 的选择理由是可机判的：`repo_of(DEFAULT_ROOT) is None`。
    """
    return _abs(os.getenv(ENV_STORE_ROOT) or DEFAULT_ROOT)


def assert_outside_repos(root: str, *, allow_inside_repos: bool = False) -> str:
    """库根必须在两侧仓库之外；否则结构化拒绝（**不许"默认值好看、一改就没"**）。

    `allow_inside_repos=True` 是**测试专用的显式逃生口**：本轮硬边界禁止往
    两侧仓库之外写文件，所以单测只能在仓库内（`.tmp/`）造一个临时库根来验
    写/读/归档。它有三个保护：

      1. 只能**显式**传关键字实参 —— 生产代码没有任何一处会传它；
      2. `profile()["scope"]["outside_repos"]["relaxed"]` 会把这个事实**印出来**
         （隔离被放宽了就是放宽了，不许静默）；
      3. 默认值仍是拒绝 ⇒ 不传就拦住。
    """
    target = _abs(root)
    repo = repo_of(target)
    if repo and not allow_inside_repos:
        raise StoreScopeError(
            "store-root-inside-repo",
            f"记忆库根落在仓库内: {target}（仓库 {repo}）",
            path=target,
            allowed_roots=tuple(FORBIDDEN_ROOTS),
            hint=(
                "记忆库是**物理隔离**的：把库根指到仓库之外"
                f"（默认 {DEFAULT_ROOT}），或去掉 {ENV_STORE_ROOT}"
            ),
        )
    return target


def resolve_store_path(rel: str, root: str | None = None,
                       *, allow_inside_repos: bool = False) -> str:
    """把库内相对路径解析成绝对路径；越出库根 ⇒ 结构化拒绝。

    判据：先拒绝**绝对路径**（库内的东西一律用相对路径访问，调用方不该知道
    库根长什么样），再拒绝 `..` / 空白名 —— 走的是**解析后**的比较，
    所以 `a/../..` 这种绕过写法同样会被抓住。
    """
    base = assert_outside_repos(root or default_root(),
                               allow_inside_repos=allow_inside_repos)
    raw = str(rel or "").strip()
    if not raw:
        raise StoreScopeError(
            "empty-path", "库内路径为空", path="",
            allowed_roots=(base,), hint="库内路径一律是相对库根的相对路径",
        )
    norm = raw.replace("\\", "/")
    if os.path.isabs(norm) or (len(norm) > 1 and norm[1] == ":"):
        raise StoreScopeError(
            "out-of-scope-write",
            f"库内路径不许是绝对路径: {_abs(norm)}",
            path=_abs(norm), allowed_roots=(base,),
            hint="用相对路径（例如 units/ab12.json）；库根由 store.root() 决定",
        )
    target = _abs(os.path.join(base, norm))
    if not within(target, base):
        raise StoreScopeError(
            "out-of-scope-write",
            f"路径越出记忆库根: {target}（库根 {base}）",
            path=target, allowed_roots=(base,),
            hint="不要用 `..` 逃出库根",
        )
    return target


def describe(root: str | None = None, *, allow_inside_repos: bool = False) -> dict:
    """契约面：库根、隔离判据、布局、越界错误码（可读事实）。"""
    base = assert_outside_repos(root or default_root(),
                               allow_inside_repos=allow_inside_repos)
    repo = repo_of(base)
    return {
        "root": base,
        "env": ENV_STORE_ROOT,
        "default_root": DEFAULT_ROOT,
        "root_is_default": _norm(base) == _norm(DEFAULT_ROOT),
        "outside_repos": {
            "repos": list(FORBIDDEN_ROOTS),
            "root_repo": repo,
            "ok": repo is None,
            # 隔离被放宽了就是放宽了 —— 不许静默（测试专用逃生口）
            "relaxed": bool(repo) and allow_inside_repos,
            "how_checked": "os.path.normcase + 前缀比较（机判，不是约定）",
        },
        "layout": dict(LAYOUT),
        "scope_error_codes": [
            "store-root-inside-repo", "out-of-scope-write", "out-of-scope-read",
            "empty-path",
        ],
        "error_shape": {
            "keys": ["code", "message", "path", "allowed_roots", "hint"],
            "envelope": {"ok": False, "kind": "error", "error": "{...}"},
            "compatible_with": "core/runtime.py::scope_error_result（同形，未 import）",
        },
    }
