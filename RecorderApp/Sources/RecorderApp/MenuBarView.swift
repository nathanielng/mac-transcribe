import SwiftUI
import AVKit

struct MenuBarView: View {
    @ObservedObject var controller: RecordingController
    @ObservedObject var sessionStore: SessionStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            recordSection
            if let error = controller.errorMessage {
                Text(error).font(.caption).foregroundColor(.red).lineLimit(3)
            }
            folderRow
            Divider()
            Text("Recent Recordings").font(.headline)
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(sessionStore.sessions) { session in
                        SessionRow(session: session, sessionStore: sessionStore)
                    }
                }
            }
            .frame(maxHeight: 320)
            Divider()
            Button("Quit") { NSApplication.shared.terminate(nil) }
        }
        .padding(12)
        .frame(width: 340)
    }

    private var recordSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Picker("Source", selection: $controller.selectedSource) {
                ForEach(RecordingSource.allCases) { source in
                    Text(source.rawValue).tag(source)
                }
            }
            .pickerStyle(.segmented)
            .disabled(controller.isRecording)

            Button(controller.isRecording ? "Stop Recording" : "Start Recording") {
                controller.isRecording ? controller.stop() : controller.start()
            }
            .buttonStyle(.borderedProminent)
            .tint(controller.isRecording ? .red : .accentColor)

            if controller.isRecording {
                Text("Detected: \(controller.detectedSource.rawValue)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if controller.selectedSource == .mic || controller.selectedSource == .both {
                    LevelMeter(level: controller.micLevel)
                }
            }
        }
    }

    private var folderRow: some View {
        HStack(spacing: 6) {
            Image(systemName: "folder")
                .foregroundColor(.secondary)
            Text(controller.recordingsDir.path)
                .font(.caption)
                .foregroundColor(.secondary)
                .lineLimit(1)
                .truncationMode(.head)
            Spacer()
            Button(action: { controller.openRecordingsFolder() }) {
                Text("📂")
            }
            .buttonStyle(.plain)
            .help("Open recordings folder")
        }
    }
}

/// Simple horizontal input-level bar so the user can confirm the mic is
/// actually picking up sound before trusting a session to a full recording —
/// far faster to eyeball than waiting for a transcript to find out.
private struct LevelMeter: View {
    let level: Float // 0...1

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "mic.fill")
                .font(.caption2)
                .foregroundColor(.secondary)
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color.gray.opacity(0.25))
                    RoundedRectangle(cornerRadius: 3)
                        .fill(level > 0.85 ? Color.red : Color.green)
                        .frame(width: geo.size.width * CGFloat(level))
                        .animation(.linear(duration: 0.08), value: level)
                }
            }
            .frame(height: 6)
        }
    }
}

private struct SessionRow: View {
    let session: Session
    @ObservedObject var sessionStore: SessionStore

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(session.title.replacingOccurrences(of: "-", with: " ").capitalized)
                    .font(.system(size: 13, weight: .medium))
                Spacer()
                Text(session.date).font(.caption2).foregroundColor(.secondary)
            }
            HStack(spacing: 10) {
                if let mic = session.micURL { PlayButton(url: mic, label: "Mic") }
                if let sys = session.systemURL { PlayButton(url: sys, label: "System") }
                Spacer()
                StageChip(label: "Transcript", state: session.transcriptState) {
                    sessionStore.regenerate(session, stage: "transcript")
                }
                StageChip(label: "Outline", state: session.outlineState) {
                    sessionStore.regenerate(session, stage: "outline")
                }
                if let html = session.htmlURL {
                    Button(action: { NSWorkspace.shared.open(html) }) {
                        Image(systemName: "arrow.up.right.square")
                    }
                    .buttonStyle(.plain)
                    .help("Open outline HTML")
                }
            }
            .font(.caption)
        }
        .padding(6)
        .background(Color.gray.opacity(0.08))
        .cornerRadius(6)
    }
}

private struct PlayButton: View {
    let url: URL
    let label: String

    var body: some View {
        Button(action: { NSWorkspace.shared.open(url) }) {
            Label(label, systemImage: "play.circle")
        }
        .buttonStyle(.plain)
    }
}

private struct StageChip: View {
    let label: String
    let state: StageState
    let onRegenerate: () -> Void

    var body: some View {
        HStack(spacing: 3) {
            Text(label)
            Text(symbol).help(helpText)
            if case .failed = state {
                Button(action: onRegenerate) {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Regenerate \(label.lowercased())")
            }
        }
    }

    private var symbol: String {
        switch state {
        case .pending: return "⏳"
        case .running: return "⏳"
        case .ok: return "✅"
        case .failed(let msg): return msg.hasPrefix("auth:") ? "🔑" : "❌"
        }
    }

    private var helpText: String {
        if case .failed(let msg) = state { return msg }
        return label
    }
}
