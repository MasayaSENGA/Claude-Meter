// 設定画面
// 動作確認で PNG に保存できるよう（SwiftUI は cacheDisplay で描けない部品がある）AppKit で組む。
import AppKit

final class SettingsWindowController: NSWindowController, NSWindowDelegate {
    var onOK: ((Settings, Bool) -> Void)?
    var onClose: (() -> Void)?

    private var base: Settings // 画面に出さない項目（位置など）はこれを引き継ぐ
    private let refresh = NSTextField()
    private let refreshStepper = NSStepper()
    private let timeZone = NSPopUpButton()
    private let peakStart = SettingsWindowController.timePicker()
    private let peakEnd = SettingsWindowController.timePicker()
    private let weekdaysOnly = NSButton(checkboxWithTitle: "平日のみ（土日はオフピーク）", target: nil, action: nil)
    private let localPeak = NSTextField(labelWithString: "")
    private let styleBar = NSButton(radioButtonWithTitle: "バー", target: nil, action: nil)
    private let styleGauge = NSButton(radioButtonWithTitle: "スピードメーター", target: nil, action: nil)
    private let layoutHorizontal = NSButton(radioButtonWithTitle: "横並び", target: nil, action: nil)
    private let layoutVertical = NSButton(radioButtonWithTitle: "縦並び", target: nil, action: nil)
    private let gaugeSweep = NSButton(checkboxWithTitle: "起動時に針を最大まで振り切る（スイープ）", target: nil, action: nil)
    private let showFable = NSButton(checkboxWithTitle: "週間制限（Fable）を表示", target: nil, action: nil)
    private let topMost = NSButton(checkboxWithTitle: "常に手前に表示", target: nil, action: nil)
    private let opacity = NSSlider(value: 95, minValue: 30, maxValue: 100, target: nil, action: nil)
    private let opacityValue = NSTextField(labelWithString: "")
    private let startup = NSButton(checkboxWithTitle: "ログイン時に開始", target: nil, action: nil)

    private static let zones: [(id: String, title: String)] = {
        let ja = Locale(identifier: "ja_JP")
        let now = Date()
        return TimeZone.knownTimeZoneIdentifiers.compactMap { id -> (Int, String, String)? in
            guard let tz = TimeZone(identifier: id) else { return nil }
            let off = tz.secondsFromGMT(for: now)
            let sign = off < 0 ? "-" : "+"
            let gmt = String(format: "(GMT%@%02d:%02d)", sign, abs(off) / 3600, abs(off) % 3600 / 60)
            let name = tz.localizedName(for: .generic, locale: ja).map { " " + $0 } ?? ""
            return (off, id, "\(gmt) \(id)\(name)")
        }
        .sorted { $0.0 != $1.0 ? $0.0 < $1.0 : $0.1 < $1.1 }
        .map { ($0.1, $0.2) }
    }()

