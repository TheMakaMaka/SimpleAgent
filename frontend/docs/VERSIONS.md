# 版本记录

> **本文件由 `scripts/backup.ps1` 在每次成功备份后自动追加一条，请勿手改。**
>
> 纪律与上游 `docs/VERSIONS.md` 一致：**只增不改**。
> 每条记录四样东西 —— 标签与时间、**改了什么**（机械核对）、**验证结果**、**还原命令**。
>
> 「改了什么」不是人写的总结，而是 `backup.ps1 -Verify -From <上一版>` 的
> **机械 diff**（本机没有 git，这是 `git diff --stat` 的等价物）。
> 所以本文件里的改动清单**不会漏**——手写的一定会漏，这一点已被实测抓到过两次。
>
> 起点说明：本文件自 **v10** 起建立。`v1`…`v9` 只在 `_backups/` 留有目录名，
> 没有机械记录（当时还没做出等价 diff 的手段）。**不追溯补写**——
> 凭记忆补出来的记录不是记录。

---

## `v20-safe-contract` · 2026-09-28 22:30:22

| 项 | 值 |
|---|---|
| 还原点 | `20260928-223020_v20-safe-contract` |
| 验证结果 | 单测 38/38 · layout 通过 · typecheck 零错误 · dist 新鲜 · 端到端 17/17 |
| 改了什么 | 13 改动 / 1 新增 / 0 删除（对比 `20260928-212704_v19-p5b-hook-globals`） |
| 对比基准 | `20260928-212704_v19-p5b-hook-globals` |

**这一版做到了什么**

P6：_safe 契约修正（只放行 RunCancelled，普通异常真的被吞）+ emit_safe/parse_worker_args 让 payload 构造也在保护内；新增判据 H/I 与注入故障的端到端证据；修掉两处扫描器只认旧 emit 写法（会导致事件静默少认）；真实运行 run_20260928_221959_80417d passed

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
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
  + docs\EVALUATION-SAFE-CONTRACT.md
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260928-223020_v20-safe-contract
.\scripts\backup.ps1 -Restore -From 20260928-223020_v20-safe-contract
```

---
## `v19-p5b-hook-globals` · 2026-09-28 21:27:05

| 项 | 值 |
|---|---|
| 还原点 | `20260928-212704_v19-p5b-hook-globals` |
| 验证结果 | 单测 38/38 · layout 通过 · typecheck 零错误 · dist 新鲜 · 端到端 17/17 |
| 改了什么 | 11 改动 / 1 新增 / 0 删除（对比 `20260928-091633_v18-hooks-passthrough`） |
| 对比基准 | `20260928-091633_v18-hooks-passthrough` |

**这一版做到了什么**

P5b 阻塞修复：挂钩体不再引用只在函数内 import 的名字（worker_cls 延迟取类 + _safe 包住解析）；新增门禁：ruff F821 --ignore-noqa 零命中 + dis 扫 LOAD_GLOBAL + Worker._invoke 生产路径冒烟；harness 改为不绕过任何挂钩点；真实运行 run_20260928_212052_3d1143 passed

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\hooks.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\EVALUATION-TRANSPARENCY2-UI.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ README.md
  ~ tests\diagnostics\hook_verify_e2e.py
  ~ tests\unit\test_hook_compat.py
  + docs\EVALUATION-HOOKS-PASSTHROUGH-2.md
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260928-212704_v19-p5b-hook-globals
.\scripts\backup.ps1 -Restore -From 20260928-212704_v19-p5b-hook-globals
```

---
## `v18-hooks-passthrough` · 2026-09-28 09:16:34

| 项 | 值 |
|---|---|
| 还原点 | `20260928-091633_v18-hooks-passthrough` |
| 验证结果 | 单测 38/38 · layout 通过 · typecheck 零错误 · dist 新鲜 · 端到端 17/17 |
| 改了什么 | 13 改动 / 2 新增 / 0 删除（对比 `20260928-000917_v17-transparency2-ui`） |
| 对比基准 | `20260928-000917_v17-transparency2-ui` |

**这一版做到了什么**

