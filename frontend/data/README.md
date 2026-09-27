# data/ —— 运行态数据

这里的全部内容都是**跑出来的**，不是写出来的。它和 `backend/`、`frontend/`
分开是刻意的：源码需要版本管理，运行产物需要能随时删掉重来。

路径的唯一来源是 `backend/paths.py`——**不要在任何地方自己拼 `data/...`**，
更不要用 `os.path.abspath("...")`（那是 CWD 相对的，换个目录启动就会在别处
静默新建一套空目录）。

| 目录 | 内容 | 对应常量 |
|---|---|---|
| `workspace/` | 模型写出的代码。**内含一个独立 git 仓库**，回退机制靠它 | `paths.WORKSPACE_DIR` |
| `storage_data/` | 事件流、压缩快照、人工决策、技能库 | `paths.STORAGE_DIR` |
| `sessions/` | 每次 run 的完整任务记录（JSON） | `paths.SESSIONS_DIR` |

`storage_data/` 的细分：

```
storage_data/
  events.jsonl          原始事件，只增不改（压缩快照的输入）
  meta.json             事件序号
  snapshots/            每个 cycle 一个压缩快照（派生视图，可重算）
  runs/<run_id>/        前端订阅的那条实时流
    ├─ meta.json            运行状态与最终报告
    └─ events.jsonl         追加型事件流（SSE 读的就是它）
  decisions/            一决策一文件（跨进程存活，手机端可作答）
  skills/               ★ 例外：技能是**资产**，会入库
  skill_candidates/     封装候选（归纳产物，未经验证）
  skill_staging/        副本区（审核通过，待实测）
```

## 想清空？

```powershell
# 只清模型产出，保留事件与技能
Remove-Item -Recurse -Force data/workspace/*

# 全部重来（技能库也会没）
Remove-Item -Recurse -Force data/*
```

删掉后无需手动重建：`backend/paths.py` 的 `ensure_dirs()` 会在启动时补齐。
