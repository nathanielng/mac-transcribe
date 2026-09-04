import re
from pathlib import Path

import pytest

from mac_transcribe.html import build_html, parse_outline, parse_transcript, slice_transcript

TRANSCRIPT_MD = """# Test Session
- **Date:** 2026-08-15
- **Sources:** Mic, System Audio

## Transcript

**[00:00:00] [You]** Hi everyone, thanks for joining.

**[00:00:03] [Call]** Sure, happy to be here. Let's get started.

**[00:00:07] [Call]** First topic is the budget for next quarter.
"""

OUTLINE_MD = """# Outline: Test Session
- **Source:** local recording
---
This is a short meeting about budget planning.
---
## 1. Introductions
<!-- anchor: "Hi everyone, thanks for joining." -->
**Summary:** The host opens the meeting.
---
## 2. Budget Discussion
<!-- anchor: "First topic is the budget for next quarter." -->
**Summary:** The group discusses next quarter's budget.
---
## Key Takeaways
| Point | Detail |
|---|---|
| Budget raised | Next quarter's budget was discussed |
"""


def test_parse_transcript_extracts_metadata():
    title, date, sources, normalized = parse_transcript(TRANSCRIPT_MD)

    assert title == "Test Session"
    assert date == "2026-08-15"
    assert sources == "Mic, System Audio"
    assert "Hi everyone" in normalized


def test_parse_outline_finds_sections_and_takeaways():
    overview_html, sections, footer_html = parse_outline(OUTLINE_MD)

    assert "budget planning" in overview_html
    assert len(sections) == 2
    assert sections[0]["title"] == "1. Introductions"
    assert sections[0]["anchor"] == "Hi everyone, thanks for joining."
    assert "Budget raised" in footer_html


def test_slice_transcript_matches_anchors_in_order():
    _, _, _, normalized = parse_transcript(TRANSCRIPT_MD)
    _, sections, _ = parse_outline(OUTLINE_MD)

    slices = slice_transcript(normalized, sections)

    assert len(slices) == 2
    assert "Hi everyone" in slices[0]
    assert "budget for next quarter" in slices[1]
    assert not sections[0].get("anchor_missing")
    assert not sections[1].get("anchor_missing")


def test_slice_transcript_flags_missing_anchor():
    _, _, _, normalized = parse_transcript(TRANSCRIPT_MD)
    sections = [{"title": "Nonexistent", "anchor": "this text is not in the transcript"}]

    slices = slice_transcript(normalized, sections)

    assert sections[0]["anchor_missing"] is True
    assert "Could not locate" in slices[0]


def test_build_html_writes_output_and_reports_no_warnings(tmp_path: Path):
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text(OUTLINE_MD)

    warnings = build_html(transcript_path, outline_path, output_path)

    assert warnings == []
    html = output_path.read_text()
    assert "Test Session" in html
    assert "Introductions" in html
    assert "Budget Discussion" in html


def test_build_html_raises_on_outline_with_no_sections(tmp_path: Path):
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text("# Outline: Test\n---\nJust an overview, no sections.\n")

    with pytest.raises(ValueError):
        build_html(transcript_path, outline_path, output_path)


def test_build_html_handles_braces_and_dollar_signs_in_content(tmp_path: Path):
    """PAGE_TEMPLATE is rendered with string.Template ($-style), not
    str.format() ({}-style) — real transcript/outline content can contain
    literal braces (code snippets, JSON someone read aloud) or dollar signs
    without corrupting the page or raising, regardless of which
    substitution mechanism is used (neither re-scans substituted values —
    verified directly), but this locks in the actual rendered behavior."""
    transcript_md = (
        "# Test Session\n"
        "- **Date:** 2026-08-15\n"
        "- **Sources:** Mic\n\n"
        "## Transcript\n\n"
        '**[00:00:00] [You]** Config snippet: {"key": "value"} and $HOME and unicode 日本語.\n'
    )
    outline_md = (
        "# Outline: Test Session\n"
        "- **Source:** local recording\n"
        "---\n"
        "Overview mentioning {braces} and $dollars too.\n"
        "---\n"
        "## 1. Config Snippet\n"
        '<!-- anchor: "Config snippet:" -->\n'
        "**Summary:** Discusses a config with {braces} and a $VAR.\n"
        "---\n"
        "## Key Takeaways\n"
        "| Point | Detail |\n"
        "|---|---|\n"
        "| Braces | {a} $b handled fine |\n"
    )
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(transcript_md)
    outline_path.write_text(outline_md)

    warnings = build_html(transcript_path, outline_path, output_path)

    assert warnings == []
    html = output_path.read_text()

    # Outline/summary text goes through convert_markdown()'s inline() escaper
    # (HTML-escaped, not raw) but should still be present, braces/dollars intact.
    assert "{braces}" in html
    assert "$dollars" in html
    assert "{a} $b handled fine" in html

    # The transcript body itself is only present base64-encoded (for the
    # Download Transcript button), not as raw/escaped text in the page body —
    # decode it and confirm the original braces/dollar-sign content survived
    # the whole Template-substitution pipeline intact.
    import base64
    b64_match = re.search(r'TRANSCRIPT_B64 = "([^"]*)"', html)
    assert b64_match is not None
    decoded = base64.b64decode(b64_match.group(1)).decode("utf-8")
    assert '{"key": "value"}' in decoded
    assert "$HOME" in decoded


