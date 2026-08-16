"""Import an existing audio or video file into the normal pipeline.

    python -m mac_transcribe.import_media <path-to-file> [--title "My Title"]

Wraps the file into a new session folder (same layout a live recording
produces) and runs the full transcribe -> outline -> HTML pipeline on it.
Works on video files too — ffmpeg extracts the audio track, same as it
already does for RecorderApp's WAV -> MP3 encoding step; nothing downstream
(transcription, outline, HTML) knows or cares whether the source was audio
or video.
"""

import re
import subprocess
import sys
from datetime import date as date_cls
from pathlib import Path

from .config import load_config
from .mp3_encode import ffmpeg_path
from .process import process_session

# ffmpeg can read essentially any audio/video container; this list is just
# what we bother to sanity-check up front so a typo'd path fails fast with a
# clear message instead of a cryptic ffmpeg error.
SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".aiff", ".aif",
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm",
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "import"


def make_session_dir(recordings_dir: Path, title: str, date_str: str) -> Path:
    slug = slugify(title)
    name = f"{date_str}-{slug}"
    session_dir = recordings_dir / name
    suffix = 2
    while session_dir.exists():
        session_dir = recordings_dir / f"{name}-{suffix}"
        suffix += 1
    session_dir.mkdir(parents=True)
    return session_dir


def extract_audio(input_path: Path, mp3_path: Path) -> None:
    process = subprocess.run(
        [
            ffmpeg_path(), "-y", "-nostdin", "-v", "error",
            "-i", str(input_path),
            "-vn",  # drop video stream if present — we only want audio
            "-codec:a", "libmp3lame",
            str(mp3_path),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed extracting audio from {input_path}: {process.stderr.strip()}")


def import_file(input_path: Path, title: str | None = None, force: set[str] | None = None) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"No such file: {input_path}")
    if input_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unrecognized extension {input_path.suffix!r} for {input_path.name} — "
            f"expected one of: {', '.join(sorted(SUPPORTED_EXTENSIONS))} "
            "(ffmpeg likely handles it anyway; add it to SUPPORTED_EXTENSIONS if so)"
        )

    cfg = load_config()
    recordings_dir = Path(cfg["recordings_dir"]).expanduser()
    recordings_dir.mkdir(parents=True, exist_ok=True)

    date_str = date_cls.today().isoformat()
    session_title = title or input_path.stem
    session_dir = make_session_dir(recordings_dir, session_title, date_str)

    print(f"Importing {input_path.name} -> {session_dir}")
    extract_audio(input_path, session_dir / "mic.mp3")

    return process_session(session_dir, force)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--force-")}
    force = {f.replace("--force-", "") for f in flags}

    title = None
    if "--title" in sys.argv:
        idx = sys.argv.index("--title")
        if idx + 1 < len(sys.argv):
            title = sys.argv[idx + 1]

    if not args:
        print(__doc__)
        sys.exit(1)

    input_path = Path(args[0]).expanduser().resolve()
    try:
        final_dir = import_file(input_path, title=title, force=force)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Done: {final_dir}")


if __name__ == "__main__":
    main()
