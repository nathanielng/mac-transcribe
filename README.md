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
  Apple Silicon GPU), generates an outline via Amazon Bedrock (Z.ai's GLM-5
  by default) or fully locally via MLX, and merges both into a
  self-contained HTML page with a collapsible outline sidebar. The original
  transcript is embedded in the page itself (base64) behind a "Download
  Transcript" button — the HTML survives if you later delete the mp3s and
  `transcript.md`, since that's a normal cleanup workflow. The outline's
  Key Takeaways are split into Action Items / Next Steps, Information, and
  Other — a category is omitted entirely (not left as an empty table) when
  a recording has none of it, e.g. a seminar with no action items.

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
`[Call]` — MLX-Whisper has no speaker diarization, so this label marks
which *source* a segment came from (mic vs. system), not who's speaking;
it's only shown when there are two sources to distinguish. A single-source
transcript (mic-only, the common case for an in-person meeting recorded on
one device) has no per-segment label at all, since one source recording
multiple people talking can't be told apart into individual speakers
either way — labeling everything "[You]" would misrepresent that. An
optional stage generates a short AI title from the transcript
and renames the whole session (mp3s, transcript, outline, html, folder) to
use it — runs concurrently with outline generation, gated by
`auto_rename_with_ai_title` in the config. The rename also updates the
title *inside* `transcript.md` (not just the filenames), so the generated
HTML page's `<title>`/`<h1>` reflect the new name too.

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
  (`aws sts get-caller-identity` should work). Default model is Z.ai's
  GLM-5 (`zai.glm-5`, open-weight) — reportedly competitive with Claude
  Sonnet on summarization/outline-style tasks, and unlike Sonnet 5 it
  doesn't require requesting model access first. `bedrock_model` also
  accepts Claude Sonnet 5 (`global.anthropic.claude-sonnet-5`, the Global
  cross-region inference profile — **needs to be requested manually** in
  the Bedrock console under Model access even with valid AWS credentials;
  not enabled by default) or other open-weight alternatives, all verified
  working with real calls: `deepseek.v3.2` or `qwen.qwen3-vl-235b-a22b`
  (cheaper/faster, Haiku-tier). If `AWS_BEARER_TOKEN_BEDROCK` is set in
  your environment, `pipeline` explicitly clears it and uses IAM/SigV4
  instead — see `mac_transcribe/bedrock.py`. Uses boto3's `bedrock-runtime`
  Converse API
  (model-agnostic) rather than the `anthropic` SDK's Bedrock client, which
  only speaks Claude's wire format and can't actually invoke non-Anthropic
  models. For Claude models specifically, extended thinking is explicitly
  disabled (`additionalModelRequestFields: {"thinking": {"type":
  "disabled"}}`) — outline/title generation don't need step-by-step
  reasoning, and a reasoning phase can otherwise consume the entire
  `maxTokens` budget before any usable text is produced.
- **`mlx_lm`** — fully local, no AWS credentials or network needed. Install
  with `uv pip install -e ".[mlx_lm]"`. `mlx_outline_model` accepts any
  mlx-lm-compatible instruct model; default is
  `mlx-community/Qwen3.5-4B-MLX-4bit` (fast, ~4GB), with
  `mlx-community/Qwen3.5-9B-MLX-4bit` (~6GB) or `mlx-community/Qwen3.8-27B-4bit`
  (~16GB, highest quality) as higher-RAM options — same models offered in
  RecorderApp's Settings picker. All download from Hugging Face on first
  use via `mlx_lm.load()` (which uses `huggingface_hub` under the hood,
  the same mechanism mlx-whisper already uses for transcription), cached
  under `~/.cache/huggingface/hub/` — no separate pull/download step.

Transcription (Stage 2) is local-only via `mlx-whisper`; `whisper_model`
accepts any mlx-whisper-compatible model repo as a drop-in swap.

Config lives at `~/.config/mac-transcribe/config.toml` (created with
defaults on first run):

