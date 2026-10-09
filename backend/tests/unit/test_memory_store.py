"""P21 / M1 门禁：**外部记忆库的存储与检索 + 独立根 + 越界拒绝 + 归档不删除**。

统筹方 `WORK-ORDER.md`【P21】把工作拆成三期、**不许跳级**，M1 的验收逐字是：

  ① 写入/读取可机械复现；
  ② 越界写被**结构化拒绝**；
  ③ 库根在**两侧仓库之外**（可机判）；
  ④ 有**归档**而非删除。

统筹方另补三条硬要求，本文件逐条钉住：

  1. 判据覆盖**漏召 / 误召**，不能只看「调用成功」；
  2. 必须有**第二路召回** —— 挂在已有结构索引上（`find_symbol`/`get_module`/
     `get_architecture`），**别另起关键词库**；
  3. 阈值第一阶段**不许定死**：只记分、不决策。

反空洞（「不是把检查关掉」）：
  · 第二路召回拿一个**关键词绝对召不回**的单元证明它真的有牙（不是空转）；
  · 越界写：断言**文件真的没被写到那个地方**，另外断言 `..` 绕过写法也被拒；
  · 归档：断言归档后 `read()` 仍读得到原文、计数仍算得出来（**没有删除路径**）；
  · 独立性：断言 M1 包**不 import 主链路**、**不注册成工具**（"不接模型"是判据，不是口号）。
"""

import ast
import inspect
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import Checker, ROOT  # noqa: E402

from core.context_store import scope, units as units_mod  # noqa: E402
from core.context_store.store import ContextStore  # noqa: E402

c = Checker()
TEMPS: list[str] = []


def temp_store_root() -> str:
    """一个**仓库内**的临时库根（测试用；默认根在仓库之外，见 §4）。

    为什么测试不直接用默认根（`D:\\PythonProject\\08-memory`）：那会写到
    **本仓库和工作单之外**，违反本轮的硬边界（只改本仓库）。
    所以测试用 `allow_inside_repos=True` 这个**显式逃生口**（生产路径从不传它），
    并且 §3 会证明"不传就拦住"——隔离判据本身没有被放宽，只是测试要造一个
    受控的库根。放宽这件事会出现在 `profile()["scope"]["outside_repos"]["relaxed"]`。
    """
    path = tempfile.mkdtemp(prefix="p21_store_", dir=os.path.join(ROOT, ".tmp"))
    TEMPS.append(path)
    return path


def cleanup() -> None:
    for p in TEMPS:
        shutil.rmtree(p, ignore_errors=True)


def fresh_store() -> ContextStore:
    # 测试专用逃生口：本轮硬边界只许写本仓库，所以临时库根造在 `.tmp/`
    # （生产代码从不传这个参数；§3 证明不传就被拦）。
    return ContextStore(temp_store_root(), allow_inside_repos=True)


def w(store: ContextStore, content: str, **kw) -> dict:
    return store.write(content, **kw)


# ---------------------------------------------------------------------------
print("=" * 74)
print("[1] M1 验收①：写入/读取**可机械复现**（内容寻址 + 幂等 + 确定性字节）")
print("=" * 74)

s1 = fresh_store()
u1 = w(s1, "T9 失败是因为 reuse 层把 app.route 判成了「不存在的符号」",
       source="T9", keywords=["reuse", "false-positive"], symbols=["app.route"])
same = w(s1, "T9 失败是因为 reuse 层把 app.route 判成了「不存在的符号」",
         source="T9")
print(f"  第一次写入: id={u1['id']} status={u1['status']}")
print(f"  第二次写入: id={same['id']} status={same['status']} deduped={same['deduped']}")
c.check("★ 同 source 同内容 ⇒ 同一个 id（内容寻址）", u1["id"] == same["id"])
c.check("★ 重复写入不新增（幂等，deduped=True）", same["deduped"] is True
        and len(s1.list_units()) == 1)

