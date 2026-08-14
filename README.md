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
  4.6), and merges both into a self-contained HTML page with a collapsible
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
cd pipeline
uv pip install -e ".[dev]"        # add ".[cjk]" too for Mandarin/Cantonese support
python3 -m pytest                  # pure-logic tests, no AWS/audio needed
```

Requires AWS credentials with Bedrock access (`aws sts get-caller-identity`
should work) and access to the Claude Sonnet 4.6 Global cross-region
inference profile (`global.anthropic.claude-sonnet-4-6`) in `us-east-1`. If
`AWS_BEARER_TOKEN_BEDROCK` is set in your environment, `pipeline` explicitly
clears it and uses IAM/SigV4 instead — see `mac_transcribe/bedrock.py`.

Config lives at `~/.config/mac-transcribe/config.toml` (created with
defaults on first run):

```toml
recordings_dir = "~/Recordings/mac-transcribe"
whisper_model = "mlx-community/whisper-large-v3-turbo"
bedrock_model = "global.anthropic.claude-sonnet-4-6"
bedrock_region = "us-east-1"
bedrock_profile = "default"
auto_rename_with_ai_title = true
```

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
