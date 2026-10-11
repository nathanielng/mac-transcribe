"""CLI used by RecordingsVisualizer to transcribe a single, arbitrary audio
file (not a RecorderApp session folder) and propose a title for it.

    python3 -m mac_transcribe.describe_recording <audio-path> [--force]

Local inference first: transcription always goes through mlx-whisper
(transcribe_file in transcribe.py), the same path RecorderApp's own
pipeline uses. Title proposal reuses llm_backend.generate_text, so it
follows whatever outline_backend/model is already configured (mlx_lm by
default; Bedrock if the user has that set) — no separate config surface
for this feature. Amazon Transcribe is deliberately not wired in here yet
(local inference first, per the ask); transcribe_file would need a backend
switch mirroring transcribe.py's own transcribe_backend to add it later.

Writes/reuses a sidecar "<name>.transcript.txt" next to the audio file so
re-running (e.g. the user just wants a different title) doesn't re-run
whisper — pass --force to discard it and re-transcribe. Always prints
exactly one JSON object to stdout:

    {"transcript_path": "...", "transcript": "...",
     "proposed_title": "...", "error": null}

`error` is set (and proposed_title left "") only for a transcription
failure; a title-generation failure alone is reported the same way but
still includes the transcript, since that half succeeded and is still
useful (e.g. local mlx_lm outline model not installed).
"""

import json
import re
import sys
from pathlib import Path

from .config import load_config
from .llm_backend import generate_text
from .title import TITLE_PROMPT, humanize_slug
from .transcribe import transcribe_file

# Keeps the title prompt's token count bounded for a multi-hour recording's
# transcript — a title only needs the gist, not the whole thing, and every
# backend (local mlx_lm included) has a context limit this could otherwise
# blow past.
MAX_TRANSCRIPT_CHARS_FOR_TITLE = 8000


def transcript_sidecar(audio_path: Path) -> Path:
    return audio_path.with_name(audio_path.name + ".transcript.txt")


def transcribe_plain(audio_path: Path, cfg: dict) -> str:
    segments = transcribe_file(audio_path, cfg["whisper_model"])
    return " ".join(seg["text"] for seg in segments).strip()


def propose_title(transcript: str, cfg: dict) -> str:
    if not transcript:
        return ""
    prompt = TITLE_PROMPT.format(transcript=transcript[:MAX_TRANSCRIPT_CHARS_FOR_TITLE])
    raw = generate_text(prompt, cfg, max_tokens=32).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "recording"
    return humanize_slug(slug)


def describe(audio_path: Path, force: bool = False) -> dict:
    cfg = load_config()
    sidecar = transcript_sidecar(audio_path)

    if sidecar.exists() and not force:
        transcript = sidecar.read_text()
    else:
        transcript = transcribe_plain(audio_path, cfg)
        sidecar.write_text(transcript)

    proposed_title = propose_title(transcript, cfg)
    return {
        "transcript_path": str(sidecar),
        "transcript": transcript,
        "proposed_title": proposed_title,
        "error": None,
    }


def main():
    args = sys.argv[1:]
    force = "--force" in args
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(__doc__)
        sys.exit(1)

    audio_path = Path(positional[0]).expanduser().resolve()
    if not audio_path.exists():
        print(json.dumps({"error": f"No such file: {audio_path}"}))
        sys.exit(1)

    try:
        result = describe(audio_path, force=force)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
