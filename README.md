# SimpleAgent2

一个**会自己写代码、并且不肯口头宣称"我做完了"**的编码智能体。
本仓库是它的完整源码：后端（执行内核）+ 前端（可观测 Web 界面）。

---

## 目录结构

| 目录 | 是什么 | 自己的说明 |
|---|---|---|
| [`backend/`](backend/) | 执行内核：编排循环、强制检查、机器可判定的验证、检查点/回退、契约自检 | [`backend/README.md`](backend/README.md) |
| [`frontend/`](frontend/) | Vue 3 界面 + `bridge/` 适配层（把上游事件流转成可观测的实时界面） | [`frontend/README.md`](frontend/README.md) |

两侧**版本号刻意不通用**：两个仓库各自演进，跨侧唯一的刻度是上游契约的
`CONTRACT_VERSION`。各自的版本记录见 `backend/docs/VERSIONS.md` 与
`frontend/docs/VERSIONS.md`（**含逐版本的改动、验证结果与还原命令**）。

---

## 它想解决的那个问题

一般的编码 agent 的失败方式是**「说自己做完了」**。本项目的立场是：

> **「目标是否达成」由机器可判定的判据决定，不由模型自述决定。**

由此有一串具体的设计（都能在源码里找到，也都有对应的测试）：

- **强制检查阶段**：语法 → lint → 交付清单（manifest）逐层拦；
- **验证必须可机器判定**：`verify_command` 的退出码说了算；
- **调用方的判据是权威的**：模型可以决定「怎么实现」，不能改写「什么叫对」；
  只有调用方没给时，才采纳模型自拟的判据 —— 且**自拟判据有一条可机器判定的下限**
  （必须引用本轮真实交付物，`print('PASS')` 这类恒真判据会被拒绝）；
- **不许静默降级**：验证被跳过、判据被拒、检查阶段"没东西可查"，
  都会作为**显式事实**留在事件流与报告里，而不是消失在一个绿灯里；
- **检查点与回退**：每一轮都可退回上一个可行状态。

> 这个项目里最贵的一课是：**观察到的绿灯不等于被验证过的绿灯。**
> 所以它的门禁大多是"**能被证明会红**"的 —— 包括给门禁自己写负向测试。

---

## 快速开始

两端都需要，先起后端再起前端。

```bash
# 后端
cd backend
python -m venv .venv && .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env                                # 按需改模型档位
python -m uvicorn main:app --port 8000

# 前端（bridge 同时提供 API 与已构建界面）
cd frontend
npm install
npm run build
# 关键：把后端指向 backend/ 的这份源码
# PowerShell: $env:AGENT_BACKEND_DIR="<本仓库绝对路径>/backend"
uvicorn bridge.app:app --port 8000
```

**默认模型档位是本地 Ollama 上的 `qwen2.5:7b`**（见 `.env.example`）。
换模型改 `.env` 里的 `ORCH_*` / `WORKER_*` 即可。

各项目自己的运行、测试与排查细节，见它们各自的 `README.md` 与 `docs/OPERATIONS.md`。

---

## 本仓库刻意**不含**的内容

| 不含 | 为什么 |
|---|---|
| `.env`（只有 `.env.example`） | 含 API key / base_url 等本地凭据 |
| `storage_data/`、`sessions/`、`data/workspace/` | 运行时产物与模型生成的中间文件；**技能（`storage_data/skills/`）除外，那是资产** |
| `.venv/`、`node_modules/`、`.npm-cache/` | 体积大且可由锁文件重建 |
| `_backups/` | 本地回退快照，每台机器各不相同 |
| `frontend/backend/` | **前端仓库里那份自带的后端副本**。它只是"开箱即跑"的便利，会**落后于** `backend/`（实测曾落后到缺 `core/contract.py`），是「以为在跑新代码、其实在跑旧代码」这一类事故的源头。**本仓库只保留 `backend/` 这一份权威源码。** |

> 最后一条值得单独说：那份副本造成过一次真实事故 ——
> 上游连修几轮，而实例一直在跑副本，**所有修复一条都没生效**，且**没有任何症状**。
> 因此前端现在会在解析到该副本时**拒绝启动**，并要求显式设置 `AGENT_BACKEND_DIR`。
