"""版本记录 `docs/VERSIONS.md`（架构清单 **A4**）。

纪律是**只增不改** —— 一个会静默改写历史的 bug 比没有记录更糟：
它会让"这一版当时验过没有"变成编出来的。所以追加逻辑住在可测的
Python 模块（`scripts/versions.py`）里，而不是埋在 PowerShell 字符串拼接里。

这个测试钉四件事：
  1. 追加后**只多一条**，旧条目**逐字未变**；
  2. 四样必填字段都在（标签与时间 / 改了什么 / 验证结果 / 还原点与命令）；
  3. 缺失字段如实写"未记录"，**不编**；
  4. 最新在上（读版本记录的人先看到最新的）。

运行：python tests/unit/test_versions.py
"""

import io
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401

sys.path.insert(0, os.path.join(ROOT, "scripts"))
import versions  # noqa: E402

checks: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))


def tmpfile() -> str:
    fd, p = tempfile.mkstemp(prefix="sa2_versions_", suffix=".md")
    os.close(fd)
    os.unlink(p)          # 让它先不存在，走"首次创建"的分支
    return p


# ============================================================
print("=" * 74)
print("[1] 首次创建：带头部，且头部说明了纪律")
print("=" * 74)
p = tmpfile()
e1 = versions.append_entry(
    p, label="v1", snapshot="20260101-000000_v1", note="第一版",
    verify="单测 10/10", diff="—（第一个）", created_at="2026-01-01 00:00:00",
)
check("文件被创建", os.path.isfile(p))
text = io.open(p, encoding="utf-8").read()
check("带头部（# 版本记录）", text.startswith("# 版本记录"))
check("★ 头部写明「只增不改」", "只增不改" in text)
check("★ 头部写明由 backup.ps1 自动追加（不许手改）",
      "backup.ps1" in text and "请勿手改" in text)
check("★ 头部说明「改了什么」来自机械 diff（不是人写的总结）",
      "机械" in text and "Verify" in text)
check("头部交代了起点（不追溯补写）", "不追溯" in text)
check("条目编号为 1 条", len(versions.entries(p)) == 1, str(len(versions.entries(p))))


# ============================================================
print("\n" + "=" * 74)
print("[2] ★ 只增不改：追加一条后，旧条目逐字未变")
print("=" * 74)
before_entries = dict(versions.entries(p))
before_text = io.open(p, encoding="utf-8").read()

versions.append_entry(
    p, label="v2", snapshot="20260102-000000_v2", note="第二版",
    verify="单测 12/12", diff="3 改动 / 1 新增", baseline="20260101-000000_v1",
    changed_files=["~ bridge/a.py", "+ bridge/b.py"],
    created_at="2026-01-02 00:00:00",
)
after_entries = dict(versions.entries(p))
after_text = io.open(p, encoding="utf-8").read()

check("★ 条目数 +1", len(after_entries) == len(before_entries) + 1,
      f"{len(before_entries)} → {len(after_entries)}")
check("★ 旧条目**逐字未变**",
      all(after_entries.get(k) == v for k, v in before_entries.items()),
      str([k for k, v in before_entries.items() if after_entries.get(k) != v]))
check("★ 头部也逐字未变",
      versions.split_header(before_text)[0] == versions.split_header(after_text)[0])
check("★ 旧条目的编号/时间也没被改写（不是重新渲染）",
      "2026-01-01 00:00:00" in after_entries["v1"])

# 再来一次，验证多次追加同样安全
versions.append_entry(p, label="v3", snapshot="20260103-000000_v3",
                      created_at="2026-01-03 00:00:00")
e = versions.entries(p)
check("★ 连续追加 3 次 = 3 条", len(e) == 3, str(len(e)))
check("★ 最新在上（读的人先看到最新版）", e[0][0] == "v3", str([k for k, _ in e]))
check("最旧在末", e[-1][0] == "v1", str([k for k, _ in e]))
check("★ 顺序稳定：再追加不改变已有顺序",
      [k for k, _ in versions.entries(p)] == ["v3", "v2", "v1"])


# ============================================================
print("\n" + "=" * 74)
print("[3] 四样必填字段（A4 验收）")
print("=" * 74)
v2 = after_entries["v2"]
check("① 标签与时间", "`v2` · 2026-01-02 00:00:00" in v2, v2.splitlines()[0])
check("② 还原点", "| 还原点 | `20260102-000000_v2` |" in v2)
check("③ 验证结果", "| 验证结果 | 单测 12/12 |" in v2)
check("④ 改了什么（机械 diff）", "| 改了什么 | 3 改动 / 1 新增 |" in v2)
check("对比基准也记了（否则看不懂 diff 是跟谁比）",
      "| 对比基准 | `20260101-000000_v1` |" in v2)
check("改动清单被列出", "~ bridge/a.py" in v2 and "+ bridge/b.py" in v2)
check("还原命令给全（Verify + Restore 各一条）",
      "-Verify  -From 20260102-000000_v2" in v2
      and "-Restore -From 20260102-000000_v2" in v2)


# ============================================================
print("\n" + "=" * 74)
print("[4] 字段缺失时如实写「未记录」—— 不编")
print("=" * 74)
p2 = tmpfile()
versions.append_entry(p2, label="bare", snapshot="snap", created_at="2026-01-01 00:00:00")
bare = versions.entries(p2)[0][1]
check("★ 验证结果缺失 → 写「未记录」", "—（未记录）" in bare, bare[:40])
check("★ 改了什么缺失 → 也写「未记录」", bare.count("—（未记录）") >= 2,
      str(bare.count("—（未记录）")))
check("★ 没填 -Note 时提示下次填（不是留空）",
      "未填 `-Note`" in bare, "提示语应在")
check("还原命令仍然给全（缺失字段不影响它）",
      "-Restore -From snap" in bare)


# ============================================================
print("\n" + "=" * 74)
print("[5] 仓库里那份真实文件：存在、被登记、格式合规")
print("=" * 74)
real = os.path.join(ROOT, "docs", "VERSIONS.md")
check("docs/VERSIONS.md 存在", os.path.isfile(real))
if os.path.isfile(real):
    rt = io.open(real, encoding="utf-8").read()
    check("★ 真实文件也声明了只增不改", "只增不改" in rt)
    check("真实文件交代了不追溯补写的理由", "不追溯" in rt, "凭记忆补出来的记录不是记录")
    got = versions.entries(real)
    check("真实文件至少有一条（起点条目）", len(got) >= 1, str(len(got)))
    for label, body in got:
        for field in ("还原点", "验证结果", "改了什么"):
            check(f"真实条目 `{label}` 有「{field}」", f"| {field} |" in body)
    readme = io.open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    check("★ README 登记了 docs/VERSIONS.md", "docs/VERSIONS.md" in readme)
    ops = io.open(os.path.join(ROOT, "docs", "OPERATIONS.md"), encoding="utf-8").read()
    check("★ OPERATIONS 备份章节提到 VERSIONS.md（否则没人知道它会自动追加）",
          "VERSIONS.md" in ops)


# ============================================================
print("\n" + "=" * 74)
print("断言检查")
print("=" * 74)
failed = [n for n, ok in checks if not ok]
print(f"通过 {len(checks) - len(failed)}/{len(checks)}")
if failed:
    print("失败: " + "; ".join(failed))
raise SystemExit(1 if failed else 0)
