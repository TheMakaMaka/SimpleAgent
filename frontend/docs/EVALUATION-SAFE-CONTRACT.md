# 变更评估文档 · `EVAL-SAFE-CONTRACT`（`_safe` 的契约）

- **变更编号**：`EVAL-SAFE-CONTRACT`（工作单建议名；也可叫 `HOOKS-SAFE`）
- **提出方**：统筹方（`DISPATCH.md`，契约 **v1.0.28**）—— 本轮起因为
  「`_safe` 没有兜住任何东西」，且**我自己的评估文档写了它做不到的事**
- **执行侧**：frontend（`SimpleAgent2_Cycle_VueWeb` 的 `bridge/` + 测试；**前端一行未动**）
- **日期**：2026-09-28
- **契约版本**：`1.0.28`（镜像与主本 SHA256 一致）

---

## 1. 变更意图

> 引指令原文：

> 🔴 本轮只有一件事：**【`_safe` 没有兜住任何东西】**
>
> `bridge/hooks.py` 抬头**明确承诺**：
> > **全部失败都不影响上游**：每个包装都兜住自己的异常，进度坏掉不能让 cycle 失败。
> > 唯一的例外是 `RunCancelled`（协作式取消），它继承 `BaseException`，故意穿出去。
>
> **而这个承诺没有被实现** —— `_safe` 是：
>
> ```python
> try:
>     return fn(*args, **kwargs)
> except BaseException:   # 注释：RunCancelled 要穿出去，见 progress.py
>     raise               # ← 它把所有异常都截走并**重抛**了
> except Exception:       # ← **永远走不到**（死代码）
>     return None
> ```
>
> **实测**（我这一侧的门禁做的行为判据）：`_safe(lambda: 1/0)` → 抛出了 `ZeroDivisionError`
>
> 要做的：① `_safe` 只放行 `RunCancelled`；② 把 `worker_cls()` 的求值**也纳入保护**；
> ③ **加一条会红的测试**（普通异常被吞 / `RunCancelled` 仍穿出）；
> ④ 顺手修两处：`test_hook_compat.py:405` 的**硬编码 `True` 空洞断言**；
> `worker_cls()` 纳入 `undefined_globals` 的覆盖。
>
> **验收**：1. `hook-compat.py` 全绿（新增判据 **H** 行为 / **I** 结构）；
> **2. 并且真的跑一次任务照样能过** —— **"修好 A 弄坏 B"的常见形态**。

---

## 2. 问题陈述与复现方式（对应 C1）

### 2.1 位置（改前）

```python
# bridge/hooks.py:48-55（改前）
def _safe(fn, *args, **kwargs):
    """挂钩内部一律走这里：进度出问题绝不能影响上游执行。"""
    try:
        return fn(*args, **kwargs)
    except BaseException:  # RunCancelled 要穿出去，见 progress.py
        raise
    except Exception:      # ← 死代码：上面那条已经把 Exception 也截走了
        return None
```

**复现命令**（离线）：

```powershell
python tests/unit/test_hook_compat.py        # [8] 段
python -c "from bridge import hooks; print(hooks._safe(lambda: 1/0))"
```

改前实测：抛 `ZeroDivisionError`（**不是** `None`）。

### 2.2 为什么这不是"少挡一个异常"

| 后果 | 说明 |
|---|---|
| **挂钩自身的 bug 会杀掉整轮运行** | `emit_progress` 撞上意外 payload、`preview_args` 遇到没料到的类型 —— 都会让用户看到 `status=error` |
| **而那与"模型做不出来"长得一模一样** | ⇒ **污染能力画像**（正是四值结局里 `invalid` 要解决的问题） |
| **它让人以为这一层已经包住了** | 我的 `EVALUATION-HOOKS-PASSTHROUGH-2.md` §35.3 写着"解析失败由 `_safe` 兜住"——**代码没有兜住**。这是又一次 **U- 类（声明 vs 实现不符）**，而方向是危险的 |

### 2.3 同一类的第二处：**参数在进 `_safe` 之前求值**

```python
args = _safe(worker_cls()._parse_args, arguments_json)
#            ^^^^^^^^^^^^ 在 _safe **之外**求值 ⇒ 取类失败照样炸穿
```

**这条不止一处**。全量扫了一遍 `_safe(emit_progress, …)` 的调用点，凡**实参里带函数调用**的
都在保护之外 —— 其中最容易炸的就是这几处：

