from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_MAX_ATTEMPTS = 2


@dataclass(slots=True)
class AiTaskConfig:
    """开发 Issue 中的 AI 任务配置。"""

    prd_path: str
    task_type: str = "feature"
    validation: list[str] = field(default_factory=list)
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    docker_required: bool = False


def parse_ai_task_config(issue_body: str) -> AiTaskConfig:
    block = _extract_ai_task_block(issue_body)
    values = _parse_simple_yaml_mapping(block)

    prd_path = str(values.get("prd_path") or "").strip()
    if not prd_path:
        raise ValueError("Issue 缺少 ai_task.prd_path")

    validation = values.get("validation", [])
    if isinstance(validation, str):
        validation = [validation]
    if not isinstance(validation, list):
        raise ValueError("ai_task.validation 必须是字符串列表")

    return AiTaskConfig(
        prd_path=prd_path,
        task_type=str(values.get("type") or "feature"),
        validation=[str(item) for item in validation if str(item).strip()],
        max_attempts=int(values.get("max_attempts") or DEFAULT_MAX_ATTEMPTS),
        docker_required=bool(values.get("docker_required", False)),
    )


def slugify(value: str, fallback: str = "task", max_length: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (slug or fallback)[:max_length].strip("-") or fallback


def load_json_from_text(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("空响应无法解析为 JSON")
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", stripped, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_ai_task_block(issue_body: str) -> str:
    lines = issue_body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "ai_task:":
            continue

        root_indent = _indent(line)
        collected = [line[root_indent:]]
        in_fence = _previous_fence_is_open(lines, index)

        for next_line in lines[index + 1 :]:
            stripped = next_line.strip()
            if in_fence and stripped.startswith("```"):
                break
            if not in_fence and stripped.startswith("## "):
                break
            if stripped and _indent(next_line) <= root_indent and not stripped.startswith("-"):
                break
            collected.append(next_line[root_indent:] if len(next_line) >= root_indent else next_line)
        return "\n".join(collected)
    raise ValueError("Issue 缺少 ai_task 配置块")


def _parse_simple_yaml_mapping(block: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    current_list_key: str | None = None

    lines = block.splitlines()
    if not lines or lines[0].strip() != "ai_task:":
        raise ValueError("ai_task 配置块格式不正确")

    for raw_line in lines[1:]:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if not current_list_key:
                raise ValueError(f"列表项缺少所属字段: {stripped}")
            values.setdefault(current_list_key, []).append(_parse_scalar(stripped[2:].strip()))
            continue

        key_match = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$", stripped)
        if not key_match:
            raise ValueError(f"无法解析 ai_task 行: {raw_line}")

        key, value = key_match.groups()
        if value == "":
            values[key] = []
            current_list_key = key
        else:
            values[key] = _parse_scalar(value)
            current_list_key = None
    return values


def _parse_scalar(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value.strip('"').strip("'")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _previous_fence_is_open(lines: list[str], index: int) -> bool:
    fence_count = sum(1 for line in lines[:index] if line.strip().startswith("```"))
    return fence_count % 2 == 1

