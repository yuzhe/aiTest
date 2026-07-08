from __future__ import annotations

import subprocess
from pathlib import Path

from .task import slugify


class GitOps:
    """Git 操作封装，避免 Runner 拼接 shell 字符串。"""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root

    def branch_for_issue(self, issue_number: int, title: str) -> str:
        return f"ai/issue-{issue_number}-{slugify(title, fallback='task')}"

    def worktree_for_issue(self, issue_number: int) -> Path:
        return self.repo_root / ".ai-worktrees" / f"issue-{issue_number}"

    def ensure_worktree(self, *, branch: str, worktree_path: Path, base: str = "main") -> None:
        if worktree_path.exists():
            return
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        self._run(["git", "worktree", "add", "-B", branch, str(worktree_path), base])

    def changed_files(self, cwd: Path) -> list[str]:
        result = self._run(["git", "status", "--porcelain"], cwd=cwd)
        files: list[str] = []
        for line in result.stdout.splitlines():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ")[-1]
            if path:
                files.append(path)
        return files

    def has_changes(self, cwd: Path) -> bool:
        result = self._run(["git", "status", "--porcelain"], cwd=cwd)
        return bool(result.stdout.strip())

    def commit_all(self, cwd: Path, message: str) -> None:
        self._run(["git", "add", "-A"], cwd=cwd)
        self._run(["git", "commit", "-m", message], cwd=cwd)

    def push_branch(self, cwd: Path, branch: str) -> None:
        self._run(["git", "push", "-u", "origin", branch], cwd=cwd)

    def _run(self, command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=cwd or self.repo_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
