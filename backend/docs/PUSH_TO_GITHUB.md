# 推送到 GitHub —— 需要你手动填写的信息

本文件是**模板**。里面的 `__PLACEHOLDER__` 需要你替换成真实值。
但请注意下面的使用方式：**不要把填好的凭据提交进仓库**。

---

## 你需要提供的信息

| 项 | 说明 | 示例 |
|---|---|---|
| `GH_USER` | GitHub 用户名 | `yourname` |
| `GH_REPO` | 仓库名（建议新建一个空仓库） | `SimpleAgent2_Cycle` |
| `GH_TOKEN` | Personal Access Token（**仅当用 HTTPS 推送时**） | `ghp_xxx` |
| 可见性 | public / private | 建议先 private |

**Token 的作用域**：`repo`（private 仓库）或 `public_repo`（仅 public）。
在 GitHub → Settings → Developer settings → Personal access tokens 生成。
**不要把 token 写进任何文件。**

---

## 方式 A：手动推送（推荐，你不用把 token 给我）

```bash
cd D:\PythonProject\SimpleAgent2_Cycle

# 首次推送前，仓库自身的 git 身份（与 workspace 里 agent 用的身份独立）
git config user.name  "__YOUR_NAME__"
git config user.email "__YOUR_EMAIL__"

# 新增 remote；这一步会把 URL 写进 .git/config
git remote add origin https://github.com/__GH_USER__/__GH_REPO__.git

git add -A
git status          # ★ 提交前务必看一眼，确认没有 .env / token / storage_data
git commit -m "initial commit"
git push -u origin main
```

**关于 token 与 URL**：如果用
`https://__GH_USER__:__GH_TOKEN__@github.com/...` 这种带 token 的 URL，
token 会明文写进 `.git/config`。虽已加入 `.gitignore`（`.gitconfig.local`），
但 `.git/config` 本身**不在**忽略范围内——它属于仓库元数据。
更安全的做法是用 credential helper 或 SSH：

```bash
# 让 git 记住凭据（存在系统凭据管理器，不落盘到仓库）
git config --global credential.helper manager
```

**如果误把 token 提交了**：立刻在 GitHub 上 revoke 该 token，
然后 `git filter-repo` 或重建仓库——**仅仅删除文件再提交是不够的，历史里还在**。

---

## 推送前的自检清单

在 `git add -A` 之后、`git commit` 之前跑：

```bash
git status --short
```

确认**没有**以下内容：

- [ ] `.env`（含 API key）
- [ ] `storage_data/`（运行事件与快照）
- [ ] `.checkpoints/`（回退快照）
- [ ] `tests/output/`（跑批产物）
- [ ] `workspace/` 下模型产出的代码（除非你想留作示例）
- [ ] 任何含 token / secret / key 的文件
- [ ] `.idea/`

已经加进 `.gitignore` 了，但**首次提交前请亲眼确认一遍**。

### 一键排查（不依赖工具）

```bash
# 列出将要提交的文件
git diff --cached --name-only

# 在暂存内容里搜敏感词
git diff --cached | grep -iE "ghp_|github_pat_|api[_-]?key|secret|password|token"
```

> 第二条命令命中不代表一定有问题（文档里提到了 "token" 这个词也会命中），
> 但每一条命中都要人工确认。

---

## 当前仓库已有的 git 状态说明

注意：**`workspace/` 目录里已经有一个独立的 git 仓库**（由 agent 的回退机制创建），
用于每轮编码打检查点。它与你要推送的项目仓库是**两个不同的仓库**。

- 项目仓库：`D:\PythonProject\SimpleAgent2_Cycle`（本次要推送的）
- agent 回退仓库：`D:\PythonProject\SimpleAgent2_Cycle\workspace`

如果直接把项目仓库初始化并 `git add -A`，`workspace/.git` 会被当作嵌套仓库
处理（git 会提示 "adding embedded git repository"，且只记录一个 gitlink 而非内容）。
这**通常不是你想要的结果**。

两种处理方式：

**方式 1（推荐）：忽略 workspace 的内容**

```bash
echo "workspace/" >> .gitignore
```

适合"workspace 只是模型产出，不该进版本库"的定位。

**方式 2：让 workspace 作为普通目录入库，但不含它自己的 .git**

```bash
# 提交前删掉它的 git 元数据（会丢失回退历史）
rm -rf workspace/.git
```

适合"想把模型产出的示例代码一并公开"的场景。

**本文件不替你决定**——取决于你想不想公开 workspace 内容。

---

## 我不会做的事

- 不会执行 `git push`
- 不会读取或存储你的 token
- 不会把凭据写进任何文件

仓库的 `.gitignore` 已经挡掉了常见凭据文件名。
