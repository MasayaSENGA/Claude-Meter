// ウィンドウ・メニュー・タイマー
import AppKit
import ServiceManagement

final class MeterPanel: NSPanel {
    init(size: NSSize) {
        super.init(contentRect: NSRect(origin: .zero, size: size),
                   styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        isFloatingPanel = true
        hidesOnDeactivate = false
        hasShadow = true
        backgroundColor = Theme.back
        collectionBehavior = [.canJoinAllSpaces, .fullScreenNone]
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate, NSMenuDelegate {
    private var settings = Settings.load()
    private var panel: MeterPanel!
    private var view: MeterView!
    private var statusItem: NSStatusItem!
    private var refreshTimer: Timer?
    private var sweepTimer: Timer?
    private var last: UsageResult?
    private var fetching = false
    private var settingsWindow: SettingsWindowController?
    private var restoringFrame = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        view = MeterView(settings: settings)
        view.onDoubleClick = { [weak self] in self?.refresh() }
        view.menu = makeMenu()

        panel = MeterPanel(size: view.frame.size)
        panel.contentView = view
        panel.delegate = self
        applyWindowSettings()
        restoringFrame = true
        panel.setFrameOrigin(initialOrigin(for: panel.frame.size))
        restoringFrame = false
        panel.orderFrontRegardless()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem.button?.image = AppIcon.menuBarImage()
        statusItem.button?.toolTip = "Claude Meter"
        statusItem.menu = makeMenu()

        restartRefreshTimer()
        // 残り時間とピーク表示の更新
        let clock = Timer(timeInterval: 30, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.view.needsDisplay = true
                self?.updateToolTip()
            }
        }
        RunLoop.main.add(clock, forMode: .common)

        startSweep()
        refresh()
    }

    func applicationWillTerminate(_ notification: Notification) { savePosition() }

    // MARK: 取得

    private func refresh() {
        if fetching { return }
        fetching = true
        view.fetching = true
        view.needsDisplay = true
        Task {
            let r = await UsageClient.shared.fetch()
            // 失敗時は前回値を残してエラーだけ差し替える
            if r.error != nil, var prev = last, prev.error == nil {
                prev.error = r.error
                last = prev
            } else {
                last = r
            }
            fetching = false
            view.fetching = false
            view.result = last
            view.needsDisplay = true
            updateToolTip()
        }
    }

    private func restartRefreshTimer() {
        refreshTimer?.invalidate()
        let t = Timer(timeInterval: TimeInterval(settings.refreshMinutes * 60), repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.refresh() }
        }
        RunLoop.main.add(t, forMode: .common)
        refreshTimer = t
    }

    private func updateToolTip() {
        guard let last else { return }
        var s = "Claude"
        if last.fiveHour.present { s += " 5h:" + Format.percent(last.fiveHour.utilization) }
        if last.weekly.present { s += " 週:" + Format.percent(last.weekly.utilization) }
        if settings.showFable && last.weeklyFable.present { s += " Fable:" + Format.percent(last.weeklyFable.utilization) }
        statusItem.button?.toolTip = s
    }

    // MARK: スイープ

    private func startSweep() {
        guard settings.isGauge && settings.gaugeSweep else { return }
        view.sweepStart = CACurrentMediaTime()
        sweepTimer?.invalidate()
        let t = Timer(timeInterval: 1.0 / 60, repeats: true) { [weak self] timer in
            MainActor.assumeIsolated {
                guard let self, let start = self.view.sweepStart else { timer.invalidate(); return }
                if CACurrentMediaTime() - start >= MeterView.sweepTotal {
                    self.view.sweepStart = nil
                    timer.invalidate()
                }
                self.view.needsDisplay = true
            }
        }
        RunLoop.main.add(t, forMode: .common)
        sweepTimer = t
    }

    // MARK: ウィンドウ

    private func applyWindowSettings() {
        panel.level = settings.topMost ? .floating : .normal
        panel.alphaValue = settings.opacity
    }

    // 保存位置が画面外なら、メイン画面の右下に出す
    private func initialOrigin(for size: NSSize) -> NSPoint {
        let saved = NSRect(x: CGFloat(settings.x), y: CGFloat(settings.y) - 40, width: 40, height: 40)
        if !(settings.x == -1 && settings.y == -1),
           NSScreen.screens.contains(where: { $0.visibleFrame.contains(saved) }) {
            return NSPoint(x: CGFloat(settings.x), y: CGFloat(settings.y) - size.height)
        }
        let vf = (NSScreen.main ?? NSScreen.screens[0]).visibleFrame
        return NSPoint(x: vf.maxX - size.width - 16, y: vf.minY + 16)
    }

