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
from .llm_backend import OutlineAuthError
from .outline import run as run_outline
from .session_split import split_session
from .silence import trim_trailing_silence
from .title import generate_title_slug, rename_session
from .transcribe import run as run_transcribe
from .html import build_html


def guess_title(session_dir: Path) -> str:
    # Session folder is named "<date>-<title>"; strip the leading date.
    name = session_dir.name
    parts = name.split("-", 3)
    return "-".join(parts[3:]) if len(parts) > 3 else name


def _trim_trailing_silence(session_dir: Path, cfg: dict) -> None:
    if not cfg.get("trim_trailing_silence", True):
        return
    threshold = cfg.get("trailing_silence_trim_threshold_seconds", 120)
    for source in ("mic", "system"):
        audio_path = session_dir / f"{source}.mp3"
        if not audio_path.exists():
            continue
        try:
            trimmed = trim_trailing_silence(audio_path, threshold)
            if trimmed:
                print(f"[trim] Removed {trimmed:.0f}s of trailing silence from {source}.mp3", flush=True)
        except Exception as e:
            # Forgetting to stop a recording is common and this is a
            # disk-space nicety, not a correctness requirement -- a broken
            # ffmpeg/ffprobe install shouldn't block transcription over it.
            print(f"[trim] Skipped ({source}.mp3): {e}", flush=True)


def process_session(session_dir: Path, force: set[str] | None = None) -> Path:
    force = force or set()
    cfg = load_config()
    date_str = date_cls.today().isoformat()

    # --- Stage 2: transcript ---
    transcript_path = session_dir / "transcript.md"
    # "--force-outline" (the menu bar app's Regenerate-outline button) never
    # implies "--force-transcript". If status.json doesn't explicitly say
    # transcript is ok (e.g. it predates status.json, or was reset), the old
    # check here re-ran mlx-whisper regardless, which requires mic.mp3/
    # system.mp3 — files that may well have been deleted long after
    # transcript.md was kept. A transcript.md already on disk is proof the
    # transcript stage doesn't need to be redone, same fallback logic
    # Session.swift already uses for its status pill (transcriptState).
    if "transcript" in force or (not status.stage_ok(session_dir, "transcript") and not transcript_path.exists()):
        _trim_trailing_silence(session_dir, cfg)
        transcribe_backend_desc = (
            f"mlx-whisper (model={cfg['whisper_model']})"
            if cfg.get("transcribe_backend", "mlx_whisper") == "mlx_whisper"
            else "Amazon Transcribe"
        )
        print(f"[transcript] Transcribing with {transcribe_backend_desc}...", flush=True)
        status.set_stage(session_dir, "transcript", "running")
        try:
            run_transcribe(session_dir, guess_title(session_dir), date_str, cfg)
            status.set_stage(session_dir, "transcript", "ok")
            print("[transcript] Done.", flush=True)
        except Exception as e:
            status.set_stage(session_dir, "transcript", "failed", str(e))
            print(f"[transcript] FAILED: {e}", flush=True)
            return session_dir  # nothing downstream can run without a transcript
    else:
        status.set_stage(session_dir, "transcript", "ok")
        print("[transcript] Already ok, skipping.", flush=True)

    # A long silent gap followed by more conversation usually means Stop
    # Recording got forgotten and a second, unrelated conversation ended up
    # in the same file -- split into separate sessions rather than silently
    # merging two unrelated outlines into one. Each part re-enters the rest
    # of this function on its own, so it gets its own outline/title/HTML.
    part_dirs = split_session(session_dir, cfg)
    if len(part_dirs) > 1:
        print(f"[split] Long gap detected -- split into {len(part_dirs)} sessions: "
              f"{', '.join(d.name for d in part_dirs)}", flush=True)
        results = [_process_outline_title_html(part_dir, cfg, force, date_str) for part_dir in part_dirs]
        return results[0]

    return _process_outline_title_html(part_dirs[0], cfg, force, date_str)


def _process_outline_title_html(session_dir: Path, cfg: dict, force: set[str], date_str: str) -> Path:
    title = guess_title(session_dir)
    transcript_md = (session_dir / "transcript.md").read_text()

    # --- Stage 3: outline + optional AI title/rename, concurrently ---
    run_title_stage = cfg.get("auto_rename_with_ai_title", True)
    backend_desc = (
        f"Bedrock (model={cfg['bedrock_model']}, region={cfg['bedrock_region']})"
        if cfg["outline_backend"] == "bedrock"
        else f"local MLX (model={cfg['mlx_outline_model']})"
    )

    def do_outline():
        if "outline" in force or not status.stage_ok(session_dir, "outline"):
            print(f"[outline] Submitting to {backend_desc}...", flush=True)
            status.set_stage(session_dir, "outline", "running")
            try:
                run_outline(session_dir, title, cfg)
                status.set_stage(session_dir, "outline", "ok")
                print("[outline] Done.", flush=True)
            except OutlineAuthError as e:
                status.set_stage(session_dir, "outline", "failed", f"auth: {e}")
                print(f"[outline] FAILED (auth): {e}", flush=True)
            except Exception as e:
                status.set_stage(session_dir, "outline", "failed", str(e))
                print(f"[outline] FAILED: {e}", flush=True)
        else:
            print("[outline] Already ok, skipping.", flush=True)

    def do_title_slug() -> str | None:
        if not run_title_stage:
            return None
        if "title" in force or not status.stage_ok(session_dir, "title_rename"):
            print(f"[title] Submitting to {backend_desc}...", flush=True)
            status.set_stage(session_dir, "title_rename", "running")
            try:
                slug = generate_title_slug(transcript_md, cfg)
                print(f"[title] Done: {slug!r}", flush=True)
                return slug
            except OutlineAuthError as e:
                status.set_stage(session_dir, "title_rename", "failed", f"auth: {e}")
                print(f"[title] FAILED (auth): {e}", flush=True)
            except Exception as e:
                status.set_stage(session_dir, "title_rename", "failed", str(e))
                print(f"[title] FAILED: {e}", flush=True)
        else:
            print("[title] Already ok, skipping.", flush=True)
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
        print(f"[title] Renaming session to use {slug!r}...", flush=True)
        session_dir = rename_session(session_dir, date_str, slug)
        status.set_stage(session_dir, "title_rename", "ok")
        print(f"[title] Renamed to: {session_dir}", flush=True)

    # --- Stage 3b: HTML (only if outline succeeded) ---
    if status.stage_ok(session_dir, "outline"):
        html_path = session_dir / f"{session_dir.name}.html"
        print(f"[html] Building {html_path.name}...", flush=True)
        try:
            build_html(session_dir / "transcript.md", session_dir / "outline.md", html_path)
            print(f"[html] Saved: {html_path}", flush=True)
        except Exception as e:
            status.set_stage(session_dir, "outline", "failed", f"html merge: {e}")
            print(f"[html] FAILED: {e}", flush=True)

    return session_dir


def main():
    # PipelineRunner.swift redirects this process's stdout/stderr to a log
    # file (and, since the process isn't attached to a real terminal,
    # Python defaults to fully-buffered rather than line-buffered stdout) —
    # without this, every print() above sits in a buffer and only appears
    # when the process exits, which looks identical to "nothing is being
    # printed at all" for a job that takes any real time to run.
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

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