P5 阻塞修复：11 个挂钩点全部改成透传（HOOK_POINTS 唯一名单 + make_hook 工厂，同步/异步问上游）；新增 test_hook_compat（含负向）与 hook_verify_e2e（离线真跑到 verify）；契约 v1.0.26 使滞后表第二次到期清空

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\hooks.py
  ~ bridge\partition.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\DIAGNOSTICS.md
  ~ docs\EVALUATION-TRANSPARENCY2-UI.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ README.md
  ~ tests\unit\test_event_contract.py
  ~ tests\unit\test_hooks_passthrough.py
  + tests\diagnostics\hook_verify_e2e.py
  + tests\unit\test_hook_compat.py
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260928-091633_v18-hooks-passthrough
.\scripts\backup.ps1 -Restore -From 20260928-091633_v18-hooks-passthrough
```

---
## `v17-transparency2-ui` · 2026-09-28 00:09:19

| 项 | 值 |
|---|---|
| 还原点 | `20260928-000917_v17-transparency2-ui` |
| 验证结果 | 单测 37/37 · layout 通过 · typecheck 零错误 · dist 新鲜 · 端到端 17/17 |
| 改了什么 | 27 改动 / 7 新增 / 2 删除（对比 `20260927-135246_v16.1-transparency-ui-docs`） |
| 对比基准 | `20260927-135246_v16.1-transparency-ui-docs` |

**这一版做到了什么**

TRANSPARENCY2-UI：P1 交付新鲜度（dist vs src，含负向门禁与备份前检查）、P2 任务面板（不压缩/内部滚动/自动跟随/折叠已完成，19 任务实测）、P3 结局四值+判据来源+独立性、P4 拆解合规审查（violated 与 undecidable 分开）；契约 v1.0.25 滞后表换批；新增 fix_bom

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\partition.py
  ~ bridge\runner.py
  ~ bridge\spec.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\DIAGNOSTICS.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ frontend\dist\index.html
  ~ frontend\scripts\replay-check.mjs
  ~ frontend\src\App.vue
  ~ frontend\src\components\TaskPanel.vue
  ~ frontend\src\components\TransparencyPanel.vue
  ~ frontend\src\components\VerifyPanel.vue
  ~ frontend\src\generated\expectations.ts
  ~ frontend\src\store\run.ts
  ~ frontend\src\store\transparency.ts
  ~ frontend\src\types.ts
  ~ README.md
  ~ scripts\backup.ps1
  ~ tests\diagnostics\make_transparency_fixture.py
  ~ tests\fixtures\transparency-fixture.json
  ~ tests\unit\test_event_contract.py
  ~ tests\unit\test_partition.py
  ~ tests\unit\test_transparency_ui.py
  + docs\EVALUATION-TRANSPARENCY2-UI.md
  + frontend\dist\assets\index-Bu5N1N67.js
  + frontend\dist\assets\index-yo24bi27.css
  + frontend\src\store\tasklist.ts
  + scripts\fix_bom.py
  + scripts\freshness.py
  + tests\unit\test_dist_freshness.py
  - frontend\dist\assets\index-BcJOtip4.js
  - frontend\dist\assets\index-DZFXNCxx.css
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260928-000917_v17-transparency2-ui
.\scripts\backup.ps1 -Restore -From 20260928-000917_v17-transparency2-ui
```

---
## `v16.1-transparency-ui-docs` · 2026-09-27 13:52:47

| 项 | 值 |
|---|---|
| 还原点 | `20260927-135246_v16.1-transparency-ui-docs` |
| 验证结果 | 单测 36/36 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 5 改动 / 0 新增 / 1 删除（对比 `20260927-134929_v16-transparency-ui`） |
| 对比基准 | `20260927-134929_v16-transparency-ui` |

**这一版做到了什么**

