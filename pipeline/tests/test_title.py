from pathlib import Path

from mac_transcribe.title import humanize_slug, rename_session, update_transcript_title


def make_session(tmp_path: Path, name: str) -> Path:
    session_dir = tmp_path / name
    session_dir.mkdir()
    (session_dir / "mic.mp3").write_bytes(b"fake")
    (session_dir / "transcript.md").write_text("# placeholder\n- **Date:** 2026-08-15\n\n## Transcript\n\nHello.")
    (session_dir / f"{name}.html").write_text("<html></html>")
    return session_dir


def test_humanize_slug():
    assert humanize_slug("nea-aws-strategy-planning-meeting") == "Nea Aws Strategy Planning Meeting"
    assert humanize_slug("recording") == "Recording"


def test_update_transcript_title_replaces_only_the_header_line(tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    (session_dir / "transcript.md").write_text("# Old Title\n- **Date:** 2026-08-15\n\n## Transcript\n\nHello.")

    update_transcript_title(session_dir, "New Title")

    text = (session_dir / "transcript.md").read_text()
    assert text.startswith("# New Title\n")
    assert "- **Date:** 2026-08-15" in text
    assert "Hello." in text


def test_update_transcript_title_noop_when_no_transcript(tmp_path: Path):
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    update_transcript_title(session_dir, "New Title")  # should not raise

    assert not (session_dir / "transcript.md").exists()


def test_rename_session_moves_folder_and_html(tmp_path: Path):
    session_dir = make_session(tmp_path, "2026-08-15-recording")

    new_dir = rename_session(session_dir, "2026-08-15", "budget-planning-meeting")

    assert new_dir.name == "2026-08-15-budget-planning-meeting"
    assert new_dir.exists()
    assert not session_dir.exists()
    assert (new_dir / "mic.mp3").exists()
    assert (new_dir / "2026-08-15-budget-planning-meeting.html").exists()


def test_rename_session_avoids_collision_with_existing_folder(tmp_path: Path):
    make_session(tmp_path, "2026-08-15-budget-planning-meeting")
    session_dir = make_session(tmp_path, "2026-08-15-recording")

    new_dir = rename_session(session_dir, "2026-08-15", "budget-planning-meeting")

    assert new_dir.name == "2026-08-15-budget-planning-meeting-2"
    assert new_dir.exists()


def test_rename_session_is_noop_when_slug_matches_current_name(tmp_path: Path):
    session_dir = make_session(tmp_path, "2026-08-15-budget-planning-meeting")

    new_dir = rename_session(session_dir, "2026-08-15", "budget-planning-meeting")

    assert new_dir == session_dir
    assert session_dir.exists()


def test_rename_session_updates_transcript_title_header(tmp_path: Path):
    session_dir = make_session(tmp_path, "2026-08-15-recording")

    new_dir = rename_session(session_dir, "2026-08-15", "budget-planning-meeting")

    text = (new_dir / "transcript.md").read_text()
    assert text.startswith("# Budget Planning Meeting\n")
