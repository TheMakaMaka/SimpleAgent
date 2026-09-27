"""编码回退：每个 Cycle 一个检查点。

两条纪律：
  1. git 命令绝不出现在模型可见的工具里。模型只能「申请检查点」，
     具体命令由程序生成——7B 对 reset --hard 的语义理解不可靠。
  2. 后端可插拔：优先用系统 git；git 不可用时退化为文件快照，
     回退能力不因环境缺失而消失。

checkpoint 目录刻意放在 workspace 之外，避免把快照自己提交进仓库。
"""

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

WORKSPACE_DIR = os.path.abspath("workspace")
SNAPSHOT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(WORKSPACE_DIR), ".checkpoints")
)

_BOT_NAME = "SimpleAgent2 Bot"
_BOT_EMAIL = "agent@localhost"

# git 的常见安装位置。用于「已安装但当前进程 PATH 未刷新」的情况——
# Windows 上安装 Git 只更新注册表，已经打开的终端/进程不会立刻看到。
_GIT_CANDIDATES = (
    r"C:\Program Files\Git\cmd\git.exe",
    r"C:\Program Files (x86)\Git\cmd\git.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Git\cmd\git.exe"),
    "/usr/bin/git",
    "/usr/local/bin/git",
    "/opt/homebrew/bin/git",
)

_git_exe_cache: str | None = None


def resolve_git() -> str | None:
    """定位 git 可执行文件；找不到返回 None。

    顺序：PATH → 常见安装目录。结果缓存，避免每次提交都做一遍探测。
    """
    global _git_exe_cache
    if _git_exe_cache is not None:
        return _git_exe_cache or None

    found = shutil.which("git")
    if not found:
        for cand in _GIT_CANDIDATES:
            if cand and os.path.isfile(cand):
                found = cand
                break

    _git_exe_cache = found or ""
    return found


def git_status() -> dict:
    """诊断用：说明 git 是否可用、路径来源、以及后端选择结果。"""
    exe = resolve_git()
    in_path = bool(shutil.which("git"))
    rc, out, _ = _run_git(["--version"], WORKSPACE_DIR) if exe else (-1, "", "")
    return {
        "available": bool(exe) and rc == 0,
        "executable": exe,
        "from_path": in_path,
        "version": out.strip() if rc == 0 else None,
        "note": (
            "PATH 中未找到，已从常见安装目录回退"
            if exe and not in_path else ""
        ),
    }


@dataclass
class Checkpoint:
    ref: str
    label: str


