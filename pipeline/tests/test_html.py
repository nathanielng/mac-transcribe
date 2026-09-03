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
