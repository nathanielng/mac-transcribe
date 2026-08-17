import IOKit.pwr_mgt

/// Prevents the Mac from sleeping (including with the lid closed, no
/// external display required) while a recording is in progress — the same
/// IOKit mechanism `caffeinate -s` uses under the hood. Recording audio
/// requires the process to keep running, which system sleep would pause.
///
/// Not a standalone toggle: enabled automatically on Start Recording,
/// released automatically on Stop Recording or app quit, so there's no
/// separate "did I remember to turn this back off" state to manage —
/// standby behavior is only ever different from normal while actively
/// recording.
final class SleepAssertion {
    private var assertionID: IOPMAssertionID = 0
    private(set) var isActive = false

    func enable() {
        guard !isActive else { return }
        var id: IOPMAssertionID = 0
        let result = IOPMAssertionCreateWithName(
            kIOPMAssertionTypePreventSystemSleep as CFString,
            IOPMAssertionLevel(kIOPMAssertionLevelOn),
            "mac-transcribe is recording" as CFString,
            &id
        )
        if result == kIOReturnSuccess {
            assertionID = id
            isActive = true
        }
    }

    func disable() {
        guard isActive else { return }
        IOPMAssertionRelease(assertionID)
        isActive = false
    }

    deinit {
        disable()
    }
}