TRANSPARENCY-UI 收尾：契约滞后按方向分流（CONTRACT_LAG_KINDS）、前端词表含采集器声明、doctor 按配置分流、九节评估文档与文档同步

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ docs\CHANGELOG.md
  ~ docs\DIAGNOSTICS.md
  ~ docs\EVALUATION-TRANSPARENCY-UI.md
  ~ docs\MODULES.md
  ~ docs\VERSIONS.md
  - tmp_doc2.txt
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260927-135246_v16.1-transparency-ui-docs
.\scripts\backup.ps1 -Restore -From 20260927-135246_v16.1-transparency-ui-docs
```

---
## `v16-transparency-ui` · 2026-09-27 13:49:30

| 项 | 值 |
|---|---|
| 还原点 | `20260927-134929_v16-transparency-ui` |
| 验证结果 | 单测 36/36 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 25 改动 / 11 新增 / 2 删除（对比 `20260927-105719_v15-verify-skipped`） |
| 对比基准 | `20260927-105719_v15-verify-skipped` |

**这一版做到了什么**

TRANSPARENCY-UI：四块「为什么」视图（A2/A3/B4/C3）+ D3 结局四值与判据来源；上游三个新事件（orchestrator_round/verify_criterion/self_report）的校准与采集；契约滞后按方向分流

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\partition.py
  ~ bridge\spec.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\DIAGNOSTICS.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ frontend\dist\index.html
  ~ frontend\package.json
  ~ frontend\README.md
  ~ frontend\scripts\gen-expectations.mjs
  ~ frontend\src\App.vue
  ~ frontend\src\components\TaskPanel.vue
  ~ frontend\src\components\VerifyPanel.vue
  ~ frontend\src\generated\expectations.ts
  ~ frontend\src\store\run.ts
  ~ frontend\src\types.ts
  ~ README.md
  ~ scripts\doctor.py
  ~ tests\diagnostics\check_contract_report.py
  ~ tests\unit\test_audit.py
  ~ tests\unit\test_event_contract.py
  ~ tests\unit\test_partition.py
  + docs\EVALUATION-TRANSPARENCY-UI.md
  + frontend\dist\assets\index-BcJOtip4.js
  + frontend\dist\assets\index-DZFXNCxx.css
  + frontend\scripts\replay-check.mjs
  + frontend\src\components\TransparencyPanel.vue
  + frontend\src\store\args.ts
  + frontend\src\store\transparency.ts
  + tests\diagnostics\make_transparency_fixture.py
  + tests\fixtures\transparency-fixture.json
  + tests\unit\test_transparency_ui.py
  + tmp_doc2.txt
  - frontend\dist\assets\index-OwZY1JQb.css
  - frontend\dist\assets\index--XpunQ0C.js
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260927-134929_v16-transparency-ui
.\scripts\backup.ps1 -Restore -From 20260927-134929_v16-transparency-ui
```

---
## `v15-verify-skipped` · 2026-09-27 10:57:20

| 项 | 值 |
|---|---|
| 还原点 | `20260927-105719_v15-verify-skipped` |
| 验证结果 | 单测 35/35 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 18 改动 / 2 新增 / 2 删除（对比 `20260926-141024_v14-arch-a2b`） |
| 对比基准 | `20260926-141024_v14-arch-a2b` |

**这一版做到了什么**

