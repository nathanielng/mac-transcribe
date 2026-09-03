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
- Fixed the actual "Recent Recordings is empty" bug: `SessionStore`'s
  refresh `Timer` was on the default run-loop mode, which doesn't fire while
  a menu is being tracked (`NSMenu` tracking uses `.eventTracking`, not
  `.default`) — added to `.common` mode instead. Separately, and this was
  the actual cause of the reported empty list: the recordings `ScrollView`
  had no `minHeight`, so it collapsed to zero height inside `MenuBarExtra`'s
  auto-sizing content window even when `sessionStore.sessions` genuinely had
  entries — added `.frame(minHeight: 80, maxHeight: 560)` and a proper empty
  state. (An earlier attempted fix here — forcing the list's `.id()` to
  change on every refresh, guessing at a `MenuBarExtra` content-caching
  issue — was not actually verified against the real UI and likely made the
  zero-height collapse worse; removed. Diagnosed properly this time by
  driving the live app with `osascript`/System Events and screenshotting the
  real dropdown rather than reasoning about SwiftUI internals in the
  abstract — see `LEARNINGS.md` for the full writeup and the corrected
  lesson about verifying GUI fixes against the actual screen, not just a
  successful build.)
- **Pause/Resume** — `MicRecorder.pause()`/`resume()` via
  `AVAudioEngine.pause()`/`start()` (same tap, same open file; verified with
  a real engine test that frame count stays flat while paused and resumes
  correctly). `SystemAudioRecorder.pause()`/`resume()` drop sample buffers
  instead of writing them, since `SCStream` has no native pause and
  stopping/restarting it risks a capture gap — the paused flag is behind an
  `NSLock` since the delegate callback runs on a background queue, not the
  main actor. Sleep prevention deliberately stays active while paused.
- `AudioPlayerController` — in-app Play/Stop for mic/system playback via
  `AVAudioPlayer`, replacing `NSWorkspace.shared.open()`, which handed the
  file off to an external player with no way to stop it from RecorderApp
  itself. One shared player: starting a second clip stops the first.
- A 🔄 **Reprocess** button per completed session (`SessionStore.reprocess`),
  distinct from the per-stage regenerate buttons on `StageChip` (which only
  appear on a *failed* stage) — forces transcript+outline+title to re-run
  from scratch even on a fully successful session, e.g. after switching
  outline backend/model in Settings.
- **Robust to deleted mp3s/transcript.md** — a normal cleanup workflow is
  keeping only the final HTML and deleting the raw audio/transcript.
  `Session.hasAudio`/`hasTranscript` gate the Transcript-regenerate,
  Outline-regenerate, and Reprocess buttons (greyed out + a tooltip
  explaining what's missing, rather than failing when clicked); the Play
  buttons already only render when the corresponding mp3 file actually
  exists. Verified by deleting a real session's `mic.mp3`/`transcript.md`
  and screenshotting the real dropdown — the row still renders, with the
  right controls visibly disabled compared side-by-side against an
  untouched session's row.

## Not yet implemented / known gaps

- Not code-signed or notarized; not packaged as a distributable `.app`
- `SystemAudioRecorder` is untested against a real Zoom/Teams call end-to-end
  (compiles and follows the documented ScreenCaptureKit audio-capture
  pattern; the level meter is the fastest way to confirm it's actually
  capturing during a real call — if it stays at zero, check System Settings
  → Privacy & Security → Screen & System Audio Recording)
