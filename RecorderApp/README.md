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
  4B/9B/27B for local MLX — plus free-text "Custom…" for either; a toggle for
  auto title/rename; a toggle for sleep prevention). Opened via the menu's
  Settings… button, which calls `NSApp.activate(ignoringOtherApps: true)`
  before `openWindow` — accessory apps don't get their windows raised by
  `openWindow` alone, a real bug found via manual testing (button visibly
  did nothing)
- `SleepAssertion` — holds an IOKit `PreventSystemSleep` assertion (the same
  mechanism `caffeinate -s` uses) for the duration of a recording, so it
  continues with the lid closed and no external display — no manual
  `caffeinate` command needed. Enabled on Start Recording, released on Stop
  Recording or app quit; gated by the "Prevent sleep while recording"
  Settings toggle (on by default). Verified with a real `pmset -g assertions`
  check while held.
- `MenuBarView` — record button + source picker, live mic AND system-audio
  level meters (`SystemAudioRecorder.onLevel`, scaled 4x since system audio
  tends to run quieter than a close mic), recordings-folder row with a 📂
  open button, a live "currently configured" transcription/outline summary
  line, recent-recordings list with play buttons (mic/system), per-stage
  status chips (✅/⏳/❌/🔑 for auth failures) with a regenerate button on
  failed stages, a ▶ Run button instead of static chips for sessions that
  have audio but no `status.json` yet (e.g. the app quit before the pipeline
  handoff ran), a manual ↺ refresh button next to the "Recent Recordings"
  heading, click-through to the outline HTML, and the Settings… button
- `.onAppear { sessionStore.refresh() }` on the popover content — without
  it, `SessionStore.init()`'s first refresh could race the popover's lazy
  first construction and lose, showing a blank Recent Recordings list until
  the next 3s poll tick. Now it also just re-syncs with disk every time you
  open the menu, which is the more useful behavior anyway.
- Two more real bugs behind "Recent Recordings shows stale/blank data,"
  found via manual testing (the underlying scan/parse logic itself checked
  out fine standalone against real recording folders): `SessionStore`'s
  refresh `Timer` was on the default run-loop mode, which doesn't fire while
  a menu is being tracked (`NSMenu` tracking uses `.eventTracking`, not
  `.default`) — added to `.common` mode instead. And `MenuBarExtra`'s
  `.window` style has been observed to cache its content view rather than
  reliably re-rendering on a plain `@Published` array mutation — added
  `SessionStore.lastRefreshed` and keyed the list's `.id()` to it, forcing a
  real rebuild every refresh.
- **Pause/Resume** — `MicRecorder.pause()`/`resume()` via
  `AVAudioEngine.pause()`/`start()` (same tap, same open file; verified with
  a real engine test that frame count stays flat while paused and resumes
  correctly). `SystemAudioRecorder.pause()`/`resume()` drop sample buffers
  instead of writing them, since `SCStream` has no native pause and
  stopping/restarting it risks a capture gap — the paused flag is behind an
  `NSLock` since the delegate callback runs on a background queue, not the
  main actor. Sleep prevention deliberately stays active while paused.

## Not yet implemented / known gaps

- Not code-signed or notarized; not packaged as a distributable `.app`
- `SystemAudioRecorder` is untested against a real Zoom/Teams call end-to-end
  (compiles and follows the documented ScreenCaptureKit audio-capture
  pattern; the level meter is the fastest way to confirm it's actually
  capturing during a real call — if it stays at zero, check System Settings
  → Privacy & Security → Screen & System Audio Recording)
