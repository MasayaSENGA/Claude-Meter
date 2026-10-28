// Claude Code のログイン情報の読み書き
// macOS の Claude Code はキーチェーン（汎用パスワード「Claude Code-credentials」）に保存する。
// 項目は /usr/bin/security が作っていて、その ACL で許可されているので、同じ security コマンド経由で
// 読み書きすれば許可ダイアログが出ない。キーチェーンに無ければ ~/.claude/.credentials.json を見る。
import Foundation

struct MeterError: Error {
    let message: String
    init(_ message: String) { self.message = message }
}

struct Credentials {
    enum Store {
        case keychain(account: String)
        case file(URL)
    }

    var all: [String: Any]
    var oauth: [String: Any]
    let store: Store

    var accessToken: String { oauth["accessToken"] as? String ?? "" }
    var expiresAt: Int64 { (oauth["expiresAt"] as? NSNumber)?.int64Value ?? 0 }

    static var fileURL: URL {
        let dir: URL
        if let env = ProcessInfo.processInfo.environment["CLAUDE_CONFIG_DIR"], !env.isEmpty {
            dir = URL(fileURLWithPath: env, isDirectory: true)
        } else {
            dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude", isDirectory: true)
        }
        return dir.appendingPathComponent(".credentials.json")
    }

    static func load() throws -> Credentials {
        if let item = Keychain.read() {
            return try parse(Data(item.json.utf8), store: .keychain(account: item.account))
        }
        let url = fileURL
        guard let data = try? Data(contentsOf: url) else {
            throw MeterError("Claude Code のログイン情報が見つかりません（claude で /login してください）")
        }
        return try parse(data, store: .file(url))
    }

    private static func parse(_ data: Data, store: Store) throws -> Credentials {
        guard let all = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] else {
            throw MeterError("ログイン情報を読めません")
        }
        guard let oauth = all["claudeAiOauth"] as? [String: Any], oauth["accessToken"] is String else {
            throw MeterError("ログイン情報にアクセストークンがありません（claude で /login してください）")
        }
        return Credentials(all: all, oauth: oauth, store: store)
    }

    // 元の保存先に書き戻す。他のフィールドはそのまま残す
    mutating func save() throws {
        all["claudeAiOauth"] = oauth
        let data = try JSONSerialization.data(withJSONObject: all, options: [.withoutEscapingSlashes])
        switch store {
        case .keychain(let account):
            try Keychain.write(String(decoding: data, as: UTF8.self), account: account)
        case .file(let url):
            try Credentials.writeFile(data, to: url)
        }
    }

    private static func writeFile(_ data: Data, to url: URL) throws {
        let tmp = url.appendingPathExtension("claudemeter.tmp")
        // トークンを含む一時ファイルを失敗時にも残さない
        defer { try? FileManager.default.removeItem(at: tmp) }
        guard FileManager.default.createFile(atPath: tmp.path, contents: data, attributes: [.posixPermissions: 0o600]) else {
            throw MeterError("ログイン情報を書き込めません")
        }
        if rename(tmp.path, url.path) != 0 {
            throw MeterError("ログイン情報を書き込めません: " + String(cString: strerror(errno)))
        }
    }
}

enum Keychain {
    static let service = "Claude Code-credentials"
    private static let tool = "/usr/bin/security"

    static func read() -> (json: String, account: String)? {
        let pw = run(["find-generic-password", "-s", service, "-w"])
        guard pw.status == 0 else { return nil }
        var json = String(decoding: pw.out, as: UTF8.self).trimmingCharacters(in: .newlines)
        // 表示できない文字を含むと security は16進で出力する
        if !json.hasPrefix("{"), let d = hexDecode(json) { json = String(decoding: d, as: UTF8.self) }

        var account = NSUserName()
        let attrs = run(["find-generic-password", "-s", service])
        for line in String(decoding: attrs.out, as: UTF8.self).split(separator: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            let prefix = "\"acct\"<blob>=\""
            if t.hasPrefix(prefix), t.hasSuffix("\"") {
                account = String(t.dropFirst(prefix.count).dropLast())
            }
        }
        return (json, account)
    }

    static func write(_ json: String, account: String) throws {
        guard !account.contains("\""), !account.contains("\n") else { throw MeterError("キーチェーンのアカウント名を扱えません") }
        let hex = json.utf8.map { String(format: "%02x", $0) }.joined()
        // トークンがプロセス一覧に見えないよう、コマンドは標準入力で渡す（security -i は1行約4KBまで）
        let line = "add-generic-password -U -a \"\(account)\" -s \"\(service)\" -X \(hex)\n"
        let r = line.utf8.count < 4000
            ? run(["-i"], input: line)
            : run(["add-generic-password", "-U", "-a", account, "-s", service, "-X", hex])
        guard r.status == 0, read()?.json == json else {
            throw MeterError("キーチェーンに書き込めません")
        }
    }

    private static func run(_ args: [String], input: String? = nil) -> (status: Int32, out: Data) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: tool)
        p.arguments = args
        let out = Pipe(), err = Pipe(), inp = Pipe()
        p.standardOutput = out
        p.standardError = err
        p.standardInput = inp
        do { try p.run() } catch { return (-1, Data()) }
        if let input { inp.fileHandleForWriting.write(Data(input.utf8)) }
        try? inp.fileHandleForWriting.close()
        let data = out.fileHandleForReading.readDataToEndOfFile()
        _ = err.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return (p.terminationStatus, data)
    }

    private static func hexDecode(_ s: String) -> Data? {
        let chars = Array(s.utf8)
        guard chars.count % 2 == 0 else { return nil }
        var d = Data(capacity: chars.count / 2)
        var i = 0
        while i < chars.count {
            guard let b = UInt8(String(decoding: chars[i..<i + 2], as: UTF8.self), radix: 16) else { return nil }
            d.append(b)
            i += 2
        }
        return d
    }
}
