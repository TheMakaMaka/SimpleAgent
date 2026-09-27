"""fetch_url 的地址校验自检（安全回归）。

背景：曾经 `raise ValueError("禁止访问内网地址")` 写在 try 块内，
被同语句的 `except ValueError: pass` 吞掉，导致所有内网 IP 字面量全部放行。
这个测试锁住该回归，防止再次写坏。
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from _bootstrap import ROOT  # noqa: E402,F401  (把仓库根目录加入 sys.path)

from tools.net import _check_url  # noqa: E402

# (URL, 是否应被拒绝)
CASES = [
    # ---- 必须拒绝：内网 / 保留 / 回环 ----
    ("http://127.0.0.1/x", True),
    ("http://127.0.0.1:8000/x", True),
    ("http://localhost/x", True),
    ("http://LOCALHOST/x", True),
    ("http://localhost./x", True),
    ("http://foo.local/x", True),
    ("http://10.0.0.5/x", True),
    ("http://192.168.1.1/x", True),
    ("http://172.16.0.1/x", True),
    ("http://169.254.169.254/latest/meta-data/", True),   # 云元数据端点
    ("http://0.0.0.0/x", True),
    ("http://[::1]/x", True),                              # IPv6 回环
    ("http://[fe80::1]/x", True),                          # IPv6 link-local
    ("http://224.0.0.1/x", True),                          # 组播
    # ---- 必须允许：公网域名 / 公网 IP ----
    ("https://example.com/x", False),
    ("http://93.184.216.34/x", False),
    ("https://pypi.org/simple/", False),
    # ---- 必须拒绝：协议 ----
    ("file:///etc/passwd", True),
    ("ftp://example.com/x", True),
    ("gopher://example.com/x", True),
]


def main() -> int:
    print("=" * 72)
    print("fetch_url 地址校验")
    print("=" * 72)

    results: list[tuple[str, bool]] = []
    for url, should_block in CASES:
        try:
            _check_url(url)
            blocked = False
        except ValueError:
            blocked = True
        ok = blocked == should_block
        results.append((url, ok))
        verdict = "BLOCKED" if blocked else "ALLOWED"
        flag = "PASS" if ok else "FAIL"
        want = "应拒绝" if should_block else "应放行"
        print(f"  {flag}  {verdict:<8} ({want}) {url}")

    print("\n" + "=" * 72)
    print("关键回归项")
    print("=" * 72)
    checks = [
        ("127.0.0.1 被拦（原 bug）", _blocked("http://127.0.0.1/x")),
        ("10.0.0.5 被拦（原 bug）", _blocked("http://10.0.0.5/x")),
        ("169.254.169.254 被拦（原 bug）", _blocked("http://169.254.169.254/")),
        ("公网域名放行", not _blocked("https://example.com/")),
        ("公网 IP 放行", not _blocked("http://93.184.216.34/")),
        ("非 http(s) 被拦", _blocked("file:///etc/passwd")),
    ]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")

    failed = [n for n, ok in checks if not ok] + [u for u, ok in results if not ok]
    print(f"\n通过 {len(checks) - len([n for n, ok in checks if not ok])}/{len(checks)} 项关键检查")
    return 1 if failed else 0


def _blocked(url: str) -> bool:
    try:
        _check_url(url)
        return False
    except ValueError:
        return True


raise SystemExit(main())
