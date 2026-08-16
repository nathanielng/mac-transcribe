# mac-transcribe

Record audio on macOS — mic and/or system audio from apps like Zoom or
Microsoft Teams — and automatically get a transcript and a browsable HTML
outline. No cloud recording service, no virtual audio driver.

## How it works

Two components, coupled only through the filesystem:

- **`RecorderApp`** — a Swift/SwiftUI menu-bar app. Captures mic audio
  (`AVAudioEngine`) and/or system audio (`ScreenCaptureKit`, no BlackHole or
  similar driver required), encodes to MP3, and spawns the pipeline below.
- **`pipeline/`** — a Python CLI. Transcribes with MLX-Whisper (on-device,
  Apple Silicon GPU), generates an outline via Amazon Bedrock (Claude Sonnet
  5 by default) or fully locally via MLX, and merges both into a
  self-contained HTML page with a collapsible
  outline sidebar.

Every recording becomes one folder:

```
<recordings-dir>/2026-08-15-zoom-call/
  mic.mp3               # your voice
  system.mp3            # the other side of the call
  transcript.md          # merged, timestamp-interleaved
  outline.md              # Bedrock-generated
  2026-08-15-zoom-call.html
  status.json              # per-stage progress, polled by the app
```

If both mic and system audio are recorded, both are transcribed separately
and merged into one transcript ordered by timestamp, labeled `[You]` /
`[Call]`. An optional stage generates a short AI title from the transcript
and renames the whole session (mp3s, transcript, outline, html, folder) to
use it — runs concurrently with outline generation, gated by
`auto_rename_with_ai_title` in the config.

See [`plan.md`](plan.md) for the full design writeup and the reasoning behind
these choices (why two languages, why per-session folders, why not depend on
Claude Code/Kiro skills at runtime, etc).

## Setup

### Pipeline (Python)

```bash
source ~/.venv/bin/activate        # uv pip install below targets ~/.venv — without
                                    # this, `python3` resolves elsewhere and pytest
                                    # (or mac_transcribe itself) won't be found
cd pipeline
uv pip install -e ".[dev]"        # add ".[cjk]" too for Mandarin/Cantonese support
python3 -m pytest                  # pure-logic tests, no AWS/audio needed
```

Outline generation (Stage 3) has two backends, selected by `outline_backend`:

- **`bedrock`** (default) — requires AWS credentials with Bedrock access
  (`aws sts get-caller-identity` should work) and access to the Claude
  Sonnet 5 Global cross-region inference profile
  (`global.anthropic.claude-sonnet-5`) in `us-east-1`. If
  `AWS_BEARER_TOKEN_BEDROCK` is set in your environment, `pipeline`
  explicitly clears it and uses IAM/SigV4 instead — see
  `mac_transcribe/bedrock.py`. `bedrock_model` also accepts open-weight
  models hosted on Bedrock as Sonnet/Haiku-tier alternatives:
  `deepseek.v3.2` or `qwen.qwen3-vl-235b-a22b`.
- **`mlx_lm`** — fully local, no AWS credentials or network needed. Install
  with `uv pip install -e ".[mlx_lm]"`. `mlx_outline_model` accepts any
  mlx-lm-compatible instruct model; default is
  `mlx-community/Qwen3.5-4B-MLX-4bit` (fast, ~4GB), with
  `mlx-community/Qwen3.5-9B-MLX-4bit` or `mlx-community/Qwen3.8-27B-4bit`
  as higher-quality/higher-RAM options.

Transcription (Stage 2) is local-only via `mlx-whisper`; `whisper_model`
accepts any mlx-whisper-compatible model repo as a drop-in swap.

Config lives at `~/.config/mac-transcribe/config.toml` (created with
defaults on first run):

```toml
recordings_dir = "~/Recordings/mac-transcribe"
whisper_model = "mlx-community/whisper-large-v3-turbo"
outline_backend = "bedrock"                  # or "mlx_lm"
bedrock_model = "global.anthropic.claude-sonnet-5"
bedrock_region = "us-east-1"
bedrock_profile = "default"
mlx_outline_model = "mlx-community/Qwen3.5-4B-MLX-4bit"
auto_rename_with_ai_title = true
```

### Importing an existing audio or video file

To run an already-recorded file (not captured by RecorderApp) through the
same transcribe → outline → HTML pipeline:

```bash
cd pipeline
python3 -m mac_transcribe.import_media /path/to/file.mp4 --title "Optional Title"
```

Works on audio (mp3, wav, m4a, aac, flac, ogg, aiff) and video (mp4, mov,
m4v, mkv, avi, webm) — video files have their audio track extracted via
ffmpeg (`-vn`, same as RecorderApp's own WAV→MP3 encoding step); the rest of
the pipeline doesn't know or care whether the source was audio or video.
Wraps the file into a normal session folder under `recordings_dir` (same
layout a live recording produces, so it shows up in RecorderApp's recent
list and supports the same regenerate-on-failure flow), then runs the full
pipeline on it. `--title` is optional; defaults to the input filename.

### RecorderApp (Swift)

```bash
cd RecorderApp
swift build
.build/debug/RecorderApp
```

No Xcode required — builds with the Command Line Tools. See
[`RecorderApp/README.md`](RecorderApp/README.md) for first-run permission
setup (microphone + Screen & System Audio Recording) and current
implementation status.

## Status

Both halves are scaffolded and independently verified:

- **Pipeline**: full run verified end-to-end against real audio — MLX-Whisper
  transcription, a real Bedrock outline call, AI-title rename, and HTML
  generation all succeeded. 20 pytest cases cover the pure logic (merge,
  render, HTML build, status state machine, rename/collision handling).
- **RecorderApp**: builds and launches cleanly (`swift build`, confirmed
  running without crashing). Mic capture, system-audio capture, encoding,
  and the pipeline handoff are implemented but not yet exercised end-to-end
  against a live recording or a real meeting — see
  [`RecorderApp/README.md`](RecorderApp/README.md) for the current gap list.

## License

See [LICENSE](LICENSE).
