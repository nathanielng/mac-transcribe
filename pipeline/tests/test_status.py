from pathlib import Path

from mac_transcribe import status


def test_load_defaults_when_missing(tmp_path: Path):
    data = status.load(tmp_path)

    assert set(data["stages"]) == set(status.STAGES)
    assert all(s["status"] == "pending" for s in data["stages"].values())


def test_set_stage_persists_and_round_trips(tmp_path: Path):
    status.set_stage(tmp_path, "transcript", "ok")

    assert status.stage_ok(tmp_path, "transcript") is True
    assert status.load(tmp_path)["stages"]["transcript"] == {"status": "ok", "error": None}


def test_set_stage_failed_with_error(tmp_path: Path):
    status.set_stage(tmp_path, "outline", "failed", "auth: expired token")

    data = status.load(tmp_path)
    assert data["stages"]["outline"]["status"] == "failed"
    assert "expired token" in data["stages"]["outline"]["error"]
    assert status.stage_ok(tmp_path, "outline") is False


def test_set_stage_does_not_clobber_other_stages(tmp_path: Path):
    status.set_stage(tmp_path, "transcript", "ok")
    status.set_stage(tmp_path, "outline", "failed", "boom")

    data = status.load(tmp_path)
    assert data["stages"]["transcript"]["status"] == "ok"
    assert data["stages"]["outline"]["status"] == "failed"


def test_concurrent_set_stage_does_not_lose_updates(tmp_path: Path):
    # Regression test for the race found during manual end-to-end testing:
    # process.py runs the outline and title-rename stages concurrently, and
    # both do read-modify-write on the same status.json. Without the lock in
    # status.py, one thread's write could clobber the other's.
    import threading

    def worker(stage):
        for _ in range(20):
            status.set_stage(tmp_path, stage, "running")
            status.set_stage(tmp_path, stage, "ok")

    threads = [
        threading.Thread(target=worker, args=("outline",)),
        threading.Thread(target=worker, args=("title_rename",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = status.load(tmp_path)
    assert data["stages"]["outline"]["status"] == "ok"
    assert data["stages"]["title_rename"]["status"] == "ok"
