from pathlib import Path

from mac_transcribe import process, status


def _stub_cfg(monkeypatch):
    monkeypatch.setattr(process, "load_config", lambda: {
        "whisper_model": "stub", "outline_backend": "bedrock",
        "bedrock_model": "stub", "bedrock_region": "us-east-1",
        "auto_rename_with_ai_title": False,
    })


def test_force_outline_does_not_require_audio_when_transcript_exists(tmp_path: Path, monkeypatch):
    """Regression test: --force-outline alone used to also re-run mlx-whisper
    whenever status.json didn't explicitly mark transcript "ok" (e.g. a
    status.json that predates the transcript, or one that was reset), which
    raises FileNotFoundError if mic.mp3/system.mp3 were deleted after
    transcript.md was already written. transcript.md on disk should be
    enough to skip re-transcribing, regardless of status.json."""
    session_dir = tmp_path / "2026-01-01-test-session"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text("# Test\n\n## Transcript\n\nhello\n")
    # Deliberately no mic.mp3/system.mp3, and no status.json at all.

    _stub_cfg(monkeypatch)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("run_transcribe should not be called when transcript.md already exists")

    monkeypatch.setattr(process, "run_transcribe", fail_if_called)
    monkeypatch.setattr(process, "run_outline", lambda *a, **k: None)
    monkeypatch.setattr(process, "build_html", lambda *a, **k: None)
    status.set_stage(session_dir, "outline", "ok")  # so do_outline's own skip path is exercised too, harmlessly

    process.process_session(session_dir, force={"outline"})

    assert status.stage_ok(session_dir, "transcript") is True


def test_process_session_splits_and_runs_outline_on_each_part(tmp_path: Path, monkeypatch):
    """A transcript with a qualifying gap should result in two session
    folders, each independently getting an outline (and HTML, since outline
    "succeeds" via the stub) -- not one outline covering both
    conversations."""
    session_dir = tmp_path / "2026-01-01-two-conversations"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text(
        "# Test\n\n## Transcript\n\n"
        "**[00:00:00]** First conversation.\n\n"
        "**[00:20:00]** Second conversation, much later.\n\n"
    )
    status.set_stage(session_dir, "transcript", "ok")

    _stub_cfg(monkeypatch)
    outline_calls = []
    monkeypatch.setattr(process, "run_transcribe", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not re-transcribe")))
    monkeypatch.setattr(process, "run_outline", lambda session_dir, title, cfg: outline_calls.append(session_dir))
    monkeypatch.setattr(process, "build_html", lambda *a, **k: None)

    process.process_session(session_dir, force=set())

    assert len(outline_calls) == 2
    assert not session_dir.exists()  # replaced by the two "-part1"/"-part2" dirs
    for part_dir in outline_calls:
        assert status.stage_ok(part_dir, "outline") is True