def test_build_html_embeds_downloadable_transcript(tmp_path: Path):
    """The HTML must let you regenerate transcript.md even after it's been
    deleted from disk (a real user workflow: keep the HTML, delete mp3s and
    transcript.md) - so the ORIGINAL transcript.md bytes must round-trip
    exactly out of the embedded base64, not just some derived text."""
    import base64

    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text(OUTLINE_MD)

    build_html(transcript_path, outline_path, output_path)
    html = output_path.read_text()

    assert 'id="downloadTranscriptBtn"' in html

    b64_match = re.search(r'TRANSCRIPT_B64 = "([^"]*)"', html)
    assert b64_match is not None
    decoded = base64.b64decode(b64_match.group(1)).decode("utf-8")
    assert decoded == TRANSCRIPT_MD

    filename_match = re.search(r'TRANSCRIPT_FILENAME = "([^"]*)"', html)
    assert filename_match is not None
    assert filename_match.group(1) == "test-session-transcript.md"


def test_page_template_has_no_premature_script_close(tmp_path: Path):
    """Real bug: PAGE_TEMPLATE's JS block once had a comment containing the
    literal text "</script>" as an example of what the code guards against.
    HTML parsers scan <script> content for that exact byte sequence
    case-insensitively, with zero awareness of JS syntax - they don't know
    it was "just a comment." That closes the script tag right there,
    dumping the rest of the real JS as visible text in the page body. The
    fix isn't just "don't do that in the current comment" (a human could
    reintroduce it in a future edit without realizing), so this asserts the
    literal tag appears exactly once in the whole rendered page - the one
    real closing tag - not just checks the specific line that broke once."""
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text(OUTLINE_MD)

    build_html(transcript_path, outline_path, output_path)
    html = output_path.read_text()

    assert html.lower().count("</script>") == 1


def test_build_html_renders_categorized_key_takeaways(tmp_path: Path):
    """outline.py's prompt now asks for Key Takeaways split into ### Action
    Items / Next Steps, ### Information, and ### Other subsections instead
    of one flat table - html.py needed no code changes for this (its
    markdown converter already handles arbitrary heading levels and
    multiple tables in sequence), but this wasn't previously exercised with
    more than one table in the footer block, so lock in that it actually
    renders all three as separate <h3> + <table> pairs."""
    outline_md = (
        "# Outline: Test Session\n"
        "- **Source:** local recording\n"
        "---\n"
        "Overview.\n"
        "---\n"
        "## 1. Introductions\n"
        '<!-- anchor: "Hi everyone, thanks for joining." -->\n'
        "**Summary:** The host opens the meeting.\n"
        "---\n"
        "## Key Takeaways\n"
        "### Action Items / Next Steps\n"
        "| Item | Detail |\n"
        "|---|---|\n"
        "| Send follow-up email | Owner: Alice, by Friday |\n"
        "### Information\n"
        "| Point | Detail |\n"
        "|---|---|\n"
        "| Budget approved | Next quarter's budget was discussed and approved |\n"
        "### Other\n"
        "| Point | Detail |\n"
        "|---|---|\n"
        "| Room booking issue | The usual meeting room was double-booked |\n"
    )
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text(outline_md)

    warnings = build_html(transcript_path, outline_path, output_path)

    assert warnings == []
    html = output_path.read_text()
    assert "<h3>Action Items / Next Steps</h3>" in html
    assert "<h3>Information</h3>" in html
    assert "<h3>Other</h3>" in html
    assert "Send follow-up email" in html
    assert "Budget approved" in html
    assert "Room booking issue" in html
    # Three separate tables, not one merged table
    assert html.count("<table>") == 3


def test_build_html_renders_key_takeaways_with_only_some_categories(tmp_path: Path):
    """The prompt tells the model to omit a ### subsection entirely (not
    leave an empty table) when a category has no items - e.g. a seminar
    with no action items. Confirm that renders fine with just one table."""
    outline_md = (
        "# Outline: Test Session\n"
        "- **Source:** local recording\n"
        "---\n"
        "Overview.\n"
        "---\n"
        "## 1. Introductions\n"
        '<!-- anchor: "Hi everyone, thanks for joining." -->\n'
        "**Summary:** The host opens the meeting.\n"
        "---\n"
        "## Key Takeaways\n"
        "### Information\n"
        "| Point | Detail |\n"
        "|---|---|\n"
        "| Budget approved | Next quarter's budget was discussed |\n"
    )
    transcript_path = tmp_path / "transcript.md"
    outline_path = tmp_path / "outline.md"
    output_path = tmp_path / "out.html"
    transcript_path.write_text(TRANSCRIPT_MD)
    outline_path.write_text(outline_md)

    warnings = build_html(transcript_path, outline_path, output_path)

    assert warnings == []
    html = output_path.read_text()
    assert "<h3>Information</h3>" in html
    assert "Action Items" not in html
    assert html.count("<table>") == 1
