import Foundation

/// Per-folder cache of analysed recordings, keyed by filename, invalidated
/// by size/mtime — same scheme as iPhone-Recorder/visualize.py's
/// .waveform-cache.json, so reopening a folder doesn't re-decode every file.
struct WaveformCache {
    private struct Entry: Codable {
        let size: Int64
        let mtime: Double
        let duration: Double
        let sampleRate: Double
        let channels: Int
        let peaks: [Float]
        let peakDB: Double?
        let error: String?
    }

    private let fileURL: URL
    private var entries: [String: Entry] = [:]

    init(folder: URL) {
        fileURL = folder.appendingPathComponent(".waveform-cache.json")
        if let data = try? Data(contentsOf: fileURL),
           let decoded = try? JSONDecoder().decode([String: Entry].self, from: data) {
            entries = decoded
        }
    }

    func lookup(url: URL, size: Int64, mtime: Date) -> Recording? {
        guard let e = entries[url.lastPathComponent],
              e.size == size, abs(e.mtime - mtime.timeIntervalSince1970) < 1 else { return nil }
        var rec = Recording(url: url, size: size, mtime: mtime)
        rec.duration = e.duration
        rec.sampleRate = e.sampleRate
        rec.channels = e.channels
        rec.peaks = e.peaks
        rec.peakDB = e.peakDB
        rec.error = e.error
        return rec
    }

    mutating func store(_ rec: Recording) {
        entries[rec.name] = Entry(
            size: rec.size, mtime: rec.mtime.timeIntervalSince1970,
            duration: rec.duration, sampleRate: rec.sampleRate, channels: rec.channels,
            peaks: rec.peaks, peakDB: rec.peakDB, error: rec.error
        )
    }

    /// Drops entries for files no longer in the folder, keeping the cache
    /// from growing unbounded across renames/deletes.
    mutating func prune(keeping names: Set<String>) {
        entries = entries.filter { names.contains($0.key) }
    }

    func save() {
        guard let data = try? JSONEncoder().encode(entries) else { return }
        try? data.write(to: fileURL)
    }
}
