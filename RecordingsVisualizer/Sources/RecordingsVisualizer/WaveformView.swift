import SwiftUI

/// Native stand-in for the original page's inline SVG bars — a Canvas
/// drawing `peaks` as vertical bars, with a playback-progress overlay and
/// click/drag-to-seek.
struct WaveformView: View {
    let recording: Recording
    @ObservedObject var player: PlayerController

    var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                if recording.peaks.isEmpty {
                    RoundedRectangle(cornerRadius: 4)
                        .strokeBorder(Color.secondary.opacity(0.3), style: StrokeStyle(lineWidth: 1, dash: [3]))
                    Text(recording.error ?? "no waveform")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity)
                } else {
                    Canvas { context, size in
                        let n = recording.peaks.count
                        let pitch = size.width / CGFloat(n)
                        let barWidth = max(1, pitch * 0.7)
                        for (i, v) in recording.peaks.enumerated() {
                            let h = max(CGFloat(v), 0.02) * size.height
                            let rect = CGRect(
                                x: CGFloat(i) * pitch, y: (size.height - h) / 2,
                                width: barWidth, height: h
                            )
                            context.fill(Path(roundedRect: rect, cornerRadius: 1), with: .color(isHovering ? .primary : .secondary))
                        }
                    }
                    if isCurrent, geo.size.width > 0 {
                        Rectangle()
                            .fill(Color.accentColor.opacity(0.25))
                            .frame(width: progressFraction * geo.size.width)
                        Rectangle()
                            .fill(Color.accentColor)
                            .frame(width: 2)
                            .offset(x: progressFraction * geo.size.width)
                    }
                }
            }
            .contentShape(Rectangle())
            .onTapGesture { location in seek(at: location.x, width: geo.size.width) }
            .onHover { isHovering = $0 }
        }
        .frame(height: 44)
        .background(Color(nsColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    @State private var isHovering = false

    private var isCurrent: Bool { player.currentURL == recording.url }

    private var progressFraction: Double {
        guard isCurrent, player.duration > 0 else { return 0 }
        return min(1, player.currentTime / player.duration)
    }

    private func seek(at x: CGFloat, width: CGFloat) {
        guard width > 0 else { return }
        let fraction = max(0, min(1, x / width))
        player.play(url: recording.url, atFraction: fraction)
    }
}
