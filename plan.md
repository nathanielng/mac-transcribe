# mac-transcribe — Plan

Record audio on macOS (mic and/or system audio from apps like Zoom/Teams), transcribe it
on-device, and generate a browsable HTML outline — automatically, end to end.

## Architecture

Two components, coupled only through the filesystem — no runtime dependency on Claude Code
or Kiro being installed/running:

- **`RecorderApp`** (SwiftUI menu bar app) — Stage 1: capture, encode, UI, orchestration trigger.
  Native because system-audio capture (ScreenCaptureKit) is Apple-API-only; no Python path exists.
- **`pipeline/`** (Python, `uv`-managed venv) — Stages 2–3: transcription, outline, HTML.
  Native because MLX-Whisper is Python/MLX-only; no Swift path exists.

The app invokes `pipeline/process.py <session-dir>` as a detached subprocess after recording
stops. Both sides read/write a shared `status.json` per session so the app can poll progress
and the pipeline can resume partial failures without redoing completed stages.

Why not depend on the existing Claude Code skills (`audio-transcribe`, `outline`,
`transcript-outline-html`) directly at runtime: `audio-transcribe` has no LLM step at all
(it's just `mlx_whisper` + save), and `transcript-outline-html`'s `merge-html.py` is a
plain dependency-free script — both get **ported/vendored** into `pipeline/` rather than
invoked through Claude Code, so the app never requires Claude Code to be running. The
`outline` skill's LLM step is replaced with a direct Anthropic API call from `pipeline/`,
using an equivalent prompt. Improvements to the original skills would need to be manually
ported — a deliberate one-way sync, trading auto-update for not having a background
recorder depend on an interactive coding tool.

## File layout & naming

Per-session folder (not flat files) so mic-only / mic+system / retries can share one title
and the app has a single `status.json` to poll:

```
<configured-folder>/
  2026-08-15-zoom-call/
    mic.mp3
    system.mp3
    transcript.md          # merged, timestamp-interleaved across mic + system
    outline.md              # Claude-generated
    2026-08-15-zoom-call.html
    status.json              # {mic: ok, system: ok, transcript: ok, outline: failed, error: "..."}
```

Naming: `yyyy-mm-dd-short-title`. Initial title = detected foreground app at record start
(Zoom, Microsoft Teams, etc.), slugified; falls back to `recording` for plain mic capture.
Numeric suffix (`-2`, `-3`) if the day+title collides. See **AI title & rename** below for
the optional follow-up rename once a better title is available.

Recordings folder location is user-configurable (`~/.config/mac-transcribe/config.toml`);
moving it just updates the config path — sessions are self-contained folders, so nothing
else needs to migrate.

## Stage 1 — RecorderApp (Swift/SwiftUI, menu bar)

- **Source detection:** poll `NSWorkspace.shared.frontmostApplication` / running apps for
  known bundle IDs (Zoom, Teams, Slack huddles, etc.) at record start, to label the source
  in the UI and seed the title. Manual override in the source picker if detection is wrong.
- **Capture:** `SCStream` (ScreenCaptureKit, audio-only) for system audio → `system.mp3`;
  `AVAudioEngine` for mic → `mic.mp3`. Always independent files (not mixed) — since in a
  call both streams typically contain speech (your voice via mic, others via system audio),
  keeping them separate lets Stage 2 transcribe both and merge properly.
- **Encoding:** record to WAV, convert to MP3 on stop (ffmpeg or LAME, whichever's already
  available).
- **On stop:** write initial `status.json`, spawn `pipeline/process.py <session-dir>`
  detached, update UI as the pipeline updates `status.json` (poll or FSEvents on the folder).
- **UI (menu bar dropdown):**
  - Record button + live source picker (Mic / System / Both) + detected-source label
  - Recent recordings list: title, date, source, duration, ▶ playback
  - Per-item status chips: Transcript ✅/⏳/❌, Outline ✅/⏳/❌ (❌ from auth issues shown
    distinctly, see below)
  - "Regenerate transcript" / "Regenerate outline" buttons — re-invoke just that pipeline
    stage on an existing session folder
  - Clicking a completed item opens its `.html` in the default browser
- **Settings:** recordings folder picker, stored in `~/.config/mac-transcribe/config.toml`

## Stage 2 — Transcription (`pipeline/transcribe.py`)

- Ported from the `audio-transcribe` skill: `mlx-whisper` (`whisper-large-v3-turbo`) default
  backend, `mlx-audio`/Qwen3-ASR as CJK opt-in
- Runs once per mp3 present in the session (`mic.mp3`, `system.mp3`, or both); each produces
  timestamped segments (Whisper gives segment-level timestamps natively)
- Merge step interleaves `mic` and `system` segments by timestamp into one `transcript.md`,
  labeling each segment's source (`[You]` / `[Call]`) so a merged conversation stays legible
- Updates `status.json` (`transcript: ok|failed` + error text). This is a local, no-auth
  step — failures here are audio/model issues, not the auth-fallback case below.

## Stage 3 — Outline + HTML (`pipeline/outline.py`, `pipeline/merge_html.py`)

- `outline.py` calls the Anthropic API directly (`anthropic` SDK) with a prompt mirroring
  the `outline` skill's structure (overview, per-section title/anchor/summary, key
  takeaways table). Reads credentials from `ANTHROPIC_API_KEY` env var or a configured path.
