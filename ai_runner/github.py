from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass


@dataclass(slots=True)
class IssueData:
    number: int
    title: str
    body: str


class GitHubCli:
    """gh CLI 适配层；MVP 保持 GitHub 操作可脚本化。"""

    def __init__(self, gh_bin: str = "gh") -> None:
        self.gh_bin = gh_bin

    def ensure_available(self) -> None:
        if shutil.which(self.gh_bin) is None:
            raise RuntimeError("未找到 gh CLI，请安装并登录后再执行 GitHub 写操作")

    def issue_view(self, issue_number: int) -> IssueData:
        data = self._run_json(["issue", "view", str(issue_number), "--json", "number,title,body"])
        return IssueData(number=int(data["number"]), title=data["title"], body=data.get("body") or "")

    def list_label_names(self) -> set[str]:
        labels = self._run_json(["label", "list", "--limit", "1000", "--json", "name"])
        return {item["name"] for item in labels}

    def comment_issue(self, issue_number: int, body: str) -> None:
        self._run(["issue", "comment", str(issue_number), "--body", body])

    def comment_pr(self, pr_number: int, body: str) -> None:
        self._run(["pr", "comment", str(pr_number), "--body", body])

    def add_issue_labels(self, issue_number: int, labels: list[str]) -> None:
        if labels:
            self._run(["issue", "edit", str(issue_number), "--add-label", ",".join(labels)])

    def add_pr_labels(self, pr_number: int, labels: list[str]) -> None:
        if labels:
            self._run(["pr", "edit", str(pr_number), "--add-label", ",".join(labels)])

    def create_issue(self, *, title: str, body: str, labels: list[str] | None = None) -> str:
        command = ["issue", "create", "--title", title, "--body", body]
        for label in labels or []:
            command.extend(["--label", label])
        result = self._run(command)
        return result.stdout.strip()

    def create_pr(self, *, title: str, body: str, head: str, base: str = "main") -> str:
        result = self._run(["pr", "create", "--title", title, "--body", body, "--head", head, "--base", base])
        return result.stdout.strip()

    def _run_json(self, args: list[str]) -> dict:
        result = self._run(args)
        return json.loads(result.stdout)

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.ensure_available()
        result = subprocess.run(
            [self.gh_bin, *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            command = " ".join([self.gh_bin, *args])
            raise RuntimeError(f"gh CLI 执行失败: {command}\n{detail}")
        return result
