// 動作確認用: 描画を PNG に保存して終了する
//   --snapshot <path> [--style gauge,vertical,nofable] [--scale 2]
//                     [--sample <usage.json> | --nodata] [--error <文言>] [--sweep <秒>] [--now <ISO 8601>]
//   --snapshot-settings <path> [--scale 2]
// --sample も --nodata も無ければ実際に取得する。設定ファイルは書き換えない（位置も保存しない）。
import AppKit

enum Snapshot {
    static func meter(_ path: String, args: [String]) {
        var settings = Settings.load()
        if let style = value(args, "--style") {
            let opts = style.split(separator: ",").map(String.init)
            settings.style = opts.contains("gauge") ? "gauge" : "bar"
            settings.gaugeVertical = opts.contains("vertical")
            settings.showFable = !opts.contains("nofable")
        }
        if let now = value(args, "--now") {
            Clock.override = ISO8601DateFormatter().date(from: now)
        }

        var result: UsageResult?
        if let sample = value(args, "--sample") {
            var r = UsageResult()
            do { try UsageClient.parse(Data(contentsOf: URL(fileURLWithPath: sample)), into: &r) }
            catch { r.error = "サンプルを読めません: \(error)" }
            result = r
        } else if !args.contains("--nodata") {
            let sem = DispatchSemaphore(value: 0)
            Task.detached {
                result = await UsageClient.shared.fetch()
                sem.signal()
            }
            sem.wait()
        }
        if let error = value(args, "--error") {
            if result == nil { result = UsageResult() }
            result?.error = error
        }

        let view = MeterView(settings: settings)
        view.result = result
        if let sweep = value(args, "--sweep").flatMap(Double.init) { view.sweepElapsedOverride = sweep }
        write(view, path, scale(args))
        let info = "size=\(view.frame.size) \(result?.error ?? "")\n\(result?.rawBody ?? "")"
        try? info.write(toFile: path + ".txt", atomically: true, encoding: .utf8)
    }

    static func settings(_ path: String, args: [String]) {
        let c = SettingsWindowController(settings: Settings.load(), startupEnabled: false)
        guard let view = c.window?.contentView else { return }
        view.layoutSubtreeIfNeeded()
        write(view, path, scale(args), background: .windowBackgroundColor)
    }

    private static func write(_ view: NSView, _ path: String, _ scale: CGFloat, background: NSColor? = nil) {
        let size = view.bounds.size
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return }
        rep.size = size
        if let background, let ctx = NSGraphicsContext(bitmapImageRep: rep) {
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = ctx
            background.setFill()
            NSRect(origin: .zero, size: size).fill()
            NSGraphicsContext.restoreGraphicsState()
        }
        view.cacheDisplay(in: view.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
    }

    private static func scale(_ args: [String]) -> CGFloat {
        value(args, "--scale").flatMap(Double.init).map { CGFloat($0) } ?? 2
    }

    static func value(_ args: [String], _ name: String) -> String? {
        guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
        return args[i + 1]
    }
}
