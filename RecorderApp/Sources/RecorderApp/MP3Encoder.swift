import Foundation

/// Shells out to ffmpeg for WAV -> MP3 encoding rather than linking an MP3
/// encoder library — ffmpeg is already a dependency of the pipeline side
/// (mac-transcribe assumes a dev machine with it installed via Homebrew).
enum MP3Encoder {
    static func ffmpegPath() -> String {
        for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"] {
            if FileManager.default.isExecutableFile(atPath: candidate) { return candidate }
        }
        return "ffmpeg" // fall back to PATH lookup
    }

    static func encodeToMP3(wavURL: URL, mp3URL: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ffmpegPath())
        // -nostdin belt-and-suspenders on top of standardInput = nullDevice below:
        // without both, ffmpeg calls tcsetattr() on whatever terminal it inherits
        // to configure interactive keyboard controls. Launched from an app that
        // itself inherited a controlling tty (e.g. started from a terminal), that
        // tcsetattr call happens from a background process group and the kernel
        // sends SIGTTOU, whose default action is to *stop* (not kill) the process
        // — ffmpeg just hangs forever in T state, no error, nothing in the log.
        process.arguments = ["-y", "-nostdin", "-v", "error", "-i", wavURL.path, "-codec:a", "libmp3lame", mp3URL.path]

        process.standardInput = FileHandle.nullDevice
        process.standardOutput = FileHandle.nullDevice
        let stderr = Pipe()
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        if process.terminationStatus != 0 {
            let msg = String(data: stderr.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "unknown ffmpeg error"
            throw NSError(domain: "MP3Encoder", code: Int(process.terminationStatus), userInfo: [NSLocalizedDescriptionKey: msg])
        }

        try? FileManager.default.removeItem(at: wavURL)
    }
}
