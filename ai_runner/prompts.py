from __future__ import annotations

from .state import TaskState
from .task import AiTaskConfig


def build_prd_review_prompt(prd_path: str, prd_content: str) -> str:
    return f"""你是资深需求评审与研发风险评估专家。

请评审下面的 PRD，并结合仓库代码、文档和 AGENTS.md 约定判断是否可以进入开发。

最终只能输出 JSON，字段如下：
- conclusion: APPROVED / REJECTED / NEED_CLARIFICATION / SPLIT_REQUIRED
- summary: 简短结论
- findings: 问题列表，每项包含 severity、area、message、evidence
- required_changes: 需求方必须修改或补充的事项
- suggested_dev_notes: 进入开发后需要注意的实现点

PRD 路径: {prd_path}

PRD 内容:
{prd_content}
"""


def build_split_prompt(prd_path: str, prd_content: str) -> str:
    return f"""你是资深技术负责人，请把已经通过评审的 PRD 拆成适合 AI 独立开发的小任务。

每个任务必须足够小，能独立验证，不要把多个模块的大改混到一个任务。

最终只能输出 JSON，字段如下：
- tasks: 数组，每项包含 title、body、labels
- notes: 拆分说明

每个 task.body 必须包含 GitHub Issue 正文，并包含 ai_task YAML 块：
ai_task:
  prd_path: {prd_path}
  type: feature
  validation:
    - 按项目实际情况填写验证命令
  max_attempts: 2
  docker_required: false

PRD 路径: {prd_path}

PRD 内容:
{prd_content}
"""


def build_develop_prompt(
    *,
    issue_number: int,
    issue_body: str,
    task_config: AiTaskConfig,
    prd_content: str,
    checkpoint: dict | None,
) -> str:
    checkpoint_text = "无历史 checkpoint。" if not checkpoint else str(checkpoint)
    validation = "\n".join(f"- {command}" for command in task_config.validation) or "- 未配置验证命令，请根据项目现状选择最直接验证方式。"
    return f"""你是本地 Codex CLI 开发执行器。

请在当前 worktree 内完成 Issue #{issue_number} 对应开发任务。

硬性要求：
- 只修改和当前任务直接相关的文件。
- 遵守 AGENTS.md、当前文件编码和中文注释风格。
- 不要提交代码，不要创建分支，不要合并 PR。
- 修改后尽量运行验证；无法运行时说明原因和可执行的人工验证方式。
- 最终输出简短 Markdown 总结，包含已完成内容、修改文件、验证结果、未覆盖风险、下一步。
- 如果上下文不足或任务过大，先写出 handoff 摘要并停止继续扩大修改。

建议验证命令：
{validation}

上次 checkpoint：
{checkpoint_text}

Issue 正文：
{issue_body}

关联 PRD 内容：
{prd_content}
"""


def build_review_prompt(task_state: TaskState | None = None) -> str:
    task_text = "" if not task_state else f"任务: {task_state.task_id}, 分支: {task_state.branch}"
    return f"""请以代码审查视角 review 当前 worktree 相对 base 分支的改动。

重点检查：
- 是否满足关联 PRD 和 Issue 的验收标准。
- 是否存在行为回归、边界遗漏、编码或中文乱码风险。
- 是否缺少必要测试或验证证据。

请优先列出问题，最后给出结论 PASS / NEEDS_FIX / BLOCKED。
{task_text}
"""

