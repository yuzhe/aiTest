from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(".ai/state/runner.sqlite3")
_UNSET = object()


@dataclass(slots=True)
class TaskState:
    task_id: str
    issue_number: int | None
    branch: str
    worktree_path: str
    phase: str
    attempt: int
    status: str
    last_checkpoint: str | None
    last_error: str | None
    heartbeat_at: str


class RunnerState:
    """SQLite 状态库，负责让 Runner 跨进程恢复任务。"""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def upsert_task(
        self,
        *,
        task_id: str,
        issue_number: int | None,
        branch: str,
        worktree_path: str,
        phase: str,
        status: str,
        attempt: int = 0,
        last_checkpoint: str | None = None,
        last_error: str | None = None,
    ) -> None:
        now = _now()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, issue_number, branch, worktree_path, phase, attempt,
                    status, last_checkpoint, last_error, heartbeat_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    issue_number=excluded.issue_number,
                    branch=excluded.branch,
                    worktree_path=excluded.worktree_path,
                    phase=excluded.phase,
                    attempt=excluded.attempt,
                    status=excluded.status,
                    last_checkpoint=excluded.last_checkpoint,
                    last_error=excluded.last_error,
                    heartbeat_at=excluded.heartbeat_at,
                    updated_at=excluded.updated_at
                """,
                (
                    task_id,
                    issue_number,
                    branch,
                    worktree_path,
                    phase,
                    attempt,
                    status,
                    last_checkpoint,
                    last_error,
                    now,
                    now,
                    now,
                ),
            )

    def get_task(self, task_id: str) -> TaskState | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(self, limit: int = 20) -> list[TaskState]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_task(row) for row in rows]

    def heartbeat(self, task_id: str) -> None:
        now = _now()
        with self._connection() as conn:
            conn.execute(
                "UPDATE tasks SET heartbeat_at = ?, updated_at = ? WHERE task_id = ?",
                (now, now, task_id),
            )

    def mark(
        self,
        task_id: str,
        *,
        phase: str | None = None,
        status: str | None = None,
        attempt: int | None = None,
        last_checkpoint: str | None | object = _UNSET,
        last_error: str | None | object = _UNSET,
    ) -> None:
        existing = self.get_task(task_id)
        if not existing:
            raise KeyError(f"任务不存在: {task_id}")

        self.upsert_task(
            task_id=task_id,
            issue_number=existing.issue_number,
            branch=existing.branch,
            worktree_path=existing.worktree_path,
            phase=phase or existing.phase,
            attempt=existing.attempt if attempt is None else attempt,
            status=status or existing.status,
            last_checkpoint=existing.last_checkpoint if last_checkpoint is _UNSET else last_checkpoint,
            last_error=existing.last_error if last_error is _UNSET else last_error,
        )

    def add_checkpoint(
        self,
        task_id: str,
        *,
        phase: str,
        summary: str,
        data: dict[str, Any] | None = None,
    ) -> str:
        now = _now()
        data_json = json.dumps(data or {}, ensure_ascii=False, indent=2)
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO checkpoints (task_id, phase, summary, data_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (task_id, phase, summary, data_json, now),
            )
            checkpoint_id = f"{task_id}#{cursor.lastrowid}"
        self.mark(task_id, phase=phase, last_checkpoint=checkpoint_id)
        return checkpoint_id

    def latest_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT phase, summary, data_json, created_at
                FROM checkpoints
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "phase": row["phase"],
            "summary": row["summary"],
            "data": json.loads(row["data_json"]),
            "created_at": row["created_at"],
        }

    def find_stale_running(self, older_than_minutes: int) -> list[TaskState]:
        cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'RUNNING' AND heartbeat_at < ?
                ORDER BY heartbeat_at ASC
                """,
                (cutoff.isoformat(timespec="seconds"),),
            ).fetchall()
        return [_row_to_task(row) for row in rows]

    def _init_schema(self) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    issue_number INTEGER,
                    branch TEXT NOT NULL,
                    worktree_path TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    last_checkpoint TEXT,
                    last_error TEXT,
                    heartbeat_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _row_to_task(row: sqlite3.Row) -> TaskState:
    return TaskState(
        task_id=row["task_id"],
        issue_number=row["issue_number"],
        branch=row["branch"],
        worktree_path=row["worktree_path"],
        phase=row["phase"],
        attempt=row["attempt"],
        status=row["status"],
        last_checkpoint=row["last_checkpoint"],
        last_error=row["last_error"],
        heartbeat_at=row["heartbeat_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
