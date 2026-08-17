import SwiftUI

@main
struct RecorderApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var sessionStore: SessionStore
    @StateObject private var controller: RecordingController

    init() {
        let store = SessionStore()
        _sessionStore = StateObject(wrappedValue: store)
        _controller = StateObject(wrappedValue: RecordingController(sessionStore: store))
    }

    var body: some Scene {
        MenuBarExtra {
            MenuBarView(controller: controller, sessionStore: sessionStore)
        } label: {
            Image(systemName: controller.isRecording ? "record.circle.fill" : "mic.circle")
        }
        .menuBarExtraStyle(.window)

        Window("Settings", id: "settings") {
            SettingsView()
        }
        .windowResizability(.contentSize)
    }
}

/// Runs as an accessory app (no Dock icon, no menu bar app menu) — this is a
/// menu-bar-only utility, not a regular windowed app.
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        // As an accessory app there's no Dock icon and no window on launch —
        // without this, running the binary from a terminal gives no sign of
        // life at all, which reads as "did it even start?" rather than "it's
        // running, look at the menu bar."
        print("""
        mac-transcribe RecorderApp is running.
        Look for the mic icon (🎙️) in the menu bar — click it to record.
        Press Ctrl+C here, or use its Quit button, to stop.
        """)
        // stdout is fully buffered (not line-buffered) when it's not a tty —
        // e.g. redirected to a file or piped — so without this the message
        // above can sit in the buffer indefinitely instead of showing up.
        fflush(stdout)
    }
}
