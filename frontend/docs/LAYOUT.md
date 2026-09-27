# 目录归属与转移流程

**这份文档回答一件事：把上游最新版拿过来时，哪些覆盖、哪些千万别动。**

> 当前清单**不要手抄**——它是会漂的。跑 `python scripts/layout.py` 生成，
> 那份脚本按目录规则分类，文件增减自动反映。

---

## 1. 一张总表

| 目录 | 谁写的 | 转移上游时 |
|---|---|---|
| `backend/` | **上游**（我一行没改） | ✅ **整包替换**，或者更好：用 `AGENT_BACKEND_DIR` **指过去，不复制** |
| `bridge/` | **我**（上游根本没有这个目录） | 🛑 **绝对不要覆盖** |
| `frontend/` | **我** | 🛑 不要覆盖；改渲染时才动 |
| `tests/` | 上游原有 + 我加了 5 个、改了 3 个 | ⚠️ 只替换 `tests/unit/` 里**上游原有**的那些 |
| `docs/` | 上游原有 + 我大改 | ⚠️ 别整目录覆盖 |
| `scripts/` | **我** | 🛑 不要覆盖（备份 / 启动 / 迁移都在这儿） |
| `data/` | 跑出来的运行态 | ⛔ 与转移无关，忽略 |
| 根目录几个文件 | 上游原有 + 我改过 | ⚠️ 见下表逐个判断 |

### 根文件

| 文件 | 归属 | 转移时 |
|---|---|---|
| `backend/requirements.txt` | 我新增 | 上游若自带依赖清单，取它 |
| `README.md` | 上游原有，我大改 | ⚠️ 建议保留我的（含结构说明与工作方式） |
| `CYCLE.md` | 上游原有，我改了版本戳与结构引用 | ⚠️ 取上游新版后，重跑 `test_doc_consistency` |
| `能力评估报告.md` | **上游原有，我没动** | ✅ 可覆盖 |
| `.env.example` | 上游原有，我追加了前端变量 | ⚠️ 建议保留我的 |
| `.gitignore` | 上游原有，我改了（data/、bridge/、frontend/） | ⚠️ 建议保留我的 |
| `spec.override.example.json` | 我新增 | 🛑 不要覆盖 |

---

## 2. 转移流程（按情况选）

### 情况 A：拿到新的后端目录（最常见）

**首选：指过去，不复制。** 上游代码留在原地，bridge 从环境变量找到它：

```powershell
$env:AGENT_BACKEND_DIR = "D:\upstream\SimpleAgent2_Cycle\backend"
.\scripts\run.ps1
```

好处：**没有任何复制动作**，也就不存在"覆盖掉什么"的风险；
上游自己迭代，你这边只是换了个指向。写进 `.env` 就持久了。

**次选：复制进来**（想固定住某个版本时）：

```powershell
.\scripts\backup.ps1 -Label "before-adopt" -Note "换后端之前"
.\scripts\adopt-backend.ps1 -From D:\path\to\new\backend
python tests/run_unit.py
.\scripts\run.ps1
```

> 无论哪种方式，**验证方式一样**：`python scripts\doctor.py` 一条命令出结论。

`adopt-backend.ps1` 会：
- 把当前 `backend/` 备份到 `_backups/backend-<时间戳>/`
- 覆盖 `backend/`
- **契约自检**：bridge 依赖的 16 个上游接口还在不在，缺了哪个、会导致前端少看到什么，
  逐条列出来；并打印每个挂钩点的**实际签名**供比对

全绿就完事了，**正常情况下一行代码都不用改**。

### 情况 B：拿到的是**整个上游项目文件夹**

🛑 **不要把它整个覆盖到本项目上。** 那会抹掉 `bridge/`、`frontend/`、`scripts/`
和你的运行态配置——而且服务照常起得来，只是没有 `/api/*`、没有前端，**静默失效**。

正确做法：**只把它的 `backend/` 取出来**，然后按情况 A 走。

```powershell
# 假设上游新项目在 D:\upstream\SimpleAgent2_Cycle
.\scripts\adopt-backend.ps1 -From D:\upstream\SimpleAgent2_Cycle\backend
```

上游的 `tests/` 与 `docs/` 也想同步的话，**逐个文件比**，别整目录覆盖：

| 想同步 | 安全做法 |
|---|---|
| 上游测试 | 只覆盖 `tests/unit/` 里那 21 个上游原有文件；**跳过**我新增的 5 个与改过的 3 个 |
| 上游文档 | 只取 `CYCLE.md`、`能力评估报告.md`、`docs/PUSH_TO_GITHUB.md`；其余是我改过的 |

---

## 3. 千万别被覆盖的清单

这些文件**上游没有**，或者**含了上游没有的设计**。一旦被覆盖，症状是"服务起得来但前端死了"：

```
bridge/                              整个目录（适配层）
frontend/                            整个目录
scripts/                             整个目录
data/                                运行态
spec.override.example.json
docs/CHANGELOG.md                    修复记录（上游没有）
docs/LAYOUT.md                       本文件

tests/_bootstrap.py                  sys.path 指向 backend/、CWD 切到运行根
tests/unit/test_isolation.py         ★ 隔离看门
tests/unit/test_event_contract.py    ★ 事件词表契约
tests/unit/test_spec.py              ★ 标定一致性
tests/unit/test_webui_runtime.py
tests/diagnostics/check_webui_stream.py
```

其中**三个新测试是"别被覆盖"的自动守卫**：

