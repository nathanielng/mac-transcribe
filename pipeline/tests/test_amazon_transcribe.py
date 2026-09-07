import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mac_transcribe import amazon_transcribe
from mac_transcribe.amazon_transcribe import parse_transcribe_result, transcribe_file_aws


def _item(type_, content, start=None, end=None):
    item = {"type": type_, "alternatives": [{"content": content}]}
    if start is not None:
        item["start_time"] = start
    if end is not None:
        item["end_time"] = end
    return item


def test_parse_transcribe_result_groups_words_by_speaker_turn():
    data = {
        "results": {
            "items": [
                _item("pronunciation", "Hello", start="0.0", end="0.5"),
                _item("pronunciation", "there", start="0.5", end="1.0"),
                _item("punctuation", "."),
                _item("pronunciation", "Hi", start="2.0", end="2.5"),
                _item("pronunciation", "back", start="2.5", end="3.0"),
                _item("punctuation", "."),
            ],
            "speaker_labels": {
                "segments": [
                    {"speaker_label": "spk_0", "items": [{"start_time": "0.0"}, {"start_time": "0.5"}]},
                    {"speaker_label": "spk_1", "items": [{"start_time": "2.0"}, {"start_time": "2.5"}]},
                ]
            },
        }
    }

    segments = parse_transcribe_result(data)

    assert segments == [
        {"start": 0.0, "end": 1.0, "text": "Hello there.", "speaker": 1},
        {"start": 2.0, "end": 3.0, "text": "Hi back.", "speaker": 2},
    ]


def test_parse_transcribe_result_renumbers_speakers_in_first_appearance_order():
    """Transcribe's raw spk_0/spk_1 labels are meaningless to a human reader
    -- and don't necessarily appear in numeric order in the transcript, so
    the renumbering must follow appearance order, not label sort order."""
    data = {
        "results": {
            "items": [
                _item("pronunciation", "First", start="0.0", end="0.5"),
                _item("pronunciation", "second", start="1.0", end="1.5"),
            ],
            "speaker_labels": {
                "segments": [
                    {"speaker_label": "spk_3", "items": [{"start_time": "0.0"}]},
                    {"speaker_label": "spk_1", "items": [{"start_time": "1.0"}]},
                ]
            },
        }
    }

    segments = parse_transcribe_result(data)

    assert [s["speaker"] for s in segments] == [1, 2]


def test_parse_transcribe_result_without_speaker_labels():
    data = {
        "results": {
            "items": [_item("pronunciation", "Solo", start="0.0", end="0.5")],
        }
    }

    segments = parse_transcribe_result(data)

    assert segments == [{"start": 0.0, "end": 0.5, "text": "Solo", "speaker": None}]

def _mock_clients(job_status="COMPLETED", result_data=None):
    transcribe_client = MagicMock()
    transcribe_client.exceptions.BadRequestException = type("BadRequestException", (Exception,), {})
    transcribe_client.get_transcription_job.return_value = {
        "TranscriptionJob": {"TranscriptionJobStatus": job_status, "FailureReason": "boom"}
    }

    s3_client = MagicMock()
    body = MagicMock()
    body.read.return_value = json.dumps(result_data or {"results": {"items": []}}).encode()
    s3_client.get_object.return_value = {"Body": body}

    return transcribe_client, s3_client


def test_transcribe_file_aws_requires_bucket_config():
    with pytest.raises(ValueError, match="transcribe_s3_bucket"):
        transcribe_file_aws(Path("audio.mp3"), {})


def test_transcribe_file_aws_cleans_up_audio_result_and_job_on_success(tmp_path, monkeypatch):
    """Regression test: a run must never leave stray artifacts behind --
    the uploaded audio, the result JSON, and the job's own entry in
    Transcribe's job list should all be deleted once the job completes."""
    transcribe_client, s3_client = _mock_clients()
    monkeypatch.setattr(amazon_transcribe, "get_clients", lambda region, profile: (transcribe_client, s3_client))
    monkeypatch.setattr(amazon_transcribe, "POLL_INTERVAL_SECONDS", 0)

    audio_path = tmp_path / "mic.mp3"
    audio_path.write_bytes(b"fake audio")

    transcribe_file_aws(audio_path, {"transcribe_s3_bucket": "my-bucket"})

    assert s3_client.delete_object.call_count == 2
    deleted_keys = {call.kwargs["Key"] for call in s3_client.delete_object.call_args_list}
    assert any("mic.mp3" in k for k in deleted_keys)
    assert any("result.json" in k for k in deleted_keys)
    transcribe_client.delete_transcription_job.assert_called_once()


def test_transcribe_file_aws_cleans_up_even_when_job_fails(tmp_path, monkeypatch):
    transcribe_client, s3_client = _mock_clients(job_status="FAILED")
    monkeypatch.setattr(amazon_transcribe, "get_clients", lambda region, profile: (transcribe_client, s3_client))
    monkeypatch.setattr(amazon_transcribe, "POLL_INTERVAL_SECONDS", 0)

    audio_path = tmp_path / "mic.mp3"
    audio_path.write_bytes(b"fake audio")

    with pytest.raises(RuntimeError, match="failed"):
        transcribe_file_aws(audio_path, {"transcribe_s3_bucket": "my-bucket"})

    assert s3_client.delete_object.call_count == 2
    transcribe_client.delete_transcription_job.assert_called_once()
