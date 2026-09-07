"""Amazon Transcribe backend for transcribe.py -- adds speaker diarization
(Speaker 1/2/3/...) that mlx-whisper has no way to do at all. Selected via
config's transcribe_backend = "amazon_transcribe" (default remains
"mlx_whisper", fully local).

Batch (not streaming) Transcribe jobs require the source audio to sit in
S3 and write their JSON result back to S3 too, so this uploads the local
mp3, starts a job, polls for completion, downloads + parses the result,
then deletes the uploaded audio copy (the small result JSON is left in
the bucket in case you want to re-inspect a job later).
"""

import json
import time
import uuid
from pathlib import Path

import boto3

from .bedrock import is_auth_error  # same AWS-auth-error classification Bedrock calls use

POLL_INTERVAL_SECONDS = 5
JOB_TIMEOUT_SECONDS = 1800


def get_clients(region: str, profile: str):
    session = boto3.Session(profile_name=profile or "default", region_name=region)
    return session.client("transcribe"), session.client("s3")


def transcribe_file_aws(path: Path, cfg: dict) -> list[dict]:
    """Returns [{start, end, text, speaker}, ...] via an Amazon Transcribe
    batch job with speaker diarization enabled. speaker is a 1-based int
    (Transcribe's own "spk_0"/"spk_1" labels renumbered to be human-facing),
    or None if Transcribe couldn't assign one."""
    bucket = cfg.get("transcribe_s3_bucket")
    if not bucket:
        raise ValueError(
            "transcribe_backend is 'amazon_transcribe' but transcribe_s3_bucket "
            "isn't set in config.toml -- Amazon Transcribe batch jobs require an "
            "S3 bucket for input/output."
        )
    region = cfg.get("transcribe_region", "us-east-1")
    profile = cfg.get("transcribe_profile", "default")
    max_speakers = cfg.get("transcribe_max_speakers", 10)

    transcribe_client, s3_client = get_clients(region, profile)

    job_name = f"mac-transcribe-{uuid.uuid4().hex}"
    audio_key = f"mac-transcribe/{job_name}/{path.name}"
    result_key = f"mac-transcribe/{job_name}/result.json"

    try:
        s3_client.upload_file(str(path), bucket, audio_key)
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": f"s3://{bucket}/{audio_key}"},
            MediaFormat=path.suffix.lstrip(".") or "mp3",
            LanguageCode="en-US",
            OutputBucketName=bucket,
            OutputKey=result_key,
            Settings={"ShowSpeakerLabels": True, "MaxSpeakerLabels": max_speakers},
        )
        _wait_for_job(transcribe_client, job_name)
        obj = s3_client.get_object(Bucket=bucket, Key=result_key)
        data = json.loads(obj["Body"].read())
        return parse_transcribe_result(data)
    except Exception as e:
        if is_auth_error(e):
            raise
        raise
    finally:
        s3_client.delete_object(Bucket=bucket, Key=audio_key)


def _wait_for_job(client, job_name: str) -> dict:
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        resp = client.get_transcription_job(TranscriptionJobName=job_name)
        job = resp["TranscriptionJob"]
        job_status = job["TranscriptionJobStatus"]
        if job_status == "COMPLETED":
            return job
        if job_status == "FAILED":
            raise RuntimeError(f"Amazon Transcribe job {job_name} failed: {job.get('FailureReason')}")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"Amazon Transcribe job {job_name} did not complete within {JOB_TIMEOUT_SECONDS}s")


def parse_transcribe_result(data: dict) -> list[dict]:
    """Reshapes Transcribe's result JSON (results.items + results.speaker_labels.segments)
    into [{start, end, text, speaker}] segments, one per speaker turn --
    Transcribe reports word-level timing/speaker but not turn-level
    grouping, so this groups consecutive same-speaker words together the
    way a human reading a transcript would expect."""
    results = data["results"]
    word_items = results["items"]

    speaker_by_start_time: dict[str, str] = {}
    if "speaker_labels" in results:
        for seg in results["speaker_labels"]["segments"]:
            for item in seg["items"]:
                speaker_by_start_time[item["start_time"]] = seg["speaker_label"]

    segments: list[dict] = []
    current: dict | None = None
    for item in word_items:
        content = item["alternatives"][0]["content"]
        if item["type"] == "punctuation":
            if current is not None:
                current["text"] += content
            continue

        start = float(item["start_time"])
        end = float(item["end_time"])
        speaker_label = speaker_by_start_time.get(item["start_time"])

        if current is not None and current["speaker_label"] == speaker_label:
            current["text"] += " " + content
            current["end"] = end
        else:
            if current is not None:
                segments.append(current)
            current = {"start": start, "end": end, "text": content, "speaker_label": speaker_label}
    if current is not None:
        segments.append(current)

    # Renumber Transcribe's raw "spk_0"/"spk_1" labels to 1-based ints in
    # first-appearance order -- "spk_0" means nothing to a human reader, and
    # "Speaker 1" starting from a 0-indexed label would be confusing.
    speaker_numbers: dict[str, int] = {}
    for seg in segments:
        label = seg.pop("speaker_label")
        if label is not None and label not in speaker_numbers:
            speaker_numbers[label] = len(speaker_numbers) + 1
        seg["speaker"] = speaker_numbers.get(label)

    return segments
