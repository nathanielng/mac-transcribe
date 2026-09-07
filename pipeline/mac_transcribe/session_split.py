"""Splits a session into multiple sessions when its transcript has a long
silent gap in the middle -- usually Stop Recording being forgotten,
followed by an unrelated second conversation captured in the same file.

Detected purely from transcript.md's per-line timestamps (works the same
regardless of transcribe_backend), then the underlying audio is sliced to
match with ffmpeg (stream copy, no re-encode). Each resulting part gets its
own session folder with transcript stage already marked "ok" -- outline/
title/HTML still need to run per part, same as any freshly transcribed
session.
"""

import re
import shutil
import subprocess
from pathlib import Path

from . import status
from .mp3_encode import ffmpeg_path
from .transcribe import format_timestamp

TIMESTAMP_LINE_RE = re.compile(r"^\*\*\[(\d\d):(\d\d):(\d\d)\]")

# transcript.md only records each line's *start* time, not its end, so a
# gap measured between consecutive start times slightly overstates the
# actual silence (it also includes however long the earlier line took to
# say). Cutting the audio this far past the earlier line's start -- rather
# than exactly at it -- keeps the cut comfortably inside the silence
# without needing real segment-end timing.
SPLIT_BUFFER_SECONDS = 5.0


def _parse_timestamp(h: str, m: str, s: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s)


def parse_transcript_timestamps(transcript_md: str) -> list[float]:
    """One timestamp per transcript line that has one, in the order they appear."""
    times = []
    for line in transcript_md.splitlines():
        match = TIMESTAMP_LINE_RE.match(line.strip())
        if match:
            times.append(_parse_timestamp(*match.groups()))
    return times


def find_gap_indices(timestamps: list[float], gap_seconds: float) -> list[int]:
    """Returns the index of the first line *after* each qualifying gap --
    i.e. where a new part should start. Empty if no gap is long enough."""
    return [i + 1 for i in range(len(timestamps) - 1) if timestamps[i + 1] - timestamps[i] >= gap_seconds]


def split_transcript_md(transcript_md: str, boundary_indices: list[int]) -> list[str]:
    """Splits transcript_md into len(boundary_indices) + 1 parts at the
    given segment indices, re-basing each part's timestamps to start at
    00:00:00 (each part is its own standalone transcript) while keeping
    the original title/date/sources header on every part."""
    lines = transcript_md.splitlines()
    header_end = next(i for i, line in enumerate(lines) if line.strip() == "## Transcript") + 2
    header = lines[:header_end]

    segments: list[tuple[str, float]] = []
    for line in lines[header_end:]:
        match = TIMESTAMP_LINE_RE.match(line.strip())
        if match:
            segments.append((line, _parse_timestamp(*match.groups())))

    bounds = [0, *boundary_indices, len(segments)]
    parts = []
    for start, end in zip(bounds, bounds[1:]):
        chunk = segments[start:end]
        if not chunk:
            continue
        offset = chunk[0][1]
        body: list[str] = []
        for line, ts in chunk:
            new_line = TIMESTAMP_LINE_RE.sub(f"**[{format_timestamp(ts - offset)}]", line.strip(), count=1)
            body.append(new_line)
            body.append("")
        parts.append("\n".join([*header, *body]) + "\n")
    return parts


def _make_part_dirs(session_dir: Path, count: int) -> list[Path]:
    parent = session_dir.parent
    dirs = []
    for i in range(1, count + 1):
        name = f"{session_dir.name}-part{i}"
        part_dir = parent / name
        suffix = 2
        while part_dir.exists():
            part_dir = parent / f"{name}-{suffix}"
            suffix += 1
        part_dir.mkdir(parents=True)
        dirs.append(part_dir)
    return dirs


def _slice_audio(src_path: Path, cut_times: list[float], out_paths: list[Path]) -> None:
    starts = [0.0, *cut_times]
    for i, (start, out_path) in enumerate(zip(starts, out_paths)):
        args = [ffmpeg_path(), "-y", "-nostdin", "-v", "error"]
        if start:
            args += ["-ss", str(start)]
        args += ["-i", str(src_path)]
        if i < len(cut_times):
            args += ["-t", str(cut_times[i] - start)]
        args += ["-c", "copy", str(out_path)]
        subprocess.run(args, check=True)


def split_session(session_dir: Path, cfg: dict) -> list[Path]:
    """If transcript.md has a gap of cfg['split_gap_minutes'] (default 5) or
    more between two consecutive lines, splits the session into multiple
    session folders -- transcript and audio both sliced to match, one part
    per detected conversation. Returns [session_dir] unchanged if
    auto_split_on_gaps is off or no qualifying gap was found."""
    if not cfg.get("auto_split_on_gaps", True):
        return [session_dir]

    transcript_path = session_dir / "transcript.md"
    if not transcript_path.exists():
        return [session_dir]

    transcript_md = transcript_path.read_text()
    timestamps = parse_transcript_timestamps(transcript_md)
    gap_seconds = cfg.get("split_gap_minutes", 5) * 60
    boundary_indices = find_gap_indices(timestamps, gap_seconds)
    if not boundary_indices:
        return [session_dir]

    cut_times = [timestamps[i - 1] + SPLIT_BUFFER_SECONDS for i in boundary_indices]
    transcript_parts = split_transcript_md(transcript_md, boundary_indices)
    part_dirs = _make_part_dirs(session_dir, len(transcript_parts))

    for part_dir, part_transcript in zip(part_dirs, transcript_parts):
        (part_dir / "transcript.md").write_text(part_transcript)
        status.set_stage(part_dir, "transcript", "ok")

    for source in ("mic", "system"):
        src_audio = session_dir / f"{source}.mp3"
        if src_audio.exists():
            _slice_audio(src_audio, cut_times, [d / f"{source}.mp3" for d in part_dirs])

    shutil.rmtree(session_dir)
    return part_dirs
