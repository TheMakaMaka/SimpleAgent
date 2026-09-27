# 变更评估文档 · `ARCH-A2B`

> 按 `.interface_contract/EVALUATION-TEMPLATE.md` 的九节填写。
> 验收依据：`ARCHITECTURE-CHECKLIST.md` 的 **A2b** 一节（逐条打勾）+ `CHANGE-PROCESS.md` C1–C8。
>
> **先贴机械输出，手写表只作导读**（模板 §3）。

---

- **变更编号**：`ARCH-A2B`
- **提出方**：统筹（源自 A2 的原目标被证伪）
- **执行侧**：frontend（`bridge/` 属前端边界，契约 `boundary_definition`）
- **日期**：2026-09-26
- **契约版本**：`1.0.22`

---

## 1. 变更意图

> 引原话，不转述。

用户（批准）：

> 「按你推荐的来，保证版本追溯性就行，我希望下次我打开对应网页应用的版本是最新的」

统筹方 `WORK-ORDER.md`：

> A2 当初的决定是「不删除 `VueWeb\backend\`，但**让它无法被静默使用**」——
> 探针暴露、启动警告、陈旧检测都做了，**都验收通过了**。
> **然后真的出事了。** 用户实例 `:8000` 用**无 `AGENT_BACKEND_DIR`** 的方式启动，
> 于是走 bundled 副本；从后端 v1.12 到 v1.14 约 **10 轮**里，
> **上游所有修复一条都没生效**，而启动警告没人看见、探针字段没人去看。
>
> > **这不是你实现得不好，是"警告"这个手段本身不够。**
> > 你要做的不是"把警告写得更醒目"（那还是同一条路），而是**让误解不可能发生**。

---

## 2. 问题陈述与复现方式（对应 C1）

**现象**：bundled 副本被**默认使用**，且**没有任何东西阻止它**。

**复现命令**

```powershell
# 清掉指向，模拟"用户实例"的启动方式
Remove-Item Env:\AGENT_BACKEND_DIR -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m uvicorn bridge.app:app --app-dir . --port 8000
```

**改前的实际输出**（A2 之后、A2b 之前）：服务**正常起来**，只在 stderr 打一段横幅警告。

**改后的实际输出**

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
[拒绝启动] 解析到的后端是**仓库自带的 bundled 副本**。

  实际 backend_dir : D:\...\SimpleAgent2_Cycle_VueWeb\backend
  判定依据         : backend_is_bundled = True（判形态，不判状态）

  为什么这不可用：
    落后：缺 core/contract.py（契约机制）→ CONTRACT_VERSION / ISSUE_RULES /
    /contract/check 整体不可用，契约版本会静默退回 fallback；…
  怎么修（复制一条执行，然后重启）：
    PowerShell : $env:AGENT_BACKEND_DIR = "D:\PythonProject\SimpleAgent2_Cycle"
    ...
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

退出码 **2**，端口**未监听**。

**为什么这是问题**：不是"警告不够醒目"，而是**「可见」被当成了「足够」**。
约 10 轮里上游修复一条都没生效 —— 代价是**用户以为在用最新版**。

---

## 3. 拟改动清单（对应 C4）

**机械输出（权威内容）**

```powershell
.\scripts\backup.ps1 -Verify -From 20260926-122805_v13.1-d8-docs
```

**实际输出**

```
[改动] 15
   ~ bridge\agent_api.py
   ~ bridge\app.py
   ~ bridge\staleness.py
   ~ CYCLE.md
   ~ docs\ARCHITECTURE.md
   ~ docs\CHANGELOG.md
   ~ docs\DIAGNOSTICS.md
   ~ docs\MODULES.md
   ~ docs\OPERATIONS.md
   ~ docs\VERSIONS.md
   ~ README.md
   ~ scripts\run.ps1
   ~ tests\_bootstrap.py
   ~ tests\unit\test_doc_consistency.py
   ~ tests\unit\test_doc_review.py
[新增] 3
   + bridge\__main__.py
   + docs\EVALUATION-ARCH-A2B.md
   + tests\unit\test_bundled_gate.py

