# GitHub 标签配置

当前 MVP 需要在 GitHub 仓库手动创建以下标签：

| 标签 | 用途 |
| --- | --- |
| `prd-review` | 等待 AI 评审 |
| `prd-rejected` | 需求评审不通过，需要修改 |
| `prd-approved` | 需求评审通过 |
| `ready-for-dev` | 可以进入开发 |
| `ai-dev` | 等待 AI Runner 开发 |
| `ai-review` | 等待 AI Review |
| `ai-blocked` | AI Runner 无法继续，需要人工处理 |
| `human-review` | AI 流程已完成，等待人工 review/合并 |

GitHub 页面操作路径：

```text
仓库 -> Issues -> Labels -> New label
```

第一阶段先手动维护标签。Runner 接入 `gh` CLI 后，可以自动增删标签、回写评审意见、创建 Issue 和 PR。