| 测试 | 被覆盖后它会报什么 |
|---|---|
| `test_isolation.py` | `backend/` 里出现了 bridge 痕迹 / 仓库根冒出 `workspace/` |
| `test_event_contract.py` | 前端认得的事件与后端发的不一致 |
| `test_spec.py` | 标定里的阶段不再是上游 `PHASE_ORDER` / 端点对不上真实路由 |

所以**转移完先跑 `python tests/run_unit.py`**，它会替你抓。

---

## 4. 当前清单（生成，勿手抄）

```bash
python scripts/layout.py            # 完整分类树
python scripts/layout.py --counts   # 只要数量
python scripts/layout.py --json     # 给脚本消费
python scripts/layout.py --check    # 有没归类的顶层目录就返回非零
```

拿到手的样子（本次实测）：

```
上游后端 backend/       46 项   ← 整包替换
适配层 bridge/          15 项   ← 别覆盖
前端 frontend/          29 项   ← 别覆盖
测试 · 上游原有          27 项
测试 · 我新增/改过        8 项   ← 别覆盖
文档 · 上游原有           2 项
文档 · 我改过             9 项   ← 别覆盖
脚本 scripts/            4 项   ← 别覆盖
根目录文件                1 项
运行态 data/             1 项   ← 忽略
```

**`--check` 建议加进回归清单**：将来谁在根目录新加一个目录却忘了归类，它会报出来。

---

## 5. 转移后的验证清单

按顺序跑，任何一步红了都别继续：

```powershell
# 1) 隔离没被破坏（上游是纯上游、运行根生效、仓库根没被污染）
python tests/unit/test_isolation.py

# 2) 事件词表两边一致
python tests/unit/test_event_contract.py

# 3) 标定与上游事实一致
python tests/unit/test_spec.py

# 4) 全量
python tests/run_unit.py

# 5) 端到端（需服务在跑）
.\scripts\run.ps1
python tests/diagnostics/check_webui_stream.py
```

---

## 6. 为什么不是"改上游几行就完事"

因为你的工作流是**复制**，不是 `git pull`。复制是**覆盖式**的：

- 写在上游文件里的东西 → 被抹掉，**而且不报错**；
- 写在上游之外的目录里的东西（`bridge/`）→ 安然无恙。

这就是 §20 把集成代码从 `backend/` 搬进 `bridge/` 的全部理由，
也是本文档存在的原因——**转移这件事本身需要一个明确的操作规程**。

---

## 7. 为什么可以「指过去」而不是「复制过来」

后端是**服务**。它不需要住在你的仓库里——只要 bridge 能在**同一个进程**里
import 到它就行。所以用一个环境变量指向它的位置：

```powershell
$env:AGENT_BACKEND_DIR = "D:\upstream\SimpleAgent2_Cycle\backend"
```

**为什么必须同进程，不能是纯远端服务**：进度事件靠**运行时挂钩**（见
`bridge/UPSTREAM.md`）。挂钩要求上游代码在本进程内可 import。
如果后端是纯 HTTP 黑盒，你只能看到 `/encode` 的最终返回——
没有 round / task / tool 级过程，可视化会退化成"一个转圈图标"。

所以三者的取舍是：

| 方案 | 前端能力 | 成本 |
|---|---|---|
| bridge 与上游**同进程**，`AGENT_BACKEND_DIR` 指过去 | 完整（全量事件） | 上游要在同机可读 |
| bridge 与上游同进程，代码复制进 `backend/` | 完整 | 有复制/覆盖动作 |
| 上游独立部署，bridge 当纯 HTTP 客户端 | **大幅降级**（无过程事件） | 上游零耦合，但要接受看不到进度 |

**推荐第一种。** 第二种作为"固定版本"的兜底保留。

### 7.1 ★ 判据是 `paths.BACKEND_DIR`，不是「import 到了 `core` 就算对」

这一条容易搞错，而且**搞错了不会报错**：

```
<仓库>/backend/core/    ← 自带副本的 core（27 个模块）
<上游>/core/            ← 上游的 core（29 个模块）
```

两个包**同名**。`import core` 成功只说明 `sys.path` 里有它，
**完全不能说明用的是哪一份** —— 谁生效只取决于 `sys.path` 的顺序。

唯一正确的判据是 `paths.BACKEND_DIR`（由 `AGENT_BACKEND_DIR` 决定，
默认才是仓库自带的副本）。它有三个可查的出口：

| 出口 | 怎么看 |
|---|---|
| 探针 | `GET /api/health` → `backend_dir` / `backend_is_bundled` / `backend_stale` |
| 体检 | `python scripts\doctor.py` → 「路径与隔离」节 |
| 启动日志 | bundled 模式会打 `!` × 72 的横幅警告 |

**为什么值得单独说**：自带副本缺 `core/contract.py` 时，
新契约机制（`CONTRACT_VERSION` / `ISSUE_RULES` / `/contract/check`）
**整体静默不可用**，而服务照常启动、界面照常显示、没有一处报错。
`bridge/staleness.py` 就是治它的（`tests/unit/test_staleness.py` 用负向测试钉住）。

出错时怎么查：`python scripts\doctor.py`——它自己采集、自己判断、自己给结论，
不需要你整理报告。详见 `docs/DIAGNOSTICS.md`。

**兼容性也不用你比**：服务起来后 `GET /api/audit` 自审（我声明的我真的做了吗），
前端启动时 `POST /api/audit` 报上自己的期望，服务直接判
「该改前端」还是「后端接口定义有问题」。顶栏有徽标，点开是分好归属的清单。
详见 `docs/DIAGNOSTICS.md` §7 与 §7.4（两个入口的**职责切分**：
跨侧归属以上游 `/contract/check` 为准，`/api/audit` 管本地自检）。
