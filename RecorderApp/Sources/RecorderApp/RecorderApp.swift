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
    }
}