def _run_git(args: list[str], cwd: str, timeout: int = 30) -> tuple[int, str, str]:
    exe = resolve_git()
    if not exe:
        return -1, "", "git executable not found"

    # Git >= 2.35.2 会拒绝操作「属主与当前用户不一致」的仓库
    # （CVE-2022-24765 的防护）。用命令行级的 safe.directory 放行，
    # 不写 global config——不污染用户环境，只影响本次调用。
    base = ["-c", f"safe.directory={os.path.abspath(cwd)}", *args]

    try:
        p = subprocess.run(
            [exe, *base], cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return -1, "", "git executable not found"
    except subprocess.TimeoutExpired:
        return -2, "", "git timeout"


class CheckpointBackend(Protocol):
    name: str

    def is_available(self) -> bool: ...
    def init(self) -> None: ...
    def commit(self, label: str) -> Checkpoint | None: ...
    def rollback(self, ref: str) -> bool: ...
    def current_ref(self) -> str | None: ...


class GitBackend:
    name = "git"

    def __init__(self, base_dir: str = WORKSPACE_DIR):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _has_git(self) -> bool:
        rc, _, _ = _run_git(["--version"], self.base_dir)
        return rc == 0

    def is_available(self) -> bool:
        return self._has_git()

    def _in_repo(self) -> bool:
        rc, out, _ = _run_git(["rev-parse", "--is-inside-work-tree"], self.base_dir)
        return rc == 0 and out.strip() == "true"

    def init(self) -> None:
        if not self._in_repo():
            rc, _, err = _run_git(["init", "-b", "main"], self.base_dir)
            if rc != 0:
                print(f"[git] init 失败: {err.strip()[:200]}", file=sys.stderr)
        # 本地身份，不依赖全局 git config
        _run_git(["config", "user.name", _BOT_NAME], self.base_dir)
        _run_git(["config", "user.email", _BOT_EMAIL], self.base_dir)
        _run_git(["config", "core.autocrlf", "false"], self.base_dir)

        gitignore = os.path.join(self.base_dir, ".gitignore")
        if not os.path.exists(gitignore):
            with open(gitignore, "w", encoding="utf-8") as f:
                f.write("# agent 自动生成\n_tmp/\n_debug/\n__pycache__/\n*.pyc\n")

    def _has_changes(self) -> bool:
        rc, out, err = _run_git(["status", "--porcelain"], self.base_dir)
        if rc != 0:
            # 静默失败会让回退机制看起来"启用"了其实没工作，必须可见
            print(f"[git] status 失败: {err.strip()[:200]}", file=sys.stderr)
            return False
        return bool(out.strip())

    def commit(self, label: str) -> Checkpoint | None:
        if not self._has_changes():
            rc, out, err = _run_git(["rev-parse", "HEAD"], self.base_dir)
            if rc != 0:
                # 仓库可能还没有任何提交——先建一个初始提交再返回
                rc2, _, err2 = _run_git(["commit", "--allow-empty", "-m", label],
                                        self.base_dir)
                if rc2 != 0:
                    print(f"[git] 首次提交失败: {err2.strip()[:200]}", file=sys.stderr)
                    return None
                rc, out, err = _run_git(["rev-parse", "HEAD"], self.base_dir)
                if rc != 0:
                    return None
            return Checkpoint(ref=out.strip(), label=label)

        rc, _, err = _run_git(["add", "-A"], self.base_dir)
        if rc != 0:
            print(f"[git] add 失败: {err.strip()[:200]}", file=sys.stderr)
            return None
        rc, _, err = _run_git(["commit", "-m", label], self.base_dir)
        if rc != 0:
            print(f"[git] commit 失败: {err.strip()[:300]}", file=sys.stderr)
            return None
        rc, out, _ = _run_git(["rev-parse", "HEAD"], self.base_dir)
        if rc != 0:
            return None
        return Checkpoint(ref=out.strip(), label=label)

    def _untracked_to_remove(self) -> list[str]:
        """列出 `clean -fd` 将会删除的文件（**只列不删**）。

        `clean -fd` 默认**不删被忽略的文件**（无 -x），所以 `.gitignore`
        覆盖的 `_tmp/` `_debug/` 等是安全的；但任何未跟踪且未被忽略的文件
        （例如你手动放进 workspace 的笔记/脚本）会被清掉。
        """
        rc, out, _ = _run_git(["clean", "-nd"], self.base_dir)
        if rc != 0:
            return []
        victims: list[str] = []
        for line in (out or "").splitlines():
            # 形如 "Would remove path/to/file"
            _, _, path = line.partition("Would remove ")
            if path.strip():
                victims.append(path.strip())
        return victims

    def rollback(self, ref: str) -> bool:
        # 先把"将被清除的未跟踪文件"打出来再执行 —— 这个副作用不该是静默的
        victims = self._untracked_to_remove()
        if victims:
            shown = victims[:10]
            more = f" …等 {len(victims)} 个" if len(victims) > len(shown) else ""
            print(
                f"[rollback] 警告：将清除 {len(victims)} 个未跟踪文件"
                f"（手动放进 workspace 的文件也会被删）: {', '.join(shown)}{more}",
                file=sys.stderr,
            )

        rc, _, _ = _run_git(["reset", "--hard", ref], self.base_dir)
        if rc != 0:
            return False
        _run_git(["clean", "-fd"], self.base_dir)
        return True

    def current_ref(self) -> str | None:
        rc, out, _ = _run_git(["rev-parse", "HEAD"], self.base_dir)
        return out.strip() if rc == 0 else None


class FileSnapshotBackend:
    """git 不可用时的兜底：把 workspace 拷进编号快照目录。

    不是 git 的替代品（没有 diff、没有分支），但保证「改坏了能退回去」。
    记录每个快照的文件清单，回退时能清掉之后新增的文件。
    """

    name = "snapshot"

    def __init__(self, base_dir: str = WORKSPACE_DIR, root: str = SNAPSHOT_ROOT):
        self.base_dir = base_dir
        self.root = root
        self._index_path = os.path.join(root, "index.json")
        self._counter = 0

    def is_available(self) -> bool:
        return True

    def init(self) -> None:
        os.makedirs(self.root, exist_ok=True)
        # 从已有索引恢复计数，避免同进程内第二个 cycle 又从 snap0001 开始而互相覆盖
        snaps = self._load_index().get("snapshots") or []
        max_n = 0
        for s in snaps:
            m = re.fullmatch(r"snap(\d+)", str(s.get("ref", "")))
            if m:
                max_n = max(max_n, int(m.group(1)))
        self._counter = max_n

    # ---------- 索引 ----------
    def _load_index(self) -> dict:
        if not os.path.exists(self._index_path):
            return {"snapshots": []}
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"snapshots": []}

    def _save_index(self, data: dict) -> None:
        tmp = self._index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._index_path)

    def _rel_files(self) -> list[str]:
        out: list[str] = []
        for root, dirs, names in os.walk(self.base_dir):
            dirs[:] = [d for d in dirs if d not in ("_tmp", "_debug", "__pycache__", ".git")]
            for n in names:
                if n.endswith(".pyc"):
                    continue
                full = os.path.join(root, n)
                out.append(os.path.relpath(full, self.base_dir).replace("\\", "/"))
        return sorted(out)

    def commit(self, label: str) -> Checkpoint | None:
        self.init()
        files = self._rel_files()
        self._counter += 1
        ref = f"snap{self._counter:04d}"
        snap_dir = os.path.join(self.root, ref)

        if os.path.exists(snap_dir):
            shutil.rmtree(snap_dir, ignore_errors=True)
        shutil.copytree(
            self.base_dir, snap_dir,
            ignore=shutil.ignore_patterns("_tmp", "_debug", "__pycache__", "*.pyc", ".git"),
        )

        index = self._load_index()
        index["snapshots"].append({
            "ref": ref,
            "label": label,
            "files": files,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        self._save_index(index)
        return Checkpoint(ref=ref, label=label)

    def rollback(self, ref: str) -> bool:
        snap_dir = os.path.join(self.root, ref)
        if not os.path.isdir(snap_dir):
            return False

        index = self._load_index()
        target = next((s for s in index["snapshots"] if s["ref"] == ref), None)
        keep = set(target["files"]) if target else set()

        # 先清掉快照时刻不存在的文件，再还原
        for rel in self._rel_files():
            if rel not in keep:
                try:
                    os.remove(os.path.join(self.base_dir, rel))
                except OSError:
                    pass

        for root, dirs, names in os.walk(snap_dir):
            for n in names:
                src = os.path.join(root, n)
                rel = os.path.relpath(src, snap_dir)
                dst = os.path.join(self.base_dir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        return True

    def current_ref(self) -> str | None:
        snaps = self._load_index()["snapshots"]
        return snaps[-1]["ref"] if snaps else None


class CheckpointManager:
    """对外统一入口。选一个可用后端，并记录实际用的是哪个。"""

    def __init__(self, prefer: str = "git"):
        candidates: list[CheckpointBackend] = (
            [GitBackend(), FileSnapshotBackend()]
            if prefer == "git"
            else [FileSnapshotBackend(), GitBackend()]
        )
        self.backend: CheckpointBackend | None = None
        for b in candidates:
            try:
                if b.is_available():
                    self.backend = b
                    b.init()
                    break
            except Exception:
                continue

    @property
    def name(self) -> str:
        return self.backend.name if self.backend else "none"

    def commit(self, label: str) -> Checkpoint | None:
        if not self.backend:
            return None
        try:
            return self.backend.commit(label)
        except Exception:
            return None

    def rollback(self, ref: str) -> bool:
        if not self.backend:
            return False
        try:
            return self.backend.rollback(ref)
        except Exception:
            return False

    def current_ref(self) -> str | None:
        if not self.backend:
            return None
        try:
            return self.backend.current_ref()
        except Exception:
            return None
