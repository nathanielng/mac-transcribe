#!/usr/bin/env python3
"""Aggregate Information (facts/decisions) across sessions into one table.

Same idea as build_action_items.py, but for the "### Information"
subsection under Key Takeaways instead of Action Items — the facts,
decisions, and findings worth remembering that AREN'T action items (see
outline.py's OUTLINE_PROMPT for exactly how the model is told to split
these two categories apart).

Accepts the same session-selection forms as regenerate_outlines.py: a
session folder, a transcript.md file (parent folder used), or a root
folder containing multiple session folders one level down. If no paths are
given, defaults to config.toml's recordings_dir (i.e. "every session").

Usage (from pipeline/, with the venv active):
    python3 scripts/build_information.py                              # everything in recordings_dir
    python3 scripts/build_information.py ~/Recordings/mac-transcribe
    python3 scripts/build_information.py session-a/ session-b/
    python3 scripts/build_information.py --since 2026-08-01 --until 2026-08-31
    python3 scripts/build_information.py --output ~/Desktop/facts

Writes <output>.md and <output>.csv (default "./information"). Columns:
date, session_title, point, detail, html_path. No status column (unlike
build_action_items.py) — "done/pending" doesn't mean anything for a fact,
only for a task.

Sessions without an outline.md (outline stage never ran or failed) fall
back to the outline embedded (base64) in the session's HTML — html.py
embeds it specifically so it survives outline.md being deleted, without
needing a Bedrock/mlx_lm call to regenerate it. Only if neither outline.md
nor the HTML have it is a session actually skipped. Sessions whose folder
name isn't date-prefixed in the yyyy-mm-dd-title convention (so
--since/--until would fail to filter it) are also skipped, both noted, not
silently dropped.
"""

import argparse
import csv
import sys
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mac_transcribe.config import load_config  # noqa: E402
from _session_discovery import parse_session_name, resolve_all  # noqa: E402
from _takeaways import extract_table_rows, load_outline_text  # noqa: E402


def main():
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Session folder(s)/transcript.md file(s)/root folder(s). Defaults to config.toml's recordings_dir.",
    )
    parser.add_argument("--since", type=str, default=None, help="Only sessions dated on/after this (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, default=None, help="Only sessions dated on/before this (YYYY-MM-DD)")
    parser.add_argument(
        "--output", type=Path, default=Path("information"),
        help="Output path without extension (writes <output>.md and <output>.csv). Default: ./information",
    )
    args = parser.parse_args()

    since = date_cls.fromisoformat(args.since) if args.since else None
    until = date_cls.fromisoformat(args.until) if args.until else None

    input_paths = args.paths or [Path(load_config()["recordings_dir"])]
    try:
        session_dirs = resolve_all(input_paths)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Resolved {len(session_dirs)} session(s) before date filtering.")

    rows: list[dict] = []
    skipped_no_outline = []
    skipped_bad_date = []
    skipped_out_of_range = []

    for session_dir in session_dirs:
        date_str, title = parse_session_name(session_dir.name)

        session_date = None
        if date_str:
            try:
                session_date = date_cls.fromisoformat(date_str)
            except ValueError:
                session_date = None
        if (since or until) and session_date is None:
            skipped_bad_date.append(session_dir)
            continue
        if since and session_date and session_date < since:
            skipped_out_of_range.append(session_dir)
            continue
        if until and session_date and session_date > until:
            skipped_out_of_range.append(session_dir)
            continue

        html_path = session_dir / f"{session_dir.name}.html"
        outline_text = load_outline_text(session_dir, html_path)
        if outline_text is None:
            skipped_no_outline.append(session_dir)
            continue

        points = extract_table_rows(outline_text, "Information")
        for point, detail in points:
            rows.append({
                "date": date_str,
                "session_title": title.replace("-", " "),
                "point": point,
                "detail": detail,
                "html_path": str(html_path) if html_path.exists() else "",
            })

    print(f"Found {len(rows)} information item(s) across {len(session_dirs) - len(skipped_no_outline) - len(skipped_bad_date) - len(skipped_out_of_range)} session(s) with an outline.")
    if skipped_out_of_range:
        print(f"  {len(skipped_out_of_range)} session(s) outside --since/--until range, skipped.")
    if skipped_bad_date:
        print(f"  {len(skipped_bad_date)} session(s) skipped: folder name isn't date-prefixed, can't apply --since/--until to it.")
    if skipped_no_outline:
        print(f"  {len(skipped_no_outline)} session(s) skipped: no outline.md (outline stage never ran or failed).")

    columns = ["date", "session_title", "point", "detail", "html_path"]

    md_lines = ["| " + " | ".join(c.replace("_", " ").title() for c in columns) + " |",
                "|" + "|".join("---" for _ in columns) + "|"]
    for row in rows:
        md_lines.append("| " + " | ".join(row[c].replace("|", "\\|") for c in columns) + " |")

    md_path = args.output.with_suffix(".md")
    csv_path = args.output.with_suffix(".csv")
    md_path.parent.mkdir(parents=True, exist_ok=True)

    md_path.write_text("\n".join(md_lines) + "\n")
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {md_path} and {csv_path} ({len(rows)} rows).")


if __name__ == "__main__":
    main()
