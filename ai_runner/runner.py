from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from .executor import CodexCliExecutor
from .github import GitHubCli, IssueData
from .git_ops import GitOps
from .prompts import build_develop_prompt, build_prd_review_prompt, build_review_prompt, build_split_prompt
from .state import DEFAULT_DB_PATH, RunnerState
from .task import load_json_from_text, parse_ai_task_config, read_text, slugify


REPO_ROOT = Path.cwd()
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex CLI 驱动的 AI 需求评审与自动开发 Runner")
    parser.add_argument("--state-db", type=Path, default=DEFAULT_DB_PATH, help="SQLite 状态库路径")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI 命令路径")
    parser.add_argument("--gh-bin", default="gh", help="gh CLI 命令路径")
    parser.add_argument("--model", default=None, help="可选 Codex 模型")

    subparsers = parser.add_subparsers(required=True)

    init_parser = subparsers.add_parser("init", help="初始化 Runner 状态目录和数据库")
    init_parser.set_defaults(func=cmd_init)

    status_parser = subparsers.add_parser("status", help="查看 Runner 任务状态")
    status_parser.add_argument("--task-id", default=None, help="只查看指定任务，例如 issue-123")
    status_parser.add_argument("--limit", type=int, default=20, help="最多显示最近多少个任务")
    status_parser.add_argument("--json", action="store_true", help="输出 JSON")
    status_parser.set_defaults(func=cmd_status)

    review_parser = subparsers.add_parser("review-prd", help="评审 PRD Markdown 文件")
    review_parser.add_argument("--prd", type=Path, required=True)
    review_parser.add_argument("--pr", type=int, default=None, help="可选：回写评论的 PR 编号")
    review_parser.add_argument("--post-comment", action="store_true", help="使用 gh CLI 回写 PR 评论")
    review_parser.add_argument("--dry-run", action="store_true")
    review_parser.set_defaults(func=cmd_review_prd)

    split_parser = subparsers.add_parser("split-prd", help="把 PRD 拆分为开发 Issue 草稿")
    split_parser.add_argument("--prd", type=Path, required=True)
    split_parser.add_argument("--create-issues", action="store_true", help="使用 gh CLI 创建 Issue")
    split_parser.add_argument("--dry-run", action="store_true")
    split_parser.set_defaults(func=cmd_split_prd)

    develop_parser = subparsers.add_parser("develop-issue", help="执行开发 Issue")
    develop_parser.add_argument("--issue", type=int, required=True)
    develop_parser.add_argument("--issue-body-file", type=Path, default=None)
    develop_parser.add_argument("--issue-title", default=None)
    develop_parser.add_argument("--base", default="main")
    develop_parser.add_argument("--commit", action="store_true", help="验证通过后自动提交")
    develop_parser.add_argument("--push", action="store_true", help="提交后推送远端分支")
    develop_parser.add_argument("--create-pr", action="store_true", help="推送后使用 gh CLI 创建 PR")
    develop_parser.add_argument("--dry-run", action="store_true")
    develop_parser.set_defaults(func=cmd_develop_issue)

    review_code_parser = subparsers.add_parser("review-pr", help="对 worktree 改动运行 Codex Review")
    review_code_parser.add_argument("--worktree", type=Path, required=True)
    review_code_parser.add_argument("--task-id", default=None)
    review_code_parser.add_argument("--base", default="main")
    review_code_parser.add_argument("--dry-run", action="store_true")
    review_code_parser.set_defaults(func=cmd_review_code)

    resume_parser = subparsers.add_parser("resume-stale", help="列出或恢复 heartbeat 超时的运行中任务")
    resume_parser.add_argument("--older-than-minutes", type=int, default=30)
    resume_parser.add_argument("--dry-run", action="store_true", help="只打印待恢复任务，不重新执行")
    resume_parser.set_defaults(func=cmd_resume_stale)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    RunnerState(args.state_db)
    Path(".ai/state").mkdir(parents=True, exist_ok=True)
    Path(".ai-worktrees").mkdir(parents=True, exist_ok=True)
    print(f"Runner 状态库已初始化: {args.state_db}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state = RunnerState(args.state_db)
    tasks = [state.get_task(args.task_id)] if args.task_id else state.list_tasks(args.limit)
    tasks = [task for task in tasks if task is not None]

    if args.json:
        print(json.dumps([_task_to_dict(task, state.latest_checkpoint(task.task_id)) for task in tasks], ensure_ascii=False, indent=2))
        return 0

    if not tasks:
        print("没有 Runner 任务状态。")
        return 0

    print(f"状态库: {args.state_db}")
    for task in tasks:
        checkpoint = state.latest_checkpoint(task.task_id)
        print("")
        print(f"- task_id: {task.task_id}")
        print(f"  status: {task.status}")
        print(f"  phase: {task.phase}")
        print(f"  attempt: {task.attempt}")
        print(f"  issue: {task.issue_number or '-'}")
        print(f"  branch: {task.branch}")
        print(f"  worktree: {task.worktree_path}")
        print(f"  heartbeat_at: {task.heartbeat_at}")
        print(f"  last_checkpoint: {task.last_checkpoint or '-'}")
        if checkpoint:
            print(f"  checkpoint_summary: {checkpoint['summary']}")
        if task.last_error:
            print(f"  last_error: {task.last_error}")
    return 0


def cmd_review_prd(args: argparse.Namespace) -> int:
    state = RunnerState(args.state_db)
    executor = _executor(args)
    prd_content = read_text(args.prd)
    output_path = _state_file(args.state_db, "prd-review", f"{_artifact_name(args.prd.stem)}.json")
    prompt = build_prd_review_prompt(str(args.prd), prd_content)
    result = executor.exec(
        cwd=REPO_ROOT,
        prompt=prompt,
        last_message_path=output_path,
        output_schema=SCHEMA_DIR / "prd_review.schema.json",
        dry_run=args.dry_run,
    )
    state.upsert_task(
        task_id=f"prd-review:{args.prd}",
        issue_number=None,
        branch="main",
        worktree_path=str(REPO_ROOT),
        phase="review_prd",
        status="DRY_RUN" if args.dry_run else ("DONE" if result.ok else "FAILED"),
        last_error=None if result.ok else result.stderr,
    )
    _print_command_result(result, show_stdout=args.dry_run or not result.ok)
    if result.ok and not args.dry_run:
        body = read_text(output_path)
        print(body)
        if args.post_comment and args.pr:
            GitHubCli(args.gh_bin).comment_pr(args.pr, body)
    return 0 if result.ok else result.returncode


def cmd_split_prd(args: argparse.Namespace) -> int:
    executor = _executor(args)
    prd_content = read_text(args.prd)
    output_path = _state_file(args.state_db, "split", f"{_artifact_name(args.prd.stem)}.json")
    result = executor.exec(
        cwd=REPO_ROOT,
        prompt=build_split_prompt(str(args.prd), prd_content),
        last_message_path=output_path,
        output_schema=SCHEMA_DIR / "task_split.schema.json",
        dry_run=args.dry_run,
    )
    _print_command_result(result, show_stdout=args.dry_run or not result.ok)
    if not result.ok or args.dry_run:
        return 0 if result.ok else result.returncode

    payload = load_json_from_text(read_text(output_path))
    if args.create_issues:
        gh = GitHubCli(args.gh_bin)
        existing_labels = gh.list_label_names()
        for task in payload.get("tasks", []):
            labels = _filter_existing_labels(task.get("labels") or ["ai-dev"], existing_labels)
            url = gh.create_issue(
                title=task["title"],
                body=task["body"],
                labels=labels,
            )
            print(url)
    else:
        print(read_text(output_path))
    return 0


def cmd_develop_issue(args: argparse.Namespace) -> int:
    state = RunnerState(args.state_db)
    git = GitOps(REPO_ROOT)
    issue = _load_issue(args)
    task_config = parse_ai_task_config(issue.body)
    if task_config.docker_required:
        print("当前 MVP 未启用 Docker 执行器；请将该任务交给人工或后续 DockerExecutor。", file=sys.stderr)
        return 2

    branch = git.branch_for_issue(issue.number, issue.title)
    worktree = git.worktree_for_issue(issue.number)
    task_id = f"issue-{issue.number}"
    existing = state.get_task(task_id)
    attempt = 1 if existing is None else existing.attempt + 1
    if attempt > task_config.max_attempts:
        state.mark(task_id, status="AI_BLOCKED", last_error=f"超过最大尝试次数: {task_config.max_attempts}")
        print(f"任务 {task_id} 已超过最大尝试次数 {task_config.max_attempts}，需要人工处理。", file=sys.stderr)
        return 2

    state.upsert_task(
        task_id=task_id,
        issue_number=issue.number,
        branch=branch,
        worktree_path=str(worktree),
        phase="prepare",
        attempt=attempt,
        status="RUNNING",
    )
    if not args.dry_run:
        git.ensure_worktree(branch=branch, worktree_path=worktree, base=args.base)
    state.add_checkpoint(task_id, phase="prepare", summary="已准备分支和 worktree", data={"branch": branch, "worktree": str(worktree)})

    prd_path = worktree / task_config.prd_path
    prd_content = read_text(prd_path) if prd_path.exists() else f"未找到 PRD 文件: {task_config.prd_path}"
    checkpoint = state.latest_checkpoint(task_id)
    output_path = _state_file(args.state_db, task_id, "develop-last-message.md")
    result = _executor(args).exec(
        cwd=worktree,
        prompt=build_develop_prompt(
            issue_number=issue.number,
            issue_body=issue.body,
            task_config=task_config,
            prd_content=prd_content,
            checkpoint=checkpoint,
        ),
        last_message_path=output_path,
        dry_run=args.dry_run,
    )
    _print_command_result(result, show_stdout=args.dry_run or not result.ok)
    if not result.ok:
        status = "AI_BLOCKED" if attempt >= task_config.max_attempts else "NEEDS_FIX"
        state.mark(task_id, phase="develop", status=status, last_error=result.stderr)
        return result.returncode

    validation_result = _run_validation(task_config.validation, worktree, dry_run=args.dry_run)
    changed_files = [] if args.dry_run else git.changed_files(worktree)
    state.add_checkpoint(
        task_id,
        phase="validate",
        summary="已完成开发执行和验证",
        data={"validation": validation_result, "changed_files": changed_files},
    )
    if any(item["returncode"] != 0 for item in validation_result):
        status = "AI_BLOCKED" if attempt >= task_config.max_attempts else "NEEDS_FIX"
        state.mark(task_id, phase="validate", status=status, last_error="验证命令失败")
        return 1

    if args.commit and not args.dry_run and git.has_changes(worktree):
        git.commit_all(worktree, f"AI: implement issue #{issue.number}")
    if args.push and not args.dry_run:
        git.push_branch(worktree, branch)
    if args.create_pr and not args.dry_run:
        pr_body = _build_pr_body(issue, task_config, changed_files, validation_result)
        pr_url = GitHubCli(args.gh_bin).create_pr(title=f"[AI] {issue.title}", body=pr_body, head=branch, base=args.base)
        print(pr_url)

    state.mark(task_id, phase="done", status="DONE", last_error=None)
    return 0


def cmd_review_code(args: argparse.Namespace) -> int:
    state = RunnerState(args.state_db)
    task_state = state.get_task(args.task_id) if args.task_id else None
    output_path = _state_file(args.state_db, args.task_id or "review", "code-review-last-message.md")
    result = _executor(args).review(
        cwd=args.worktree,
        prompt=build_review_prompt(task_state),
        last_message_path=output_path,
        base=args.base,
        dry_run=args.dry_run,
    )
    _print_command_result(result, show_stdout=args.dry_run or not result.ok)
    if task_state:
        state.add_checkpoint(
            task_state.task_id,
            phase="ai_review",
            summary="已执行 Codex CLI Review",
            data={"returncode": result.returncode, "last_message": str(output_path)},
        )
        state.mark(task_state.task_id, phase="ai_review", status="DONE" if result.ok else "NEEDS_FIX")
    return 0 if result.ok else result.returncode


def cmd_resume_stale(args: argparse.Namespace) -> int:
    state = RunnerState(args.state_db)
    stale_tasks = state.find_stale_running(args.older_than_minutes)
    if not stale_tasks:
        print("没有 heartbeat 超时的 RUNNING 任务。")
        return 0
    for task in stale_tasks:
        print(f"{task.task_id} phase={task.phase} branch={task.branch} worktree={task.worktree_path} heartbeat={task.heartbeat_at}")
        if not args.dry_run:
            state.mark(task.task_id, status="NEEDS_RESUME", last_error="Runner 中断或 heartbeat 超时，等待重新执行 develop-issue")
    return 0


def _executor(args: argparse.Namespace) -> CodexCliExecutor:
    return CodexCliExecutor(codex_bin=args.codex_bin, model=args.model)


def _load_issue(args: argparse.Namespace) -> IssueData:
    if args.issue_body_file:
        title = args.issue_title or f"Issue {args.issue}"
        return IssueData(number=args.issue, title=title, body=read_text(args.issue_body_file))
    return GitHubCli(args.gh_bin).issue_view(args.issue)


def _run_validation(commands: list[str], cwd: Path, *, dry_run: bool) -> list[dict]:
    results: list[dict] = []
    for command in commands:
        if dry_run:
            results.append({"command": command, "returncode": 0, "stdout": "", "stderr": "", "dry_run": True})
            continue
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
        )
    return results