- `merge_html.py` — vendored copy of `transcript-outline-html`'s `merge-html.py`, unmodified.
  Takes `transcript.md` + `outline.md`, produces the session's `.html`.
- **Auth-failure fallback:** the API call is wrapped so an `AuthenticationError` (expired/
  missing key) writes `status.json: outline: failed, error: "auth"` and stops cleanly,
  rather than crashing the subprocess. The menu bar app shows a distinct "🔑 needs auth"
  state (vs. generic failure), with the regenerate button re-attempting once credentials
  are fixed. The transcript is never blocked by an outline failure.

### AI title & rename (optional pipeline stage)

Config-gated (`auto_rename_with_ai_title = true/false` in `config.toml`). When enabled:

- Runs as a second AI call **in parallel with** outline generation (both only need
  `transcript.md`, so they run concurrently — e.g. via `asyncio.gather` or a thread pool —
  rather than serially, to avoid adding latency)
- Produces a short, filesystem-safe title from the transcript content
- Once **both** the title and outline calls complete, the pipeline renames in place:
  `mic.mp3`, `system.mp3`, `transcript.md`, `outline.md`, the generated `.html`, and the
  session folder itself, from the placeholder (app-detected) title to the AI-generated one
- `status.json` is updated with the new name so the menu bar app's recent-recordings list
  reflects it immediately
- If this stage fails (including auth failure, same fallback as outline), the session
  simply keeps its original app-detected title — never blocks transcript/outline access
- Manual "Regenerate title" follows the same per-stage regenerate pattern as
  transcript/outline

## Stage 4 — Glue (`pipeline/process.py`)

Single entry point the Swift app calls: transcribe (both files if present) → merge →
[outline + optional AI title/rename, run concurrently] → html. Each stage checks
`status.json` and skips work already marked `ok`, so re-running after a partial failure
only redoes the failed stage. This is also what the UI's "Regenerate transcript/outline/
title" buttons call, scoped to one stage.

## Build order

1. `pipeline/` first, fully working from the CLI against manually-recorded test mp3s —
   validates the transcription merge logic and the outline/title auth-fallback path without
   any Xcode/Swift friction.
2. Bare-bones `RecorderApp`: mic-only recording, save mp3, shell out to pipeline, no UI
   polish — proves ScreenCaptureKit/AVAudioEngine capture works end to end.
3. Add system-audio capture, source detection, then the full menu bar UI (recent list,
   playback, regenerate buttons, status chips).
