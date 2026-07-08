# 需求 PR 与 AI 评审流程

本目录用于存放已经通过评审的需求文档。每个需求使用一个 Markdown 文件，文件名建议使用日期加需求名称，例如：

```text
docs/requirements/2026-07-用户列表手机号搜索.md
```

## 流程

1. 从 `main` 新建需求分支，分支名建议为 `prd/需求简写`。
2. 复制 `_template.md`，填写完整需求内容。
3. 提交 Pull Request，标题格式为 `PRD: 需求名称`。
4. 给 PR 添加 `prd-review` 标签，并指定开发负责人评审。
5. 开发负责人运行 AI Runner 或把 PRD 内容/PR diff 交给 AI 评审。
6. 评审不通过时，在 PR 评论中贴出 AI 评审意见，添加 `prd-rejected` 标签，需求人员继续修改同一个 PR。
7. 评审通过时，添加 `prd-approved` 和 `ready-for-dev` 标签，由开发负责人合并 PR。
8. 合并后再创建开发 Issue，Issue 必须关联已经合并的 PRD 文件。

## Runner 命令

```bash
python -m ai_runner.runner review-prd --prd docs/requirements/xxx.md
python -m ai_runner.runner split-prd --prd docs/requirements/xxx.md
python -m ai_runner.runner develop-issue --issue 123
python -m ai_runner.runner review-pr --worktree .ai-worktrees/issue-123 --task-id issue-123
```

详细说明见 `docs/ai-runner.md`。

## AI 评审清单

- 目标是否清楚。
- 业务边界是否明确。
- 验收标准是否可测试。
- 异常场景是否完整。
- 权限与数据范围是否说明清楚。
- 是否存在与现有系统冲突或遗漏的上下游影响。

## 状态标签

- `prd-review`：等待 AI 评审。
- `prd-rejected`：需求评审不通过，需要需求人员补充或修改。
- `prd-approved`：需求评审通过。
- `ready-for-dev`：可以进入开发。
- `ai-dev`：等待 AI Runner 开发。
- `ai-review`：等待 AI Review。
- `ai-blocked`：AI Runner 无法继续，需要人工处理。
- `human-review`：AI 流程已完成，等待人工 review/合并。
