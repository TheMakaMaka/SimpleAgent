# 变更评估文档 · `D8-D9-D6`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收依据：统筹方 `DISPATCH.md`（2026-09-26 12:10，契约 **v1.0.19**）。
>
> **每个"主张"都跟一条可复现的命令。** 命令在仓库根执行，
> `$PY` = `.venv\Scripts\python.exe`。

---

- **变更编号**：`D8-D9-D6`（D8 阻塞 / D9 可选 / D6 建议做）
- **提出方**：统筹（D8 由后端先报、统筹逐环复核；D9 后端提出；D6 统筹建议）
- **执行侧**：frontend（本仓库）
- **日期**：2026-09-26
- **契约版本**：`1.0.19`

---

## 1. 变更意图

> 引原话，不转述。

**D8（阻塞）**：

> 后端把 `decision_opened` 的 payload 键 `kind` → `decision_kind` … 并称"前端未读该键"。
> **他们核漏了：前端是通过扁平化命名空间读的 `ev.kind`。**
> **要做的**：第 717 行改读 **`ev.decision_kind`**。

**D9（可选）**：

> 包装器**镜像了 `_emit` 的签名、位置参数就叫 `kind`** …
> **建议**：改为 `def _emit(self, *args, **kwargs)` 透传，不再镜像签名。

**D6（建议做）**：

> **但一次性对拍挡不住回归。** 而 A1a 的全部承诺就是"同一件事只有一个判据" ——
> **只有这个测试能守住那句话。**
> **建议写的测试**：构造同一跨侧不一致，**同时调 `/contract/check` 与 `/api/audit`**，
> 断言两者的 `code` / `owner` / `severity` / `verdict` 一致。

---

## 2. 问题陈述与复现方式（对应 C1）

**D8 的链条**（我逐环复现，不照抄）

```powershell
$PY -c "import io;t=io.open('bridge/runner.py',encoding='utf-8').read().splitlines();print(chr(10).join(t[74:83]))"
Select-String -Path frontend\src\store\run.ts -Pattern "decision_opened" -Context 0,6
$PY -c "import io,re;t=io.open(r'D:\PythonProject\SimpleAgent2_Cycle\core\coding_cycle.py',encoding='utf-8').read();m=re.search(r'_emit\(\s*\"decision_opened\".*?\)',t,re.S);print(' '.join(m.group(0).split()))"
```

**实际输出**

```
    def append(self, kind: str, **payload: Any) -> dict:
            record = {
                "seq": self._seq,
                "ts": _now(),
                "kind": kind,
                **payload,          ← payload 在 kind **之后**展开 → 同名键会覆盖它
            }

    case 'decision_opened': {
      state.decisions.unshift({
        id: String(ev.decision_id || ''),
        kind: String(ev.kind || ''),        ← 读错了：这是**事件类型**
```

**为什么这是问题**：`ev.kind` 现在是 `'decision_opened'`（事件类型），
于是**决策种类显示成事件名**。而这条路径此前**从未真正跑通过**
（上游那个 TypeError 让它发不出事件），所以它是**新近才可到达的代码**。

**顺带一层（统筹方没提，我核出来的）**：改名**同时修好了** `switch (kind)` ——
覆盖存在时 `ev.kind` 是决策种类，`case 'decision_opened'` **匹配不上**，
这个分支此前是**死的**。所以"从未跑通"比统筹方说的还多一层。

**D9 的复现**（改前会炸）

```powershell
$PY -c "import sys;sys.path.insert(0,'tests');from _bootstrap import ROOT;from bridge import hooks;from core.coding_cycle import CodingCycle;w=hooks.make_emit_wrapper(lambda self,event_kind,cycle_id,goal='',**p:None);print('ok')"
```

改前的形态是 `def _emit(self, kind, cycle_id, goal="", **payload)` ——
写 `_emit("x", cid, kind="y")` 即
`TypeError: got multiple values for argument 'kind'` → **整轮 run status=error**。

---

## 3. 拟改动清单（对应 C4）

