# AI Runner 快速试跑说明

## 背景

当前 `docs/ai-runner.md` 已经说明了 AI Runner 的各个命令，但新使用者需要在多个小节之间来回查找，才能串起一次最小可行的试跑流程。为了方便验证需求评审、任务拆分、开发执行和状态查看流程，需要在文档中增加一个更短的快速试跑入口。

## 目标

在 `docs/ai-runner.md` 中增加“快速试跑”小节，让使用者可以按顺序复制少量命令，完成一次不写入 GitHub 的本地试跑。

## 业务规则

快速试跑小节只说明本地 dry-run 和状态查看流程。命令顺序应包含初始化、PRD 评审 dry-run、查看状态三步。说明文字应明确 `--dry-run` 不会真实调用 AI 生成评审结果，也不会创建 Issue、PR 或修改远端 GitHub 数据。

## 页面/接口变化

仅修改文档 `docs/ai-runner.md`。不新增命令行参数，不修改 Runner 行为，不调整 GitHub 模板。

## 异常场景

如果本地没有安装 Codex CLI，文档不需要新增排障说明，继续引用已有“前置条件”小节。命令执行失败时，由现有 Runner 输出错误信息。

## 权限与数据范围

不涉及业务权限和数据范围。该说明仅面向本仓库维护者或试用 AI Runner 的开发人员。

## 验收标准

- `docs/ai-runner.md` 中新增“快速试跑”小节。
- 小节包含初始化 Runner 的命令。
- 小节包含对示例 PRD 执行 `review-prd --dry-run` 的命令。
- 小节包含查看 Runner 状态的命令。
- 小节说明 `--dry-run` 不会创建 Issue、PR 或写入 GitHub。
- 修改后运行 `python -m unittest discover -s tests` 通过。

## 不在本次范围

不实现新的 Runner 功能。不接入 GitHub Actions。不创建真实 GitHub Issue 或 PR。不调整 Codex CLI 调用参数。
