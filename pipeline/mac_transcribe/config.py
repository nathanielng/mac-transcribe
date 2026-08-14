"""Load ~/.config/mac-transcribe/config.toml (with sane defaults)."""

import tomllib
from pathlib import Path

CONFIG_PATH = Path("~/.config/mac-transcribe/config.toml").expanduser()

DEFAULTS = {
    "recordings_dir": str(Path("~/Recordings/mac-transcribe").expanduser()),
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    # Bedrock Global cross-region inference profile for Claude Sonnet 4.6.
    "bedrock_model": "global.anthropic.claude-sonnet-4-6-v1:0",
    "bedrock_region": "us-east-1",
    "auto_rename_with_ai_title": True,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            cfg.update(tomllib.load(f))
    return cfg
