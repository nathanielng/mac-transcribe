import Foundation

/// One audio file in the browsed folder, plus whatever we've managed to
/// analyse about it. Mirrors the fields iPhone-Recorder/visualize.py's
/// `analyse()` produces, minus the ffprobe tag dump (not worth the extra
/// AVFoundation plumbing for a "nice to have" detail no one asked to keep).
struct Recording: Identifiable, Equatable {
    let url: URL
    let size: Int64
    let mtime: Date

    var duration: TimeInterval = 0
    var sampleRate: Double = 0
    var channels: Int = 0
    /// Normalized 0...1 peak magnitude per bucket, left-to-right.
    var peaks: [Float] = []
    /// Peak level in dBFS, for display only.
    var peakDB: Double?
    var error: String?

    var id: String { url.path }
    var name: String { url.lastPathComponent }

    static let audioExtensions: Set<String> = [
        "aac", "m4a", "mp3", "wav", "aif", "aiff", "flac", "ogg", "opus", "caf",
    ]
}

extension Recording {
    var formattedDuration: String {
        let sec = Int(duration.rounded())
        let h = sec / 3600, m = (sec / 60) % 60, s = sec % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    var formattedSize: String {
        var b = Double(size)
        for unit in ["B", "KB", "MB", "GB"] {
            if b < 1024 || unit == "GB" {
                return unit == "B" ? "\(Int(b)) B" : String(format: "%.1f %@", b, unit)
            }
            b /= 1024
        }
        return "\(size) B"
    }

    /// Groups recordings in the UI the way the original page's "yyyymmdd
    /// hh-mm-ss" filename convention did, falling back to file mtime for
    /// anything that doesn't match (e.g. RecorderApp's own
    /// "yyyy-MM-dd-source" session folder naming).
    var sortTimestamp: String {
        let df = DateFormatter()
        df.dateFormat = "yyyyMMddHHmmss"
        let name = url.deletingPathExtension().lastPathComponent
        if let match = name.range(of: #"\d{8} \d{2}-\d{2}-\d{2}"#, options: .regularExpression) {
            return String(name[match]).replacingOccurrences(of: "[ -]", with: "", options: .regularExpression)
        }
        df.timeZone = .current
        return df.string(from: mtime)
    }

    var year: String { String(sortTimestamp.prefix(4)) }
}
