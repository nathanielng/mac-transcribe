import Foundation
import Combine

enum SortOrder: String, CaseIterable, Identifiable {
    case newest = "Newest first"
    case oldest = "Oldest first"
    case name = "Name"
    case longest = "Longest first"
    case largest = "Largest first"
    var id: String { rawValue }
}

@MainActor
final class LibraryModel: ObservableObject {
    @Published var folder: URL?
    @Published var recordings: [Recording] = []
    @Published var isScanning = false
    @Published var filter: String = ""
    @Published var sortOrder: SortOrder = .newest
    @Published var progress: (done: Int, total: Int)?

    private let defaultsKey = "lastFolder"

    init() {
        // Default to RecorderApp's own recordings folder — the two apps
        // are meant to look at the same recordings by default — unless the
        // user has already explicitly picked a different one here.
        if let path = UserDefaults.standard.string(forKey: defaultsKey) {
            folder = URL(fileURLWithPath: path)
        } else {
            folder = SharedConfig.recordingsDir
        }
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        if panel.runModal() == .OK, let url = panel.url {
            folder = url
            UserDefaults.standard.set(url.path, forKey: defaultsKey)
            Task { await scan() }
        }
    }

    func scan() async {
        guard let folder else { return }
        isScanning = true
        defer { isScanning = false }

        let fm = FileManager.default
        guard let entries = try? fm.contentsOfDirectory(
            at: folder, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            recordings = []
            return
        }
        let files = entries
            .filter { Recording.audioExtensions.contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }

        var cache = WaveformCache(folder: folder)
        var results: [Recording] = []
        var toAnalyse: [URL] = []

        for url in files {
            let attrs = try? fm.attributesOfItem(atPath: url.path)
            let size = (attrs?[.size] as? Int64) ?? 0
            let mtime = (attrs?[.modificationDate] as? Date) ?? Date()
            if let cached = cache.lookup(url: url, size: size, mtime: mtime) {
                results.append(cached)
            } else {
                toAnalyse.append(url)
            }
        }

        progress = toAnalyse.isEmpty ? nil : (0, toAnalyse.count)
        recordings = results.sorted { $0.name < $1.name }

        // Analyse missing/changed files a few at a time. Capped at 4
        // regardless of core count: each analyse() call now only briefly
        // occupies a cooperative-pool thread (the actual decode runs on a
        // GCD queue off that pool — see decodePeaksOffPool), so this limit
        // is just to avoid opening hundreds of file handles / AVAssetReaders
        // at once on a folder with many recordings, not a CPU constraint.
        let maxConcurrent = 4
        var index = 0
        while index < toAnalyse.count {
            let batch = toAnalyse[index..<min(index + maxConcurrent, toAnalyse.count)]
            await withTaskGroup(of: Recording.self) { group in
                for url in batch {
                    group.addTask { await WaveformExtractor.analyse(url: url) }
                }
                for await rec in group {
                    cache.store(rec)
                    results.append(rec)
                    recordings = results.sorted { $0.name < $1.name }
                    if let p = progress { progress = (p.done + 1, p.total) }
                }
            }
            index += batch.count
        }
        progress = nil
        cache.prune(keeping: Set(files.map { $0.lastPathComponent }))
        cache.save()
    }

    enum RenameError: LocalizedError {
        case destinationExists(String)
        var errorDescription: String? {
            switch self {
            case .destinationExists(let name): return "\"\(name)\" already exists"
            }
        }
    }

    /// Applies a user-approved title: renames the audio file on disk
    /// (keeping its yyyymmdd hh-mm-ss prefix — see Recording.renamedURL),
    /// moves its transcript sidecar along with it, and carries the
    /// waveform cache entry over under the new name so the rename alone
    /// doesn't force a re-decode.
    func rename(_ recording: Recording, to newURL: URL) throws {
        let fm = FileManager.default
        guard !fm.fileExists(atPath: newURL.path) else {
            throw RenameError.destinationExists(newURL.lastPathComponent)
        }
        try fm.moveItem(at: recording.url, to: newURL)

        let oldSidecar = recording.transcriptSidecarURL
        if fm.fileExists(atPath: oldSidecar.path) {
            let newSidecar = newURL.deletingLastPathComponent()
                .appendingPathComponent(newURL.lastPathComponent + ".transcript.txt")
            try? fm.moveItem(at: oldSidecar, to: newSidecar)
        }

        if let folder {
            var cache = WaveformCache(folder: folder)
            cache.rename(from: recording.name, to: newURL.lastPathComponent)
            cache.save()
        }

        if let idx = recordings.firstIndex(where: { $0.url == recording.url }) {
            recordings[idx] = Recording(
                url: newURL, size: recording.size, mtime: recording.mtime,
                duration: recording.duration, sampleRate: recording.sampleRate,
                channels: recording.channels, peaks: recording.peaks,
                peakDB: recording.peakDB, error: recording.error
            )
        }
    }

    var filteredSorted: [Recording] {
        let f = filter.lowercased()
        let filtered = f.isEmpty ? recordings : recordings.filter { $0.name.lowercased().contains(f) }
        switch sortOrder {
        case .newest: return filtered.sorted { $0.sortTimestamp > $1.sortTimestamp }
        case .oldest: return filtered.sorted { $0.sortTimestamp < $1.sortTimestamp }
        case .name: return filtered.sorted { $0.name < $1.name }
        case .longest: return filtered.sorted { $0.duration > $1.duration }
        case .largest: return filtered.sorted { $0.size > $1.size }
        }
    }

    var isGroupedByDate: Bool { sortOrder == .newest || sortOrder == .oldest }

    var summary: String {
        guard !recordings.isEmpty else { return "" }
        let total = recordings.reduce(0) { $0 + $1.duration }
        let size = recordings.reduce(Int64(0)) { $0 + $1.size }
        var rec = Recording(url: folder ?? URL(fileURLWithPath: "/"), size: size, mtime: Date())
        rec.duration = total
        return "\(recordings.count) files · \(rec.formattedDuration) total · \(rec.formattedSize)"
    }
}

#if canImport(AppKit)
import AppKit
#endif
