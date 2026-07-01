# GitHub 标签配置

当前 MVP 需要在 GitHub 仓库手动创建以下标签：

| 标签 | 用途 |
| --- | --- |
| `prd-review` | 等待 AI 评审 |
| `prd-rejected` | 需求评审不通过，需要修改 |
| `prd-approved` | 需求评审通过 |
| `ready-for-dev` | 可以进入开发 |

GitHub 页面操作路径：

```text
仓库 -> Issues -> Labels -> New label
```

第一阶段先手动维护标签。后续接入 GitHub Actions 或 Bot 后，再自动增删标签和回写评审意见。
