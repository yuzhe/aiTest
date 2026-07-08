from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    last_message_path: Path | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class CodexCliExecutor:
    """Codex CLI 执行器，只负责调用本地 codex 命令。"""

    def __init__(
        self,
        *,
        codex_bin: str = "codex",
        model: str | None = None,
        sandbox: str = "workspace-write",
    ) -> None:
        self.codex_bin = codex_bin
        self.model = model
        self.sandbox = sandbox

    def ensure_available(self) -> None:
        if _resolve_executable(self.codex_bin) is None:
            raise RuntimeError(f"未找到 Codex CLI: {self.codex_bin}")

    def build_exec_command(
        self,
        *,
        cwd: Path,
        prompt: str,
        last_message_path: Path,
        output_schema: Path | None = None,
    ) -> list[str]:
        command = [
            _resolve_executable(self.codex_bin) or self.codex_bin,
            "exec",
            "--cd",
            str(cwd),
            "--sandbox",
            self.sandbox,
            "--json",
            "--output-last-message",
            str(last_message_path),
        ]
        if self.model:
            command.extend(["--model", self.model])
        if output_schema:
            command.extend(["--output-schema", str(output_schema)])
        command.append("-")
        return command

    def exec(
        self,
        *,
        cwd: Path,
        prompt: str,
        last_message_path: Path,
        output_schema: Path | None = None,
        dry_run: bool = False,
    ) -> CommandResult:
        last_message_path.parent.mkdir(parents=True, exist_ok=True)
        command = self.build_exec_command(
            cwd=cwd,
            prompt=prompt,
            last_message_path=last_message_path,
            output_schema=output_schema,
        )
        if dry_run:
            return CommandResult(command=command, returncode=0, stdout="", stderr="", last_message_path=last_message_path)

        self.ensure_available()
        completed = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            last_message_path=last_message_path,
        )

    def review(
        self,
        *,
        cwd: Path,
        prompt: str,
        last_message_path: Path,
        base: str = "main",
        dry_run: bool = False,
    ) -> CommandResult:
        command = [
            _resolve_executable(self.codex_bin) or self.codex_bin,
            "exec",
            "review",
            "--uncommitted",
            "--base",
            base,
            "--json",
            "--output-last-message",
            str(last_message_path),
            "-",
        ]
        if self.model:
            command[3:3] = ["--model", self.model]
        last_message_path.parent.mkdir(parents=True, exist_ok=True)
        if dry_run:
            return CommandResult(command=command, returncode=0, stdout="", stderr="", last_message_path=last_message_path)

        self.ensure_available()
        completed = subprocess.run(
            command,
            cwd=cwd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            last_message_path=last_message_path,
        )


def _resolve_executable(command: str) -> str | None:
    """Windows 下优先选择可被 CreateProcess 直接启动的 shim。"""

    path = Path(command)
    if path.parent != Path(".") or path.suffix:
        return str(path) if path.exists() else shutil.which(command)

    if os.name == "nt":
        for suffix in (".cmd", ".exe", ".bat"):
            resolved = shutil.which(f"{command}{suffix}")
            if resolved:
                return resolved
    return shutil.which(command)
