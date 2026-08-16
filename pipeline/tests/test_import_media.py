from pathlib import Path

import pytest

from mac_transcribe.import_media import import_file, make_session_dir, slugify


def test_slugify():
    assert slugify("My Great Meeting!") == "my-great-meeting"
    assert slugify("   ") == "import"
    assert slugify("already-a-slug") == "already-a-slug"


def test_make_session_dir_creates_folder(tmp_path: Path):
    session_dir = make_session_dir(tmp_path, "Team Sync", "2026-08-16")

    assert session_dir.name == "2026-08-16-team-sync"
    assert session_dir.exists()


def test_make_session_dir_avoids_collision(tmp_path: Path):
    (tmp_path / "2026-08-16-team-sync").mkdir()

    session_dir = make_session_dir(tmp_path, "Team Sync", "2026-08-16")

    assert session_dir.name == "2026-08-16-team-sync-2"


def test_import_file_rejects_unrecognized_extension(tmp_path: Path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("not media")

    with pytest.raises(ValueError, match="Unrecognized extension"):
        import_file(bogus)


def test_import_file_rejects_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        import_file(tmp_path / "does-not-exist.mp4")