改动合计 18 个文件。
```

**导读（为什么改，不是改动范围）**

| # | 文件 | 为什么 |
|---|---|---|
| 1 | `bridge/staleness.py` | 门禁的**判据与文本**：`should_refuse()` / `refusal_message()` / `allow_bundled_requested()` / `frontend_asset()` / `provenance()` —— 全是纯函数，可离线断言 |
| 2 | `bridge/app.py` | 在 **import 期**执行门禁（uvicorn 先 import 再绑端口 → 端口不监听） |
| 3 | `bridge/agent_api.py` | `/api/health` 加 `backend_bundled_override` 与 `frontend_asset` |
| 4 | `bridge/__main__.py` | **新增**：`python -m bridge [--allow-bundled]`，因为 `uvicorn` 不认识自定义 flag |
| 5 | `scripts/run.ps1` | `-AllowBundled` |
| 6 | `tests/_bootstrap.py` | 测试要 in-process 拿 `app` 对象 → 显式声明"只是导入" |
| 7 | `tests/unit/test_bundled_gate.py` | **新增**：含**子进程负向测试** |
| 8 | `tests/unit/test_doc_consistency.py`、`test_doc_review.py` | **顺带修**：章节池漏了 DIAGNOSTICS/LAYOUT，导致"`docs/DIAGNOSTICS.md` §7.5"这种**合法**引用被判无效（见 §7） |
| 9 | 文档 | 启动说明必须写明新的拒绝行为（否则用户会以为服务坏了） |

> **诚实记一笔**：我先前预估的是"12 改动 / 3 新增"，机械核对是 **15 / 3**。
> 多出来的三个是 `docs/VERSIONS.md` 与那两个**测试文件**（改文档时顺带修的）——
> 也就是说，**我又漏列了**，只不过这次漏的是测试而不是文档。
> 判据请一律以 `-Verify` 的输出为准（这是 §3 新模板的要点）。

---

## 4. 主张与验证命令（对应 C2、C3）

| # | 主张 | 验证命令 | 期望 | 实测 |
|---|---|---|---|---|
| 1 | 不设 `AGENT_BACKEND_DIR` → **端口不监听** | `uvicorn bridge.app:app --port N`（无 env） | 连接失败 | ✅ |
| 2 | 退出码非 0 | 同上 | `$LASTEXITCODE != 0` | ✅ **2** |
| 3 | 拒绝输出含 `backend_dir` | 同上（读输出） | 含实际路径 | ✅ |
| 4 | 拒绝输出含**带后果的**理由 | 同上 | 含"静默/不可用" | ✅ |
| 5 | 拒绝输出含**可复制的修复命令** | 同上 | 含 `AGENT_BACKEND_DIR=` | ✅ |
| 6 | ★ **负向测试**：一个只打警告的实现不得通过 | `$PY tests\unit\test_bundled_gate.py` | `31/31` | ✅ |
| 7 | `--allow-bundled` 能启动 | `python -m bridge --allow-bundled --port N` | 端口在听 | ✅ |
| 8 | 逃生舱**留痕** | `GET /api/health` | `backend_bundled_override=true` | ✅ |
| 9 | `/api/health` 含 `frontend_asset` 且 == 实际服务值 | 同上 | == `dist/index.html` 引用值 | ✅ |
| 10 | 启动日志含全部版本追溯字段 | 读启动 stderr | 六项齐全 | ✅ |
| 11 | 判**形态**不判**状态** | `$PY tests\unit\test_bundled_gate.py` | `{stale:False}` 仍拒 | ✅ |
| 12 | 指向上游**不**被拒（闸门非恒真） | 同上 §[4] | `is_bundled=False → False` | ✅ |
| 13 | 全量无回归（两种配置） | `$PY tests\run_unit.py` | `35/35` | ✅ |
| 14 | 统筹方契约测试 | `test_interface_contract.py --backend <port>` | `29/29` | ✅ |

**第 1/2/6 项的实测输出**（`test_bundled_gate.py` §[2]，**真的起了进程**）

```
PASS  端口 55993 起前空闲
PASS  ★ 进程**退出了**（不是还在跑）
PASS  ★ 退出码非 0（实测 2）   2
PASS  ★★ 端口**没有被监听**
PASS  拒绝输出含 backend_dir
PASS  ★ 拒绝输出含带后果的理由
PASS  ★ 拒绝输出含可复制的修复命令
PASS  退出很快（不是先起来再关）   0.5s
```

**第 7/8/9 项的实测**

```
PASS  ★ `python -m bridge --allow-bundled` 起来了（端口在听）
PASS  ★★ /api/health 报 backend_bundled_override=true   True
PASS  同时仍如实报 backend_is_bundled=true   True
PASS  ★ /api/health 含 frontend_asset   index-CsUZBNxG.js
PASS  ★ frontend_asset == dist/index.html 引用的那个 bundle
```

**第 10 项的实测**（启动日志，指向上游时）

```
[bridge] ── 本次运行（版本追溯）────────────────────────────
[bridge]   后端目录      : D:\PythonProject\SimpleAgent2_Cycle
[bridge]   自带副本      : False
[bridge]   逃生舱        : False
[bridge]   陈旧          : False — 标记齐备，未发现落后
[bridge]   core 模块     : 29 个
[bridge]   契约版本      : 1.0
[bridge]   前端 bundle   : index-CsUZBNxG.js
```

**未验证的部分**（诚实列出）

- **窗口期外的启动方式未穷举**：只验了 `uvicorn bridge.app:app`（无 env）、
  `python -m bridge --allow-bundled`、`python -m bridge`（指向上游）三种。
  未验：`python backend/main.py`（绕过 bridge，**不受本闸门保护**）、
  Docker/服务化启动。**绕过 bridge 的启动方式这条闸门管不到** —— 这是它的边界。
- **`frontend_asset` 只覆盖 JS**：不含 CSS/其它资源，不是完整构建指纹。
- **界面未人眼看**：本轮无界面改动。

---

## 5. 对接口契约的影响（对应 C5）

| 事实面 | 是否改动 | 说明 |
|---|---|---|
| 事件 `kind` 名 / payload 键 | **无** | — |
| 上游 `PHASE_ORDER` 阶段 | **无** | — |
| `CycleReport` / `Snapshot` / `Event` 字段 | **无** | — |
| `TOOLS_MAP` 条目结构 | **无** | — |
| 三个版本常量 | **无** | — |
| 端点路径 | **无** | — |
| `.interface_contract/` 覆盖的规则与词表 | **无改动** | 只读资产 |

**`/api/health` 新增两个字段（additive）**

```
backend_bundled_override : bool   # 是否用了逃生舱
frontend_asset           : str    # 正在服务的前端 bundle 名
```

**新增一个入口**：`python -m bridge`（`bridge/__main__.py`）。
它是**新增**，不改变 `uvicorn bridge.app:app` 的可用性。

**⚠️ 一处行为收紧（不是接口改动，但影响运维）**：
**不设 `AGENT_BACKEND_DIR` 就不再能启动**。这是本项的目的。
它会让"照着旧文档启动"的人第一次遇到时以为服务坏了 ——
所以 `docs/OPERATIONS.md` §1.2 已在**最前面**加了警示块，
拒绝输出里也给了修复命令与逃生舱。

---

## 6. 对另一侧的影响（对应 C6、C7）

- **另一侧需要跟着改吗？** **不要。**
- **有没有可能"问题被平移到对侧"？** 有一条，值得明说：
  闸门拒的是**本仓库自带的副本**。若有人把上游 checkout 放到
  **`<仓库>/backend/`**（即"复制过来"那种用法），他会被**误拒** ——
  因为判据是**路径位置**（`paths.ROOT/backend`），不是"内容是否落后"。
  这是**刻意的**：`boundary` 决定判形态，而"这个目录是不是仓库自带的那个"
  只能由位置回答。
  逃生舱就是给这种情况用的（他会看到"降级必须留痕"，从而知道自己在用哪份）。
  **若统筹方认为这不可接受，请提出 —— 我没有单方面放宽判据。**
- **前端会静默少显示什么吗？** 不会：`/api/health` 的两个字段是 additive；
  前端当前不读它们（本轮未改前端）。**但这也意味着：这两个字段目前只有
  探针/人能看**，界面上没有展示。若要"打开网页就能看到自己在跑哪一版"，
  需要前端消费它们 —— **那是一个新的界面改动，我没有擅自做**。

---

## 7. 不做的部分及理由（对应 C7）

- **不改 `.interface_contract/`**（只读资产）。
- **不删 `VueWeb\backend\`** —— 用户批的是 **(2) 启动即拒**，不是 (3) 删副本。
  副本留着（保持"可显式使用"），只是不再能被**默认**用到。
- **不把"陈旧"当门禁** —— 判据是 `backend_is_bundled`（**形态**）；
  `stale` 只用于说明后果。测试里专门断言"即使 `stale=False` 也拒"。
- **不擅自把 `frontend_asset` 显示到界面上**（见 §6）—— 那超出本项范围，
  且会让"打开网页"多一个界面元素，应由统筹方/用户定。
- **`python backend/main.py` 绕过 bridge 的启动方式不设防** ——
  闸门在 `bridge/` 里；绕过适配层就没有适配层的保护。这是边界，不是疏漏。
- **顺带修的两处测试门禁**（不在 A2b 范围内，但改了才能让文档通过）：
  `test_doc_consistency.py` / `test_doc_review.py` 的**章节池漏了
  `DIAGNOSTICS.md` 与 `LAYOUT.md`**，于是"详见 `docs/DIAGNOSTICS.md` §7.5"
  这种**带文件名限定的合法引用**被判成"无效引用"。
  那是**漏检**（池子太小），不是纠错。放宽方向是安全的：
  池子变大只会让能解析的引用变多，`§99` 这类哪儿都不存在的引用照样红。

### 请统筹方确认的两处

1. **"副本被放到 `<仓库>/backend/`"会被误拒**（§6 第一条）。判据是位置而非内容，
   这是按"判形态"来的；请确认这个取舍，或指示如何区分。
2. **`frontend_asset` 是否要显示到界面上**（§6 末条）。用户要的是
   "我打开看到的是哪一版"，而当前只有 `/api/health` 能回答。

---

## 8. 回退点（对应 C8）

```powershell
.\scripts\backup.ps1 -List
# → 20260926-122805_v13.1-d8-docs   （本轮改动前的基线）
.\scripts\backup.ps1 -Verify  -From v13.1-d8-docs
.\scripts\backup.ps1 -Restore -From v13.1-d8-docs                       # 整树
```

**文件级**

```powershell
.\scripts\backup.ps1 -Restore -From v13.1-d8-docs `
    -Path bridge/app.py -Path bridge/staleness.py -Path bridge/agent_api.py `
    -Path scripts/run.ps1 -Path tests/_bootstrap.py
