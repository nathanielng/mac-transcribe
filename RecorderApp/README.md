# RecorderApp

Stage 1 of mac-transcribe: a menu-bar-only app that records mic and/or system
audio, encodes to MP3, and hands off to the Python pipeline in `../pipeline`
(Stages 2–3: transcription, outline, HTML).

## Build & run

```bash
swift build
.build/debug/RecorderApp
```

No Xcode required — this builds with the Command Line Tools (`swift build`),
since it only links system frameworks (AppKit, AVFoundation,
ScreenCaptureKit). There's no `.app` bundle; permission prompts and identity
are handled by embedding `Info.plist` directly into the binary's
`__TEXT,__info_plist` section (see `Package.swift`), which is the standard
approach for a plain SwiftPM executable that needs mic/screen permissions.

Launching prints a confirmation to stdout (`mac-transcribe RecorderApp is
running...`) — accessory apps have no Dock icon or window on launch, so
without this there's no sign of life from a terminal. Look for the mic icon
(🎙️) in the menu bar after that.

## First run — permissions

- **Microphone**: macOS will prompt the first time `MicRecorder` taps the
  input node (`NSMicrophoneUsageDescription` is embedded, so this is a normal
  prompt, not a crash).
- **Screen & System Audio Recording**: required for `SystemAudioRecorder`
  (ScreenCaptureKit). macOS won't prompt automatically for a CLI-launched
  binary the first time — go to System Settings → Privacy & Security →
  Screen & System Audio Recording and add `.build/debug/RecorderApp`
  manually if system-audio capture silently fails.
- Permissions are tied to the binary's path (`.build/debug/RecorderApp`) —
  a `swift build` that doesn't move the binary won't require re-granting.

## What's implemented

- `MicRecorder` — mic capture via `AVAudioEngine`, writes WAV, and reports a
  live 0...1 RMS input level (`onLevel`) so the UI can show a level meter
- `SystemAudioRecorder` — system-audio-only capture via `ScreenCaptureKit`
  (`SCStream`, audio-only, no BlackHole/virtual-driver dependency), writes WAV
- `MP3Encoder` — shells out to `ffmpeg` for WAV → MP3. Explicitly redirects
  ffmpeg's stdin/stdout to `/dev/null` and passes `-nostdin` — without this,
  ffmpeg inherited the app's controlling tty when launched from a terminal,
  called `tcsetattr` on it, and got suspended forever by `SIGTTOU` (a real
  bug found via manual testing: recordings would encode silently forever,
  no error, no crash — see `../LEARNINGS.md`)
- `RecordingController` — start/stop orchestration, session-folder naming
  (`yyyy-mm-dd-detected-source`, collision-suffixed), triggers the pipeline
  subprocess on stop (also with stdin hardened the same way, defensively)
- `SourceDetector` — labels the session by frontmost known meeting app
  (Zoom/Teams/Slack/FaceTime) at record start; manual override via the
  source picker either way
- `PipelineRunner` — spawns `python3 -m mac_transcribe.process <session-dir>`
  from `../pipeline` using `~/.venv/bin/python3`, non-blocking
- `SessionStore` — polls the recordings folder + each session's
  `status.json` every 3s to drive the UI
- `Config` — reads/writes `~/.config/mac-transcribe/config.toml` as a generic
  key/value dict (preserves keys this app doesn't know about yet, e.g. new
  pipeline-only config), with typed accessors for the keys it does know
- `SettingsView` — a separate window (recordings folder picker; transcription
  model field; outline backend segmented control with a curated model picker
  for each — Sonnet 5 / DeepSeek V3.2 / Qwen3-VL-235B for Bedrock, Qwen3.5
  4B/9B/27B for local MLX — plus free-text "Custom…" for either). Opened via
  the menu's Settings… button, which calls `NSApp.activate(ignoringOtherApps:
  true)` before `openWindow` — accessory apps don't get their windows raised
  by `openWindow` alone, a real bug found via manual testing (button visibly
  did nothing)
- `MenuBarView` — record button + source picker, live mic level meter,
  recordings-folder row with a 📂 open button, a live "currently configured"
  transcription/outline summary line, recent-recordings list with play
  buttons (mic/system), per-stage status chips (✅/⏳/❌/🔑 for auth
  failures) with a regenerate button on failed stages, click-through to the
  outline HTML, and the Settings… button

## Not yet implemented / known gaps

- Not code-signed or notarized; not packaged as a distributable `.app`
- `SystemAudioRecorder` is untested against a real Zoom/Teams call end-to-end
  (compiles and follows the documented ScreenCaptureKit audio-capture
  pattern, but hasn't been run against a live meeting yet)
- No waveform/level meter for system audio, only mic (system audio doesn't
  go through a tap callback the same way, so it'd need separate wiring)
