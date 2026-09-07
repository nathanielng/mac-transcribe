import shutil
import subprocess
from pathlib import Path

import pytest

from mac_transcribe import status
from mac_transcribe.mp3_encode import ffmpeg_path
from mac_transcribe.session_split import (
    find_gap_indices,
    parse_transcript_timestamps,
    split_session,
    split_transcript_md,
)

TRANSCRIPT_WITH_GAP = """# Test Session
- **Date:** 2026-01-01
- **Sources:** Mic

## Transcript

**[00:00:00]** Hello there.

**[00:00:10]** Bye now.

**[00:20:00]** Second conversation starts.

**[00:20:05]** Yep.
"""

TRANSCRIPT_NO_GAP = """# Test Session
- **Date:** 2026-01-01
- **Sources:** Mic

## Transcript

**[00:00:00]** Hello there.

**[00:00:30]** Still talking.
"""


def test_parse_transcript_timestamps():
    assert parse_transcript_timestamps(TRANSCRIPT_WITH_GAP) == [0, 10, 1200, 1205]


def test_find_gap_indices_detects_qualifying_gap():
    timestamps = parse_transcript_timestamps(TRANSCRIPT_WITH_GAP)
    assert find_gap_indices(timestamps, gap_seconds=300) == [2]


def test_find_gap_indices_no_gap_below_threshold():
    timestamps = parse_transcript_timestamps(TRANSCRIPT_NO_GAP)
    assert find_gap_indices(timestamps, gap_seconds=300) == []


def test_split_transcript_md_rebases_timestamps_and_keeps_header():
    parts = split_transcript_md(TRANSCRIPT_WITH_GAP, boundary_indices=[2])

    assert len(parts) == 2
    assert "# Test Session" in parts[0] and "# Test Session" in parts[1]
    assert "**[00:00:00]** Hello there." in parts[0]
    assert "**[00:00:10]** Bye now." in parts[0]
    assert "1200" not in parts[1] and "20:00" not in parts[1]
    assert "**[00:00:00]** Second conversation starts." in parts[1]
    assert "**[00:00:05]** Yep." in parts[1]


def test_split_transcript_md_no_boundaries_returns_single_part():
    parts = split_transcript_md(TRANSCRIPT_NO_GAP, boundary_indices=[])
    assert len(parts) == 1
    assert parts[0].strip().endswith("Still talking.")


def test_split_session_no_qualifying_gap_returns_unchanged(tmp_path: Path):
    session_dir = tmp_path / "2026-01-01-test-session"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text(TRANSCRIPT_NO_GAP)

    result = split_session(session_dir, {"split_gap_minutes": 5})

    assert result == [session_dir]
    assert session_dir.exists()


def test_split_session_disabled_via_config(tmp_path: Path):
    session_dir = tmp_path / "2026-01-01-test-session"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text(TRANSCRIPT_WITH_GAP)

    result = split_session(session_dir, {"auto_split_on_gaps": False, "split_gap_minutes": 5})

    assert result == [session_dir]


def _ffmpeg_available() -> bool:
    return shutil.which(ffmpeg_path()) is not None or Path(ffmpeg_path()).exists()


def _make_silent_mp3(path: Path, duration_seconds: float) -> None:
    subprocess.run(
        [ffmpeg_path(), "-y", "-nostdin", "-v", "error",
         "-f", "lavfi", "-i", f"anullsrc=r=16000:cl=mono", "-t", str(duration_seconds),
         "-codec:a", "libmp3lame", str(path)],
        check=True,
    )


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_split_session_end_to_end_splits_audio_and_transcript(tmp_path: Path):
    """Real ffmpeg round-trip: a session with a qualifying gap should end up
    as two session folders, each with its own mic.mp3 (roughly the right
    length) and its own rebased transcript.md, with the original folder
    removed."""
    session_dir = tmp_path / "2026-01-01-test-session"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text(TRANSCRIPT_WITH_GAP)
    _make_silent_mp3(session_dir / "mic.mp3", duration_seconds=1210)
    status.set_stage(session_dir, "transcript", "ok")

    result = split_session(session_dir, {"split_gap_minutes": 5})

    assert len(result) == 2
    assert not session_dir.exists()
    for part_dir in result:
        assert (part_dir / "transcript.md").exists()
        assert (part_dir / "mic.mp3").exists()
        assert status.stage_ok(part_dir, "transcript") is True

    part1_timestamps = parse_transcript_timestamps((result[0] / "transcript.md").read_text())
    part2_timestamps = parse_transcript_timestamps((result[1] / "transcript.md").read_text())
    assert part1_timestamps == [0, 10]
    assert part2_timestamps == [0, 5]
