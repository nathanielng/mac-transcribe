"""Shared Key-Takeaways table extraction for the aggregation scripts in this
directory (build_action_items.py, build_information.py) — kept in one place
so the two extraction mechanisms (raw outline.md, or the base64 fallback
embedded in a session's HTML) don't quietly drift between scripts."""

import base64
import re
from pathlib import Path

# Matches html.py's `const OUTLINE_B64 = "...";` line exactly.
OUTLINE_B64_RE = re.compile(r'OUTLINE_B64\s*=\s*"([^"]*)"')


def extract_outline_from_html(html_path: Path) -> str | None:
    """Recovers outline.md's original content from a session's HTML page,
    for when outline.md itself has been deleted from disk (see html.py's
    build_html() — it embeds outline.md as base64 for exactly this)."""
    match = OUTLINE_B64_RE.search(html_path.read_text())
    if not match or not match.group(1):
        return None
    return base64.b64decode(match.group(1)).decode("utf-8")


def load_outline_text(session_dir: Path, html_path: Path) -> str | None:
    """outline.md on disk if present, else falls back to what's embedded in
    the session's HTML. Returns None if neither has it."""
    outline_path = session_dir / "outline.md"
    if outline_path.exists():
        return outline_path.read_text()
    if html_path.exists():
        return extract_outline_from_html(html_path)
    return None


def extract_table_rows(outline_md: str, heading_prefix: str) -> list[tuple[str, str]]:
    """Pulls (first-column, second-column) rows out of the "### <heading_prefix>..."
    subsection of the Key Takeaways section — parses the raw markdown
    directly (not via html.py's parse_outline, which converts to HTML)
    since we want structured data, not rendered markup. heading_prefix is
    matched literally at the start of the heading text, e.g. "Action Items"
    matches "### Action Items / Next Steps"; "Information" matches
    "### Information"."""
    pattern = re.compile(
        r"(?m)^###\s*" + re.escape(heading_prefix) + r".*?\n(.*?)(?=\n###\s|\Z)", re.DOTALL
    )
    match = pattern.search(outline_md)
    if not match:
        return []

    rows = []
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if re.match(r"^:?-+:?$", first):  # markdown table separator row
            continue
        if first.lower() in ("item", "point"):  # header row
            continue
        second = cells[1] if len(cells) > 1 else ""
        rows.append((first, second))
    return rows