> **先贴机械输出，它才是权威内容；下表只是"导读"。**
> 依据 `EVALUATION-TEMPLATE.md` §3 的修订（统筹方 2026-09-26 采纳本仓库提出的流程问题）。

**实际 diff（机械核对，本机无 git，用 `-Verify`）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-103118_v12-arch-d2
```

**实际输出**

```
[改动] 15
   ~ bridge\contract_vocab.py
   ~ bridge\hooks.py
   ~ bridge\progress.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ frontend\dist\index.html
   ~ frontend\src\store\run.ts
   ~ README.md
   ~ tests\_bootstrap.py
   ~ tests\unit\test_event_contract.py
   ~ tests\unit\test_isolation.py
[新增] 4
   + docs\EVALUATION-D8-D9-D6.md
   + frontend\dist\assets\index-CsUZBNxG.js
   + tests\unit\test_hooks_passthrough.py
   + tests\unit\test_two_entrypoints.py
[删除] 1
   - frontend\dist\assets\index-BY1HBqvb.js

改动合计 20 个文件。
```

> **第一次填这里是"12 改动"** —— 那是我**凭印象**写的，机械核对是 15。
> 差的 3 个是 `docs/VERSIONS.md`、`frontend/dist/index.html`、
> `docs/CHANGELOG.md`（写文档时又产生了改动）。
> **这就是"机械输出是权威、手写表只是导读"的现场例子** ——
> 连"我刚跑过一次 diff"的人也会记错，所以判据不能是记忆。

**导读（为什么改，不是改动范围）**

| # | 文件 | 为什么 |
|---|---|---|
| 1 | `frontend/src/store/run.ts` | **D8**：`ev.kind` → `ev.decision_kind` |
| 2 | `bridge/hooks.py` | **D9**：抽出 `make_emit_wrapper()`，按上游签名 `bind`，展开 VAR_KEYWORD |
| 3 | `bridge/progress.py` | **D9 连带**：首参 `kind` → `event_kind`（否则载荷里的 `kind` 在此层再撞名并被 `_safe` 吞掉） |
| 4 | `tests/unit/test_two_entrypoints.py` | **D6**：双入口对拍常驻化 |
| 5 | `tests/unit/test_hooks_passthrough.py` | D9 的行为断言（用不同签名的假上游直接调工厂） |
| 6 | `tests/_bootstrap.py` | **自查发现**：上游目录写死，不认 `AGENT_BACKEND_DIR` |
| 7 | `tests/unit/test_event_contract.py` | D8 的**跨语言**核对（后端发的键 ↔ 前端读的键）+ 全类检查 |
| 8 | `tests/unit/test_isolation.py` | 钉住 `_bootstrap.BACKEND == paths.BACKEND_DIR`；另两处判据纠正 |
| 9 | `bridge/contract_vocab.py` | 统筹方提的过期路标（注释里写契约 v1.0.1） |
| 10 | 5 个 `.md` | 同步文档（**每次都会漏，所以判据看上面机械输出**） |

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | D8：reducer 读 `ev.decision_kind` | `$PY tests\unit\test_event_contract.py` | 断言通过 | ✅ |
| 2 | D8：后端发 `decision_kind`（**跨语言对上**） | 同上（指向上游时） | `21/21` | ✅ |
| 3 | D8：全类检查——没有别的 `_emit(..., kind=…)` | 同上 | 0 处 | ✅ |
| 4 | D9：`kind=` 作为关键字不再 TypeError | `$PY tests\unit\test_hooks_passthrough.py` | `19/19` | ✅ |
| 5 | D9：载荷**完整**（`cycle_id` 不丢、VAR_KEYWORD 展开） | 同上 | 载荷含 `cycle_id`/`decision_id`/`kind` | ✅ |
| 6 | D9：事件名不取错（`decision_opened` 而非 payload 的 `kind`） | 同上 | ✅ | ✅ |
| 7 | D6：双入口 `owner`/`severity` 逐条一致 | `$PY tests\unit\test_two_entrypoints.py` | `16/16` | ✅ |
| 8 | D6：自带副本时按配置 **SKIP**（不是 FAIL） | 同上（默认配置） | 退出 0 | ✅ |
| 9 | 全量无回归（两种配置） | `$PY tests\run_unit.py` | `34/34` | ✅ |
| 10 | 前端类型 / 构建 | `npm run typecheck` / `npm run build` | 零错误 | ✅ |
| 11 | 统筹方契约测试 | `test_interface_contract.py --backend <port>` | `29/29` | ✅ |

**第 3 项的实测**

```
全类扫描 upstream core/coding_cycle.py 的每个 _emit(...)：
  含 kind= 实参的调用：0
