"""Optional stage: generate a short AI title from the transcript, run in parallel with
outline generation, then rename the session's files/folder to use it.

Gated by config's auto_rename_with_ai_title. Never blocks transcript/outline access if
it fails (including auth failure, same as outline.py).
"""

import re
import shutil
from pathlib import Path

from .llm_backend import generate_text

TITLE_PROMPT = """Read this transcript and produce a short filesystem-safe title for it: \
3-6 words, lowercase, hyphen-separated, no punctuation other than hyphens. \
Reply with ONLY the slug, nothing else.

Transcript:

{transcript}
"""


def generate_title_slug(transcript_md: str, cfg: dict) -> str:
    prompt = TITLE_PROMPT.format(transcript=transcript_md)
    raw = generate_text(prompt, cfg, max_tokens=32).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "recording"


def rename_session(session_dir: Path, date: str, new_slug: str) -> Path:
    """Renames mic.mp3/system.mp3/transcript.md/outline.md/<old>.html and the session
    folder itself to use the new date-slug title. Returns the new session_dir path."""
    new_name = f"{date}-{new_slug}"
    new_dir = session_dir.parent / new_name

    if new_dir != session_dir and new_dir.exists():
        # avoid clobbering an existing session with the same generated title
        suffix = 2
        while (session_dir.parent / f"{new_name}-{suffix}").exists():
            suffix += 1
        new_name = f"{new_name}-{suffix}"
        new_dir = session_dir.parent / new_name

    old_name = session_dir.name
    for old_html in session_dir.glob(f"{old_name}.html"):
        old_html.rename(session_dir / f"{new_name}.html")

    if new_dir != session_dir:
        shutil.move(str(session_dir), str(new_dir))

    return new_dir