    // 大きさが変わったら左上を保ったまま変え、画面外にはみ出さないよう戻す
    private func resizeKeepingOnScreen() {
        let size = MeterView.size(for: settings)
        let old = panel.frame
        var f = NSRect(x: old.minX, y: old.maxY - size.height, width: size.width, height: size.height)
        if let vf = (panel.screen ?? NSScreen.main)?.visibleFrame {
            f.origin.x = max(vf.minX, min(f.minX, vf.maxX - f.width))
            f.origin.y = max(vf.minY, min(f.minY, vf.maxY - f.height))
        }
        panel.setFrame(f, display: true)
        savePosition()
    }

    func windowDidMove(_ notification: Notification) {
        if !restoringFrame { savePosition() }
    }

    private func savePosition() {
        guard let panel else { return }
        settings.x = Int(panel.frame.minX.rounded())
        settings.y = Int(panel.frame.maxY.rounded())
        settings.save()
    }

    // MARK: メニュー

    private func makeMenu() -> NSMenu {
        let m = NSMenu()
        m.delegate = self
        m.autoenablesItems = false
        m.addItem(item("今すぐ更新", #selector(refreshNow)))
        m.addItem(item("常に手前に表示", #selector(toggleTopMost), tag: 1))
        m.addItem(item("ログイン時に開始", #selector(toggleStartup), tag: 2))
        m.addItem(item("表示／非表示", #selector(toggleVisible)))
        m.addItem(item("設定...", #selector(showSettings)))
        m.addItem(.separator())
        m.addItem(item("終了", #selector(quit)))
        return m
    }

    private func item(_ title: String, _ action: Selector, tag: Int = 0) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: "")
        i.target = self
        i.tag = tag
        return i
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.item(withTag: 1)?.state = settings.topMost ? .on : .off
        menu.item(withTag: 2)?.state = isStartupEnabled ? .on : .off
    }

    @objc private func refreshNow() { refresh() }

    @objc private func toggleTopMost() {
        settings.topMost.toggle()
        applyWindowSettings()
        settings.save()
    }

    @objc private func toggleStartup() { setStartup(!isStartupEnabled) }

    @objc private func toggleVisible() {
        if panel.isVisible {
            panel.orderOut(nil)
        } else {
            panel.orderFrontRegardless()
            refresh()
        }
    }

    @objc private func quit() { NSApp.terminate(nil) }

    @objc private func showSettings() {
        if let w = settingsWindow {
            NSApp.activate(ignoringOtherApps: true)
            w.window?.makeKeyAndOrderFront(nil)
            return
        }
        let c = SettingsWindowController(settings: settings, startupEnabled: isStartupEnabled)
        c.onOK = { [weak self] s, startup in self?.applySettings(s, startup: startup) }
        c.onClose = { [weak self] in self?.settingsWindow = nil }
        settingsWindow = c
        if let w = c.window {
            // メーターのある画面の中央に開く
            let vf = (panel.screen ?? NSScreen.main ?? NSScreen.screens[0]).visibleFrame
            w.setFrameOrigin(NSPoint(x: vf.midX - w.frame.width / 2, y: vf.midY - w.frame.height / 2))
        }
        NSApp.activate(ignoringOtherApps: true)
        c.showWindow(nil)
    }

    private func applySettings(_ s: Settings, startup: Bool) {
        let wasGauge = settings.isGauge
        var s = s
        s.x = settings.x
        s.y = settings.y
        settings = s
        settings.save()
        view.settings = settings
        restartRefreshTimer()
        applyWindowSettings()
        resizeKeepingOnScreen()
        if !wasGauge && settings.isGauge { startSweep() }
        if startup != isStartupEnabled { setStartup(startup) }
        view.needsDisplay = true
        updateToolTip()
    }

    // MARK: ログイン時に開始（SMAppService なので管理者権限は不要）

    private var isStartupEnabled: Bool { SMAppService.mainApp.status == .enabled }

    private func setStartup(_ enable: Bool) {
        do {
            if enable { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
        } catch {
            let a = NSAlert()
            a.messageText = "自動起動の設定に失敗しました"
            a.informativeText = error.localizedDescription
            NSApp.activate(ignoringOtherApps: true)
            a.runModal()
        }
    }
}