read1 = s1.read(u1["id"])
read2 = s1.read(u1["id"])
c.check("★ 读取可复现：两次读出的单元逐字相同",
        json.dumps(read1["unit"], sort_keys=True, ensure_ascii=False)
        == json.dumps(read2["unit"], sort_keys=True, ensure_ascii=False))
c.check("★ 读出的内容哈希与写入时一致（新鲜度判据）",
        read1["unit"]["sha256"] == units_mod.content_sha256(
            "T9 失败是因为 reuse 层把 app.route 判成了「不存在的符号」"))

# 单元结构三件（M1 明写「时间 / 关键词 / 符号引用」）
unit = read1["unit"]
c.check("★ 单元结构含 时间 / 关键词 / 符号引用",
        bool(unit.get("created_at")) and bool(unit.get("keywords"))
        and "app.route" in (unit.get("symbol_refs") or []))
c.check("单元结构含 status/archived_at（归档判据的字段）",
        unit.get("status") == "active" and unit.get("archived_at") is None)

# CRLF 归一：跨平台同一段上下文必须得到同一个 id
s2 = fresh_store()
crlf = w(s2, "a\r\nb\r\n", source="X")
lf = w(s2, "a\nb\n", source="X")
c.check("★ CRLF/LF 归一 ⇒ 同一 id（同一件事不会变成两份）",
        crlf["id"] == lf["id"] and lf["deduped"] is True and crlf["created"] is True)

# 不同 source 同内容 = 两条记忆（来源是记忆的一部分）
s3 = fresh_store()
a = w(s3, "同样的正文", source="T9")
b = w(s3, "同样的正文", source="V2")
c.check("同内容不同 source ⇒ 两条不同单元（来源算进 id）",
        a["id"] != b["id"] and len(s3.list_units()) == 2)

# 重放：同一批写入 ⇒ units.jsonl 逐字节相同
def replay() -> str:
    st = ContextStore(temp_store_root(), allow_inside_repos=True)
    for i, text in enumerate(["第一条记忆", "第二条记忆", "第三条记忆"]):
        st.write(text, source=f"S{i}")
    with open(os.path.join(st.root(), scope.LAYOUT["units"]), "rb") as f:
        return f.read().decode("utf-8")


r1, r2 = replay(), replay()
c.check("★ 重放同一批写入 ⇒ units.jsonl 逐字节相同", r1 == r2)
c.check("索引是按 (created_at, id) 排序的确定性文本",
        r1.endswith("\n") and len(r1.splitlines()) == 3)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[2] M1 验收②：越界写被**结构化拒绝**（且文件真的没写出去）")
print("=" * 74)

s4 = fresh_store()
outside = os.path.join(ROOT, "workspace", "_p21_should_not_exist.json")
try:
    s4.path_of("../workspace/_p21_should_not_exist.json", write=True)
    err = None
except scope.StoreScopeError as exc:
    err = exc
print(f"  越界（..）异常: {err.code if err else '（没有拒绝！）'}")
c.check("★ `..` 逃出库根 ⇒ 结构化拒绝", err is not None
        and err.code == "out-of-scope-write")
c.check("★ 拒绝里带可机判字段（code/message/path/allowed_roots）",
        bool(err) and err.to_dict().get("code") == "out-of-scope-write"
        and bool(err.to_dict().get("allowed_roots"))
        and bool(err.to_dict().get("message")))
c.check("★ 拒绝信封形状与主链路一致（ok/kind/error）",
        err.to_result().get("ok") is False
        and err.to_result().get("kind") == "error"
        and isinstance(err.to_result().get("error"), dict))
c.check("★ 目标文件真的没被写出去（不是先写再报错）",
        not os.path.exists(outside))

try:
    s4.path_of(str(outside), write=True)
    abs_err = None
except scope.StoreScopeError as exc:
    abs_err = exc