| 位置 | 保护之外的表达式 | 会怎么炸 |
|---|---|---|
| `_around_invoke` | `preview_args(name, args)` | 参数类型没料到（例如 `args` 不是 dict） |
| `_around_run_verify` | `command.label()` | 伪命令对象上没有 `label`，或它自己抛 |
| `_around_enter` | `list(getattr(report, "transitions", None) or [])` | `transitions` 不是可迭代对象 |
| `_around_artifacts` | `list(paths or [])` | 同上 |
| `_around_worker_run` | `list(getattr(task, "tool_hint", None) or [])` | 同上 |

**所以修法不是"把 `worker_cls()` 挪进去"，而是让"构造 payload + 播报"整条都在保护内。**

### 2.4 改这个写法**差点弄坏另一处**：扫描器只认旧写法（**我自己的门禁抓到的**）

`emit_progress` 的"kind 在哪"有**两个** AST 扫描器：

| 扫描器 | 用途 |
|---|---|
| `bridge/spec.py` 的 `_scan_calls()` | `/api/spec` 的事件分区（`uncalibrated_events` / 契约测试靠它） |
| `tests/unit/test_event_contract.py` 的 `scan_kinds()` | "后端发的，前端必须认"那条门禁 |

它们原本只认 `emit_progress("kind", …)` 与 `_safe(emit_progress, "kind", …)`。
我改成 `emit_safe("kind", _build, …)` 之后 —— **两个扫描器都看不见那 5 个事件了**：

```
bridge 侧认到 0 个（改之前是 21 个）；总数 39 → 34
```

**它不报错、只是少认** —— 这类"静默少显示"正是本仓库最怕的失效。
**是我自己的门禁抓到的**（`test_partition` / `test_spec` / `test_event_contract` 三个同时红）。

修法：两个扫描器都学会第三种写法（`emit_safe(kind, build, *args)`），
并新增一条判据（`test_hook_compat.py` **[9]**）：
**hooks.py 里每一个 emit 调用点，扫描器都必须认得**（当前 16 ↔ 16），
外加 5 个"最容易漏"的 kind 作为金丝雀。

> 这条与 §2.3 是同一类：**"我改了一处，别处的隐含依赖被我弄坏了"**。
> 区别是这次**在门禁上就红了**，而不是等用户跑六秒才发现。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260928-212704_v19-p5b-hook-globals
```

<!-- MECHANICAL-DIFF -->
```
[改动] 13
   ~ bridge\hooks.py
   ~ bridge\spec.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\EVALUATION-HOOKS-PASSTHROUGH-2.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ README.md
   ~ tests\diagnostics\hook_verify_e2e.py
   ~ tests\unit\test_event_contract.py
   ~ tests\unit\test_hook_compat.py
[新增] 1
   + docs\EVALUATION-SAFE-CONTRACT.md

改动合计 14 个文件。
```

> 两条要说明的：
> 1. **`bridge/spec.py` 与 `tests/unit/test_event_contract.py` 在清单里**，
>    是因为它们是 §2.4 那个"扫描器只认旧写法"的修复 —— **本轮改动的一部分**，
>    不是顺手夹带。
> 2. **那次真实运行的运行数据不在清单里**：`data/` 是运行态目录（`docs/LAYOUT.md`），
>    刻意不进快照。证据是 **run_id + 结局 + 事件序**（§4.3 贴了原文），
>    并且已复制进 `data/storage_data/runs/run_20260928_221959_80417d/`，**可在界面上打开**。

**手写导读（非判据）**

| # | 文件 | 为什么改 |
|---|---|---|
| 1 | `bridge/hooks.py` | ① `_safe` 只放行 `RunCancelled`；② 新增 `parse_worker_args()`（取类在**内层**）；③ 新增 `emit_safe(kind, build, *args)` —— **payload 构造也在保护内**，并把 5 处"实参里带调用"的 emit 改成 `emit_safe`；④ `from .progress import RunCancelled` |
| 2 | `tests/unit/test_hook_compat.py` | **[8] `_safe` 的契约**（行为 5 条 + 结构 2 条 + **负向**：旧形态必须判红）；修掉 [7] 里那处**硬编码 `True`** 的空洞断言；`worker_cls()` 失败路径纳入覆盖 |
| 3 | `tests/diagnostics/hook_verify_e2e.py` | 新增 **[B] 故意注入异常**场景：挂钩里抛错 ⇒ **整轮运行照样跑完并走到 verify**，且代价可见（那一条事件确实缺了） |
| 4 | `docs/CHANGELOG.md` §36 · `docs/MODULES.md` §20.2 · `README.md` | 记录根因、两条纪律与新门禁 |

---

## 4. 主张与验证命令（对应 C2、C3）

### 4.1 改前 → 改后（就是那一处）

```diff
 def _safe(fn, *args, **kwargs):
