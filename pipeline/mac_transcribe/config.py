"""Load ~/.config/mac-transcribe/config.toml (with sane defaults)."""

import tomllib
from pathlib import Path

CONFIG_PATH = Path("~/.config/mac-transcribe/config.toml").expanduser()

DEFAULTS = {
    "recordings_dir": str(Path("~/Recordings/mac-transcribe").expanduser()),
    # Any mlx-whisper-compatible model repo works here as a drop-in swap —
    # no code change needed, just edit this value.
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    # "bedrock" (Claude Sonnet 5 / other Bedrock-hosted models) or "mlx_lm"
    # (fully local, via the mlx-lm package). Both outline.py and title.py
    # dispatch on this — see llm_backend.py.
    "outline_backend": "bedrock",
    # Bedrock Global cross-region inference profile for Claude Sonnet 5.
    # Open-weight alternatives also hosted on Bedrock: "deepseek.v3.2"
    # (Sonnet-tier reasoning/instruction-following) or
    # "qwen.qwen3-vl-235b-a22b" (cheaper/faster, Haiku-tier).
    "bedrock_model": "global.anthropic.claude-sonnet-5",
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
