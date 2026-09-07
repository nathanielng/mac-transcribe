import shutil
import subprocess
from pathlib import Path

import pytest

from mac_transcribe.mp3_encode import ffmpeg_path
from mac_transcribe.silence import detect_silences, get_duration, trim_trailing_silence


def _ffmpeg_available() -> bool:
    return shutil.which(ffmpeg_path()) is not None or Path(ffmpeg_path()).exists()


def _make_mp3(path: Path, spec: str, duration_seconds: float) -> None:
    """spec is an ffmpeg lavfi source description, e.g. anullsrc or sine."""
    subprocess.run(
        [ffmpeg_path(), "-y", "-nostdin", "-v", "error",
         "-f", "lavfi", "-i", f"{spec}", "-t", str(duration_seconds),
         "-codec:a", "libmp3lame", str(path)],
        check=True,
    )


def _make_tone_then_silence_mp3(path: Path, tone_seconds: float, silence_seconds: float) -> None:
    tone = path.with_name("tone.mp3")
    silence = path.with_name("silence.mp3")
    _make_mp3(tone, "sine=frequency=440", tone_seconds)
    _make_mp3(silence, "anullsrc=r=16000:cl=mono", silence_seconds)
    concat_list = path.with_name("concat.txt")
    concat_list.write_text(f"file '{tone}'\nfile '{silence}'\n")
    subprocess.run(
        [ffmpeg_path(), "-y", "-nostdin", "-v", "error",
         "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-codec:a", "libmp3lame", str(path)],
        check=True,
    )


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_get_duration(tmp_path: Path):
    path = tmp_path / "test.mp3"
    _make_mp3(path, "anullsrc=r=16000:cl=mono", 3.0)

    assert get_duration(path) == pytest.approx(3.0, abs=0.2)


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_detect_silences_finds_trailing_silence(tmp_path: Path):
    path = tmp_path / "test.mp3"
    _make_tone_then_silence_mp3(path, tone_seconds=2.0, silence_seconds=5.0)

    intervals = detect_silences(path, min_silence_duration=1.0)

    assert len(intervals) == 1
    start, end = intervals[0]
    assert start == pytest.approx(2.0, abs=0.3)


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_trim_trailing_silence_removes_trailing_dead_air(tmp_path: Path):
    path = tmp_path / "test.mp3"
    _make_tone_then_silence_mp3(path, tone_seconds=2.0, silence_seconds=10.0)
    original_duration = get_duration(path)

    trimmed = trim_trailing_silence(path, threshold_seconds=5.0)

    # Trims to just past where silence starts (~2s in) plus a 1s safety
    # margin, so ~9s of the 10s of trailing silence gets removed -- not
    # the full 10s, by design (see TRIM_SAFETY_MARGIN_SECONDS).
    assert trimmed is not None
    assert trimmed == pytest.approx(original_duration - 3.0, abs=0.5)
    new_duration = get_duration(path)
    assert new_duration < original_duration
    assert new_duration == pytest.approx(3.0, abs=0.5)


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_trim_trailing_silence_below_threshold_is_noop(tmp_path: Path):
    path = tmp_path / "test.mp3"
    _make_tone_then_silence_mp3(path, tone_seconds=2.0, silence_seconds=3.0)
    original_duration = get_duration(path)

    trimmed = trim_trailing_silence(path, threshold_seconds=10.0)

    assert trimmed is None
    assert get_duration(path) == pytest.approx(original_duration, abs=0.2)


@pytest.mark.skipif(not _ffmpeg_available(), reason="ffmpeg not installed")
def test_trim_trailing_silence_no_silence_is_noop(tmp_path: Path):
    path = tmp_path / "test.mp3"
    _make_mp3(path, "sine=frequency=440", 3.0)

    trimmed = trim_trailing_silence(path, threshold_seconds=1.0)

    assert trimmed is None