```toml
recordings_dir = "~/Recordings/mac-transcribe"
whisper_model = "mlx-community/whisper-large-v3-turbo"
outline_backend = "bedrock"                  # or "mlx_lm"
bedrock_model = "zai.glm-5"
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

### Manual bulk scripts

`pipeline/scripts/` has a few standalone reference tools (not covered by
`pytest` — see each script's docstring for why, and cost/API-call caveats
where relevant):

- `regenerate_outlines.py` — re-run outline generation against
  already-transcribed sessions without going through RecorderApp, e.g.
  after changing `outline_backend`/`bedrock_model`. Accepts a session
  folder, a `transcript.md` file, or a root folder (auto-discovers session
  subfolders); `--dry-run` to preview, `--also-title` to also re-title.
- `build_action_items.py` — aggregates every session's "Action Items / Next
  Steps" (from the categorized Key Takeaways) into one `action_items.md` +
  `.csv` (columns: date, session_title, action_item, detail, html_path,
  status). Same session-selection as above, plus `--since`/`--until`
  date-range filtering. Falls back to decoding the outline embedded in a
  session's HTML when `outline.md` itself has been deleted — no API call
  either way, since it's pure markdown parsing.
- `check_bedrock_models.py` — smoke-checks each curated Bedrock model still
  works and returns the expected response shape. Makes real (billable) API
  calls, so it's not run automatically — see its docstring.

### Evaluating outline quality across backends/models

`pipeline/eval/` generates outlines for a few synthetic transcripts (a
status meeting, a technical seminar, a sales discovery call — different
content shapes on purpose) using each candidate backend/model, then uses
Claude Sonnet 5 as an LLM judge to score every candidate against its own
Sonnet 5 ("ground truth") outline for the same transcript:

```bash
cd pipeline
python3 -m eval.run_eval                              # all transcripts, all candidates
python3 -m eval.run_eval --transcript sales-discovery-call
python3 -m eval.run_eval --skip-judge                   # generate only, no scoring
```

Candidates evaluated: DeepSeek V3.2 and Qwen3-VL-235B on Bedrock, plus local
Qwen3.5-4B and Qwen3.5-9B via mlx_lm. Results land in
`eval/results/<transcript>/<candidate>.md` (the outlines themselves) and
`eval/results/report.md` (scores, rationale, cross-transcript averages).
Requires the Sonnet 5 Bedrock access noted above for the ground-truth/judge
passes — without it, the harness still generates and records each
candidate's outline, it just skips scoring rather than failing outright.

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

Both halves are verified against real audio, real recordings, and real
model calls (not just unit tests):

- **Pipeline**: full run verified end-to-end — MLX-Whisper transcription,
  outline generation via Bedrock (Claude, DeepSeek, and Qwen all confirmed
  working) and via local mlx_lm, AI-title rename, HTML generation, and
  importing an existing video file all succeeded on real input. 30 pytest
  cases cover the pure logic (transcript merge/render, HTML parse/build,
  status state machine + a concurrency-race regression test, rename/
  collision handling, LLM-backend dispatch, media-import validation).
- **RecorderApp**: a full record → stop → encode → transcribe → outline
  cycle has been run manually end-to-end (mic-only) with real output
  inspected in a browser. Settings UI, mic level meter, and the
  recordings-folder shortcut are implemented and smoke-tested. System-audio
  capture (`ScreenCaptureKit`) is implemented and compiles but not yet
  exercised against a real Zoom/Teams call — see
  [`RecorderApp/README.md`](RecorderApp/README.md) for the current gap list.

See [`LEARNINGS.md`](LEARNINGS.md) (local, gitignored) for the full list of
real bugs found during manual testing and how they were diagnosed/fixed —
several were silent-failure classes that unit tests alone wouldn't have
caught (a SIGTTOU hang, a Bedrock SDK that couldn't actually invoke the
models it appeared to support, an accessory-app window-activation gotcha).

## License

See [LICENSE](LICENSE).