校准上游新事件 verify_skipped（契约 v1.0.23 唯一红项），并顺带修掉根因。①事件：上游 FIX-VERIFY-WIRING 加性新增 verify_skipped，把「有验证命令却没有 pipeline、于是验证回流整块被跳过」从静默变成显式事实（静默跳过会让上层误诊成「缺少验证命令」）。分区本来就对（13/21），缺的只是校准。标定为 label=⚠ 验证被跳过 / tone=warn（跳过了一次安全检查，不是通过也不是错误）/ panel=gate / detail={reason}。②让运行视图真的显示它，而不只是认下来：run.ts 新增 case（时间线 warn 条目 + 收进 state.verifySkipped），types.ts 的 RunState 加该字段，VerifyPanel 的 VERIFY 块加「跳过 N 次」徽标与琥珀色列表——它既非通过也非失败，混进现有状态就等于白做。生成物 33 → 34 事件。③★ 根因修复：改完三个测试红了，一查红的全是写死的常数（12/33/CONTRACT_RECORDED_*），不是分区逻辑——上游按规矩加性加了一个事件，契约升到 34=13+21。这与统筹方本轮在同一份 CHANGELOG 里自陈的失误是同一个缺陷。修法不是把 12 改成 13，而是让常数的来源变成契约：partition.recorded_snapshot() 读 event_partition.observed 与 phases_partition，读不到才回退 CONTRACT_FALLBACK_*；与 D2 的 owner_of/upstream_rule 同一模式——凡契约声明过的事，本模块不再存第二份副本。判据因此变成「实测 == 契约声明」。④三个测试的判定跟着改成「上游落后 ≠ 逻辑错」：推导≠契约是真信号（断言差集恰好是契约新增的那一个）、dead_calibrations 是「为契约的新上游备着」、U-dead-event 导致的 backend-action 正是该事件存在的意义——落后时 SKIP 并写明原因，与 doctor 的 bundled→WARN/外部→FAIL、test_two_entrypoints 的 SKIP 同一条判断。实测：统筹方契约测试回到 32/32（no uncalibrated events PASS）、/api/spec 的 uncalibrated 与 dead 都空、分区 13+21=34；全量 35/35（两种配置）、事件契约 29/29 与 20/20、分区 59/59 与 55/55、前端 typecheck/build 零错误。本轮未交九节评估文档：这是校准不是接口改动，验收是单一条件且已附机械证据——但若认为 §31.3 的根因修复需要正式文档，我补。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\partition.py
  ~ bridge\spec.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ frontend\dist\index.html
  ~ frontend\src\components\VerifyPanel.vue
  ~ frontend\src\generated\expectations.ts
  ~ frontend\src\store\run.ts
  ~ frontend\src\types.ts
  ~ README.md
  ~ tests\unit\test_audit.py
  ~ tests\unit\test_event_contract.py
  ~ tests\unit\test_partition.py
  ~ tests\unit\test_spec.py
  + frontend\dist\assets\index-OwZY1JQb.css
  + frontend\dist\assets\index--XpunQ0C.js
  - frontend\dist\assets\index-CsUZBNxG.js
  - frontend\dist\assets\index-DiEIbo8g.css
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260927-105719_v15-verify-skipped
.\scripts\backup.ps1 -Restore -From 20260927-105719_v15-verify-skipped
```

---
## `v14-arch-a2b` · 2026-09-26 14:10:25

| 项 | 值 |
|---|---|
| 还原点 | `20260926-141024_v14-arch-a2b` |
| 验证结果 | 单测 35/35 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 15 改动 / 3 新增 / 0 删除（对比 `20260926-122805_v13.1-d8-docs`） |
| 对比基准 | `20260926-122805_v13.1-d8-docs` |

**这一版做到了什么**

A2b（架构级，用户已批准）：bundled 即拒绝启动。①为什么升级：A2 的目标是「不删副本但让它无法被静默使用」，四条验收全过之后，用户实例仍以 bundled 方式跑了约 10 轮、上游修复一条都没生效——不是警告不醒目，是警告这个手段本身不够，「可见」被当成了「足够」。②判形态不判状态：门禁是 backend_is_bundled 不是 backend_stale，因为「副本此刻恰好同步」会过期，而这条要防的是「你以为在跑上游、其实在跑副本」；测试专门断言 {stale:False} 仍拒。③闸门放 import 期（uvicorn 先 import 再绑端口，只有那里退出才能保证端口不监听），代价是 import bridge.app ≠ 启动服务，所以 tests/_bootstrap.py 显式设 AGENT_ALLOW_BUNDLED=1 并写明理由，真正的门禁由 test_bundled_gate.py 用子进程验证（把该变量从子进程环境删掉，断言退出码非 0 且端口没被监听——验收标准明写「一个只打警告的实现不得通过」）。④逃生舱：--allow-bundled / AGENT_ALLOW_BUNDLED=1，必须在 /api/health 留痕 backend_bundled_override=true（降级必须留痕，否则逃生舱会变成新的静默通道）。环境变量是主入口，因为 uvicorn 不认识自定义 flag，所以新增 bridge/__main__.py 提供 python -m bridge --allow-bundled，run.ps1 加 -AllowBundled。A2 的醒目警告移到逃生舱路径上（否则默认路径改成拒绝后它就成了死代码）。⑤版本追溯（用户要求）：启动日志与 /api/health 共用 staleness.provenance()，含 backend_dir / is_bundled / bundled_override / stale+reason / core 模块数 / 契约版本 / frontend_asset；frontend_asset 从 dist/index.html 引用的那个 JS 读（不是目录里最新的那个，两者在构建中断时会不一致）。⑥拒绝输出三件事齐全：实际 backend_dir、带后果的理由、可复制的修复命令（路径不编：先看 AGENT_UPSTREAM_DIR，再看仓库同级真的有 core/ 的那份，都没有才给占位符）。⑦顺带修两处文档门禁的漏检：章节池漏了 DIAGNOSTICS/LAYOUT，导致「详见 docs/DIAGNOSTICS.md §7.5」这种合法引用被判无效（池子太小是漏检，放宽方向安全）。⑧门禁先抓到我自己：改 run.ps1 后 test_ps1_encoding 立刻红了（编辑工具又写掉 BOM），正是那个测试存在的理由。实测：拒绝退出码 2 + 端口未监听；--allow-bundled 起来且 override=true；指向上游正常启动 override=false；frontend_asset == dist/index.html 引用值；全量 35/35（两种配置）、门禁测试 31/31（bundled）与 32/32（指向上游）。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
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
  + bridge\__main__.py
  + docs\EVALUATION-ARCH-A2B.md
  + tests\unit\test_bundled_gate.py
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-141024_v14-arch-a2b
.\scripts\backup.ps1 -Restore -From 20260926-141024_v14-arch-a2b
```