def _build_pr_body(issue: IssueData, task_config, changed_files: list[str], validation_result: list[dict]) -> str:
    validation_lines = "\n".join(
        f"- `{item['command']}`: {'PASS' if item['returncode'] == 0 else 'FAIL'}" for item in validation_result
    ) or "- 未配置验证命令"
    changed_lines = "\n".join(f"- `{file}`" for file in changed_files) or "- 无 Git diff"
    return f"""关联 Issue: #{issue.number}
关联 PRD: `{task_config.prd_path}`

## 实现摘要

由 AI Runner + Codex CLI 完成开发，等待人工 review。

## 修改文件

{changed_lines}

## 验证结果

{validation_lines}

## 未覆盖风险

- 请人工确认业务规则、边界条件和 UI/接口行为是否符合 PRD。
"""


def _state_file(db_path: Path, *parts: str) -> Path:
    root = db_path.parent if db_path.parent.is_absolute() else (REPO_ROOT / db_path.parent)
    return root.joinpath(*parts)


def _artifact_name(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{slugify(value, fallback='artifact')}-{digest}"


def _filter_existing_labels(labels: list[str], existing_labels: set[str]) -> list[str]:
    kept: list[str] = []
    missing: list[str] = []
    for label in labels:
        if label in existing_labels and label not in kept:
            kept.append(label)
        elif label not in existing_labels and label not in missing:
            missing.append(label)
    if missing:
        print(f"跳过不存在的 GitHub 标签: {', '.join(missing)}", file=sys.stderr)
    return kept


def _task_to_dict(task, checkpoint):
    return {
        "task_id": task.task_id,
        "issue_number": task.issue_number,
        "branch": task.branch,
        "worktree_path": task.worktree_path,
        "phase": task.phase,
        "attempt": task.attempt,
        "status": task.status,
        "last_checkpoint": task.last_checkpoint,
        "last_error": task.last_error,
        "heartbeat_at": task.heartbeat_at,
        "checkpoint": checkpoint,
    }


def _print_command_result(result, *, show_stdout: bool = False) -> None:
    print("COMMAND:", " ".join(result.command))
    if result.command and result.command[-1] == "-":
        print("PROMPT: <stdin>")
    if show_stdout and result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