c.check("★ 绝对路径（即使指向仓库内）同样被拒",
        abs_err is not None and abs_err.code == "out-of-scope-write")

try:
    s4.path_of("", write=True)
    empty_err = None
except scope.StoreScopeError as exc:
    empty_err = exc
c.check("空路径被结构化拒绝（不是静默当成库根）",
        empty_err is not None and empty_err.code == "empty-path")

# 库内的合法相对路径应当可用，且落在库根内
ok_path = s4.path_of("archive/x.json", write=True)
c.check("库内相对路径可解析且落在库根内",
        scope.within(ok_path, s4.root()))
c.check("库内路径在两侧仓库之外（测试临时根也在仓库里 ⇒ 这只证明判据在算）",
        scope.repo_of(os.path.join(s4.root(), "archive")) is not None)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[3] M1 验收②的**硬化**：库根本身也不许在仓库里（不许默认值好看、一改就没）")
print("=" * 74)

for repo in (scope.REPO_BACKEND, scope.REPO_FRONTEND, scope.REPO_INTEGRATION):
    bad_root = os.path.join(repo, ".tmp", "p21-bad-root")
    try:
        scope.assert_outside_repos(bad_root)
        root_err = None
    except scope.StoreScopeError as exc:
        root_err = exc
    c.check(f"★ 库根指向 {os.path.basename(repo)} ⇒ 结构化拒绝",
            root_err is not None and root_err.code == "store-root-inside-repo")
    if root_err is None:
        print(f"  FAIL  没有被拒: {bad_root}")

try:
    ContextStore(os.path.join(scope.REPO_BACKEND, ".tmp", "p21-store"))
    ctor_err = None
except scope.StoreScopeError as exc:
    ctor_err = exc
c.check("★ 构造函数也拦（不是只在工具函数里拦）",
        ctor_err is not None and ctor_err.code == "store-root-inside-repo")


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[4] M1 验收③：默认库根在**两侧仓库之外**（可机判）")
print("=" * 74)

default = scope.DEFAULT_ROOT
print(f"  默认库根: {default}")
print(f"  命中仓库: {scope.repo_of(default)}")
c.check("★ 默认库根是绝对路径", os.path.isabs(default))
c.check("★ 默认库根不在任何一侧仓库里", scope.repo_of(default) is None)
for repo in scope.FORBIDDEN_ROOTS:
    c.check(f"默认库根不是 {os.path.basename(repo)} 的后代",
            not scope.within(default, repo))
c.check("★ 三个被隔离的仓库都被列了出来（backend/frontend/integration）",
        len(scope.FORBIDDEN_ROOTS) == 3
        and all(r.startswith("D:\\PythonProject\\") for r in scope.FORBIDDEN_ROOTS))

os.environ[scope.ENV_STORE_ROOT] = os.path.join(ROOT, ".tmp", "p21-env-root")
try:
    env_err = None
    try:
        scope.default_root()
        scope.assert_outside_repos(scope.default_root())
    except scope.StoreScopeError as exc:
        env_err = exc
    c.check("★ 环境变量把库根指进仓库 ⇒ 同样被拒（隔离不能靠默认值）",
            env_err is not None and env_err.code == "store-root-inside-repo")
finally:
    os.environ.pop(scope.ENV_STORE_ROOT, None)

c.check("去掉环境变量后默认根恢复（且仍在仓库之外）",
        scope.default_root() == os.path.abspath(scope.DEFAULT_ROOT)
        and scope.repo_of(scope.default_root()) is None)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[5] M1 验收④：淘汰 = **归档**，不是删除（没有删除路径）")
print("=" * 74)

s5 = fresh_store()
keep = w(s5, "要归档的旧单元", source="old")
stay = w(s5, "还在用的单元", source="new")
arch = s5.archive(keep["id"])
print(f"  归档返回: {json.dumps(arch, ensure_ascii=False)[:160]}")
c.check("归档返回 status=archived + archive_path",
        arch["ok"] and arch["status"] == "archived" and arch["archive_path"])