```

**第 4/5/6 项的实测（节选）**

```
PASS  ★ `kind=` 作为关键字**不再抛 TypeError**   None
PASS  ★ 载荷完整：cycle_id 没被丢掉   {'cycle_id': 'cycle-1', 'goal': '',
                                      'kind': 'repeated_failure', 'decision_id': 'd1', ...}
PASS  ★ payload 里的 kind 原样带出（不吞）
```

**第 7 项的实测**

```
本地 2 条 · 上游 3 条 · 共有 code 2 条
  P-event-unknown-to-frontend   本地=frontend/degraded  上游=frontend/degraded
  P-phase-unknown               本地=both/degraded      上游=both/degraded
★★ owner 逐条一致   ★★ severity 逐条一致
```

**未验证的部分**（诚实列出）

- **D8 的界面渲染未人眼看**：改的是 reducer 字段读取，已做**跨语言**核对
  （后端发 `decision_kind` ↔ 前端读 `ev.decision_kind`），但渲染结果没人眼确认。
- **D8 未端到端真跑**：要触发 `decision_opened` 需让模型连续失败两次并进入人工决策。
  当前证据在**源码/载荷层**，不是"真跑出一轮"。**这是本轮最值得补的一项。**
- **D9 只覆盖 `CodingCycle._emit`**：其余 9 个挂钩点（`Worker._invoke` 等）
  仍是镜像签名。它们**没有同类风险的原因**是：那些上游方法的首参不叫
  `kind`/`payload` 之类的通用名，且没有"payload 覆盖签名参数"的写法。
  **这是判断，不是验证** —— 若要机械保证，得给 10 个点都加同类测试。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 | **无** | 33 个事件名一个没动 |
| **事件 payload 键** | **无**（本侧） | 改的是**读取端**：前端改读 `decision_kind`。后端那个改名是**上游**已完成的 |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| 三个版本常量 | **无** | — |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 只读资产 |

**本仓库内部接口有一处收紧**：`bridge/progress.py` 的
`emit_progress(kind, ...)` → `emit_progress(event_kind, ...)`。
**只影响关键字调用方**（`emit_progress(kind=...)`），本仓库已核对**无此写法**。
它是 A1(内部) 的破坏性变更，但**没有外部消费方**（`progress` 是 bridge 内部模块）。

**事件记录的形状得到保证**：`{seq, ts, kind, cycle_id, goal, ...payload}` ——
VAR_KEYWORD 展开后是**摊平**的，不是嵌套。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要**（D8 那半他们已经改完了）。
- **有没有可能"问题被平移到对侧"？** 本轮有两处，都**已处理**：

  1. **D9 的镜像就是"第二份判据"**：上游改了 `kind → event_kind`，
     而 bridge 仍镜像旧签名 —— 若我照原样留着，下次上游再改，
     bridge 会在**无人察觉**的情况下重新变成冲突源。已改为向上游要签名。
  2. **测试层的上游歧义**（§29.4）：`_bootstrap` 写死上游目录，
     导致"测试验的不是你在用的那棵树"。这是**把问题藏进了绿灯里**，
     比代码 bug 更危险（它让人以为验过了）。已修并加断言。

- **前端会静默少显示什么吗？** **这正是 D8 的形态**（少显示成了错误的值）。
  本轮修的就是它。另外两处新增的静默风险已堵：
  `emit_progress` 撞名会静默丢事件（已改首参名）、
  `**payload` 收成嵌套会让字段变 `undefined`（已展开 VAR_KEYWORD）。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/` 任何文件**。
