// 使用状況の取得（Claude Code の /usage と同じ非公開エンドポイント）
import Foundation

struct UsageWindow {
    var present = false
    var utilization = 0.0 // 0-100
    var resetsAt: Date?
}

struct UsageResult {
    var fiveHour = UsageWindow()
    var weekly = UsageWindow()
    var weeklyFable = UsageWindow()
    var error: String?
    var rawBody: String?
    var fetchedAt = Clock.now
}

actor UsageClient {
    static let shared = UsageClient()

    private let endpoint = URL(string: "https://api.anthropic.com/api/oauth/usage")!
    private let tokenURL = URL(string: "https://platform.claude.com/v1/oauth/token")!
    private let clientId = "9d1c250a-e61b-44d9-88ed-5944d1962f5e" // Claude Code の公開クライアントID
    private let session = URLSession(configuration: .ephemeral) // トークン入りの通信をディスクに残さない

    private struct HTTPError: Error { let status: Int }

    func fetch() async -> UsageResult {
        var r = UsageResult()
        do {
            var token = try await accessToken(force: false)
            let data: Data
            do {
                data = try await getUsage(token)
            } catch let e as HTTPError where e.status == 401 {
                // 期限内でも失効していることがあるので1回だけ更新して再試行
                token = try await accessToken(force: true)
                data = try await getUsage(token)
            }
            r.rawBody = String(decoding: data, as: UTF8.self)
            try UsageClient.parse(data, into: &r)
        } catch let e as MeterError {
            r.error = e.message
        } catch let e as HTTPError {
            switch e.status {
            case 401: r.error = "認証エラー（claude で /login してください）"
            case 429: r.error = "取得回数の制限中（しばらく待ってください）"
            default: r.error = "取得失敗: HTTP \(e.status)"
            }
        } catch let e as URLError {
            r.error = "通信エラー: " + e.localizedDescription
        } catch {
            r.error = "取得失敗: " + error.localizedDescription
        }
        return r
    }

    private func getUsage(_ token: String) async throws -> Data {
        var req = URLRequest(url: endpoint, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 15)
        req.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
        req.setValue("oauth-2025-04-20", forHTTPHeaderField: "anthropic-beta")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("ClaudeMeter/1.0", forHTTPHeaderField: "User-Agent")
        let (data, resp) = try await session.data(for: req)
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw HTTPError(status: status) }
        return data
    }

    // 毎回ログイン情報を読み直し、期限切れ（または force）ならリフレッシュして書き戻す。
    // 書き戻すことで Claude Code CLI 側も新しいトークンをそのまま使える。
    private func accessToken(force: Bool) async throws -> String {
        var cred = try Credentials.load()
        let nowMs = Int64(Date().timeIntervalSince1970 * 1000)
        if !force && cred.expiresAt > nowMs + 60000 { return cred.accessToken }

        guard let refreshToken = cred.oauth["refreshToken"] as? String else {
            throw MeterError("トークンの期限切れ（claude で /login してください）")
        }
        var body: [String: Any] = [
            "grant_type": "refresh_token",
            "refresh_token": refreshToken,
            "client_id": clientId,
        ]
        if let scopes = cred.oauth["scopes"] as? [String], !scopes.isEmpty {
            body["scope"] = scopes.joined(separator: " ")
        }
        var req = URLRequest(url: tokenURL, cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 30)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("ClaudeMeter/1.0", forHTTPHeaderField: "User-Agent")
        req.httpBody = try JSONSerialization.data(withJSONObject: body)

        let data: Data, resp: URLResponse
        do {
            (data, resp) = try await session.data(for: req)
        } catch {
            throw MeterError("トークン更新の通信エラー: " + error.localizedDescription)
        }
        let status = (resp as? HTTPURLResponse)?.statusCode ?? 0
        if status == 400 || status == 401 { throw MeterError("ログインの有効期限切れ（claude で /login してください）") }
        guard (200..<300).contains(status) else { throw MeterError("トークン更新の通信エラー: HTTP \(status)") }
        guard let res = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let newToken = res["access_token"] as? String else {
            throw MeterError("トークン更新に失敗（claude で /login してください）")
        }

        cred.oauth["accessToken"] = newToken
        if let rt = res["refresh_token"] as? String { cred.oauth["refreshToken"] = rt }
        if let exp = (res["expires_in"] as? NSNumber)?.int64Value { cred.oauth["expiresAt"] = nowMs + exp * 1000 }
        if let rexp = (res["refresh_token_expires_in"] as? NSNumber)?.int64Value {
            cred.oauth["refreshTokenExpiresAt"] = nowMs + rexp * 1000
        }
        do { try cred.save() } catch let e as MeterError {
            throw MeterError("トークン更新に失敗: " + e.message)
        }
        return newToken
    }

    static func parse(_ data: Data, into r: inout UsageResult) throws {
        guard let d = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MeterError("取得失敗: 応答の形式が違います")
        }
        r.fiveHour = window(d["five_hour"])
        r.weekly = window(d["seven_day"])

        // モデル別の週間枠は limits[] に { scope: { model: { display_name } }, percent, resets_at } で入っている
        for item in d["limits"] as? [Any] ?? [] {
            guard let o = item as? [String: Any],
                  let scope = o["scope"] as? [String: Any],
                  let model = scope["model"] as? [String: Any],
                  let name = model["display_name"] as? String,
                  name.range(of: "fable", options: .caseInsensitive) != nil else { continue }
            var w = UsageWindow()
            if let p = o["percent"] as? NSNumber { w.present = true; w.utilization = p.doubleValue }
            w.resetsAt = date(o["resets_at"])
            if w.present { r.weeklyFable = w; return }
        }
        // 念のため seven_day_fable のようなキーでも探す
        for key in d.keys.sorted() where key.range(of: "fable", options: .caseInsensitive) != nil {
            let w = window(d[key])
            if w.present { r.weeklyFable = w; return }
        }
    }

    private static func window(_ v: Any?) -> UsageWindow {
        var w = UsageWindow()
        guard let o = v as? [String: Any] else { return w }
        if let u = o["utilization"] as? NSNumber { w.present = true; w.utilization = u.doubleValue }
        w.resetsAt = date(o["resets_at"])
        return w
    }

    // resets_at は ISO 8601 文字列か UNIX 秒
    private static func date(_ v: Any?) -> Date? {
        if let n = v as? NSNumber { return Date(timeIntervalSince1970: n.doubleValue) }
        guard let s = v as? String else { return nil }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: s) { return d }
        // 小数秒が6桁だと読めないことがあるので小数部を外して読み直す
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: s.replacingOccurrences(of: #"\.\d+"#, with: "", options: .regularExpression))
    }
}
