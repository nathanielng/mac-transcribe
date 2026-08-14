"""Stage 4: glue. Single entry point the RecorderApp calls after a recording is saved.

    python -m mac_transcribe.process <session-dir> [--force-transcript] [--force-outline] [--force-title]

Each stage is skipped if status.json already marks it 'ok', unless the matching
--force-* flag is passed (used by the menu bar app's "Regenerate ..." buttons).
"""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date as date_cls
from pathlib import Path

from . import status
from .config import load_config
from .outline import OutlineAuthError
from .outline import run as run_outline
from .title import generate_title_slug, rename_session
from .transcribe import run as run_transcribe
from .html import build_html


def guess_title(session_dir: Path) -> str:
    # Session folder is named "<date>-<title>"; strip the leading date.
    name = session_dir.name
    parts = name.split("-", 3)
    return "-".join(parts[3:]) if len(parts) > 3 else name


def process_session(session_dir: Path, force: set[str] | None = None) -> Path:
    force = force or set()
    cfg = load_config()
    title = guess_title(session_dir)
    date_str = date_cls.today().isoformat()

    # --- Stage 2: transcript ---
    if "transcript" in force or not status.stage_ok(session_dir, "transcript"):
        status.set_stage(session_dir, "transcript", "running")
        try:
            run_transcribe(session_dir, title, date_str, cfg["whisper_model"])
            status.set_stage(session_dir, "transcript", "ok")
        except Exception as e:
            status.set_stage(session_dir, "transcript", "failed", str(e))
            return session_dir  # nothing downstream can run without a transcript

    transcript_md = (session_dir / "transcript.md").read_text()

    # --- Stage 3: outline + optional AI title/rename, concurrently ---
    run_title_stage = cfg.get("auto_rename_with_ai_title", True)

    def do_outline():
        if "outline" in force or not status.stage_ok(session_dir, "outline"):
            status.set_stage(session_dir, "outline", "running")
            try:
                run_outline(session_dir, title, cfg["bedrock_model"], cfg["bedrock_region"], cfg["bedrock_profile"])
                status.set_stage(session_dir, "outline", "ok")
            except OutlineAuthError as e:
                status.set_stage(session_dir, "outline", "failed", f"auth: {e}")
            except Exception as e:
                status.set_stage(session_dir, "outline", "failed", str(e))

    def do_title_slug() -> str | None:
        if not run_title_stage:
            return None
        if "title" in force or not status.stage_ok(session_dir, "title_rename"):
            status.set_stage(session_dir, "title_rename", "running")
            try:
                return generate_title_slug(transcript_md, cfg["bedrock_model"], cfg["bedrock_region"], cfg["bedrock_profile"])
            except OutlineAuthError as e:
                status.set_stage(session_dir, "title_rename", "failed", f"auth: {e}")
            except Exception as e:
                status.set_stage(session_dir, "title_rename", "failed", str(e))
        return None

    # Both API calls only read transcript.md, so run them concurrently — but the
    # actual file/folder rename happens only after BOTH finish, in this (main)
    # thread, so it can never race with outline.py still writing outline.md into
    # the same directory it's about to be moved out from under.
    with ThreadPoolExecutor(max_workers=2) as pool:
        outline_future = pool.submit(do_outline)
        title_future = pool.submit(do_title_slug)
        outline_future.result()
        slug = title_future.result()

    if slug:
        session_dir = rename_session(session_dir, date_str, slug)
        status.set_stage(session_dir, "title_rename", "ok")

    # --- Stage 3b: HTML (only if outline succeeded) ---
    if status.stage_ok(session_dir, "outline"):
        html_path = session_dir / f"{session_dir.name}.html"
        try:
            build_html(session_dir / "transcript.md", session_dir / "outline.md", html_path)
        except Exception as e:
            status.set_stage(session_dir, "outline", "failed", f"html merge: {e}")

    return session_dir


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--force-")}
    force = {f.replace("--force-", "") for f in flags}

    if not args:
        print(__doc__)
        sys.exit(1)

    session_dir = Path(args[0]).expanduser().resolve()
    if not session_dir.is_dir():
        print(f"Error: session directory not found: {session_dir}", file=sys.stderr)
        sys.exit(1)

    final_dir = process_session(session_dir, force)
    print(f"Done: {final_dir}")


if __name__ == "__main__":
    main()