---
## `v13.1-d8-docs` · 2026-09-26 12:28:06

| 项 | 值 |
|---|---|
| 还原点 | `20260926-122805_v13.1-d8-docs` |
| 验证结果 | 单测 34/34 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 2 改动 / 0 新增 / 0 删除（对比 `20260926-122521_v13-d8-d9-d6`） |
| 对比基准 | `20260926-122521_v13-d8-d9-d6` |

**这一版做到了什么**

v13 之上：评估文档 §3 的机械输出由凭印象写的 12 改动改为机械核对的 15 改动，并把这个偏差本身记进文档（手写表只是导读、机械输出才是权威——连刚跑过 diff 的人也会记错）。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ docs\EVALUATION-D8-D9-D6.md
  ~ docs\VERSIONS.md
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-122805_v13.1-d8-docs
.\scripts\backup.ps1 -Restore -From 20260926-122805_v13.1-d8-docs
```

---
## `v13-d8-d9-d6` · 2026-09-26 12:25:22

| 项 | 值 |
|---|---|
| 还原点 | `20260926-122521_v13-d8-d9-d6` |
| 验证结果 | 单测 34/34 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 15 改动 / 4 新增 / 1 删除（对比 `20260926-103118_v12-arch-d2`） |
| 对比基准 | `20260926-103118_v12-arch-d2` |

**这一版做到了什么**

D8（阻塞）+D9+D6。D8：decision_opened 的 reducer 分支改读 ev.decision_kind —— 后端把 payload 键 kind 改成 decision_kind 后，ev.kind 由「决策种类」变回「事件类型」，于是决策种类会显示成 decision_opened。逐环复现确认了链条（runner.py 的 {seq,ts,kind,**payload} 展开顺序），并额外核出统筹方没提的一层：改名同时修好了 switch(kind) —— 覆盖存在时 case decision_opened 根本匹配不上，该分支此前是死的。做了全类检查：AST 扫上游每个 _emit(...)，含 kind= 载荷的 0 处，所以这类冲突只有这一个实例。D9：hooks 的 _emit 包装器不再镜像上游签名，改为 inspect.signature(orig_emit).bind —— 镜像就是第二份判据，上游上次改名它不会跟着变。改的过程中被新测试抓到两个我自己引入的坑：① bind().arguments 会把 **payload 收成嵌套字典（挂在 payload 键下）而不是摊平，前端读 ev.decision_id 会变 undefined 且不报错；② emit_progress(kind, **payload) 自己的首参就叫 kind，载荷里一旦有 kind 会在这一层再撞名，而那次被 _safe 吞掉 → 事件静默消失；两处都已修（展开 VAR_KEYWORD / 首参改名 event_kind）。D6：新增 test_two_entrypoints.py，同进程同时打 /api/audit 与 /contract/check 对拍 code/owner/severity/verdict；实测 owner 与 severity 逐条一致（P-event-unknown-to-frontend=frontend/degraded、P-phase-unknown=both/degraded），verdict 允许不同（本地还管本地环境项），真正比的是共有 code 的 owner 集合；自带副本时按配置 SKIP 而非 FAIL。★ 顺带修掉一个测试基础设施里的歧义（A3 同型）：tests/_bootstrap.py 把上游目录写死成 <仓库>/backend、不认 AGENT_BACKEND_DIR，于是用户指了上游也没用——所有扫源码的测试扫的还是旧副本，测试全绿但验错了树；已改用与 paths.BACKEND_DIR 同一条判据并加断言钉住（test_isolation §6），同时纠正两处把「生效上游」与「自带副本」混为一谈的判据。修完后同一份 test_event_contract.py 在两种配置下给出不同但都正确的结果：指向上游 21/21（真验到上游发 decision_kind），自带副本 18/18+SKIP 1。另：contract_vocab.py 注释里过期的契约版本号 v1.0.1 改成字段路径索引（版本号会过期，路径不会）。全量单测 34/34（两种配置都过）、前端 typecheck/build 零错误、layout/doctor 全过。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
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
  + docs\EVALUATION-D8-D9-D6.md
  + frontend\dist\assets\index-CsUZBNxG.js
  + tests\unit\test_hooks_passthrough.py
  + tests\unit\test_two_entrypoints.py
  - frontend\dist\assets\index-BY1HBqvb.js
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-122521_v13-d8-d9-d6
.\scripts\backup.ps1 -Restore -From 20260926-122521_v13-d8-d9-d6
```

