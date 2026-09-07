"""Load ~/.config/mac-transcribe/config.toml (with sane defaults)."""

import tomllib
from pathlib import Path

CONFIG_PATH = Path("~/.config/mac-transcribe/config.toml").expanduser()

DEFAULTS = {
    "recordings_dir": str(Path("~/Recordings/mac-transcribe").expanduser()),
    # Any mlx-whisper-compatible model repo works here as a drop-in swap —
    # no code change needed, just edit this value.
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    # "mlx_whisper" (fully local, default) or "amazon_transcribe" (adds
    # speaker diarization -- Speaker 1/2/3/... -- for recordings with
    # multiple people on one audio source, e.g. an in-person meeting on a
    # single mic; mlx-whisper has no way to do this at all). The
    # amazon_transcribe path requires transcribe_s3_bucket to be set, since
    # Transcribe's batch API needs S3 for both input audio and output JSON.
    "transcribe_backend": "mlx_whisper",
    "transcribe_region": "us-east-1",
    "transcribe_profile": "default",
    "transcribe_s3_bucket": "",
    "transcribe_max_speakers": 10,
    # Trims trailing silence (e.g. forgetting to hit Stop Recording) off
    # mic.mp3/system.mp3 before transcription -- saves disk and skips
    # wasted transcription time on dead air. See silence.py.
    "trim_trailing_silence": True,
    "trailing_silence_trim_threshold_seconds": 120,
    # If transcript.md has a gap this long (or longer) between two
    # consecutive lines, the session is split into separate sessions --
    # usually means Stop Recording was forgotten and a second, unrelated
    # conversation ended up in the same file. See session_split.py.
    "auto_split_on_gaps": True,
    "split_gap_minutes": 5,
    # "bedrock" (GLM-5 / Claude Sonnet 5 / other Bedrock-hosted models) or
    # "mlx_lm" (fully local, via the mlx-lm package). Both outline.py and
    # title.py dispatch on this — see llm_backend.py.
    "outline_backend": "bedrock",
    # Default is Z.ai's GLM-5 (open-weight, Bedrock-hosted) rather than
    # Claude Sonnet 5 — reportedly competitive with Sonnet on summarization/
    # outline-style tasks, and unlike Sonnet 5 it doesn't require requesting
    # model access manually in the Bedrock console first (see below).
    # Alternatives: "global.anthropic.claude-sonnet-5" (Global cross-region
    # inference profile — needs Model access requested manually in the
    # Bedrock console even with valid AWS credentials, not enabled by
    # default), "deepseek.v3.2" (also Sonnet-tier open-weight), or
    # "qwen.qwen3-vl-235b-a22b" (cheaper/faster, Haiku-tier).
    "bedrock_model": "zai.glm-5",
    "bedrock_region": "us-east-1",
    "bedrock_profile": "default",
    # Used when outline_backend = "mlx_lm". Any mlx-lm-compatible instruct
    # model works — this default is a good speed/quality balance; swap in
    # e.g. "mlx-community/Qwen3.5-9B-MLX-4bit" or "mlx-community/Qwen3.8-27B-4bit"
    # (~16GB download) for higher quality at the cost of more RAM and
    # slower generation, entirely via config.
    "mlx_outline_model": "mlx-community/Qwen3.5-4B-MLX-4bit",
    "auto_rename_with_ai_title": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            cfg.update(tomllib.load(f))
    return cfg
