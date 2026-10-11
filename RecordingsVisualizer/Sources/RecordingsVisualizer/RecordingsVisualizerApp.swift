import SwiftUI

@main
struct RecordingsVisualizerApp: App {
    @StateObject private var library = LibraryModel()

    var body: some Scene {
        WindowGroup {
            ContentView(library: library)
        }
    }
}
