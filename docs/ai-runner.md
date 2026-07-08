# Codex CLI AI Runner MVP

本方案使用 GitHub 作为入口和审计源，使用本地 Runner 调用 Codex CLI 完成需求评审、任务拆分、开发执行和代码 review。

## 前置条件

- Python 3.11 或更高版本。
- 本地已安装并登录 Codex CLI。
- 如果需要回写 GitHub 评论、创建 Issue 或创建 PR，需要安装并登录 `gh` CLI。

## 快速试跑

完成“前置条件”后，可以按顺序复制以下命令完成一次本地 dry-run：

```bash
python -m ai_runner.runner init
python -m ai_runner.runner review-prd --prd docs/requirements/2026-07-用户列表手机号搜索.md --dry-run
python -m ai_runner.runner status
```

`--dry-run` 不会真实调用 AI 生成评审结果，也不会创建 Issue、PR 或修改远端 GitHub 数据。

## 初始化

```bash
python -m ai_runner.runner init
```

该命令会创建 `.ai/state/runner.sqlite3` 和 `.ai-worktrees/`。这两个目录不会提交到 Git。

## 查看状态

```bash
python -m ai_runner.runner status
python -m ai_runner.runner status --task-id issue-123
python -m ai_runner.runner status --json
```

`--dry-run` 只会打印将要执行的 Codex CLI 命令，并记录一条 `DRY_RUN` 状态，不会生成真实 AI 评审结果。

Runner 会通过 stdin 把完整 prompt 传给 Codex CLI，避免在命令行里直接展开整篇 PRD。真实运行时控制台只打印最终结果和状态路径，不打印 Codex JSONL 中间事件。

## 评审 PRD

```bash
python -m ai_runner.runner review-prd --prd docs/requirements/2026-07-用户列表手机号搜索.md
```

如需把结果回写到 PR：

```bash
python -m ai_runner.runner review-prd --prd docs/requirements/xxx.md --pr 12 --post-comment
```

如果当前终端还没有刷新 PATH，可以显式指定 `gh.exe`：

```bash
python -m ai_runner.runner --gh-bin "C:\Program Files\GitHub CLI\gh.exe" review-prd --prd docs/requirements/xxx.md --pr 12 --post-comment
```

评审结论固定为 `APPROVED`、`REJECTED`、`NEED_CLARIFICATION`、`SPLIT_REQUIRED`。

## 拆分开发任务

```bash
python -m ai_runner.runner split-prd --prd docs/requirements/xxx.md
```

确认输出无误后，可以创建 GitHub Issue：

```bash
python -m ai_runner.runner split-prd --prd docs/requirements/xxx.md --create-issues
```

## 执行开发任务

开发 Issue 需要包含 `ai_task` 配置块：

```yaml
ai_task:
  prd_path: docs/requirements/xxx.md
  type: feature
  validation:
    - python -m unittest discover -s tests
  max_attempts: 2
  docker_required: false
```

执行开发：

```bash
python -m ai_runner.runner develop-issue --issue 123
```

没有 `gh` CLI 时，可以先把 Issue 正文保存为本地文件：

```bash
python -m ai_runner.runner develop-issue --issue 123 --issue-body-file .ai/examples/issue-123.md
```

开发完成后如需提交、推送并创建 PR：

```bash
python -m ai_runner.runner develop-issue --issue 123 --commit --push --create-pr
```

## 代码 Review

```bash
python -m ai_runner.runner review-pr --worktree .ai-worktrees/issue-123 --task-id issue-123
```

该命令会调用 `codex exec review --uncommitted --base main`，只负责 review，不会合并代码。

## 恢复策略

Runner 状态保存在 SQLite 中，每个任务记录 `task_id`、`issue_number`、`branch`、`worktree_path`、`phase`、`attempt`、`status`、`last_checkpoint`、`last_error`、`heartbeat_at`。

查询超时任务：

```bash
python -m ai_runner.runner resume-stale --older-than-minutes 30 --dry-run
```

标记为待恢复：

```bash
python -m ai_runner.runner resume-stale --older-than-minutes 30
```

随后重新执行对应的 `develop-issue` 命令，Runner 会复用已有 worktree、分支和 checkpoint。