-    """挂钩内部一律走这里：进度出问题绝不能影响上游执行。"""
+    """挂钩内部一律走这里：**进度与挂钩自身的毛病绝不能影响上游执行**。
+    ★ 只放行 `RunCancelled`（协作式取消，刻意继承 `BaseException`）。"""
     try:
         return fn(*args, **kwargs)
-    except BaseException:  # RunCancelled 要穿出去，见 progress.py
+    except RunCancelled:
+        raise               # 取消必须穿出去，否则「取消」就失效了
+    except Exception:
+        return None         # 其余一律吞掉：挂钩是旁路，坏掉不能拖垮 cycle
-    except Exception:      # ← 死代码
-        return None
```

```diff
+ def parse_worker_args(arguments_json):
+     """取 `Worker` 类并解析工具参数 —— **整条**都在 `_safe` 的保护范围内。"""
+     return worker_cls()._parse_args(arguments_json)
+
+ def emit_safe(event_kind: str, build, *args):
+     """播报一条事件，**payload 的构造也在保护范围内**。"""
+     return _safe(lambda: emit_progress(event_kind, **build(*args)))
```

并把这 5 处的 payload 构造搬进内层函数：
`phase`（`transitions`）/ `files`（`touched`）/ `task_start`（`tool_hint`）/
`tool_call`（`preview_args`）/ `verify_probe`（`command.label()`）。

### 4.2 判据 H（行为）：普通异常被吞 / `RunCancelled` 仍穿出

```powershell
python tests/unit/test_hook_compat.py            # [8] 段
```

实测（原文）：

```
[8] ★ `_safe` 的契约：**普通异常必须被吞、`RunCancelled` 必须穿出去**
  PASS  ★ 普通异常被吞掉（返回 None）
  PASS  ★ 自定义异常同样被吞
  PASS  ★ 正常返回值照旧透出（不是把成功也吞了）
  PASS  ★★ `RunCancelled` **仍然穿出去**（否则「取消」就失效了）
  PASS  ★ `KeyboardInterrupt` 也穿出去（它不是 `Exception`）
  PASS  ★ 结构：`_safe` 里没有 `except BaseException`（那会把所有异常重抛）
  PASS  ★ 结构：`_safe` 里确有 `except RunCancelled` 与 `except Exception`
  PASS  ★ 负向：旧形态（`except BaseException: raise`）**兜不住**普通异常
  PASS  ★ 「取类失败」也在 `_safe` 保护范围内（不炸穿）   None
  PASS  ★ 源码里调用点是 `_safe(parse_worker_args, …)`（取类在**内层**）
```

**判据 I（结构）的断言只看代码**：`_safe` 的 docstring 里引用着旧形态（那是说明），
所以用 `ast` 摘掉 docstring 再判 —— 打印出来的**代码**是：

```
'safe` 的**代码**（摘掉 docstring）：'try:\n    return fn(*args, **kwargs)\n
except RunCancelled:\n    raise\nexcept Exception:\n    return None'
```

### 4.3 ★★「修好 A 弄坏 B」的反面：真的跑一次任务**照样能过**

**真实运行**（临时实例指向真上游、真模型 `qwen2.5:7b`，端口 **8301** —— 注意是**重启后**的实例，
见 §6 的 freshness 判据）：

```
run_id  : run_20260928_221959_80417d
status  : passed        phase: record
touched : str_utils.py
verify  : passed=True   source=caller
verdict : {"outcome":"pass","criterion_source":"caller",
           "criterion_trust":"caller-authoritative","criterion_independent":true}
