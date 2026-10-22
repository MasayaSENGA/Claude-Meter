// ピーク／オフピーク判定
import Foundation

enum PeakClock {
    struct State {
        let peak: Bool
        let change: Date? // 次に状態が切り替わる時刻（8日以内に無ければ nil）
    }

    // スイープ中は毎フレーム呼ばれるので、同じ分・同じ設定なら前回の結果を使う
    private static var cache: (key: String, state: State)?

    static func state(_ s: Settings, now: Date) -> State {
        let minute = Int(floor(now.timeIntervalSince1970 / 60))
        let key = "\(minute)|\(s.peakTimeZone)|\(s.peakStart)|\(s.peakEnd)|\(s.peakWeekdaysOnly)"
        if let c = cache, c.key == key { return c.state }

        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: s.peakTimeZone) ?? .current
        let start = parseTime(s.peakStart) ?? 5 * 60
        let end = parseTime(s.peakEnd) ?? 11 * 60
        let current = inPeak(cal, now, start, end, s.peakWeekdaysOnly)

        // 状態が変わる時刻を1分刻みで探す（最大8日先）
        var t = Date(timeIntervalSince1970: Double(minute + 1) * 60)
        let limit = now.addingTimeInterval(8 * 86400)
        var change: Date?
        while t < limit {
            if inPeak(cal, t, start, end, s.peakWeekdaysOnly) != current { change = t; break }
            t.addTimeInterval(60)
        }
        let state = State(peak: current, change: change)
        cache = (key, state)
        return state
    }

    private static func inPeak(_ cal: Calendar, _ t: Date, _ start: Int, _ end: Int, _ weekdaysOnly: Bool) -> Bool {
        let c = cal.dateComponents([.weekday, .hour, .minute], from: t)
        if weekdaysOnly && (c.weekday == 1 || c.weekday == 7) { return false }
        let tod = (c.hour ?? 0) * 60 + (c.minute ?? 0)
        if start <= end { return tod >= start && tod < end }
        return tod >= start || tod < end // 日付をまたぐ設定
    }

    // "H:mm" / "HH:mm" を 0 時からの分に
    static func parseTime(_ s: String) -> Int? {
        let parts = s.split(separator: ":")
        guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]),
              (0..<24).contains(h), (0..<60).contains(m), parts[1].count == 2 else { return nil }
        return h * 60 + m
    }
}