after = s5.read(keep["id"])
c.check("★ 归档后**仍读得到原文**（淘汰不抹证据）",
        after["ok"] and after["unit"]["content"] == "要归档的旧单元")
c.check("★ 索引里留下 status=archived + archived_at",
        after["unit"]["status"] == "archived"
        and bool(after["unit"]["archived_at"]))
archive_file = os.path.join(s5.root(), arch["archive_path"])
c.check("★ 归档层真的有一份副本（物理留痕）",
        os.path.exists(archive_file)
        and json.load(open(archive_file, encoding="utf-8"))["id"] == keep["id"])
c.check("★ 计数分得开（active=1 / archived=1）",
        len(s5.list_units(include_archived=False)) == 1
        and len(s5.list_units(include_archived=True)) == 2)
c.check("★ 归档不删原件：再次归档是幂等的（already-archived）",
        s5.archive(keep["id"])["status"] == "already-archived")
c.check("★ 没有任何删除方法（delete/remove/purge/drop 都不存在）",
        not [m for m in dir(s5)
             if any(k in m.lower() for k in ("delete", "remove", "purge", "drop"))])
c.check("profile 明确写出 delete_path=None（可机判的没有删除路径）",
        s5.profile()["delete_path"] is None
        and s5.profile()["archive_is_not_delete"] is True)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[6] 第二路召回：挂在结构索引上（**不是**另起关键词库）")
print("=" * 74)

s6 = fresh_store()
# 三个单元：只有 B 的「符号引用」能召回它 —— 关键词与正文都召不回
a_id = w(s6, "候选插件被否决了", source="A",
         keywords=["candidate"])["id"]
b_id = w(s6, "占位说明（真正的线索在结构引用里）", source="B",
         symbols=["obstacle_generator.generate_obstacles"])["id"]
d_id = w(s6, "无关的日志清理脚本", source="D", keywords=["cleanup"])["id"]

kw_only = s6.recall(query="candidate")
sym_only = s6.recall(symbols=["obstacle_generator.generate_obstacles"])
print(f"  关键词路: {[r['id'] for r in kw_only['results']]}")
print(f"  符号路  : {[r['id'] for r in sym_only['results']]}  paths={sym_only['paths']}")
c.check("关键词路召回了 A、**召不回** B（这就是它的盲点）",
        [r["id"] for r in kw_only["results"]] == [a_id])
c.check("★ 符号路召回了 B（第二路召回**真的有牙**，不是空转）",
        [r["id"] for r in sym_only["results"]] == [b_id])
c.check("★ 召回结果如实写出走了哪一路",
        sym_only["results"][0]["paths"] == ["symbol"]
        and kw_only["results"][0]["paths"] == ["keyword"])
c.check("★ 符号路给出结构索引查询原料（find_symbol/get_module/get_architecture）",
        sym_only["results"][0]["structure_lookup"]["symbols"]
        == ["obstacle_generator.generate_obstacles"]
        and "find_symbol" in sym_only["results"][0]["structure_lookup"]["via"])
c.check("无关单元（D）两路都没被召回（不是一律全召）",
        d_id not in [r["id"] for r in sym_only["results"]])

# 两路都命中 ⇒ paths 各写各的（融合是合并，不是取其一）
both = s6.recall(query="candidate", symbols=["obstacle_generator.generate_obstacles"])
paths = {tuple(r["paths"]) for r in both["results"]}
c.check("★ 两路独立命中后合并（paths 同时出现 keyword 与 symbol）",
        ("keyword",) in paths and ("symbol",) in paths)

