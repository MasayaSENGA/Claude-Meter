// メーターの描画（座標は左上原点・下向き、単位はポイント）
import AppKit

final class MeterView: NSView {
    var settings: Settings
    var result: UsageResult?
    var fetching = false
    var onDoubleClick: (() -> Void)?

    // 起動時のスイープ（針が一度最大まで振り切ってから実際の値に戻る）
    static let sweepUp = 0.7, sweepHold = 0.2, sweepDown = 0.8 // 秒
    static let sweepTotal = sweepUp + sweepHold + sweepDown
    var sweepStart: CFTimeInterval?
    var sweepElapsedOverride: Double? // 動作確認用に特定のコマを描く
    var sweeping: Bool { sweepStart != nil || sweepElapsedOverride != nil }

    static let gaugeCell: CGFloat = 130, gaugeRow: CGFloat = 134

    private let titleFont = NSFont.systemFont(ofSize: 12, weight: .bold)
    private let labelFont = NSFont.systemFont(ofSize: 12)
    private let pctFont = NSFont.monospacedDigitSystemFont(ofSize: 13.33, weight: .bold)
    private let smallFont = NSFont.systemFont(ofSize: 10.67)

    init(settings: Settings) {
        self.settings = settings
        super.init(frame: NSRect(origin: .zero, size: MeterView.size(for: settings)))
    }

    required init?(coder: NSCoder) { fatalError() }

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    // メーター部の下にピーク表示（縦並びは2行）とエラー行が入る
    static func size(for s: Settings) -> NSSize {
        let n = CGFloat(s.meterCount)
        if !s.isGauge { return NSSize(width: 260, height: 34 + 46 * n + 50) }
        if s.isVertical { return NSSize(width: 170, height: 34 + gaugeRow * n + 56) }
        return NSSize(width: 24 + gaugeCell * n, height: 214)
    }

    override func mouseDown(with event: NSEvent) {
        if event.clickCount == 2 { onDoubleClick?() } else { window?.performDrag(with: event) }
    }