---
## `v12-arch-d2` · 2026-09-26 10:31:19

| 项 | 值 |
|---|---|
| 还原点 | `20260926-103118_v12-arch-d2` |
| 验证结果 | 单测 32/32 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 13 改动 / 1 新增 / 0 删除（对比 `20260926-100606_v11.1-arch-docs`） |
| 对比基准 | `20260926-100606_v11.1-arch-docs` |

**这一版做到了什么**

ARCH-D2（契约 v1.0.7 两处裁定的落实）。①P-phase-unknown：统筹方采纳本仓库的判断，由 backend/breaking 改判 both/degraded；那条 DEVIATIONS 偏离随之撤销，表现在为空（空表本身就是断言：两侧判据一致）。契约还补了一条我没论证到的——真正的上游删阶段由 U-removed-surface(backend,breaking) 覆盖，改判不会漏检。②U-dead-event：本仓库报的缺陷真实，但指的位置偏了（我指同一行的两个字段，实际是 upstream_only 与 bridge_backend_prefixed 两行之间）；已统一为 degraded，本仓库的 U-dead-event/bridge.dead_event 级别改从契约取。③修根因而不是症状：D2 字面只有两行值要改，但值会漂是因为被抄了一份——所以把跨侧规则也改成读契约（contract_vocab.load_upstream_rules/upstream_rule），与既有 owner_of+REATTRIBUTED 回退同一模式，并新增断言「离线回退表必须与契约逐条一致」，这类漂移从此当场红。④另两项主动询问也裁了（ops.warnings 维持单一语义、id 不需要别名映射），本仓库现状已符合，无需改代码。⑤端到端自检修两处（真跑才暴露）：404 的 body 是合法 JSON 会被当成「上游答了但没命中」记 FAIL（改为显式判 200）；把「按配置不可测」与「测了没过」分开——bundled 配置做不了跨侧对账是配置事实，记 FAIL 会让默认配置永远红着，新增 skip() 印 SKIP 并写明原因。实测 bundled 39/39+SKIP 1、指向上游 41/41。⑥报上游一条瞬时观察：/contract/check 曾在旧加载实例上 500（NameError _version_tuple），磁盘上第 731 行已定义它，重启后 200——判断是模块被改过而实例还是旧版本，请确认已修。⑦另有一条没能复现的观察：仓库根冒出一个空 workspace/（只有 _debug/_tmp），隔离门禁按预期抓到，但排查五种路径全部干净、同样命令重跑也干净，触发条件未知——已删除，不写没验证过的修复。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\audit.py
  ~ bridge\contract_vocab.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ docs\VERSIONS.md
  ~ README.md
  ~ tests\diagnostics\check_contract_report.py
  ~ tests\unit\test_audit.py
  ~ tests\unit\test_audit_authority.py
  ~ tests\unit\test_contract_vocab.py
  + docs\EVALUATION-ARCH-D2.md
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-103118_v12-arch-d2
.\scripts\backup.ps1 -Restore -From 20260926-103118_v12-arch-d2
```

---
## `v11.1-arch-docs` · 2026-09-26 10:06:07

| 项 | 值 |
|---|---|
| 还原点 | `20260926-100606_v11.1-arch-docs` |
| 验证结果 | 单测 32/32 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 3 改动 / 0 新增 / 0 删除（对比 `20260926-100256_v11-arch-a1a-a4`） |
| 对比基准 | `20260926-100256_v11-arch-a1a-a4` |

**这一版做到了什么**

v11 之上补文档：CHANGELOG 27.5 记下备份前验证自己修的四处坑（backup.ps1 从未定义 python 变量、EAP=Stop 让子进程 stderr 终止备份、取到某个测试文件的通过数当全量、差异清单用管道数组相加报 op_Addition）+ check_webui_stream.py 缺 UTF-8 输出设置；EVALUATION-ARCH-A1A-A4 的 C4 改用最终实测（17 改动 / 7 新增 / 0 删除，共 24 个文件）并补记清单漏列的 check_webui_stream.py。要点：第 3、4 处的失败方式是诚实的——没有静默写一个错数字，而是把失败本身写进记录（未识别输出 / op_Addition 错误），这正是只增不改 + 如实记录要的效果。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ docs\CHANGELOG.md
  ~ docs\EVALUATION-ARCH-A1A-A4.md
  ~ docs\VERSIONS.md
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-100606_v11.1-arch-docs
.\scripts\backup.ps1 -Restore -From 20260926-100606_v11.1-arch-docs
```

