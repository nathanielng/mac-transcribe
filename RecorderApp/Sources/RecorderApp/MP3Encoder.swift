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
        process.arguments = ["-y", "-v", "error", "-i", wavURL.path, "-codec:a", "libmp3lame", mp3URL.path]

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