```

事件序完整（挂钩点一个不少）：

```
queued → run_start → baseline → cycle_start → attempt_start → phase → round_start
→ orchestrator_decision → task_start → worker_step → model_reply → tool_call → tool_result
→ worker_step → model_reply → task_done → verify_probe → orchestrator_round → verify_criterion
→ plan → task_result → decompose_review → phase → files → manifest → phase → reuse
→ syntax → lint → phase → verify → phase → cycle_end → self_report → run_end
```

（该运行已复制进 `data/storage_data/runs/`，可在界面上打开。）

### 4.4 ★★ 故意往挂钩里注入异常：**整轮运行照样跑完**

```powershell
$env:AGENT_BACKEND_DIR="D:\PythonProject\SimpleAgent2_Cycle"
python tests/diagnostics/hook_verify_e2e.py      # [B] 段
```

实测（原文）：

```
[B] 故意在挂钩里注入异常：**整轮运行必须照样跑完**
  phase=record · 异常=无
  PASS  ★★ 挂钩里的异常**没有**杀掉这一轮（cycle 跑完了）   None
  PASS  ★★ 而且它照样走到了 verify（坏掉的只是那一条事件）
  PASS  ★ 代价可见：`tool_call` 那一条事件确实**缺了**（不是静默假装成功）
  PASS  ★ 但流程本身照旧：run_start / task_start / cycle_end 都在
