#!/usr/bin/env python3
"""Manually regenerate outlines (and their HTML) from existing transcripts.

Meant to be invoked directly by you or an AI coding assistant — e.g. after
changing outline_backend/bedrock_model in config.toml and wanting to redo a
batch of already-transcribed sessions with the new model, or after an
outline.py prompt change you want to test against real past recordings.

Accepts any mix of, in any combination:
  - a session folder (a folder containing transcript.md directly)
  - a transcript.md file itself (its parent folder is used as the session)
  - a "root" folder containing multiple session subfolders one level down
    (e.g. your whole recordings_dir) — every immediate subfolder with a
    transcript.md is picked up automatically

Usage (from pipeline/, with the venv active):
    python3 scripts/regenerate_outlines.py ~/Recordings/mac-transcribe/2026-09-04-standup
    python3 scripts/regenerate_outlines.py ~/Recordings/mac-transcribe/2026-09-04-standup/transcript.md
    python3 scripts/regenerate_outlines.py ~/Recordings/mac-transcribe          # every session in it
    python3 scripts/regenerate_outlines.py session-a/ session-b/ transcript.md  # mixed list
    python3 scripts/regenerate_outlines.py ~/Recordings/mac-transcribe --dry-run
    python3 scripts/regenerate_outlines.py ~/Recordings/mac-transcribe --also-title

Each resolved session goes through mac_transcribe.process.process_session()
with the "outline" stage forced — the exact same code path as clicking
Regenerate Outline in RecorderApp, so behavior (Bedrock vs. mlx_lm per
config.toml, HTML rebuild once outline succeeds, status.json updates,
per-stage progress printed to stdout) is identical, not reimplemented here.

Costs real API calls (or real local compute for mlx_lm) per session, so
double-check the list — especially when passing a root folder — before
running for real; --dry-run lists what would run without doing it.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mac_transcribe import status  # noqa: E402
from mac_transcribe.process import process_session  # noqa: E402


def resolve_session_dirs(path: Path) -> list[Path]:
    """Expands a single CLI argument into the session folder(s) it refers to."""
    if not path.exists():
        raise FileNotFoundError(f"No such file or directory: {path}")

    if path.is_file():
        if path.name != "transcript.md":
            raise ValueError(f"{path}: expected a file named transcript.md")
        return [path.parent]

    direct = path / "transcript.md"
    if direct.exists():
        return [path]  # path itself is a session folder

    # No transcript.md directly here — treat path as a root containing
    # multiple session folders (e.g. the whole recordings_dir) and look one
    # level down, matching how RecorderApp lays sessions out.
    found = sorted(
        child for child in path.iterdir()
        if child.is_dir() and (child / "transcript.md").exists()
    )
    if not found:
        raise ValueError(
            f"{path}: no transcript.md here, and no immediate subfolder has one either"
        )
    return found


def main():
    # Belt-and-suspenders like process.py's own main() — matters if this
    # script's output is ever piped/redirected rather than run in a plain
    # interactive terminal, since Python fully buffers stdout when it isn't
    # a real tty.
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "paths", nargs="+", type=Path,
        help="Session folder(s), transcript.md file(s), or a root folder containing session folders",
    )
    parser.add_argument(
        "--also-title", action="store_true",
        help="Also force-regenerate the AI title/rename stage for each session (off by default — "
             "outline-only is the common case, and re-titling reshuffles filenames/folder names)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List which session folders would be processed, without actually running anything",
    )
    args = parser.parse_args()

    session_dirs: list[Path] = []
    seen: set[Path] = set()
    for raw in args.paths:
        try:
            resolved = resolve_session_dirs(raw.expanduser().resolve())
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        for session_dir in resolved:
            if session_dir not in seen:
                seen.add(session_dir)
                session_dirs.append(session_dir)

    print(f"Resolved {len(session_dirs)} session(s):")
    for d in session_dirs:
        print(f"  {d}")
    print()

    if args.dry_run:
        print("--dry-run: not actually running anything.")
        return

    force = {"outline"} | ({"title"} if args.also_title else set())

    succeeded, failed = [], []
    for i, session_dir in enumerate(session_dirs, 1):
        print(f"=== [{i}/{len(session_dirs)}] {session_dir.name} ===")
        try:
            final_dir = process_session(session_dir, force)
        except Exception as e:
            print(f"UNCAUGHT ERROR processing {session_dir}: {e}", file=sys.stderr)
            failed.append(session_dir)
            continue

        if status.stage_ok(final_dir, "outline"):
            succeeded.append(final_dir)
        else:
            failed.append(final_dir)
        print()

    print(f"Done: {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed sessions (check status.json / pipeline.log in each for why):")
        for d in failed:
            print(f"  {d}")
        sys.exit(1)


if __name__ == "__main__":
    main()
