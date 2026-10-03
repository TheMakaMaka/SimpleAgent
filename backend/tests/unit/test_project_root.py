"""P15 门禁：**任务级目标项目根** + 三个根 + 越界结构化拒绝。

契约 `runtime_paths_and_output_contract`（v1.0.32）的验收 ①②③⑤：
  ① `/profile.runtime` 给出 runtime_root / workspace_root / output_root 三个**绝对路径**，且都存在；
  ② `project_root` **任务级**可设、`/profile` 可见、且**与 `AGENT_BACKEND_DIR` 语义分离**；
  ③ 设了 `project_root` 后，文件与结构工具扫到的集合**随之改变**；
  ⑤ 越界写被**结构化拒绝**（不是静默失败）。

反空洞（"不是把检查关掉"）：
  · 同一个 workspace 根下，**没设** project_root 时扫到的集合必须**不同**
    （否则"集合变了"可能只是别的原因）；
  · 越界写不仅要报错，还要给出**可机判的 code**，且文件**真的没有**被写出去。
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker  # noqa: E402

from core import runtime  # noqa: E402
from tools import TOOLS_MAP  # noqa: E402

c = Checker()
list_workspace = TOOLS_MAP["list_workspace"]["function"]
get_architecture = TOOLS_MAP["get_architecture"]["function"]
write_file = TOOLS_MAP["write_file"]["function"]
read_file = TOOLS_MAP["read_file"]["function"]


def _mkroot(prefix: str) -> str:
    root = tempfile.mkdtemp(prefix=prefix)
    with open(os.path.join(root, "alpha.py"), "w", encoding="utf-8") as f:
        f.write("def alpha():\n    return 1\n")
    with open(os.path.join(root, "beta.py"), "w", encoding="utf-8") as f:
        f.write("import alpha\n\ndef beta():\n    return alpha.alpha()\n")
    with open(os.path.join(root, "notes.txt"), "w", encoding="utf-8") as f:
        f.write("not python\n")
    return root


async def main() -> int:
    ws = runtime.workspace_root()
    root_a = _mkroot("p15_root_a_")
    root_b = _mkroot("p15_root_b_")
    try:
        print("=" * 74)
        print("[1] 三个根：绝对路径 + 都存在（/profile.runtime 的判据）")
        print("=" * 74)
        info = runtime.describe()
        for key in ("runtime_root", "workspace_root", "output_root"):
            p = info[key]
            print(f"  {key:16s} = {p}  exists={os.path.isdir(p)}")
            c.check(f"{key} 是绝对路径", os.path.isabs(p))
            c.check(f"{key} 存在且是目录", os.path.isdir(p))
        c.check("三个根互不混淆（两两不同）",
                len({os.path.normcase(info[k]) for k in
                     ("runtime_root", "workspace_root", "output_root")}) == 3)
        c.check("输出根与工作区根**分开**（用户裁决）",
                os.path.normcase(info["workspace_root"])
                != os.path.normcase(info["output_root"]))
        c.check("deliverable_contract 声明了 {path, sha256, size}",
                info["deliverable_contract"]["actual"] == "{path, sha256, size}")

        print("\n" + "=" * 74)
        print("[2] project_root 与 AGENT_BACKEND_DIR **语义分离**")
        print("=" * 74)
        os.environ["AGENT_BACKEND_DIR"] = ws
        try:
            with runtime.use_project_root(root_a):
                d = runtime.describe()
                pr = d["project_root"]
                print(f"  active={pr['active']}")
                print(f"  backend_dir={pr['backend_dir']}")
                print(f"  distinct_from_backend_dir={pr['distinct_from_backend_dir']}")
                c.check("任务级 active == 传入的根",
                        os.path.normcase(pr["active"]) == os.path.normcase(root_a))
                c.check("lifetime 声明为 per-task", pr["lifetime"] == "per-task")
                c.check("与 backend_dir 判为**不同**（两者确实是两个概念）",
                        pr["distinct_from_backend_dir"] is True)
                c.check("effective_root == 目标项目根",
                        os.path.normcase(d["effective_root"]) == os.path.normcase(root_a))
            # 反向：把 backend_dir 设成同一个路径时必须判 False（判据有牙齿）
            os.environ["AGENT_BACKEND_DIR"] = root_a
            with runtime.use_project_root(root_a):
                c.check("把 backend_dir 设成同一个路径时必须判 False（判据不是恒真）",
                        runtime.describe()["project_root"]["distinct_from_backend_dir"]
                        is False)
        finally:
            os.environ.pop("AGENT_BACKEND_DIR", None)

        print("\n" + "=" * 74)
        print("[3] 设了 root 之后，扫到的文件集合**随之改变**（真实对真值）")
        print("=" * 74)
        before = json.loads(await list_workspace())
        with runtime.use_project_root(root_a):
            after_a = json.loads(await list_workspace())
            arch_a = json.loads(await get_architecture())
        with runtime.use_project_root(root_b):
            after_b = json.loads(await list_workspace())

        set_before = {f["path"] for f in before["files"]}
        set_a = {f["path"] for f in after_a["files"]}
        set_b = {f["path"] for f in after_b["files"]}
        print(f"  未设 root: {sorted(set_before)}")
        print(f"  root_a   : {sorted(set_a)}")
        print(f"  root_b   : {sorted(set_b)}")
        c.check("设 root 后文件集合真的变了（不是同一个根）", set_a != set_before)
        c.check("root_a 扫到的正是它自己的文件（真值）",
                set_a == {"alpha.py", "beta.py", "notes.txt"})
        c.check("两个不同 root 各自报出自己的绝对路径（换根真的生效）",
                os.path.normcase(after_a["root"]) != os.path.normcase(after_b["root"]))
        c.check("list_workspace 报的 root 就是目标根",
                os.path.normcase(after_a["root"]) == os.path.normcase(root_a))
        c.check("get_architecture 的范围显式 == 目标根",
                os.path.normcase(arch_a["scope"]["root"]) == os.path.normcase(root_a)
                and arch_a["scope"]["source"] == "project_root")
        c.check("离开 with 之后根**还原**（任务级作用域，不串到下一个任务）",
                os.path.normcase(runtime.effective_root()) == os.path.normcase(ws))

        print("\n" + "=" * 74)
        print("[4] 越界写 ⇒ **结构化拒绝**（可机判字段；不是静默失败）")
        print("=" * 74)
        with runtime.use_project_root(root_a):
            escaped = await write_file(filename="../../p15_escape_probe.txt",
                                       content="should not exist")
            print(f"  越界写返回: {escaped[:220]}")
            data = json.loads(escaped)
            c.check("越界写返回合法 JSON（结构化拒绝）", isinstance(data, dict))
            c.check("ok=false", data.get("ok") is False)
            c.check("带可机判 code=out-of-scope-write",
                    (data.get("error") or {}).get("code") == "out-of-scope-write")
            c.check("带 allowed_roots（人能看懂去哪儿写）",
                    bool((data.get("error") or {}).get("allowed_roots")))
            # 反空洞：拒绝之后，越界目标**真的不存在**
            probe = os.path.abspath(os.path.join(root_a, "..", "..", "p15_escape_probe.txt"))
            print(f"  越界目标是否被写出: {os.path.exists(probe)}  ({probe})")
            c.check("越界目标**没有被写出去**（拒绝是真的）", not os.path.exists(probe))

            # 反向：根内写必须成功（否则就是"把写全关了"）
            ok = await write_file(filename="inside.txt", content="hello")
            c.check("根内写成功（不是把写功能关掉）", ok.startswith("OK:FILE|"))
            c.check("根内文件真的存在",
                    os.path.isfile(os.path.join(root_a, "inside.txt")))
            # outputs/ 前缀 → 输出根
            ok2 = await write_file(filename="outputs/deliv_probe.txt", content="d")
            out_path = os.path.join(runtime.output_root(), "deliv_probe.txt")
            print(f"  outputs/ 前缀写入: {ok2.splitlines()[0]} -> {out_path}")
            c.check("outputs/ 前缀写到**输出根**", ok2.startswith("OK:FILE|outputs/")
                    and os.path.isfile(out_path))
            try:
                os.remove(out_path)
            except OSError:
                pass
            # 读越界也要结构化拒绝
            bad_read = json.loads(await read_file(filename="../../secret.txt"))
            c.check("越界读同样结构化拒绝（code=out-of-scope-read）",
                    bad_read.get("ok") is False
                    and (bad_read.get("error") or {}).get("code") == "out-of-scope-read")

        print("\n" + "=" * 74)
        print("[5] 目标项目根不存在 ⇒ 结构化拒绝（不静默落回 workspace）")
        print("=" * 74)
        try:
            runtime.set_project_root(os.path.join(root_a, "no_such_dir"))
            raised = None
        except runtime.ScopeError as e:
            raised = e
        print(f"  抛错: {raised.to_dict() if raised else None}")
        c.check("不存在的根被拒", raised is not None)
        c.check("code=project-root-not-found",
                raised is not None and raised.code == "project-root-not-found")
        c.check("拒绝之后根没有被改掉",
                os.path.normcase(runtime.effective_root()) == os.path.normcase(ws))

    finally:
        shutil.rmtree(root_a, ignore_errors=True)
        shutil.rmtree(root_b, ignore_errors=True)

    return c.report()


raise SystemExit(asyncio.run(main()))
