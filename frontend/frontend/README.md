# SimpleAgent Frontend

`SimpleAgent2_Cycle` 的 Vue 3 执行可视化前端。目标只有一个：**让执行过程看得见**。

后端 `POST /encode` 是阻塞的（一轮 cycle 60~300 秒），所以这里的进度不来自
轮询它的返回，而是订阅 `POST /api/runs` 起的**异步运行**：拿 `run_id`，再连
`GET /api/runs/{id}/stream` 的 SSE。

## 快速开始

```bash
npm install
npm run build          # 产物 → frontend/dist
```

然后在**后端**起服务（`.\scripts\run.ps1`，或 `cd backend` 后起 uvicorn），
打开 <http://127.0.0.1:8000/app>。

> `frontend/dist` 不存在时后端**不会注册 `/app`**，其余接口一切照常——
> 前端是可选视图，不该成为后端起不来的原因。

开发模式（HMR，API 由 Vite 代理到 `http://127.0.0.1:8000`）：

```bash
npm run dev            # http://127.0.0.1:5173
```

代理的后端地址可用环境变量覆盖：

```bash
AGENT_BACKEND=http://192.168.1.10:8000 npm run dev
```

## 命令

| 命令 | 作用 |
|---|---|
| `npm run dev` | 开发服务器（HMR，代理 `/api`） |
| `npm run build` | 构建到 `dist/` |
| `npm run typecheck` | `vue-tsc --noEmit`，零错误是当前的基线 |
| `npm run preview` | 预览构建产物（**注意**：此时 `/api` 无代理，只适合看静态骨架） |

## 目录

```
src/
  main.ts                  挂载入口
  App.vue                  布局 + 生命周期（起运行 / 订阅 / 轮询 / 历史回放）
  types.ts                 事件与视图模型（事件词表即契约）
  api/
    client.ts              REST 客户端
    sse.ts                 基于 fetch 流的 SSE 解析 + 按 seq 自动续订
  store/
    run.ts                 事件 → 界面状态的唯一归约器
  composables/
    useTween.ts            数字缓动 / 时长格式化
    useClock.ts            让耗时自己走的心跳
  components/
    TopBar.vue             后端 / 模型 / 事件流连接状态
    LaunchPanel.vue        目标、验收命令、预算、演示运行
    StatStrip.vue          尝试 / 轮次 / 步数 / 工具 / 产物 / 回退 / 耗时
    PipelineFlow.vue       ★ 六阶段流水线动画
    AttemptTrack.vue       尝试轨迹（成败 / 耗时 / 是否回退）
    ActivityFeed.vue       ★ 实时事件流
    TaskPanel.vue          任务、子循环步数、主模型推理
    VerifyPanel.vue        门禁结果（MANIFEST / CHECK / VERIFY）
    ArtifactPanel.vue      产物文件（点击查看内容）与工具调用
    RunHistory.vue         历史运行（点击回放）
    DecisionBar.vue        人工决策条（内联作答）
  styles/theme.css         主题、动画关键帧、通用零件
```

## 两个刻意的设计选择

### 1. 不用 `EventSource`

后端的 SSE 用的是**具名事件**（`event: tool_call`）。`EventSource` 对具名事件必须
逐个 `addEventListener`，事件词表一扩展前端就静默漏事件；而且它不能带
`after=<seq>` 参数续订。

`src/api/sse.ts` 用 `fetch` + `ReadableStream` 自己解析（约 130 行），换来：

- 事件词表随便扩展，`onEvent` 都能收到；
- 断线后带 `lastSeq` 重连，**不重复也不丢**；
- 服务端的 `close` 事件是一次明确的收尾信号，而不是靠超时猜。

### 2. 事件只在 `store/run.ts` 里被解释一次

组件不解析事件。好处是：

- **实时流与历史回放共用同一段代码**——回放就是把历史事件重新喂一遍；
- 动画需要的中间态（哪个阶段刚变成 active、第几次尝试、当前任务）有唯一来源；
- 后端加事件时只改一处。

归约器里有一个容易踩的坑，已经写在注释里：**回放历史时必须用事件自带的
时间戳，而不是 `Date.now()`**（`applyEvent(state, ev, now)` 的 `now` 参数）
——否则「耗时」会变成「从事件发生到现在过了多久」，实测把 7.0s / 8.0s
显示成了 75.2s / 67.2s。

## 事件词表

前端认识的事件。**后端事实由 `bridge/hooks.py` 在运行时从上游包装出来**——
上游 `backend/` 里没有任何埋点。词表由 `tests/unit/test_event_contract.py` 把守：
两边对不上就红，并指出是哪个 kind、来自哪个文件。
未认识的 `kind` 会进时间线但不改变状态，所以后端加事件不会让界面崩。

| 分类 | kind |
|---|---|
| 运行 | `queued` `run_start` `baseline` `cycle_start` `run_end` `cancelled` `error` |
| 尝试 | `attempt_start` `retry` `phase` `rollback` `cycle_end` |
| 计划 | `round_start` `orchestrator_decision` `plan` `task_result` |
| 执行 | `task_start` `worker_step` `model_reply` `tool_call` `tool_result` `task_done` `files` |
| 门禁 | `manifest` `syntax` `lint` `verify_probe` `verify` |
| 决策 | `decision_opened` `decision_notified` `decision_action` `rollback_denied` |

## 想看完整流程但不想等模型？

点界面上的 **「演示运行」**，或直接：

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"goal":"演示","demo":true}'
```

演示运行（`bridge/demo.py`）不发一次模型请求，但走的是**同一套事件词汇和同一个
SSE 通道**，脚本里刻意包含一次
「manifest 失败 → 回退 → 重试 → 通过」，把重试动画和回退标记都能看到。

## 自检

```bash
npm run typecheck                              # 前端类型
python tests/unit/test_frontend_runtime.py        # 离线：进度总线 + 运行管理器
python tests/diagnostics/check_frontend_stream.py # 需后端在跑：SSE 端到端
```