# 时间 / 来源过滤（用户原话："按对话时间/关键词分区"）
s7 = fresh_store()
old = w(s7, "旧的记忆", source="S", created_at="2026-01-01T00:00:00")["id"]
new = w(s7, "新的记忆", source="S", created_at="2026-10-01T00:00:00")["id"]
time_hit = s7.recall(query="记忆", since="2026-06-01T00:00:00")
c.check("★ 时间分区生效（since 之后只剩新的那条）",
        [r["id"] for r in time_hit["results"]] == [new])
c.check("按来源过滤生效", [r["id"] for r in s7.recall(query="记忆", source="S")["results"]]
        == [old, new]
        and s7.recall(query="记忆", source="无此来源")["results"] == [])
c.check("★ s7 的两个单元都是 active ⇒ 默认召回把它们都算进来（不是空转）",
        len(s7.recall(query="记忆")["results"]) == 2)
s7.archive(old)
c.check("★ include_archived=False 时归档单元不出现在召回里",
        old not in [r["id"] for r in s7.recall(query="记忆")["results"]])
c.check("include_archived=True 时归档单元仍召得回来（归档 ≠ 删除）",
        old in [r["id"] for r in s7.recall(query="记忆", include_archived=True)["results"]])


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[7] 硬要求③：阈值第一阶段**不许定死** —— 只记分、不决策")
print("=" * 74)

s8 = fresh_store()
ids = [w(s8, f"记忆单元 {i} 关于 auth_token 与 login 的说明", source="S",
         keywords=["auth", "login"] if i % 2 == 0 else ["cleanup"])["id"]
       for i in range(6)]
res = s8.recall(query="auth login")
print(f"  召回 {len(res['results'])} 条，分数分布 "
      f"min={res['scores']['min']} max={res['scores']['max']}")
c.check("★ recall() 没有阈值参数（阈值还没定，不许拍）",
        "threshold" not in inspect.signature(s8.recall).parameters)
c.check("★ 返回**全部**带分数的候选，不做阈值过滤",
        len(res["results"]) == len(ids))
c.check("★ 每条候选都带分数 + 分数构成（供 M2 落盘校准）",
        all(isinstance(r["score"], float) and "score_parts" in r
            for r in res["results"]))
c.check("★ 结果自带 threshold=None / decision=none（自陈没决策）",
        res["threshold"] is None and res["decision"] == "none")
c.check("排序确定性：(-score, id)", res["results"] == sorted(
    res["results"], key=lambda r: (-r["score"], str(r["id"]))))
c.check("契约面 describe() 明写 threshold=None / decision=none",
        s8.profile()["recall"]["threshold"] is None
        and s8.profile()["recall"]["decision"].startswith("none"))
c.check("两路召回的权重是**公开常量**（M2 校准时只改一处）",
        s8.profile()["recall"]["weights"] == {"keyword": 0.5, "symbol": 0.4})
c.check("第二路召回自陈没有新建关键词库",
        s8.profile()["recall"]["paths"]["symbol"]["new_keyword_library"] is False)


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[8] 硬要求①：判据覆盖**漏召 / 误召**（不是只看调用成功）")
print("=" * 74)

s9 = fresh_store()
A = w(s9, "reuse 层把 app.route 判成不存在符号", source="T9",
      keywords=["reuse", "false-positive"], symbols=["app.route"])["id"]
B = w(s9, "占位说明", source="T9b", symbols=["build_index_report"])["id"]
D = w(s9, "无关的清理脚本", source="D", keywords=["cleanup"])["id"]

q1 = s9.recall(query="reuse false-positive")
q2 = s9.recall(symbols=["build_index_report"])
q3 = s9.recall(query="cleanup")
q4 = s9.recall(symbols=["no_such_symbol_anywhere"])