---
## `v11-arch-a1a-a4` · 2026-09-26 10:02:57

| 项 | 值 |
|---|---|
| 还原点 | `20260926-100256_v11-arch-a1a-a4` |
| 验证结果 | 单测 32/32 · layout 通过 · typecheck 零错误 · 端到端 17/17 |
| 改了什么 | 17 改动 / 7 新增 / 0 删除（对比 `20260926-093147_v10-warnings-consumer`） |
| 对比基准 | `20260926-093147_v10-warnings-consumer` |

**这一版做到了什么**

架构级变更（用户已批准 P1-P5）A1a/A2/A3/A4。A1a：两个对账入口按职责切分——/api/audit 自述 authority=local-self-check 并声明跨侧归属以上游 /contract/check 为准；跨侧判定不再自造名字，id 直接用契约 rule code（P-event-unknown-to-frontend 等），ops 用契约采纳的 O-service-down；owner/severity 优先读契约 JSON 的 rule_crosswalk，手写镜像表降级为离线回退并由测试逐条比对；每条判定带 code 字段（空=契约写「无」）。过程被对账逼出三处自己的判错：契约版本没分方向（领先应判 backend/breaking，不分方向会把「后端没跟上」判成「前端要改」）、P-missing-field 级别判重了（契约明写字段可选=info）、_relabel 传契约 code 会落到默认归属把运维判成前端。一处声明偏离：P-phase-unknown 契约判 backend，本模块判 both（前端新画与上游删掉现象完全一样，事实源判不出方向），记在 audit.DEVIATIONS 并请统筹裁决。A2/A3：上游副本陈旧检测——实测自带副本 core 27 vs 上游 29，缺 contract.py 与 vision.py，9 个模块不一致；缺它会让新契约机制整体静默不可用而服务照常起、界面照常显示。新增 bridge/staleness.py（纯函数按目录取参，负向测试才写得了）+ 三个出口（启动横幅警告 / GET /api/health 暴露 backend_dir·backend_is_bundled·backend_stale / doctor.py 纳入结论）。严重度分两档：bundled 且落后=WARN（用自带副本是正当选择，判 FAIL 会让默认配置永远红着），外部却落后=FAIL（那是配错了）。A3 判据钉住：是 paths.BACKEND_DIR 不是「import 到了 core 就算对」。A4：docs/VERSIONS.md 由 backup.ps1 自动追加（逻辑在可测的 scripts/versions.py，因为纪律是只增不改而静默改写历史比没记录更糟）；与上游刻意不同：验证不过仍备份只如实标记。新增 test_staleness(34)/test_audit_authority(35)/test_versions(35)，check_contract_report 扩到 41（含双入口 owner 一致的在线证明）。备份前验证自身修了四处：backup.ps1 从来没定义 python 变量（引用到空）、预检把某个测试文件的通过数当成全量结果（须取最后一条）、控制台 GBK 让子进程 UTF-8 中文变乱码（预检局部改 OutputEncoding 且 check_webui_stream.py 补 reconfigure）、差异清单用管道数组相加在 5.1 下报 op_Addition（改显式 List）。

