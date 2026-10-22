// Claude Meter (macOS) - Claude の利用制限の使用状況を常時表示する小さなウィンドウ
import AppKit

let args = CommandLine.arguments

if let dir = Snapshot.value(args, "--make-iconset") {
    do { try AppIcon.writeIconset(to: URL(fileURLWithPath: dir)) } catch { print(error); exit(1) }
    exit(0)
}
if let path = Snapshot.value(args, "--snapshot-settings") {
    _ = NSApplication.shared
    Snapshot.settings(path, args: args)
    exit(0)
}
if let path = Snapshot.value(args, "--snapshot") {
    _ = NSApplication.shared
    Snapshot.meter(path, args: args)
    exit(0)
}

// 二重起動しない
if let id = Bundle.main.bundleIdentifier,
   NSRunningApplication.runningApplications(withBundleIdentifier: id).contains(where: { $0 != .current }) {
    exit(0)
}

MainActor.assumeIsolated {
    let app = NSApplication.shared
    let delegate = AppDelegate()
    app.delegate = delegate
    app.setActivationPolicy(.accessory) // Dock に出さない（Info.plist の LSUIElement と同じ）
    app.run()
}
