from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_runner.executor import CodexCliExecutor
from ai_runner.runner import _filter_existing_labels
from ai_runner.state import RunnerState
from ai_runner.task import parse_ai_task_config, slugify


class TaskParsingTest(unittest.TestCase):
    def test_parse_ai_task_config_from_fenced_yaml(self) -> None:
        body = """## 开发目标
实现用户搜索。

```yaml
ai_task:
  prd_path: docs/requirements/search.md
  type: feature
  validation:
    - python -m unittest discover -s tests
    - npm test
  max_attempts: 3
  docker_required: false
```
"""
        config = parse_ai_task_config(body)

        self.assertEqual(config.prd_path, "docs/requirements/search.md")
        self.assertEqual(config.task_type, "feature")
        self.assertEqual(config.max_attempts, 3)
        self.assertFalse(config.docker_required)
        self.assertEqual(config.validation, ["python -m unittest discover -s tests", "npm test"])

    def test_slugify_uses_fallback_for_chinese_title(self) -> None:
        self.assertEqual(slugify("用户列表手机号搜索", fallback="task"), "task")


class StateTest(unittest.TestCase):
    def test_state_checkpoint_and_stale_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = RunnerState(Path(tmp) / "runner.sqlite3")
            state.upsert_task(
                task_id="issue-1",
                issue_number=1,
                branch="ai/issue-1-task",
                worktree_path=".ai-worktrees/issue-1",
                phase="prepare",
                status="RUNNING",
            )
            checkpoint = state.add_checkpoint("issue-1", phase="prepare", summary="准备完成", data={"ok": True})

            task = state.get_task("issue-1")
            self.assertIsNotNone(task)
            self.assertEqual(task.last_checkpoint, checkpoint)
            self.assertEqual(state.latest_checkpoint("issue-1")["data"], {"ok": True})
            self.assertEqual(state.find_stale_running(older_than_minutes=-1)[0].task_id, "issue-1")
            self.assertEqual(state.list_tasks()[0].task_id, "issue-1")

            state.mark("issue-1", last_error="验证失败")
            self.assertEqual(state.get_task("issue-1").last_error, "验证失败")
            state.mark("issue-1", status="DONE", last_error=None)
            self.assertIsNone(state.get_task("issue-1").last_error)


class ExecutorTest(unittest.TestCase):
    def test_codex_exec_command_contains_required_flags(self) -> None:
        executor = CodexCliExecutor(codex_bin="codex")
        command = executor.build_exec_command(
            cwd=Path(".ai-worktrees/issue-1"),
            prompt="do work",
            last_message_path=Path(".ai/state/issue-1/last.md"),
        )

        self.assertIn("--sandbox", command)
        self.assertIn("workspace-write", command)
        self.assertIn("--json", command)
        self.assertEqual(command[-1], "-")


class GitHubLabelTest(unittest.TestCase):
    def test_filter_existing_labels_keeps_only_known_labels(self) -> None:
        labels = _filter_existing_labels(["feature", "documentation", "ai-runner"], {"documentation"})

        self.assertEqual(labels, ["documentation"])


if __name__ == "__main__":
    unittest.main()