    override func draw(_ dirtyRect: NSRect) {
        let size = bounds.size
        let pad: CGFloat = 12
        let w = size.width - pad * 2

        Theme.back.setFill()
        bounds.fill()
        Theme.border.setStroke()
        let frame = NSBezierPath(rect: bounds.insetBy(dx: 0.5, dy: 0.5))
        frame.lineWidth = 1
        frame.stroke()

        // ヘッダー
        draw("Claude Meter", titleFont, Theme.text, pad, 8)
        let status = fetching ? "更新中…" : result.map { Format.time($0.fetchedAt) + " 更新" } ?? ""
        drawRight(status, smallFont, Theme.sub, pad + w, 10)

        var labels = ["5時間制限", "週間制限"]
        var wins: [UsageWindow?] = [result?.fiveHour, result?.weekly]
        if settings.showFable {
            labels.append("週間制限（Fable）")
            wins.append(result?.weeklyFable)
        }

        var y: CGFloat = 34
        if settings.isGauge {
            let cw = settings.isVertical ? w : w / CGFloat(labels.count)
            for i in labels.indices {
                if settings.isVertical {
                    drawGauge(labels[i], wins[i], pad, y, cw)
                    y += MeterView.gaugeRow
                } else {
                    drawGauge(labels[i], wins[i], pad + cw * CGFloat(i), y, cw)
                }
            }
            if !settings.isVertical { y += MeterView.gaugeRow }
        } else {
            for i in labels.indices {
                drawBar(labels[i], wins[i], pad, y, w)
                y += 46
            }
        }

        // ピーク／オフピーク
        let now = Clock.now
        let peak = PeakClock.state(settings, now: now)
        let c = peak.peak ? Theme.peak : Theme.offPeak
        c.setFill()
        NSBezierPath(ovalIn: NSRect(x: pad, y: y + 4, width: 10, height: 10)).fill()
        draw(peak.peak ? "ピークタイム" : "オフピーク", titleFont, c, pad + 15, y)
        if let change = peak.change {
            let when = (peak.peak ? "終了 " : "開始 ") + Format.when(change) + "（" + Format.span(change.timeIntervalSince(now)) + "）"
            // 縦並びは幅が狭いので2行目に出す
            if settings.isVertical { draw(when, smallFont, Theme.sub, pad + 15, y + 19) }
            else { drawRight(when, smallFont, Theme.sub, pad + w, y + 2) }
        }

        if let error = result?.error {
            let ps = NSMutableParagraphStyle()
            ps.lineBreakMode = .byTruncatingTail
            (error as NSString).draw(
                with: NSRect(x: pad, y: size.height - 20, width: w, height: 16),
                options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine],
                attributes: [.font: smallFont, .foregroundColor: Theme.warn, .paragraphStyle: ps])
        }
    }

    private func drawBar(_ label: String, _ win: UsageWindow?, _ x: CGFloat, _ y: CGFloat, _ w: CGFloat) {
        draw(label, labelFont, Theme.text, x, y)
        let has = win?.present ?? false
        let pct = has ? win!.utilization : 0
        drawRight(has ? Format.percent(pct) : "—", pctFont, has ? Theme.forPercent(pct) : Theme.sub, x + w, y - 2)

        let barH: CGFloat = 7
        Theme.track.setFill()
        roundBar(NSRect(x: x, y: y + 20, width: w, height: barH)).fill()
        if has && pct > 0 {
            let fw = max(barH, min(w, w * pct / 100))
            Theme.forPercent(pct).setFill()
            roundBar(NSRect(x: x, y: y + 20, width: fw, height: barH)).fill()
        }

        draw(subText(win, withSpan: true), smallFont, Theme.sub, x, y + 29)
    }

    private func subText(_ win: UsageWindow?, withSpan: Bool) -> String {
        guard let win else { return "" }
        if !win.present { return "データなし" }
        guard let reset = win.resetsAt else { return "未使用" }
        let s = "リセット " + Format.when(reset)
        return withSpan ? s + "（" + Format.span(reset.timeIntervalSince(Clock.now)) + "）" : s
    }

    private func roundBar(_ r: NSRect) -> NSBezierPath {
        NSBezierPath(roundedRect: r, xRadius: r.height / 2, yRadius: r.height / 2)
    }

    // スピードメーター: 左下(0%)から右下(100%)まで 240° の文字盤と針
    private static let gaugeStart: CGFloat = 150, gaugeSweep: CGFloat = 240

    private static func angle(_ pct: Double) -> CGFloat { gaugeStart + gaugeSweep * CGFloat(pct) / 100 }

    private func drawGauge(_ label: String, _ win: UsageWindow?, _ x: CGFloat, _ y: CGFloat, _ cw: CGFloat) {
        let has = win?.present ?? false
        var pct = has ? max(0, min(100, win!.utilization)) : 0
        let lit = has || sweeping // スイープ中はデータ未取得でも文字盤を点灯させる
        if sweeping { pct = sweepValue(pct) }
        let r: CGFloat = 44
        let center = NSPoint(x: x + cw / 2, y: y + r + 4)

        // 目盛りの外側に 70〜90% を黄、90〜100% を赤の帯で示す
        arc(center, r + 4, from: 70, to: 90, width: 2, color: Theme.warn.withAlphaComponent(150 / 255))
        arc(center, r + 4, from: 90, to: 100, width: 2, color: Theme.danger.withAlphaComponent(170 / 255))

        arc(center, r, from: 0, to: 100, width: 7, color: Theme.track)
        if lit && pct > 0 { arc(center, r, from: 0, to: pct, width: 7, color: Theme.forPercent(pct)) }

        // 10% ごとの目盛り（0・50・100% は長く）
        for i in 0...10 {
            let major = i % 5 == 0
            let a = MeterView.angle(Double(i * 10)) * .pi / 180
            line(center, a, from: r - (major ? 15 : 11), to: r - 6,
                 width: major ? 2 : 1, color: major ? Theme.text : Theme.sub, round: false)
        }

        // 針
        line(center, MeterView.angle(pct) * .pi / 180, from: 0, to: r - 13,
             width: 2.5, color: lit ? Theme.text : Theme.sub, round: true)
        let hub: CGFloat = 5
        (lit ? Theme.forPercent(pct) : Theme.sub).setFill()
        NSBezierPath(ovalIn: NSRect(x: center.x - hub, y: center.y - hub, width: hub * 2, height: hub * 2)).fill()

        drawCenter(lit ? Format.percent(pct) : "—", pctFont, lit ? Theme.forPercent(pct) : Theme.sub, center.x, center.y + 12)
        drawCenter(label, labelFont, Theme.text, center.x, center.y + 32)
        if let win {
            drawCenter(subText(win, withSpan: false), smallFont, Theme.sub, center.x, center.y + 50)
            if win.present, let reset = win.resetsAt {
                drawCenter(Format.span(reset.timeIntervalSince(Clock.now)), smallFont, Theme.sub, center.x, center.y + 64)
            }
        }
    }

    // 経過時間に応じた針の位置。上りは 0→100%、下りは 100%→target
    private func sweepValue(_ target: Double) -> Double {
        let t = sweepElapsedOverride ?? (CACurrentMediaTime() - (sweepStart ?? 0))
        if t < MeterView.sweepUp { return 100 * ease(t / MeterView.sweepUp) }
        if t < MeterView.sweepUp + MeterView.sweepHold { return 100 }
        let k = min(1, (t - MeterView.sweepUp - MeterView.sweepHold) / MeterView.sweepDown)
        return 100 + (target - 100) * ease(k)
    }

    private func ease(_ x: Double) -> Double {
        x < 0.5 ? 4 * x * x * x : 1 - pow(-2 * x + 2, 3) / 2 // easeInOutCubic
    }

    // 下向き座標なので角度が増える向き（clockwise: false）が画面上の時計回りになる
    private func arc(_ c: NSPoint, _ radius: CGFloat, from p0: Double, to p1: Double, width: CGFloat, color: NSColor) {
        let path = NSBezierPath()
        path.appendArc(withCenter: c, radius: radius, startAngle: MeterView.angle(p0), endAngle: MeterView.angle(p1), clockwise: false)
        path.lineWidth = width
        path.lineCapStyle = .butt
        color.setStroke()
        path.stroke()
    }

    private func line(_ c: NSPoint, _ a: CGFloat, from r1: CGFloat, to r2: CGFloat, width: CGFloat, color: NSColor, round: Bool) {
        let path = NSBezierPath()
        path.move(to: NSPoint(x: c.x + cos(a) * r1, y: c.y + sin(a) * r1))
        path.line(to: NSPoint(x: c.x + cos(a) * r2, y: c.y + sin(a) * r2))
        path.lineWidth = width
        path.lineCapStyle = round ? .round : .butt
        color.setStroke()
        path.stroke()
    }

    private func attrs(_ f: NSFont, _ c: NSColor) -> [NSAttributedString.Key: Any] {
        [.font: f, .foregroundColor: c]
    }

    private func draw(_ s: String, _ f: NSFont, _ c: NSColor, _ x: CGFloat, _ y: CGFloat) {
        (s as NSString).draw(at: NSPoint(x: x, y: y), withAttributes: attrs(f, c))
    }

    private func drawRight(_ s: String, _ f: NSFont, _ c: NSColor, _ right: CGFloat, _ y: CGFloat) {
        let width = (s as NSString).size(withAttributes: attrs(f, c)).width
        draw(s, f, c, right - width, y)
    }

    private func drawCenter(_ s: String, _ f: NSFont, _ c: NSColor, _ cx: CGFloat, _ y: CGFloat) {
        let width = (s as NSString).size(withAttributes: attrs(f, c)).width
        draw(s, f, c, cx - width / 2, y)
    }
}