通过 12/12
```

**这是"承诺"与"实现"对上的证据**：注入 `preview_args` 抛 `TypeError` 之后，
`tool_call` **确实没发**（代价可见），而 `run_start → task_start → verify_probe → verify
→ cycle_end` 全在，`phase=record`、无异常。
改前这一注入会**杀掉整轮运行**（`status=error`，与"模型做不出来"同形）。

### 4.5 门禁与全量

| 检查 | 自带副本 | 真上游 |
|---|---|---|
| `tests/unit/test_hook_compat.py` | **39/39** | **42/42** |
| `tests/diagnostics/hook_verify_e2e.py` | 分流 SKIP「走到 verify」 | **12/12** |
| `tests/run_unit.py` | **38/38 文件，exit 0** | **38/38 文件，exit 0** |
| `bridge/spec` 的事件分区 | —— | **18 + 21 = 39**（`uncalibrated` / `dead` 均空） |
| `ruff --select F821 --ignore-noqa bridge/` | `All checks passed!` | 同 |
| 真实运行（真模型） | —— | **`passed`**（§4.3） |

`hook_verify_e2e.py` 在自带旧副本配置下按配置分流 SKIP「走到 verify」那几条
（那份副本的验证接线在 `FIX-VERIFY-WIRING` 之前），其余断言照跑。

### 4.6 未验证的部分

- **统筹方的 `hook-compat.py`（判据 H / I）与 `capability-run.py --only T1` 我跑不了**
  （没有执行入口）。我做了**等价判据 + 一次自己的真实运行**；**请以他那一次为准**。
- **`RunCancelled` 的"真取消"没有端到端跑过**：我只验了 `_safe` 对它的**语义**
  （穿出去）与它在 `progress.py` 里的定义；"取消一个正在跑的 cycle"没有构造。
- **`emit_safe` 的 5 处改造只验了 `tool_call` 那一处**（注入 `preview_args` 故障）；
  另外 4 处（`phase`/`files`/`task_start`/`verify_probe`）的**注入**没有逐个做。
- **自带旧副本配置下"走到 verify"仍是 SKIP**（不是失败）。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 |
|---|---|
| 事件 `kind` 名 / payload 键 | **否**（事件一个没变、键一个没改） |
| 上游 `PHASE_ORDER` / `CycleReport` / `Snapshot` / `TOOLS_MAP` | 否 |
| `CONTRACT_VERSION` / `SCHEMA_VERSION` / `SPEC_VERSION` | 否 |
| 端点路径 | 否 |
| `.interface_contract/` | 未改 |
| `bridge/hooks.py` 内部实现 | 改了（`_safe` 语义、`emit_safe` 与 `parse_worker_args` 两个内部函数）—— **不是契约面** |

**本轮零接口面改动。** 行为面的唯一变化：**挂钩自身的异常不再终结 cycle**
（代价是**那一条事件不发**，这是可见的、刻意选定的取舍）。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **上游需要改吗？不需要。** `RunCancelled` 由**本仓库**的 `progress.py` 定义，
  `_safe` 由**本仓库**实现 —— 这是纯内部契约。
- **有没有把问题平移**：没有。修法是**让本层真的兜住**，而不是"要求上游别抛"。
- **给统筹方的一条实用提示**（本轮我按它做了）：他那边的 `runtime-freshness.py`
  判据「**源码 mtime > 进程启动时间 ⇒ 该进程必定没加载这次改动**」
  ——**我改完 `hooks.py` 之后重启了实例**（并且上一版跑的是旧进程，我特意换到 8301 重跑）。
  这条判据值得保留成常驻巡检。
- **`_safe` 现在会吞掉"本来会暴露的 bug"吗？** 会 —— 所以配了**可见的代价**：
  那条事件不发（时间线上少一条），并且 `emit_safe`/`_safe` 的失败**不改变** cycle 结论。
  取舍理由写在 `_safe` 的 docstring 里：**"挂钩自身的 bug 让用户看到 `status=error`"
  比"少一条事件"危险得多**（前者污染能力画像）。

---

## 7. 不做的部分及理由（对应 C7）

1. **不把 `_safe` 的失败写进事件流**（例如发一条 `bridge_error` 事件）：
   那会在**错误处理路径上再引入一次播报**（可能再次出错），
   而且会与"事件词表 = 契约"冲突（新增 kind 要走契约）。**本轮零接口面改动**是刻意的。
2. **不修那 10 条 `F401/F841/F541`**（统筹方已同意不改）。
3. **不改前端**：本轮无前端面改动，`dist` 也无需重建（新鲜度仍 `ok`）。
4. **不逐个给 5 处 `emit_safe` 做注入测试**：做了最可能炸的一处（`preview_args`，
   它真的做类型相关逻辑），其余 4 处是 `list(...)`/`label()`，语义同构。
   这条限制写在 §4.6 里，不假装全做了。

---

## 8. 回退点（对应 C8）

- **回退命令**：

  ```powershell
  .\scripts\backup.ps1 -List   # 本版快照：20260928-223020_v20-safe-contract
  .\scripts\backup.ps1 -Restore -From 20260928-223020_v20-safe-contract
  ```

- **回退会丢什么**：`_safe` 的契约修正、`emit_safe`/`parse_worker_args`、
  `[8]` 与 `[B]` 两组门禁、以及文档。
- **回退的后果**：**挂钩自身的任何异常会再次终结整轮运行**
  （`status=error`，与"模型做不出来"同形）。**正常路径不受影响** ——
  也就是说回退**不会**让系统跑不起来，只会让"坏在挂钩里"这一类故障重新变得致命。
- **回退后必须做的事**：重启实例（freshness 判据）；确认 /app 与 `/api/health` 正常。

---

## 9. 自检结论

| # | 标准 | 结论 |
|---|---|---|
| **C1** | 问题陈述可复现 | **满足**：改前那一处 + `_safe(lambda: 1/0)` 的实测输出；并**全量扫出同类第二处**（参数在 `_safe` 之外求值，5 处） |
| **C2** | 每条主张带可复现验证命令 | **满足** |
| **C3** | 命令实测输出支持该主张 | **满足**：35/35 与 38/38、e2e 12/12、**真实运行 `passed`（run_20260928_221959_80417d）** |
| **C4** | 改动清单与实际一致 | **满足**：§3 以 `backup.ps1 -Verify` 的机械输出为权威 |
| **C5** | 对接口契约的影响已声明 | **满足**：§5 **零接口面改动**（行为面变化只有"挂钩异常不再终结 cycle"） |
| **C6** | 对另一侧的影响已评估 | **满足**：§6（纯内部契约；并说明"吞掉 bug"的取舍与可见代价） |
| **C7** | 未把接口级问题当内部问题处理 | **满足**：§7 列出不做的四件事与理由 |
| **C8** | 回退点明确 | **满足**：§8 并写明回退后果与"回退后要重启实例" |

**我希望统筹重点验证哪一条**：**判据 H 与 §4.4 的注入场景**。

- **判据 H**（行为）：请在你那一侧独立跑 —— 它同时要求"普通异常被吞"与
  "`RunCancelled` **仍穿出**"。**只验前者会把"取消"弄坏**，那正是这条判据存在的原因。
- **§4.4 的注入**：这是我这一侧能给的最强证据 —— **故意把挂钩弄坏，整轮运行照样跑完**，
  而且**代价可见**（那一条事件确实缺了）。
- 如果我把"兜底"写成了"什么都不报"（例如把 `RunCancelled` 也吞了），**请直接说这版不成立** ——
  我不会拿"测试全绿"顶过去：这一轮的起因恰恰是**我自己的文档写着做不到的事**。
