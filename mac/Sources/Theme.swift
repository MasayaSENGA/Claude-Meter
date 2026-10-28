// 配色・文言の書式・現在時刻（動作確認用に差し替えられる）
import AppKit

enum Theme {
    static let back = rgb(30, 30, 32)
    static let border = rgb(70, 70, 75)
    static let track = rgb(58, 58, 62)
    static let text = rgb(235, 235, 235)
    static let sub = rgb(150, 150, 155)
    static let brand = rgb(217, 119, 87) // アイコン用の Claude 系オレンジ
    static let ok = rgb(70, 150, 230)    // 70% 未満は青
    static let warn = rgb(230, 180, 60)
    static let danger = rgb(225, 80, 80)
    static let peak = rgb(225, 95, 80)
    static let offPeak = rgb(90, 190, 120)

    static func forPercent(_ p: Double) -> NSColor {
        if p >= 90 { return danger }
        if p >= 70 { return warn }
        return ok
    }

    static func rgb(_ r: Int, _ g: Int, _ b: Int) -> NSColor {
        NSColor(srgbRed: CGFloat(r) / 255, green: CGFloat(g) / 255, blue: CGFloat(b) / 255, alpha: 1)
    }
}

enum Clock {
    static var override: Date? // --now で指定したときだけ使う
    static var now: Date { override ?? Date() }
}

enum Format {
    private static let posix = Locale(identifier: "en_US_POSIX")

    static func time(_ t: Date) -> String {
        let f = DateFormatter()
        f.locale = posix
        f.dateFormat = "HH:mm"
        return f.string(from: t)
    }

    // 今日なら HH:mm、それ以外は M/d(曜) HH:mm
    static func when(_ t: Date) -> String {
        let cal = Calendar.current
        if cal.isDate(t, inSameDayAs: Clock.now) { return time(t) }
        let dow = ["日", "月", "火", "水", "木", "金", "土"][cal.component(.weekday, from: t) - 1]
        let f = DateFormatter()
        f.locale = posix
        f.dateFormat = "M/d"
        return "\(f.string(from: t))(\(dow)) \(time(t))"
    }

    static func span(_ s: TimeInterval) -> String {
        if s < 60 { return "まもなく" }
        let minutes = Int(s / 60)
        if s < 3600 { return "あと\(minutes)分" }
        if s < 86400 { return "あと\(minutes / 60)時間\(minutes % 60)分" }
        return "あと\(minutes / 1440)日\(minutes / 60 % 24)時間"
    }

    static func percent(_ p: Double) -> String { "\(Int(p.rounded()))%" }
}