```

**必须一并删除两个新增文件**，否则回退后它们会引用不存在的符号而变红：
`bridge/__main__.py`、`tests/unit/test_bundled_gate.py`。
（`-Path` 不接受"删除"，所以这一步要手工 `Remove-Item`。这是 `-Path` 的一条**已知局限**。）

- **回退会丢什么**：拒绝启动、逃生舱留痕、`frontend_asset`、版本追溯日志段。
- **回退不会丢什么**：契约镜像、`data/` 运行态、上游（从未改动）。
- **回退后注意**：`tests/_bootstrap.py` 里那行 `AGENT_ALLOW_BUNDLED` 也应一起去掉，
  否则会留下一个"没人用但一直在设"的环境变量。

---

## 9. 自检结论

| 标准 | 自查 | 说明 |
|---|---|---|
| **C1** 问题陈述可复现 | **满足** | §2 给了改前/改后两条命令与输出 |
| **C2** 每条主张带可复现命令 | **满足** | §4 共 14 行 |
| **C3** 命令输出支持主张 | **满足** | §4 附了 4 段实测输出 |
| **C4** 改动清单与实际一致 | **满足** | §3 先贴机械输出，手写表降级为导读 |
| **C5** 对接口契约的影响已声明 | **满足** | §5：health 两字段 additive；**并显式声明了"不设 env 就起不来"这一运维影响** |
| **C6** 对另一侧的影响已评估 | **满足** | §6 两条：误拒风险 + 字段未被界面消费，**均请确认** |
| **C7** 未把接口级问题当内部问题处理 | **满足** | §7 列明不做的部分，含两处**请确认** |
| **C8** 回退点明确 | **满足** | §8 整树 + 文件级，并注明新增文件要手工删（`-Path` 的已知局限） |

**我希望统筹重点验证的一条：§6 的第一条（"副本放到 `<仓库>/backend/` 会被误拒"）。**

理由：这条**不是缺陷，是取舍**。判据按清单要求是"**形态**"，
而"形态"在实现上只能是"**路径位置**"。后果是：
一个**内容已同步**、但**放在仓库自带位置**的上游会被拒。

我没有为了让这条更好看而放宽判据（那正是清单禁止的"悄悄放宽"），
而是把它**显式写出来请裁决**。验证动作：

```powershell
# 把真上游的内容放到仓库自带位置 → 仍会被拒（这是刻意的）
$env:AGENT_RUNTIME_ROOT="$env:TEMP\a2b_probe"
.\.venv\Scripts\python.exe -c "import sys;sys.path.insert(0,'.');from bridge import staleness as S, paths; r=S.probe(paths.BACKEND_DIR); print('is_bundled=',r['is_bundled'],'stale=',r['stale'],'→ refuse=',S.should_refuse(r, allow=False))"
```

---

## 附：本轮的三条纪律说明

1. **"警告"这条手段被证伪之后，正确的反应不是"把警告写得更醒目"。**
   统筹方说得很准：那还是同一条路。真正的修法是**让误解不可能发生** ——
   这一点我完全同意，也是本项的全部内容。

2. **闸门放 import 期是有代价的，我把代价明说而不是藏起来。**
   代价是 `import bridge.app ≠ 启动服务`，所以测试要显式开逃生舱。
   我担心的是**悄悄放宽**（例如"检测到测试就跳过闸门"那种写法）——
   那会让闸门在最需要它的地方失效。现在的做法是：
   开关**显式**、理由**写在代码里**、门禁由**子进程**独立验证。

3. **门禁在改的过程中先抓到了我自己。** 改 `scripts/run.ps1` 之后，
   `test_ps1_encoding.py` 立刻红了 —— 编辑工具把 BOM 又写掉了。
   这正是那个测试存在的理由（这个坑踩过两次）。**这次是它替我发现的。**
