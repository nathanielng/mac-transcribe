import SwiftUI
import AVKit

struct MenuBarView: View {
    @ObservedObject var controller: RecordingController
    @ObservedObject var sessionStore: SessionStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            recordSection
            if let error = controller.errorMessage {
                Text(error).font(.caption).foregroundColor(.red).lineLimit(3)
            }
            folderRow
            modelSummaryRow
            Divider()
            HStack {
                Text("Recent Recordings").font(.headline)
                Spacer()
                Button(action: { sessionStore.refresh() }) {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Refresh")
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(sessionStore.sessions) { session in
                        SessionRow(session: session, sessionStore: sessionStore)
                    }
                }
            }
            // Forces a real rebuild on every refresh — MenuBarExtra's
            // .window style has been observed to cache its content and not
            // reliably re-render on a plain @Published array mutation alone.
            .id(sessionStore.lastRefreshed)
            .frame(maxHeight: 560)
            Divider()
            HStack {
                Button("Settings…") {
                    // Accessory apps (LSUIElement, our menu-bar-only policy)
                    // don't get their windows brought to the front by
                    // openWindow alone — the app itself has to be activated
                    // first, or the Settings window opens behind whatever
                    // else has focus (or appears not to open at all).
                    NSApp.activate(ignoringOtherApps: true)
                    openWindow(id: "settings")
                }
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
            }
        }
        .padding(12)
        .frame(width: 340)
        .onAppear {
            // MenuBarExtra's content view is constructed lazily, so
            // SessionStore.init()'s first refresh() can race the popover's
            // first appearance (and lose) — this closes that gap by
            // re-refreshing every time the popover actually opens, which is
            // also just the right time to pick up anything that changed on
            // disk since the last open.
            sessionStore.refresh()
        }
    }

    /// Shows what's actually configured right now for transcription/outline
    /// so the user doesn't have to open Settings just to check — especially
    /// useful for confirming "yes, this is running fully local" or spotting
    /// a stale/misconfigured model after editing config.toml by hand.
    private var modelSummaryRow: some View {
        let cfg = AppConfig.load()
        return VStack(alignment: .leading, spacing: 2) {
            Label(cfg.transcriptionModelSummary, systemImage: "waveform")
            Label(cfg.outlineModelSummary, systemImage: "text.alignleft")
        }
        .font(.caption2)
        .foregroundColor(.secondary)
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

            HStack {
                Button(controller.isRecording ? "Stop Recording" : "Start Recording") {
                    controller.isRecording ? controller.stop() : controller.start()
                }
                .buttonStyle(.borderedProminent)
                .tint(controller.isRecording ? .red : .accentColor)

                if controller.isRecording {
                    Button(controller.isPaused ? "Resume" : "Pause") {
                        controller.isPaused ? controller.resume() : controller.pause()
                    }
                    .buttonStyle(.bordered)
                }
            }

            if controller.isRecording {
                Text("Detected: \(controller.detectedSource.rawValue)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if controller.isPaused {
                    Label("Paused — click Resume to continue", systemImage: "pause.circle")
                        .font(.caption)
                        .foregroundColor(.orange)
                }

                if controller.selectedSource == .mic || controller.selectedSource == .both {
                    LevelMeter(level: controller.micLevel, icon: "mic.fill")
                }

                if controller.selectedSource == .system || controller.selectedSource == .both {
                    LevelMeter(level: controller.systemLevel, icon: "speaker.wave.2.fill")
                }

                if controller.isSleepPrevented {
                    Label("Sleep disabled — recording continues with lid closed", systemImage: "moon.zzz")
                        .font(.caption2)
                        .foregroundColor(.secondary)
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
    var icon: String = "mic.fill"

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: icon)
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
                if session.status == nil && session.hasAudio {
                    // No status.json yet — e.g. the app quit or the pipeline
                    // handoff failed before it ever ran. Three static ⏳
                    // chips with no action here would be misleading (looks
                    // "in progress" when nothing is actually running), so
                    // offer a way to kick it off instead.
                    Button(action: { sessionStore.runPipeline(session) }) {
                        Label("Run", systemImage: "play.fill")
                    }
                    .buttonStyle(.plain)
                    .help("Run the pipeline on this session")
                } else {
                    StageChip(label: "Transcript", state: session.transcriptState) {
                        sessionStore.regenerate(session, stage: "transcript")
                    }
                    StageChip(label: "Outline", state: session.outlineState) {
                        sessionStore.regenerate(session, stage: "outline")
                    }
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