    init(settings: Settings, startupEnabled: Bool) {
        base = settings
        let window = NSWindow(contentRect: .zero, styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Claude Meter の設定"
        window.level = .floating // 常に手前のメーターの裏に隠れないように
        window.isReleasedWhenClosed = false
        super.init(window: window)
        window.delegate = self
        buildUi()
        load(settings, startupEnabled: startupEnabled)
    }

    required init?(coder: NSCoder) { fatalError() }

    private func buildUi() {
        refresh.formatter = {
            let f = NumberFormatter()
            f.minimum = 1
            f.maximum = 60
            f.allowsFloats = false
            return f
        }()
        refresh.alignment = .right
        refresh.widthAnchor.constraint(equalToConstant: 44).isActive = true
        refresh.target = self
        refresh.action = #selector(refreshEdited)
        refreshStepper.minValue = 1
        refreshStepper.maxValue = 60
        refreshStepper.target = self
        refreshStepper.action = #selector(refreshStepped)

        for z in SettingsWindowController.zones {
            timeZone.addItem(withTitle: z.title)
            timeZone.lastItem?.representedObject = z.id
        }
        timeZone.widthAnchor.constraint(equalToConstant: 380).isActive = true
        localPeak.textColor = .secondaryLabelColor
        opacityValue.widthAnchor.constraint(equalToConstant: 40).isActive = true
        opacity.widthAnchor.constraint(equalToConstant: 200).isActive = true

        for c in [timeZone, peakStart, peakEnd, weekdaysOnly] as [NSControl] {
            c.target = self
            c.action = #selector(updateLocalPeak)
        }
        // ラジオボタンは同じ親・同じ action でグループになる
        styleBar.target = self; styleBar.action = #selector(styleChanged)
        styleGauge.target = self; styleGauge.action = #selector(styleChanged)
        layoutHorizontal.target = self; layoutHorizontal.action = #selector(layoutChanged)
        layoutVertical.target = self; layoutVertical.action = #selector(layoutChanged)
        opacity.target = self
        opacity.action = #selector(opacityChanged)

        var rows: [[NSView]] = []
        var sections: [Int] = []
        func section(_ title: String) {
            let l = NSTextField(labelWithString: title)
            l.font = .boldSystemFont(ofSize: NSFont.systemFontSize)
            sections.append(rows.count)
            rows.append([l, NSGridCell.emptyContentView])
        }
        func row(_ label: String, _ views: NSView...) {
            let content = views.count == 1 ? views[0] : hstack(views)
            rows.append([label.isEmpty ? NSGridCell.emptyContentView : NSTextField(labelWithString: label), content])
        }

        section("更新")
        row("更新間隔", refresh, refreshStepper, NSTextField(labelWithString: "分ごと"))
        section("ピークタイム")
        row("基準タイムゾーン", timeZone)
        row("時間帯", peakStart, NSTextField(labelWithString: "〜"), peakEnd)
        row("", weekdaysOnly)
        row("", localPeak)
        section("表示")
        row("表示形式", styleBar, styleGauge)
        row("メーターの並び", layoutHorizontal, layoutVertical)
        row("", gaugeSweep)
        row("", showFable)
        row("", topMost)
        row("不透明度", opacity, opacityValue)
        row("", startup)

        let grid = NSGridView(views: rows)
        grid.rowSpacing = 8
        grid.columnSpacing = 12
        grid.column(at: 0).xPlacement = .trailing
        grid.rowAlignment = .firstBaseline
        for i in sections {
            let r = grid.row(at: i)
            r.mergeCells(in: NSRange(location: 0, length: 2))
            r.cell(at: 0).xPlacement = .leading
            if i > 0 { r.topPadding = 10 }
        }

        let reset = NSButton(title: "既定に戻す", target: self, action: #selector(resetDefaults))
        let cancel = NSButton(title: "キャンセル", target: self, action: #selector(cancelPressed))
        cancel.keyEquivalent = "\u{1b}"
        let ok = NSButton(title: "OK", target: self, action: #selector(okPressed))
        ok.keyEquivalent = "\r"
        for b in [reset, cancel, ok] { b.widthAnchor.constraint(greaterThanOrEqualToConstant: 90).isActive = true }
        let spacer = NSView()
        spacer.setContentHuggingPriority(.init(1), for: .horizontal)
        let buttons = NSStackView(views: [reset, spacer, cancel, ok])

        let root = NSStackView(views: [grid, buttons])
        root.orientation = .vertical
        root.alignment = .leading
        root.spacing = 20
        root.edgeInsets = NSEdgeInsets(top: 20, left: 20, bottom: 20, right: 20)
        buttons.widthAnchor.constraint(equalTo: grid.widthAnchor).isActive = true

        window?.contentView = root
        window?.setContentSize(root.fittingSize)
    }

    private func hstack(_ views: [NSView]) -> NSStackView {
        let s = NSStackView(views: views)
        s.spacing = 6
        s.alignment = .firstBaseline
        return s
    }

    private static func timePicker() -> NSDatePicker {
        let p = NSDatePicker()
        p.datePickerStyle = .textFieldAndStepper
        p.datePickerElements = .hourMinute
        p.timeZone = TimeZone(secondsFromGMT: 0) // 0 時からの経過時間として扱う
        p.locale = Locale(identifier: "ja_JP") // 24時間表記
        return p
    }

    private func load(_ s: Settings, startupEnabled: Bool) {
        setRefresh(s.refreshMinutes)
        let index = SettingsWindowController.zones.firstIndex { $0.id == s.peakTimeZone }
            ?? SettingsWindowController.zones.firstIndex { $0.id == TimeZone.current.identifier } ?? 0
        timeZone.selectItem(at: index)
        peakStart.dateValue = Date(timeIntervalSince1970: Double((PeakClock.parseTime(s.peakStart) ?? 0) * 60))
        peakEnd.dateValue = Date(timeIntervalSince1970: Double((PeakClock.parseTime(s.peakEnd) ?? 0) * 60))
        weekdaysOnly.state = s.peakWeekdaysOnly ? .on : .off
        styleGauge.state = s.isGauge ? .on : .off
        styleBar.state = s.isGauge ? .off : .on
        layoutVertical.state = s.gaugeVertical ? .on : .off
        layoutHorizontal.state = s.gaugeVertical ? .off : .on
        gaugeSweep.state = s.gaugeSweep ? .on : .off
        showFable.state = s.showFable ? .on : .off
        topMost.state = s.topMost ? .on : .off
        opacity.doubleValue = (min(1, max(0.3, s.opacity)) * 100).rounded()
        startup.state = startupEnabled ? .on : .off
        opacityChanged()
        styleChanged()
        updateLocalPeak()
    }

    private func current() -> Settings {
        var s = base
        s.refreshMinutes = min(60, max(1, refresh.integerValue))
        if let id = timeZone.selectedItem?.representedObject as? String { s.peakTimeZone = id }
        s.peakStart = SettingsWindowController.hhmm(peakStart.dateValue)
        s.peakEnd = SettingsWindowController.hhmm(peakEnd.dateValue)
        s.peakWeekdaysOnly = weekdaysOnly.state == .on
        s.style = styleGauge.state == .on ? "gauge" : "bar"
        s.gaugeVertical = layoutVertical.state == .on
        s.gaugeSweep = gaugeSweep.state == .on
        s.showFable = showFable.state == .on
        s.topMost = topMost.state == .on
        s.opacity = opacity.doubleValue.rounded() / 100
        return s
    }

    private static func hhmm(_ d: Date) -> String {
        let m = Int(d.timeIntervalSince1970) / 60 % 1440
        return String(format: "%02d:%02d", m / 60, m % 60)
    }

    private func setRefresh(_ v: Int) {
        refresh.integerValue = v
        refreshStepper.integerValue = v
    }

    @objc private func refreshEdited() { setRefresh(min(60, max(1, refresh.integerValue))) }
    @objc private func refreshStepped() { setRefresh(refreshStepper.integerValue) }
    @objc private func opacityChanged() { opacityValue.stringValue = "\(Int(opacity.doubleValue.rounded()))%" }
    @objc private func layoutChanged() {}

    // 並びとスイープの指定はスピードメーターのときだけ意味がある
    @objc private func styleChanged() {
        let gauge = styleGauge.state == .on
        layoutHorizontal.isEnabled = gauge
        layoutVertical.isEnabled = gauge
        gaugeSweep.isEnabled = gauge
    }

    // 選んだタイムゾーンの時間帯が、この Mac の時刻で今日何時になるかを示す
    @objc private func updateLocalPeak() {
        let s = current()
        guard let tz = TimeZone(identifier: s.peakTimeZone) else { localPeak.stringValue = ""; return }
        var there = Calendar(identifier: .gregorian)
        there.timeZone = tz
        let today = there.dateComponents([.year, .month, .day], from: Date())
        func at(_ hhmm: String) -> Date? {
            var c = today
            let m = PeakClock.parseTime(hhmm) ?? 0
            c.hour = m / 60
            c.minute = m % 60
            return there.date(from: c) // 夏時間開始の欠けた時刻はその後の時刻になる
        }
        guard let start = at(s.peakStart), var end = at(s.peakEnd) else { return }
        if end <= start { end.addTimeInterval(86400) }
        let nextDay = !Calendar.current.isDate(start, inSameDayAs: end)
        localPeak.stringValue = "この Mac の時刻では " + Format.time(start) + "〜" + (nextDay ? "翌" : "") + Format.time(end)
            + (s.peakWeekdaysOnly ? "（基準タイムゾーンの平日のみ）" : "（毎日）")
    }

    @objc private func resetDefaults() {
        var d = Settings()
        d.x = base.x
        d.y = base.y
        load(d, startupEnabled: startup.state == .on)
    }

    @objc private func okPressed() {
        window?.makeFirstResponder(nil) // 入力中の数値を確定させる
        onOK?(current(), startup.state == .on)
        close()
    }

    @objc private func cancelPressed() { close() }

    func windowWillClose(_ notification: Notification) { onClose?() }
}
