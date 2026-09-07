"""Trims trailing silence from a recording -- for when Stop Recording gets
forgotten and a session ends up with a long stretch of dead air at the end.
Runs before transcription (see process.py), so the wasted space is
reclaimed AND Whisper/Transcribe never has to process silence.

Pure signal-level (ffmpeg's silencedetect filter) -- no transcript needed,
so it works identically regardless of transcribe_backend.
"""

import re
import subprocess
from pathlib import Path

from .mp3_encode import ffmpeg_path, ffprobe_path

SILENCE_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([\d.]+)")

# Small safety margin kept after the detected silence start, so a trim can
# never clip the tail end of real speech even if silencedetect's boundary
# is a fraction of a second early.
TRIM_SAFETY_MARGIN_SECONDS = 1.0


def get_duration(path: Path) -> float:
    result = subprocess.run(
        [ffprobe_path(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def detect_silences(path: Path, noise_db: float = -35.0, min_silence_duration: float = 2.0) -> list[tuple[float, float]]:
    """Returns [(start, end), ...] silence intervals, in seconds. The final
    interval's `end` may be missing from ffmpeg's output if silence runs all
    the way to end-of-file (no silence_end event fires) -- callers that care
    about trailing silence should compare the last interval's start against
    the file's total duration instead of relying on `end` alone."""
    result = subprocess.run(
        [ffmpeg_path(), "-nostdin", "-i", str(path),
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    # ffmpeg logs filter output to stderr regardless of success/failure.
    starts = [float(m.group(1)) for m in SILENCE_START_RE.finditer(result.stderr)]
    ends = [float(m.group(1)) for m in SILENCE_END_RE.finditer(result.stderr)]

    intervals = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else None
        intervals.append((start, end))
    return intervals


def trim_trailing_silence(path: Path, threshold_seconds: float, noise_db: float = -35.0) -> float | None:
    """If the recording ends with >= threshold_seconds of silence, trims the
    file down to just past where that silence starts and returns how many
    seconds were removed. Returns None (no change made) if there's no
    qualifying trailing silence."""
    duration = get_duration(path)
    intervals = detect_silences(path, noise_db=noise_db, min_silence_duration=min(threshold_seconds, 2.0))
    if not intervals:
        return None

    last_start, last_end = intervals[-1]
    # Trailing silence either has no silence_end at all (ran to EOF) or one
    # that's within a fraction of a second of the file's actual duration --
    # ffmpeg's own frame-boundary rounding means it rarely lands exactly on
    # `duration`.
    runs_to_end = last_end is None or (duration - last_end) < 0.5
    if not runs_to_end:
        return None

    trailing_duration = duration - last_start
    if trailing_duration < threshold_seconds:
        return None

    new_duration = last_start + TRIM_SAFETY_MARGIN_SECONDS
    if new_duration >= duration:
        return None

    # ffmpeg picks its output muxer from the extension, so the temp file
    # needs to keep ".mp3" (a ".mp3.trimtmp" suffix fails with "Unable to
    # choose an output format") -- change the stem instead.
    tmp_path = path.with_name(path.stem + ".trimtmp" + path.suffix)
    subprocess.run(
        [ffmpeg_path(), "-y", "-nostdin", "-v", "error",
         "-i", str(path), "-t", str(new_duration), "-c", "copy", str(tmp_path)],
        check=True,
    )
    tmp_path.replace(path)
    return duration - new_duration
