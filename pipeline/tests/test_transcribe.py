from mac_transcribe.transcribe import format_timestamp, merge_segments, render_transcript_md


def test_merge_segments_interleaves_by_start_time():
    mic = [{"start": 0.0, "end": 2.0, "text": "Hi everyone."}]
    system = [{"start": 1.0, "end": 3.0, "text": "Hello."}]

    merged = merge_segments({"mic": mic, "system": system})

    assert [s["source"] for s in merged] == ["mic", "system"]


def test_merge_segments_handles_single_source():
    mic = [{"start": 0.0, "end": 2.0, "text": "Solo mic."}]

    merged = merge_segments({"mic": mic})

    assert len(merged) == 1
    assert merged[0]["text"] == "Solo mic."


def test_merge_segments_empty_input():
    assert merge_segments({}) == []


def test_format_timestamp():
    assert format_timestamp(0) == "00:00:00"
    assert format_timestamp(65) == "00:01:05"
    assert format_timestamp(3661) == "01:01:01"


def test_render_transcript_md_includes_title_date_sources_and_labels():
    merged = [
        {"start": 0.0, "source": "mic", "text": "Hi there."},
        {"start": 5.0, "source": "system", "text": "Hello back."},
    ]

    md = render_transcript_md("Test", "2026-08-15", ["mic", "system"], merged)

    assert md.startswith("# Test\n")
    assert "- **Date:** 2026-08-15" in md
    assert "- **Sources:** Mic, System Audio" in md
    assert "## Transcript" in md
    assert "[00:00:00] [You]" in md
    assert "[00:00:05] [Call]" in md


def test_render_transcript_md_mic_only_source_label():
    merged = [{"start": 0.0, "source": "mic", "text": "Solo."}]

    md = render_transcript_md("Test", "2026-08-15", ["mic"], merged)

    assert "- **Sources:** Mic" in md
    assert "System Audio" not in md


def test_render_transcript_md_omits_per_segment_label_for_single_source():
    """Whisper has no speaker diarization — with only one audio source,
    every segment would trivially get the same [You]/[Call] tag regardless
    of how many people actually spoke into that one mic, falsely implying a
    per-speaker distinction that was never made. The tag only carries real
    information when there are two sources (mic vs. system) to distinguish."""
    merged = [
        {"start": 0.0, "source": "mic", "text": "First thing."},
        {"start": 5.0, "source": "mic", "text": "Second thing."},
    ]

    md = render_transcript_md("Test", "2026-08-15", ["mic"], merged)

    assert "[You]" not in md
    assert "**[00:00:00]** First thing." in md
    assert "**[00:00:05]** Second thing." in md


def test_render_transcript_md_shows_labels_for_two_sources():
    merged = [{"start": 0.0, "source": "system", "text": "Solo system audio."}]

    md = render_transcript_md("Test", "2026-08-15", ["mic", "system"], merged)

    assert "**[00:00:00] [Call]** Solo system audio." in md
