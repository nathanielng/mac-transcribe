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

Supported extensions: `.aac .m4a .mp3 .wav .aif .aiff .flac .ogg .opus .caf`.

## Not yet verified

Builds and launches cleanly, but hasn't been run against a real recordings
folder yet:

- Decode time on very long (multi-hour) files is unverified — `AVAssetReader`
  reads the whole track into memory as `Int16` samples before bucketing,
  which could be slow or memory-heavy for long recordings.
- Large libraries (hundreds of files) — scan/cache behavior at that scale is
  untested.
- Filenames that don't match the `yyyymmdd hh-mm-ss` convention (e.g.
  RecorderApp's own `yyyy-MM-dd-source` session folders) fall back to file
  mtime for date grouping/sorting — logic is in place but not exercised on
  real RecorderApp output yet.
