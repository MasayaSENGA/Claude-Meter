// 設定（~/Library/Application Support/ClaudeMeter/settings.json。キー名は Windows 版と同じ）
import Foundation

struct Settings: Equatable {
    var refreshMinutes = 5
    var peakTimeZone = "America/Los_Angeles"
    var peakStart = "05:00"
    var peakEnd = "11:00"
    var peakWeekdaysOnly = true
    var style = "bar" // "bar" または "gauge"（スピードメーター）
    var gaugeVertical = false // スピードメーターを縦に並べる
    var gaugeSweep = true // スピードメーター表示で起動時に針をスイープさせる
    var showFable = true // Fable を使えないプランでは非表示にできる
    var topMost = true
    var opacity = 0.95
    // ウィンドウ左上の位置（AppKit の画面座標。y は上端）。-1 は未保存
    var x = -1
    var y = -1

    var isGauge: Bool { style == "gauge" }
    var isVertical: Bool { isGauge && gaugeVertical }
    var meterCount: Int { showFable ? 3 : 2 }

    static var dir: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/ClaudeMeter", isDirectory: true)
    }
    static var fileURL: URL { dir.appendingPathComponent("settings.json") }

    static func load() -> Settings {
        var s = Settings()
        if let data = try? Data(contentsOf: fileURL),
           let d = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            func num(_ k: String) -> NSNumber? { d[k] as? NSNumber }
            if let v = num("refreshMinutes") { s.refreshMinutes = min(60, max(1, v.intValue)) }
            if let v = d["peakTimeZone"] as? String { s.peakTimeZone = v }
            if let v = d["peakStart"] as? String { s.peakStart = v }
            if let v = d["peakEnd"] as? String { s.peakEnd = v }
            if let v = num("peakWeekdaysOnly") { s.peakWeekdaysOnly = v.boolValue }
            if let v = d["style"] as? String { s.style = v == "gauge" ? "gauge" : "bar" }
            if let v = num("gaugeVertical") { s.gaugeVertical = v.boolValue }
            if let v = num("gaugeSweep") { s.gaugeSweep = v.boolValue }
            if let v = num("showFable") { s.showFable = v.boolValue }
            if let v = num("topMost") { s.topMost = v.boolValue }
            if let v = num("opacity") { s.opacity = min(1.0, max(0.3, v.doubleValue)) }
            if let v = num("x") { s.x = v.intValue }
            if let v = num("y") { s.y = v.intValue }
        }
        s.save()
        return s
    }

    func save() {
        let d: [String: Any] = [
            "refreshMinutes": refreshMinutes,
            "peakTimeZone": peakTimeZone,
            "peakStart": peakStart,
            "peakEnd": peakEnd,
            "peakWeekdaysOnly": peakWeekdaysOnly,
            "style": style,
            "gaugeVertical": gaugeVertical,
            "gaugeSweep": gaugeSweep,
            "showFable": showFable,
            "topMost": topMost,
            "opacity": NSDecimalNumber(string: String(format: "%.2f", opacity)), // 0.95 が 0.9499… と書かれないように
            "x": x,
            "y": y,
        ]
        do {
            try FileManager.default.createDirectory(at: Settings.dir, withIntermediateDirectories: true)
            let data = try JSONSerialization.data(withJSONObject: d, options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes])
            try data.write(to: Settings.fileURL, options: .atomic)
        } catch {}
    }
}
