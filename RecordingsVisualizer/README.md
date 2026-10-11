# RecordingsVisualizer

A standalone Swift/SwiftUI app for browsing a folder of audio recordings as
a waveform grid — filter, sort, click-to-seek playback. A native port of
`iPhone-Recorder`'s `visualize.py` + generated `index.html` (ffmpeg/numpy →
static page), rebuilt to run live and on-device instead of generating a
static file.

Deliberately a separate app and process from `../RecorderApp` (its own
`Package.swift`, no shared code or target): a bug here — a bad waveform
decode, a UI crash — can't affect recording or the transcription pipeline.
It reads recordings read-only; it has no part in capturing or processing
them.

## Build & run

```bash
cd RecordingsVisualizer
swift build
.build/debug/RecordingsVisualizer
```

No Xcode required — builds with the Command Line Tools.

## What's implemented

- `WaveformExtractor` — decodes peaks via `AVAssetReader` (mono 16-bit PCM),
  bucketed into 240 bars with per-bucket max-abs amplitude and overall peak
  dBFS, same approach as the original script's ffmpeg pipe + numpy
  `array_split`, without the ffmpeg/ffprobe subprocess dependency.
- `WaveformCache` — per-folder `.waveform-cache.json`, keyed by filename and
  invalidated by size/mtime, so reopening a folder only re-decodes new or
  changed files — mirrors the original script's cache file.
- `LibraryModel` — folder picker (remembers the last folder via
  `UserDefaults`), concurrent batch analysis, filter-by-name, sort (newest/
  oldest/name/longest/largest), grouped by year when sorted by date.
- `WaveformView` / `RecordingCard` — bars drawn with `Canvas`, click-to-seek,
  live playback-progress overlay, double-click to toggle play.
- `PlayerController` — single shared `AVAudioPlayer` so starting a new
  waveform stops whatever was already playing (same one-at-a-time behavior
  as the original page's single `<audio>` element).
- `SharedConfig` — reads `recordings_dir` from the same
  `~/.config/mac-transcribe/config.toml` RecorderApp writes, so this app
  defaults to the same folder RecorderApp uses (unless you've explicitly
  picked a different one here, which is then remembered instead).
- Transcribe → propose title → approve/edit → rename, for recordings that
  aren't RecorderApp session folders (e.g. an old personal archive moved in
  here): a "Transcribe" button on each card shells out to the Python
  pipeline's `describe_recording` module, which transcribes locally via
  mlx-whisper (writing/reusing a `<name>.transcript.txt` sidecar) and then
  proposes a title with whatever `outline_backend`/model is already
  configured (local `mlx_lm` by default — Amazon Transcribe is
  deliberately not wired in here, per "local inference first"). The
  proposed title is shown in an editable field; nothing is renamed until
  you click "Approve & Rename". Renaming keeps the filename's existing
  `yyyymmdd hh-mm-ss` prefix (`Recording.renamedURL`) and moves the
  transcript sidecar + waveform-cache entry along with it, so approving
  doesn't force a re-decode of the waveform.

Supported extensions: `.aac .m4a .mp3 .wav .aif .aiff .flac .ogg .opus .caf`.

## Verified against real recordings

Run against ~90 real legacy recordings (various `.aac`/`.mp3`, including a
5.7-hour/494MB file) and RecorderApp's own `recordings_dir`:

- Full scan completes and all 91 files produce a waveform with zero
  decode errors — fixed two real bugs found doing this (see commit
  history): a thread-pool deadlock from running the blocking
  `AVAssetReader` loop inside a Swift Task, and a multi-GB in-memory
  buffer building up before bucketing on the long file.
- `describe_recording.py` run end-to-end on a real file: transcribes via
  mlx-whisper, writes the sidecar, and proposes a title via local
  `mlx_lm`.

## Known limitation

Local title generation can produce a nonsense title on a very short or
garbled transcript (e.g. a near-silent 1-second clip) — seen in testing,
where the model echoed fragments of its own prompt instead of a title.
This is exactly what the approve/edit step exists to catch: review before
approving, especially for short or quiet recordings.

## Not yet verified

- Large libraries (many hundreds of files) beyond the ~90 tested — scan/
  cache behavior at that scale is untested.
- Filenames that don't match the `yyyymmdd hh-mm-ss` convention fall back
  to file mtime for date grouping/sorting, and to a no-date-prefix rename
  for the transcribe/title flow — logic is in place but not exercised on
  real RecorderApp session-folder names (those aren't flat files in the
  same folder, so don't show up here as individual recordings anyway).
