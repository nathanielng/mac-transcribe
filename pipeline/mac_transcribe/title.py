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


def humanize_slug(slug: str) -> str:
    """"nea-aws-strategy-planning-meeting" -> "Nea Aws Strategy Planning Meeting" —
    matches RecorderApp's SessionRow title display (replacingOccurrences + .capitalized)
    so the HTML title/header matches what's shown in the app's recent-recordings list."""
    return slug.replace("-", " ").title()


def update_transcript_title(session_dir: Path, new_title: str) -> None:
    """Rewrites transcript.md's `# <title>` header line. Without this, the
    HTML page's <title>/<h1> stay stuck on the pre-rename placeholder title
    forever — html.py's build_html() reads its title from this line via
    parse_transcript(), and rename_session() only ever renamed *files*, never
    touched the title *inside* them."""
    path = session_dir / "transcript.md"
    if not path.exists():
        return
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines[i] = f"# {new_title}"
            break
    path.write_text("\n".join(lines) + "\n")


def rename_session(session_dir: Path, date: str, new_slug: str) -> Path:
    """Renames mic.mp3/system.mp3/transcript.md/outline.md/<old>.html and the session
    folder itself to use the new date-slug title, and updates transcript.md's title
    header to match (see update_transcript_title). Returns the new session_dir path."""
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

    update_transcript_title(session_dir, humanize_slug(new_slug))

    if new_dir != session_dir:
        shutil.move(str(session_dir), str(new_dir))

    return new_dir