report = s9.calibrate([
    {"id": "q1-关键词命中", "relevant": [A], "result": q1},
    {"id": "q2-符号路命中", "relevant": [B], "result": q2},
    {"id": "q3-误召（相关的是 A，不是 D）", "relevant": [A], "result": q3},
    {"id": "q4-漏召（库里有 A，查询召不回）", "relevant": [A], "result": q4},
])
print(f"  totals: {json.dumps(report['totals'], ensure_ascii=False)}")
by_id = {c_["id"]: c_ for c_ in report["cases"]}
c.check("★ 漏召被机械读出来（q4 的 missed 含 A 的 id）",
        A in by_id["q4-漏召（库里有 A，查询召不回）"]["missed"]
        and "miss" in by_id["q4-漏召（库里有 A，查询召不回）"]["failures"])
c.check("★ 误召被机械读出来（q3 的 false_recalled 含 D 的 id）",
        D in by_id["q3-误召（相关的是 A，不是 D）"]["false_recalled"]
        and "false-recall" in by_id["q3-误召（相关的是 A，不是 D）"]["failures"])
c.check("★ 真的命中的两问没有被冤枉（failures 为空）",
        not by_id["q1-关键词命中"]["failures"]
        and not by_id["q2-符号路命中"]["failures"])
c.check("漏召率 / 误召率都有读数（可当门禁）",
        report["totals"]["miss_rate"] is not None
        and report["totals"]["false_recall_rate"] is not None)
c.check("★ 候选阈值曲线只给数据，**不推荐阈值**",
        report["recommended_threshold"] is None
        and len(report["threshold_curve"]) > 0)
c.check("曲线随阈值给出 precision/recall/F1 的形状",
        all({"threshold", "precision", "recall", "f1"} <= set(p)
            for p in report["threshold_curve"]))


# ---------------------------------------------------------------------------
print("\n" + "=" * 74)
print("[9] 不接模型是判据：M1 包不 import 主链路、不注册成工具")
print("=" * 74)

pkg_dir = os.path.join(ROOT, "core", "context_store")
imports: list[str] = []
for fname in sorted(os.listdir(pkg_dir)):
    if not fname.endswith(".py"):
        continue
    tree = ast.parse(open(os.path.join(pkg_dir, fname), encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            # 相对导入（level>0）**只许指向本包自己** —— 这是"独立库"的判据之一
            imports.append("." * (node.level or 0) + (node.module or ""))
print(f"  core/context_store 的 import: {sorted(set(imports))}")

STDLIB = {"__future__", "hashlib", "json", "math", "os", "re", "datetime"}
external = sorted({m for m in imports
                   if m and not m.startswith(".")
                   and m.split(".")[0] not in STDLIB})
relative = sorted({m for m in imports if m.startswith(".")})
self_only = all(m in (".", ".store", ".retrieval", ".scope", ".units")
                for m in relative)
c.check("★ 不 import 任何主链路模块（core.* / tools.*）", not external)
c.check("★ 只用标准库（无新依赖 ⇒ 没有把环境改掉）", not external)
c.check("★ 相对导入只指向本包自己（独立库，不反向依赖主链路）", self_only)

from tools import TOOLS_MAP  # noqa: E402

c.check("★ 没有把记忆库注册成工具（工具数仍是 18）", len(TOOLS_MAP) == 18)
c.check("ContextStore 也没有 @register 装饰器",
        "register" not in open(os.path.join(pkg_dir, "store.py"),
                               encoding="utf-8").read())

# main.py 未动：M1 不进主链路
main_src = open(os.path.join(ROOT, "main.py"), encoding="utf-8").read()
c.check("★ main.py 未引用 context_store（M1 不接入）",
        "context_store" not in main_src)
profile = s8.profile()
c.check("★ profile() 自陈未接主链路 + 阶段是 M1",
        profile["wired_into_main_chain"] is False and profile["phase"] == "M1")

c.check("包级 describe() 同时给出根/召回/归档/下一期",
        set(["root", "recall", "units", "archival", "next_phases"])
        <= set(__import__("core.context_store", fromlist=["describe"]).describe()))


# ---------------------------------------------------------------------------
cleanup()
print()
raise SystemExit(c.report())
