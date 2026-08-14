"""Stage 2: transcribe mic.mp3 / system.mp3 with mlx-whisper, merge into transcript.md.

Ported from the ~/.kiro/skills/audio-transcribe skill's mlx-whisper backend.
"""

from pathlib import Path

SOURCE_LABELS = {"mic": "You", "system": "Call"}


def transcribe_file(path: Path, model: str, language: str | None = None) -> list[dict]:
    """Returns a list of {start, end, text} segments."""
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(path), path_or_hf_repo=model, language=language
    )
    return [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
        for seg in result["segments"]
        if seg["text"].strip()
    ]


def merge_segments(segments_by_source: dict[str, list[dict]]) -> list[dict]:
    """Interleave segments from multiple sources by start time.

    Returns a flat list of {start, source, text}, sorted chronologically.
    """
    merged = [
        {"start": seg["start"], "source": source, "text": seg["text"]}
        for source, segs in segments_by_source.items()
        for seg in segs
    ]
    merged.sort(key=lambda s: s["start"])
    return merged


def format_timestamp(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def render_transcript_md(title: str, date: str, sources: list[str], merged: list[dict]) -> str:
    source_labels = ", ".join(
        "Mic" if s == "mic" else "System Audio" for s in sources
    )
    lines = [
        f"# {title}",
        f"- **Date:** {date}",
        f"- **Sources:** {source_labels}",
        "",
        "## Transcript",
        "",
    ]
    for seg in merged:
        ts = format_timestamp(seg["start"])
        label = SOURCE_LABELS.get(seg["source"], seg["source"])
        lines.append(f"**[{ts}] [{label}]** {seg['text']}")
        lines.append("")
    return "\n".join(lines)


def run(session_dir: Path, title: str, date: str, model: str) -> Path:
    """Transcribes any of mic.mp3 / system.mp3 present, writes transcript.md."""
    segments_by_source = {}
    for source in ("mic", "system"):
        audio_path = session_dir / f"{source}.mp3"
        if audio_path.exists():
            segments_by_source[source] = transcribe_file(audio_path, model)

    if not segments_by_source:
        raise FileNotFoundError(f"No mic.mp3 or system.mp3 found in {session_dir}")

    merged = merge_segments(segments_by_source)
    transcript_md = render_transcript_md(
        title, date, list(segments_by_source.keys()), merged
    )

    out_path = session_dir / "transcript.md"
    out_path.write_text(transcript_md)
    return out_path
