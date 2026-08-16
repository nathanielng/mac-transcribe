"""Shared ffmpeg lookup — mirrors RecorderApp/Sources/RecorderApp/MP3Encoder.swift's
ffmpegPath() so both sides find the same binary the same way."""

import os
import shutil


def ffmpeg_path() -> str:
    for candidate in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    found = shutil.which("ffmpeg")
    return found or "ffmpeg"
