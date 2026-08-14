import AppKit

/// Detects which meeting app (if any) is frontmost when recording starts, to
/// seed the session title and label the source in the UI. Purely cosmetic —
/// system audio capture itself is not scoped to one app.
enum DetectedSource: String {
    case zoom = "Zoom"
    case teams = "Microsoft Teams"
    case slack = "Slack"
    case facetime = "FaceTime"
    case none = "recording"

    static let bundleIDs: [String: DetectedSource] = [
        "us.zoom.xos": .zoom,
        "com.microsoft.teams2": .teams,
        "com.microsoft.teams": .teams,
        "com.tinyspeck.slackmacgap": .slack,
        "com.apple.FaceTime": .facetime,
    ]

    static func detectFrontmost() -> DetectedSource {
        for app in NSWorkspace.shared.runningApplications {
            guard let bundleID = app.bundleIdentifier, let source = bundleIDs[bundleID] else { continue }
            if app.isActive || !app.isHidden {
                return source
            }
        }
        return .none
    }

    var slug: String {
        switch self {
        case .none: return "recording"
        default: return rawValue.lowercased().replacingOccurrences(of: " ", with: "-")
        }
    }
}
