"""Shared session-folder resolution for the manual reference scripts in this
directory (regenerate_outlines.py, build_action_items.py) — kept in one
place so the two don't quietly drift on what counts as "a session folder"."""

from pathlib import Path


def resolve_session_dirs(path: Path) -> list[Path]:
    """Expands a single CLI argument into the session folder(s) it refers to.

    Accepts: a session folder (contains transcript.md directly), a
    transcript.md file itself (parent folder is used), or a root folder
    containing multiple session folders one level down (e.g. the whole
    recordings_dir) — every immediate subfolder with a transcript.md is
    picked up automatically.
    """
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: {path}")

    if path.is_file():
        if path.name != "transcript.md":
            raise ValueError(f"{path}: expected a file named transcript.md")
        return [path.parent]

    direct = path / "transcript.md"
    if direct.exists():
        return [path]

    found = sorted(
        child for child in path.iterdir()
        if child.is_dir() and (child / "transcript.md").exists()
    )
    if not found:
        raise ValueError(
            f"{path}: no transcript.md here, and no immediate subfolder has one either"
        )
    return found


def resolve_all(paths: list[Path]) -> list[Path]:
    """Resolves + dedupes a list of CLI path arguments, in first-seen order."""
    session_dirs: list[Path] = []
    seen: set[Path] = set()
    for raw in paths:
        for session_dir in resolve_session_dirs(raw.expanduser().resolve()):
            if session_dir not in seen:
                seen.add(session_dir)
                session_dirs.append(session_dir)
    return session_dirs


def parse_session_name(name: str) -> tuple[str, str]:
    """"2026-09-04-my-session-title" -> ("2026-09-04", "my-session-title")."""
    parts = name.split("-", 3)
    date_str = "-".join(parts[:3]) if len(parts) >= 3 else ""
    title = parts[3] if len(parts) > 3 else "recording"
    return date_str, title
