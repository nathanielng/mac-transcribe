"""Read/write a session's status.json — the shared state file the menu bar app polls."""

import json
from pathlib import Path

STATUS_FILENAME = "status.json"

STAGES = ("transcript", "outline", "title_rename")


def status_path(session_dir: Path) -> Path:
    return session_dir / STATUS_FILENAME


def load(session_dir: Path) -> dict:
    p = status_path(session_dir)
    if not p.exists():
        return {"stages": {s: {"status": "pending", "error": None} for s in STAGES}}
    return json.loads(p.read_text())


def save(session_dir: Path, data: dict) -> None:
    status_path(session_dir).write_text(json.dumps(data, indent=2))


def set_stage(session_dir: Path, stage: str, status: str, error: str | None = None) -> dict:
    """status: 'pending' | 'running' | 'ok' | 'failed'"""
    data = load(session_dir)
    data.setdefault("stages", {})[stage] = {"status": status, "error": error}
    save(session_dir, data)
    return data


def stage_ok(session_dir: Path, stage: str) -> bool:
    data = load(session_dir)
    return data.get("stages", {}).get(stage, {}).get("status") == "ok"
