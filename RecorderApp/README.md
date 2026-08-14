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

## What's implemented (initial scaffold)

- `MicRecorder` — mic capture via `AVAudioEngine`, writes WAV
- `SystemAudioRecorder` — system-audio-only capture via `ScreenCaptureKit`
  (`SCStream`, audio-only, no BlackHole/virtual-driver dependency), writes WAV
- `MP3Encoder` — shells out to `ffmpeg` for WAV → MP3 (matches the pipeline
  side, which also assumes ffmpeg is installed)
- `RecordingController` — start/stop orchestration, session-folder naming
  (`yyyy-mm-dd-detected-source`, collision-suffixed), triggers the pipeline
  subprocess on stop
- `SourceDetector` — labels the session by frontmost known meeting app
  (Zoom/Teams/Slack/FaceTime) at record start; manual override via the
  source picker either way
- `PipelineRunner` — spawns `python3 -m mac_transcribe.process <session-dir>`
  from `../pipeline` using `~/.venv/bin/python3`, non-blocking
- `SessionStore` — polls the recordings folder + each session's
  `status.json` every 3s to drive the UI
- `MenuBarView` — record button + source picker, recent-recordings list with
  play buttons (mic/system), per-stage status chips (✅/⏳/❌/🔑 for auth
  failures) with a regenerate button on failed stages, click-through to the
  outline HTML

## Not yet implemented / known gaps

- No Settings UI yet for the recordings folder path (edit
  `~/.config/mac-transcribe/config.toml` directly — `Config.swift` reads/
  writes it, a picker just isn't wired into the menu yet)
- No waveform/level meter while recording
- Not code-signed or notarized; not packaged as a distributable `.app`
- `SystemAudioRecorder` is untested against a real Zoom/Teams call end-to-end
  (compiles and follows the documented ScreenCaptureKit audio-capture
  pattern, but hasn't been run against a live meeting yet)
