import SwiftUI

struct ContentView: View {
    @ObservedObject var library: LibraryModel
    @StateObject private var player = PlayerController()

    private let columns = [GridItem(.adaptive(minimum: 340), spacing: 12)]

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if library.folder == nil {
                emptyState
            } else if library.recordings.isEmpty && !library.isScanning {
                Text("No audio files in this folder")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(groupedSections, id: \.year) { section in
                            if library.isGroupedByDate {
                                yearHeader(section)
                            }
                            LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                                ForEach(section.recordings) { rec in
                                    RecordingCard(recording: rec, player: player)
                                }
                            }
                        }
                    }
                    .padding(16)
                }
            }
        }
        .frame(minWidth: 640, minHeight: 480)
        .task(id: library.folder) {
            if library.folder != nil, library.recordings.isEmpty {
                await library.scan()
            }
        }
    }

    private var header: some View {
        HStack(spacing: 12) {
            Text("Recordings").font(.title3).fontWeight(.semibold)
            if !library.summary.isEmpty {
                Text(library.summary).font(.caption).foregroundColor(.secondary)
            }
            if let p = library.progress {
                ProgressView(value: Double(p.done), total: Double(p.total))
                    .frame(width: 100)
                Text("\(p.done)/\(p.total)").font(.caption2).foregroundColor(.secondary)
            }
            Spacer()
            TextField("Filter by name…", text: $library.filter)
                .textFieldStyle(.roundedBorder)
                .frame(width: 180)
            Picker("", selection: $library.sortOrder) {
                ForEach(SortOrder.allCases) { Text($0.rawValue).tag($0) }
            }
            .frame(width: 140)
            Button(action: { Task { await library.scan() } }) {
                Image(systemName: "arrow.clockwise")
            }
            .help("Rescan folder")
            Button("Choose Folder…") { library.chooseFolder() }
        }
        .padding(12)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "waveform")
                .font(.system(size: 40))
                .foregroundColor(.secondary)
            Text("Choose a folder of recordings to visualize")
                .foregroundColor(.secondary)
            Button("Choose Folder…") { library.chooseFolder() }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private struct Section { let year: String; let recordings: [Recording] }

    private var groupedSections: [Section] {
        let items = library.filteredSorted
        guard library.isGroupedByDate else { return [Section(year: "", recordings: items)] }
        var order: [String] = []
        var byYear: [String: [Recording]] = [:]
        for r in items {
            if byYear[r.year] == nil { order.append(r.year) }
            byYear[r.year, default: []].append(r)
        }
        return order.map { Section(year: $0, recordings: byYear[$0] ?? []) }
    }

    private func yearHeader(_ section: Section) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(section.year).font(.title2).fontWeight(.semibold)
            Text("\(section.recordings.count) recording\(section.recordings.count == 1 ? "" : "s")")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.top, section.year == groupedSections.first?.year ? 0 : 12)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