- **D9 不推广到全部 10 个挂钩点**：理由见 §4 未验证项 ——
  那 9 个没有同类风险，但**这是判断不是验证**。若统筹方要求机械保证，请指示。
- **不补 D8 的端到端实跑**：需要真实模型跑出"连续失败两次 → 人工决策"，
  耗时长且依赖模型行为。**列为本轮最大未验证项**，等指示。
- **不改上游**（含仓库自带副本）：D8 的改名是上游的事，已由他们完成。

---

## 8. 回退点（对应 C8）

```powershell
.\scripts\backup.ps1 -List
# → 20260926-103118_v12-arch-d2   （本轮改动前的基线）
.\scripts\backup.ps1 -Verify  -From v12-arch-d2
.\scripts\backup.ps1 -Restore -From v12-arch-d2            # 整树
```

**文件级**（本轮 5 个代码文件 + 4 个测试）：

```powershell
.\scripts\backup.ps1 -Restore -From v12-arch-d2 `
    -Path frontend/src/store/run.ts -Path bridge/hooks.py `
    -Path bridge/progress.py -Path tests/_bootstrap.py `
    -Path tests/unit/test_event_contract.py -Path tests/unit/test_isolation.py
```

**必须连测试一起退**（历轮教训）：`test_hooks_passthrough.py` /
`test_two_entrypoints.py` 是**新增**文件，退源文件时要一并删除，
否则它们会引用不存在的符号而变红。

- **回退会丢什么**：D8 的字段修正、D9 的签名绑定与两处静默丢事件修复、
  D6 的常驻对拍、测试层上游判据的修正。
- **回退不会丢什么**：契约镜像、`data/` 运行态、上游（从未改动）。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 三条命令，逐环复现了 D8 的链条 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 11 行 |
| **C3** 命令输出支持主张 | **满足** | §4 附了 3/4/5/6/7 项输出 |
| **C4** 改动清单与实际一致 | **满足** | §3 **先贴机械输出**，手写表降级为导读（按新模板） |
| **C5** 对接口契约的影响已声明 | **满足** | §5：事件字段无改动；**声明了 `emit_progress` 首参改名的内部收紧** |
| **C6** 对另一侧的影响已评估 | **满足** | §6 两处平移风险，均**已处理** |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明不做的部分，含两处**请指示** |
| **C8** 回退点明确 | **满足** | §8 整树 + 文件级，并注明新增测试要一并删 |

**我希望统筹重点验证的一条：§7 第一项（D9 只覆盖 10 个挂钩点中的 1 个）。**

理由：D9 的字面要求是"改 `_emit` 包装器"，我照做了。但我**顺带判断**了
"其余 9 个没有同类风险"，并把它标为**判断而非验证** ——
因为两者差别很大：前者可以机械保证，后者只能靠阅读。

如果那 9 个也想机械保证，做法是给每个包装器加一条"签名不镜像"的断言
（就像我给 `_emit` 加的那样）。**请指示是否要做。**

---

## 附：本轮的三条纪律说明

1. **先写断言，再验收自己。** D9 改完我自认为"透传就够了"，
   结果测试立刻抓到两个我自己引入的坑（`**payload` 收成嵌套、
   `emit_progress` 首参撞名导致**静默丢事件**）。
   **两次都是"修好 A 弄坏 B"，而且第二处是静默的** —— 没有断言就发出去了。

2. **"全类检查"胜过"改一处"。** D8 只要求改第 717 行。
   我另外 AST 扫了上游**每一个** `_emit(...)`，确认这类冲突只有这一个实例 ——
   **这样才敢说"修完了"，而不是"这个好了"。**

3. **绿灯也可能是假的。** 本轮最有价值的发现不是 D8/D9，
   而是测试基础设施里的上游歧义：**测试全绿，但验的是另一棵树**。
   它是被"D6 要读上游源码"这个需求**顺带**逼出来的 ——
   如果我只按字面做完 D8/D9/D6，它会一直留着。
