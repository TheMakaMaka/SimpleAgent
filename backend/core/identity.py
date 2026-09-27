"""代码身份：**这一次运行加载的到底是哪一份上游代码。**

为什么需要它（实测事故，见 `docs/CHANGELOG.md` §31）
----------------------------------------------------
用户连续几次跑真实需求都失败，而**修复代码一行都没被加载** ——
前端 `bridge/paths.py` 在 `AGENT_BACKEND_DIR` 未设时会用 `<VueWeb>/backend`
**自带的陈旧副本**。于是：

  · 失败签名与修之前**逐字相同**（旧代码的表现，不是新缺陷）；
  · 定位只能靠 **traceback 恰好带了路径**（运行时记录里没有这个事实）；
  · 上游的陈旧探针只查**标记文件存在性 + 模块数**，
    若副本"标记齐全但内容陈旧"就**探不到**（内容级盲区）。

本模块补两件事：

1. **事实**：`code_dir`（这份代码是从哪个目录 import 的）；2. **内容级判据**：
   `fingerprint` —— 对 `core/*.py` 内容取的 8 位指纹。

   于是"跑的是哪一份、内容是否落后"都可以**逐字比对**，不必再靠运气。
   它被写进每次运行的 `cycle_start` 事件，也出现在 `GET /profile` 的 `code` 段。

**这不是契约的一部分**：它描述的是"本进程加载了什么"，属运行态事实。
前端/bridge 若也想在 `run_start` / `meta.json` 里记一份，直接取本模块即可。
"""

from __future__ import annotations

import hashlib
import os

#: 参与指纹的目录：只覆盖**上游代码**，不含文档/测试/产物，
#: 这样"文档改了一行"不会让指纹变化（指纹要回答的是"代码是哪一版"）。
FINGERPRINT_GLOBS: tuple[str, ...] = ("core", "tools", "storage", "web")

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
#: 上游 checkout 根（本模块在 `<root>/core/identity.py`）
CODE_DIR = os.path.dirname(PACKAGE_DIR)


def _iter_py(base_dir: str) -> list[str]:
    out: list[str] = []
    for sub in FINGERPRINT_GLOBS:
        d = os.path.join(base_dir, sub)
        if not os.path.isdir(d):
            continue
        for root, dirs, names in os.walk(d):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                if n.endswith(".py"):
                    out.append(os.path.relpath(os.path.join(root, n), base_dir)
                               .replace("\\", "/"))
    for f in ("main.py",):
        if os.path.isfile(os.path.join(base_dir, f)):
            out.append(f)
    return sorted(out)


def code_fingerprint(base_dir: str | None = None) -> str:
    """对上游代码**内容**取 8 位指纹（稳定、对内容敏感）。

    为什么不用 git 提交号：主目录未必是干净的 git 状态（实测就有未提交改动），
    而且副本根本没有 git 历史。**内容哈希不依赖版本控制**，两份代码一比即可。
    """
    base = os.path.abspath(base_dir or CODE_DIR)
    h = hashlib.sha1()
    for rel in _iter_py(base):
        h.update(rel.encode("utf-8"))
        try:
            with open(os.path.join(base, rel), "rb") as f:
                h.update(f.read())
        except OSError:
            h.update(b"<unreadable>")
    return h.hexdigest()[:8]


def describe() -> dict:
    """给 `/profile` 与 `cycle_start` 事件用的紧凑事实。"""
    return {
        "code_dir": CODE_DIR,
        "package_dir": PACKAGE_DIR,
        "fingerprint": code_fingerprint(),
        "module_files": len(_iter_py(CODE_DIR)),
        "note": "fingerprint 是上游代码内容（core/tools/storage/web + main.py）的 8 位指纹；"
                "与另一份代码的指纹不一致即内容不同",
    }
