"""端到端自检：起一次演示运行，用 SSE 收完整条事件流。

这是「前端能不能动起来」的最小可验证单元——它验证的正是浏览器要走的那条路：
    POST /api/runs  →  立刻拿到 run_id（不阻塞）
    GET  /api/runs/{id}/stream  →  逐条推进事件，直到服务端 close

在仓库根目录执行（需要后端已在 8000 端口运行）：
    python -m uvicorn main:app --host 127.0.0.1 --port 8000   # 另开一个终端
    python tests/diagnostics/check_webui_stream.py

用环境变量 AGENT_BASE 覆盖后端地址（例如换成局域网 IP）。
"""

import json
import os
import sys
import time

import httpx

# 结果里有中文（`通过 17/17`）。不钉住编码时，**被别的程序捕获**输出会按
# 控制台代码页（本机 GBK）解码 → 变成乱码 → 调用方的正则匹配不到，
# 于是"验证结果"被记成"未识别输出"。
# 实测踩到：`backup.ps1` 的备份前验证就是这么读到乱码的。
# errors="replace" 是兜底：老终端只退化显示，不抛异常。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

BASE = os.getenv("AGENT_BASE", "http://127.0.0.1:8000")


def main() -> int:
    checks: list[tuple[str, bool]] = []

    with httpx.Client(base_url=BASE, timeout=30.0) as c:
        health = c.get("/api/health")
        print(f"[health] {health.status_code} {health.json()}")
        checks.append(("GET /api/health 200", health.status_code == 200))

        index = c.get("/app/")
        checks.append(("SPA /app/ 可访问", index.status_code == 200 and "<div id=\"app\">" in index.text))
        print(f"[spa] {index.status_code} len={len(index.text)}")

        t0 = time.time()
        started = c.post("/api/runs", json={
            "goal": "端到端自检：演示运行",
            "demo": True,
            "max_attempts": 2,
        })
        checks.append(("POST /api/runs 立即返回", started.status_code == 200))
        elapsed = time.time() - t0
        checks.append((f"未阻塞（{elapsed:.2f}s < 1.5s）", elapsed < 1.5))
        run_id = started.json()["run"]["run_id"]
        print(f"[run] {run_id}  发起耗时 {elapsed*1000:.0f}ms")

        kinds: list[str] = []
        phases: list[str] = []
        frames = 0
        t_start = time.time()
        closed = False

        with c.stream("GET", f"/api/runs/{run_id}/stream") as r:
            checks.append(("SSE 200", r.status_code == 200))
            checks.append(("SSE content-type",
                           r.headers.get("content-type", "").startswith("text/event-stream")))
            event = "message"
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = json.loads(line.split(":", 1)[1].strip())
                    frames += 1
                    if event == "open":
                        print(f"[sse] open resumed_after={data.get('resumed_after')}")
                        continue
                    if event == "close":
                        closed = True
                        print(f"[sse] close status={data.get('status')} 用时 {time.time()-t_start:.1f}s")
                        break
                    kinds.append(data["kind"])
                    if data["kind"] == "phase":
                        phases.append(data["phase"])
                if frames > 400:
                    break

        print(f"[sse] 收到 {len(kinds)} 条事件")

        checks.append(("事件流有内容", len(kinds) >= 20))
        checks.append(("包含 phase 事件", len(phases) >= 5))
        checks.append(("包含工具调用", "tool_call" in kinds))
        checks.append(("包含重试/回退", "retry" in kinds and "rollback" in kinds))
        checks.append(("包含 manifest 门禁", "manifest" in kinds))
        checks.append(("包含 verify", "verify" in kinds))
        checks.append(("服务端主动 close", closed))
        checks.append((
            "阶段顺序合法",
            phases[:5] == ["plan", "write", "failed", "plan", "write"],
        ))

        detail = c.get(f"/api/runs/{run_id}").json()["run"]
        print(f"[run] 终态={detail['status']} 尝试={detail['attempts']} 文件={detail['touched_files']}")
        checks.append(("运行终态为 passed", detail["status"] == "passed"))

        # 断线续传：从中间续订，不应重复也不应漏
        ev = c.get(f"/api/runs/{run_id}/events?after=10").json()
        seqs = [e["seq"] for e in ev["events"]]
        checks.append(("按 seq 续订生效", bool(seqs) and min(seqs) > 10))

        replay = c.get(f"/api/runs/{run_id}/events").json()
        allseq = [e["seq"] for e in replay["events"]]
        checks.append(("seq 严格递增", allseq == sorted(set(allseq))))

    print("\n" + "=" * 70)
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failed = [n for n, ok in checks if not ok]
    print(f"\n通过 {len(checks) - len(failed)}/{len(checks)}")
    if failed:
        print("失败: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
