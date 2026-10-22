// アイコン（オレンジの円に白い弧と針）。32 を基準とした下向き座標で描く
import AppKit

enum AppIcon {
    // 現在のコンテキストに 32×32 基準・下向き座標で描けるよう座標系を合わせてから呼ぶ
    private static func drawGlyph(template: Bool) {
        let circle = NSBezierPath(ovalIn: NSRect(x: 1, y: 1, width: 30, height: 30))
        (template ? NSColor.black : Theme.brand).setFill()
        circle.fill()

        let path = NSBezierPath()
        // 弧: (8,8)〜(24,24) の円の 135° から 270° 分
        path.appendArc(withCenter: NSPoint(x: 16, y: 16), radius: 8, startAngle: 135, endAngle: 405, clockwise: false)
        path.move(to: NSPoint(x: 16, y: 16))
        path.line(to: NSPoint(x: 22, y: 11))
        path.lineWidth = 4
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        if template {
            // テンプレート画像は形だけが使われるので、線の部分を円から抜く
            NSGraphicsContext.current?.compositingOperation = .destinationOut
            NSColor.black.setStroke()
        } else {
            NSColor.white.setStroke()
        }
        path.stroke()
    }

    // メニューバー用（ライト／ダークに合わせて macOS が色を付ける）
    static func menuBarImage() -> NSImage {
        let image = NSImage(size: NSSize(width: 18, height: 18), flipped: true) { rect in
            let t = NSAffineTransform()
            t.scale(by: rect.width / 32)
            t.concat()
            drawGlyph(template: true)
            return true
        }
        image.isTemplate = true
        return image
    }

    static func png(pixels: Int) -> Data? {
        guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
              let ctx = NSGraphicsContext(bitmapImageRep: rep) else { return nil }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = ctx
        let t = NSAffineTransform()
        t.translateX(by: 0, yBy: CGFloat(pixels))
        t.scaleX(by: CGFloat(pixels) / 32, yBy: -CGFloat(pixels) / 32)
        t.concat()
        drawGlyph(template: false)
        NSGraphicsContext.restoreGraphicsState()
        return rep.representation(using: .png, properties: [:])
    }

    // build.sh から呼ばれ、iconutil に渡す .iconset フォルダを作る
    static func writeIconset(to dir: URL) throws {
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        for size in [16, 32, 128, 256, 512] {
            for scale in [1, 2] {
                let name = scale == 1 ? "icon_\(size)x\(size).png" : "icon_\(size)x\(size)@2x.png"
                try png(pixels: size * scale)?.write(to: dir.appendingPathComponent(name))
            }
        }
    }
}