**改动清单**（机械核对，取自 `backup.ps1 -Verify`）

```
  ~ bridge\agent_api.py
  ~ bridge\app.py
  ~ bridge\audit.py
  ~ bridge\contract_vocab.py
  ~ CYCLE.md
  ~ docs\ARCHITECTURE.md
  ~ docs\CHANGELOG.md
  ~ docs\DIAGNOSTICS.md
  ~ docs\LAYOUT.md
  ~ docs\MODULES.md
  ~ docs\OPERATIONS.md
  ~ README.md
  ~ scripts\backup.ps1
  ~ scripts\doctor.py
  ~ tests\diagnostics\check_contract_report.py
  ~ tests\diagnostics\check_webui_stream.py
  ~ tests\unit\test_audit.py
  + bridge\staleness.py
  + docs\EVALUATION-ARCH-A1A-A4.md
  + docs\VERSIONS.md
  + scripts\versions.py
  + tests\unit\test_audit_authority.py
  + tests\unit\test_staleness.py
  + tests\unit\test_versions.py
```

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-100256_v11-arch-a1a-a4
.\scripts\backup.ps1 -Restore -From 20260926-100256_v11-arch-a1a-a4
```

---
## `v10-warnings-consumer` · 2026-09-26 09:31:47

| 项 | 值 |
|---|---|
| 还原点 | `20260926-093147_v10-warnings-consumer` |
| 验证结果 | 单测 29/29 · 契约测试 29/29 · 端到端 29/29 · layout 通过 · doctor 通过（服务侧 0 失败 2 提示） |
| 改了什么 | —（本条为**起点**：本文件在此之前不存在，没有可对比的机械记录） |

**这一版做到了什么**

契约 v1.0.5 的 `warnings` 消费方义务：① `bridge/audit.py` 按后端裁定分流 ops 事实——被传输层证伪的 `service_down`（送达了却报不可达）不驱动 verdict，只进 `warnings` + `ops` 栏；与本地观测矛盾的 `frontend_not_built` 同样只进 `warnings`；服务侧观测到未构建仍判 `ops-action`（契约实测举证 ops 优先未削弱）；未知事实名忽略；报 `false` 不成事实。② 履约消费方义务「展示 verdict 的消费方应当同时展示 warnings」：`to_dict()` 输出 `warnings`/`ops`（additive）、`to_markdown()` 的提示段排在分归属正文之前、前端 `audit.ts` 取用并兜底空、`TopBar.vue` 提示段渲染在阻塞项之前且徽标自带条数（否则不点开等于没展示）、界面显示 `ops` 栏（判断环境问题不能只看 verdict）。③ 自查抓到并修掉三件事：`_relabel` 传契约 code 会落到默认归属 `frontend`（把运维问题判成前端要改）、服务侧+客户端同报一条时重复计入 `responsibility`、我自己刚加的 `transport_reached` 参数会让 `service_down` 被静默丢弃（已删，恒为真的开关只制造缝隙）。④ 新增/更新断言：`test_audit` §9b 五条 ops 路径 + 无重复 id、`test_contract_vocab` §9 契约 `response_contract` 形状 + 跨语言核对前端确实展示 `warnings`、`check_contract_report` §4/5 端到端证伪路径。⑤ 新增 `docs/EVALUATION-OPS-WARNINGS.md`（按 C1–C8 自查，并就把 `warnings` 定义在上游端点/义务适用范围提出疑问请统筹确认）。单测 29/29、契约测试 29/29、端到端 29/29、layout/doctor 全过。

**还原**

```powershell
.\scripts\backup.ps1 -Verify  -From 20260926-093147_v10-warnings-consumer
.\scripts\backup.ps1 -Restore -From 20260926-093147_v10-warnings-consumer
```

---
