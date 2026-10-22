// Claude Meter - Claude の利用制限の使用状況を常時表示する小さなウィンドウ
// .NET Framework 4.x 標準の csc.exe でビルドできるよう C# 5 の範囲で書いている。
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Globalization;
using System.IO;
using System.Net;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace ClaudeMeter
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            bool created;
            using (var mutex = new System.Threading.Mutex(true, "ClaudeMeter_SingleInstance", out created))
            {
                if (!created) return;
                ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072; // TLS 1.2
                Dpi.EnableAwareness();
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                var args = Environment.GetCommandLineArgs();
                string snapshot = args.Length >= 3 && args[1] == "--snapshot" ? args[2] : null;
                float forcedScale = 0;
                if (snapshot != null && args.Length >= 4) float.TryParse(args[3], NumberStyles.Float, CultureInfo.InvariantCulture, out forcedScale);
                Application.Run(new MeterForm(snapshot, forcedScale));
            }
        }
    }

    // ---------- 設定 ----------
    class Settings
    {
        public int RefreshMinutes = 5;
        public string PeakTimeZone = "Pacific Standard Time";
        public string PeakStart = "05:00";
        public string PeakEnd = "11:00";
        public bool PeakWeekdaysOnly = true;
        public bool TopMost = true;
        public double Opacity = 0.95;
        public int X = -1;
        public int Y = -1;

        public static string Dir
        {
            get { return Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "ClaudeMeter"); }
        }
        static string FilePath { get { return Path.Combine(Dir, "settings.json"); } }

        public static Settings Load()
        {
            var s = new Settings();
            try
            {
                if (File.Exists(FilePath))
                {
                    var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(FilePath, Encoding.UTF8));
                    object v;
                    if (d.TryGetValue("refreshMinutes", out v)) s.RefreshMinutes = Math.Max(1, Convert.ToInt32(v));
                    if (d.TryGetValue("peakTimeZone", out v)) s.PeakTimeZone = Convert.ToString(v);
                    if (d.TryGetValue("peakStart", out v)) s.PeakStart = Convert.ToString(v);
                    if (d.TryGetValue("peakEnd", out v)) s.PeakEnd = Convert.ToString(v);
                    if (d.TryGetValue("peakWeekdaysOnly", out v)) s.PeakWeekdaysOnly = Convert.ToBoolean(v);
                    if (d.TryGetValue("topMost", out v)) s.TopMost = Convert.ToBoolean(v);
                    if (d.TryGetValue("opacity", out v)) s.Opacity = Math.Min(1.0, Math.Max(0.3, Convert.ToDouble(v, CultureInfo.InvariantCulture)));
                    if (d.TryGetValue("x", out v)) s.X = Convert.ToInt32(v);
                    if (d.TryGetValue("y", out v)) s.Y = Convert.ToInt32(v);
                }
            }
            catch { }
            s.Save();
            return s;
        }

        public void Save()
        {
            try
            {
                Directory.CreateDirectory(Dir);
                var d = new Dictionary<string, object>();
                d["refreshMinutes"] = RefreshMinutes;
                d["peakTimeZone"] = PeakTimeZone;
                d["peakStart"] = PeakStart;
                d["peakEnd"] = PeakEnd;
                d["peakWeekdaysOnly"] = PeakWeekdaysOnly;
                d["topMost"] = TopMost;
                d["opacity"] = Opacity;
                d["x"] = X;
                d["y"] = Y;
                File.WriteAllText(FilePath, PrettyJson(new JavaScriptSerializer().Serialize(d)), new UTF8Encoding(false));
            }
            catch { }
        }

        public static void OpenInEditor()
        {
            try { System.Diagnostics.Process.Start("notepad.exe", "\"" + FilePath + "\""); } catch { }
        }

        static string PrettyJson(string json)
        {
            // 手編集しやすいよう1項目1行にする（値に , や { を含まない前提の簡易整形）
            return json.Replace("{", "{\r\n  ").Replace(",\"", ",\r\n  \"").Replace("}", "\r\n}");
        }
    }

    // ---------- 使用状況の取得 ----------
    class UsageWindow
    {
        public bool Present;
        public double Utilization; // 0-100
        public DateTime? ResetsAt; // ローカル時刻
    }

    class UsageResult
    {
        public UsageWindow FiveHour = new UsageWindow();
        public UsageWindow Weekly = new UsageWindow();
        public UsageWindow WeeklyFable = new UsageWindow();
        public string Error;
        public string RawBody;
        public DateTime FetchedAt;
    }

    static class UsageClient
    {
        const string Endpoint = "https://api.anthropic.com/api/oauth/usage";

        static string CredentialsPath
        {
            get
            {
                var dir = Environment.GetEnvironmentVariable("CLAUDE_CONFIG_DIR");
                if (string.IsNullOrEmpty(dir))
                    dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".claude");
                return Path.Combine(dir, ".credentials.json");
            }
        }

        const string TokenUrl = "https://platform.claude.com/v1/oauth/token";
        const string ClientId = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"; // Claude Code の公開クライアントID
        static readonly object credLock = new object();

        static Dictionary<string, object> ReadCredentials(out Dictionary<string, object> oauth, out string error)
        {
            oauth = null;
            error = null;
            var path = CredentialsPath;
            if (!File.Exists(path))
            {
                error = "Claude Code のログイン情報が見つかりません（claude で /login してください）";
                return null;
            }
            try
            {
                var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(path, Encoding.UTF8));
                object o;
                if (d.TryGetValue("claudeAiOauth", out o)) oauth = o as Dictionary<string, object>;
                if (oauth == null || !oauth.ContainsKey("accessToken"))
                {
                    error = "ログイン情報にアクセストークンがありません（claude で /login してください）";
                    return null;
                }
                return d;
            }
            catch (Exception ex)
            {
                error = "ログイン情報を読めません: " + ex.Message;
                return null;
            }
        }

        // 毎回ファイルを読み直し、期限切れ（または force）ならリフレッシュして書き戻す。
        // 書き戻すことで Claude Code CLI 側も新しいトークンをそのまま使える。
        static string GetAccessToken(bool force, out string error)
        {
            lock (credLock)
            {
                Dictionary<string, object> oauth;
                var all = ReadCredentials(out oauth, out error);
                if (all == null) return null;

                long expiresAt = 0;
                object v;
                if (oauth.TryGetValue("expiresAt", out v) && v != null) expiresAt = Convert.ToInt64(v);
                long nowMs = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                if (!force && expiresAt > nowMs + 60000) return Convert.ToString(oauth["accessToken"]);

                object rt;
                if (!oauth.TryGetValue("refreshToken", out rt) || rt == null)
                {
                    error = "トークンの期限切れ（claude で /login してください）";
                    return null;
                }
                try
                {
                    var body = new Dictionary<string, object>();
                    body["grant_type"] = "refresh_token";
                    body["refresh_token"] = Convert.ToString(rt);
                    body["client_id"] = ClientId;
                    object scopes;
                    if (oauth.TryGetValue("scopes", out scopes) && scopes is System.Collections.ArrayList)
                    {
                        var list = new List<string>();
                        foreach (var s in (System.Collections.ArrayList)scopes) list.Add(Convert.ToString(s));
                        if (list.Count > 0) body["scope"] = string.Join(" ", list);
                    }
                    var res = PostJson(TokenUrl, new JavaScriptSerializer().Serialize(body));
                    object at;
                    if (!res.TryGetValue("access_token", out at) || at == null)
                    {
                        error = "トークン更新に失敗（claude で /login してください）";
                        return null;
                    }
                    oauth["accessToken"] = Convert.ToString(at);
                    object nrt;
                    if (res.TryGetValue("refresh_token", out nrt) && nrt != null) oauth["refreshToken"] = Convert.ToString(nrt);
                    object exp;
                    if (res.TryGetValue("expires_in", out exp) && exp != null)
                        oauth["expiresAt"] = nowMs + Convert.ToInt64(exp) * 1000;
                    object rexp;
                    if (res.TryGetValue("refresh_token_expires_in", out rexp) && rexp != null)
                        oauth["refreshTokenExpiresAt"] = nowMs + Convert.ToInt64(rexp) * 1000;
                    WriteCredentials(all);
                    return Convert.ToString(at);
                }
                catch (WebException ex)
                {
                    var resp = ex.Response as HttpWebResponse;
                    if (resp != null && ((int)resp.StatusCode == 400 || (int)resp.StatusCode == 401))
                        error = "ログインの有効期限切れ（claude で /login してください）";
                    else
                        error = "トークン更新の通信エラー: " + ex.Message;
                    return null;
                }
                catch (Exception ex)
                {
                    error = "トークン更新に失敗: " + ex.Message;
                    return null;
                }
            }
        }

        static void WriteCredentials(Dictionary<string, object> all)
        {
            var path = CredentialsPath;
            var tmp = path + ".claudemeter.tmp";
            try
            {
                File.WriteAllText(tmp, new JavaScriptSerializer().Serialize(all), new UTF8Encoding(false));
                File.Copy(tmp, path, true);
            }
            finally
            {
                // トークンを含む一時ファイルを失敗時にも残さない
                try { File.Delete(tmp); } catch { }
            }
        }

        static Dictionary<string, object> PostJson(string url, string json)
        {
            var req = (HttpWebRequest)WebRequest.Create(url);
            req.Method = "POST";
            req.Timeout = 30000;
            req.ContentType = "application/json";
            req.Accept = "application/json";
            req.UserAgent = "ClaudeMeter/1.0";
            var bytes = Encoding.UTF8.GetBytes(json);
            using (var st = req.GetRequestStream()) st.Write(bytes, 0, bytes.Length);
            using (var resp = (HttpWebResponse)req.GetResponse())
            using (var sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                return new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(sr.ReadToEnd());
        }

        public static Task<UsageResult> FetchAsync()
        {
            return Task.Run(() => Fetch());
        }

        static string GetUsage(string token)
        {
            var req = (HttpWebRequest)WebRequest.Create(Endpoint);
            req.Method = "GET";
            req.Timeout = 15000;
            req.Accept = "application/json";
            req.UserAgent = "ClaudeMeter/1.0";
            req.Headers["Authorization"] = "Bearer " + token;
            req.Headers["anthropic-beta"] = "oauth-2025-04-20";
            using (var resp = (HttpWebResponse)req.GetResponse())
            using (var sr = new StreamReader(resp.GetResponseStream(), Encoding.UTF8))
                return sr.ReadToEnd();
        }

        static UsageResult Fetch()
        {
            var r = new UsageResult { FetchedAt = DateTime.Now };
            string err;
            var token = GetAccessToken(false, out err);
            if (token == null) { r.Error = err; return r; }

            try
            {
                string body;
                try { body = GetUsage(token); }
                catch (WebException ex)
                {
                    // 期限内でも失効していることがあるので1回だけ更新して再試行
                    var resp = ex.Response as HttpWebResponse;
                    if (resp == null || resp.StatusCode != HttpStatusCode.Unauthorized) throw;
                    token = GetAccessToken(true, out err);
                    if (token == null) { r.Error = err; return r; }
                    body = GetUsage(token);
                }
                r.RawBody = body;
                Parse(body, r);
            }
            catch (WebException ex)
            {
                var resp = ex.Response as HttpWebResponse;
                if (resp != null && resp.StatusCode == HttpStatusCode.Unauthorized)
                    r.Error = "認証エラー（claude で /login してください）";
                else if (resp != null && (int)resp.StatusCode == 429)
                    r.Error = "取得回数の制限中（しばらく待ってください）";
                else if (resp != null)
                    r.Error = "取得失敗: HTTP " + (int)resp.StatusCode;
                else
                    r.Error = "通信エラー: " + ex.Message;
            }
            catch (Exception ex)
            {
                r.Error = "取得失敗: " + ex.Message;
            }
            return r;
        }

        static void Parse(string body, UsageResult r)
        {
            var d = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(body);
            r.FiveHour = ToWindow(d, "five_hour");
            r.Weekly = ToWindow(d, "seven_day");

            // モデル別の週間枠は limits[] に { scope: { model: { display_name } }, percent, resets_at } で入っている
            object lv;
            if (d.TryGetValue("limits", out lv) && lv is System.Collections.ArrayList)
            {
                foreach (var item in (System.Collections.ArrayList)lv)
                {
                    var o = item as Dictionary<string, object>;
                    if (o == null) continue;
                    string name = Path3(o, "scope", "model", "display_name");
                    if (name == null || name.IndexOf("fable", StringComparison.OrdinalIgnoreCase) < 0) continue;
                    var w = new UsageWindow();
                    object pct;
                    if (o.TryGetValue("percent", out pct) && pct != null)
                    {
                        w.Present = true;
                        w.Utilization = Convert.ToDouble(pct, CultureInfo.InvariantCulture);
                    }
                    object reset;
                    if (o.TryGetValue("resets_at", out reset)) w.ResetsAt = ToLocalTime(reset);
                    if (w.Present) { r.WeeklyFable = w; return; }
                }
            }
            // 念のため seven_day_fable のようなキーでも探す
            foreach (var kv in d)
            {
                if (kv.Key.IndexOf("fable", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    var w = ToWindow(d, kv.Key);
                    if (w.Present) { r.WeeklyFable = w; return; }
                }
            }
        }

        static string Path3(Dictionary<string, object> o, string a, string b, string c)
        {
            object v;
            if (!o.TryGetValue(a, out v)) return null;
            var o1 = v as Dictionary<string, object>;
            if (o1 == null || !o1.TryGetValue(b, out v)) return null;
            var o2 = v as Dictionary<string, object>;
            if (o2 == null || !o2.TryGetValue(c, out v) || v == null) return null;
            return Convert.ToString(v);
        }

        // resets_at は ISO 文字列か UNIX 秒
        static DateTime? ToLocalTime(object v)
        {
            if (v == null) return null;
            if (v is int || v is long || v is decimal || v is double)
                return DateTimeOffset.FromUnixTimeSeconds(Convert.ToInt64(v)).LocalDateTime;
            DateTimeOffset dto;
            if (DateTimeOffset.TryParse(Convert.ToString(v), CultureInfo.InvariantCulture, DateTimeStyles.None, out dto))
                return dto.LocalDateTime;
            return null;
        }

        static UsageWindow ToWindow(Dictionary<string, object> d, string key)
        {
            var w = new UsageWindow();
            object v;
            if (!d.TryGetValue(key, out v)) return w;
            var o = v as Dictionary<string, object>;
            if (o == null) return w;
            object u;
            if (o.TryGetValue("utilization", out u) && u != null)
            {
                w.Present = true;
                w.Utilization = Convert.ToDouble(u, CultureInfo.InvariantCulture);
            }
            object reset;
            if (o.TryGetValue("resets_at", out reset)) w.ResetsAt = ToLocalTime(reset);
            return w;
        }
    }

    // ---------- ピーク／オフピーク判定 ----------
    static class PeakClock
    {
        // 戻り値: ピーク中なら true。change は次に状態が切り替わるローカル時刻
        public static bool IsPeak(Settings s, DateTime nowUtc, out DateTime changeLocal)
        {
            TimeZoneInfo tz;
            try { tz = TimeZoneInfo.FindSystemTimeZoneById(s.PeakTimeZone); }
            catch { tz = TimeZoneInfo.Local; }

            TimeSpan start = ParseTime(s.PeakStart, new TimeSpan(5, 0, 0));
            TimeSpan end = ParseTime(s.PeakEnd, new TimeSpan(11, 0, 0));
            bool now = InPeak(s, tz, nowUtc, start, end);

            // 状態が変わる時刻を1分刻みで探す（最大8日先）
            DateTime t = new DateTime(nowUtc.Year, nowUtc.Month, nowUtc.Day, nowUtc.Hour, nowUtc.Minute, 0, DateTimeKind.Utc).AddMinutes(1);
            DateTime limit = nowUtc.AddDays(8);
            changeLocal = DateTime.MaxValue;
            while (t < limit)
            {
                if (InPeak(s, tz, t, start, end) != now) { changeLocal = t.ToLocalTime(); break; }
                t = t.AddMinutes(1);
            }
            return now;
        }

        static bool InPeak(Settings s, TimeZoneInfo tz, DateTime utc, TimeSpan start, TimeSpan end)
        {
            DateTime z = TimeZoneInfo.ConvertTimeFromUtc(utc, tz);
            if (s.PeakWeekdaysOnly && (z.DayOfWeek == DayOfWeek.Saturday || z.DayOfWeek == DayOfWeek.Sunday)) return false;
            TimeSpan tod = z.TimeOfDay;
            if (start <= end) return tod >= start && tod < end;
            return tod >= start || tod < end; // 日付をまたぐ設定
        }

        static TimeSpan ParseTime(string s, TimeSpan fallback)
        {
            TimeSpan t;
            if (TimeSpan.TryParseExact(s ?? "", @"h\:mm", CultureInfo.InvariantCulture, out t)) return t;
            return fallback;
        }
    }

    // ---------- 高DPI対応 ----------
    // DPI 非対応のままだと拡大率 100% 超で Windows がビットマップ拡大してぼやけるため、
    // モニターごとの DPI 対応を宣言し、描画は自前でスケーリングする。
    static class Dpi
    {
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetProcessDpiAwarenessContext(IntPtr value);
        [System.Runtime.InteropServices.DllImport("shcore.dll")]
        static extern int SetProcessDpiAwareness(int value);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern bool SetProcessDPIAware();
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        static extern IntPtr MonitorFromPoint(Point pt, uint flags);
        [System.Runtime.InteropServices.DllImport("shcore.dll")]
        static extern int GetDpiForMonitor(IntPtr hmonitor, int dpiType, out uint dpiX, out uint dpiY);

        public static void EnableAwareness()
        {
            try { if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return; } catch { } // PER_MONITOR_AWARE_V2 (Win10 1703+)
            try { if (SetProcessDpiAwareness(2) == 0) return; } catch { }                // PER_MONITOR_DPI_AWARE (Win8.1+)
            try { SetProcessDPIAware(); } catch { }
        }

        // 指定位置のモニターの拡大率（1.0 = 100%）
        public static float ScaleAt(Point pt)
        {
            try
            {
                uint x, y;
                var mon = MonitorFromPoint(pt, 2); // MONITOR_DEFAULTTONEAREST
                if (GetDpiForMonitor(mon, 0, out x, out y) == 0 && x > 0) return x / 96f;
            }
            catch { }
            using (var g = Graphics.FromHwnd(IntPtr.Zero)) return g.DpiX / 96f;
        }
    }

    // ---------- 表示 ----------
    static class Theme
    {
        public static readonly Color Back = Color.FromArgb(30, 30, 32);
        public static readonly Color Track = Color.FromArgb(58, 58, 62);
        public static readonly Color Text = Color.FromArgb(235, 235, 235);
        public static readonly Color Sub = Color.FromArgb(150, 150, 155);
        public static readonly Color Ok = Color.FromArgb(217, 119, 87);   // Claude 系のオレンジ
        public static readonly Color Warn = Color.FromArgb(230, 180, 60);
        public static readonly Color Danger = Color.FromArgb(225, 80, 80);
        public static readonly Color Peak = Color.FromArgb(225, 95, 80);
        public static readonly Color OffPeak = Color.FromArgb(90, 190, 120);

        public static Color ForPercent(double p)
        {
            if (p >= 90) return Danger;
            if (p >= 70) return Warn;
            return Ok;
        }
    }

    class MeterForm : Form
    {
        readonly Settings settings;
        readonly Timer refreshTimer = new Timer();
        readonly Timer clockTimer = new Timer();
        readonly NotifyIcon tray = new NotifyIcon();
        readonly ToolStripMenuItem topMostItem;
        readonly ToolStripMenuItem startupItem;
        UsageResult last;
        bool fetching;
        Point dragStart;

        // 座標とフォントは 100% 時の値で書き、S() で現在の拡大率に合わせる
        float scale = 1f;
        bool scaleForced;
        Font titleFont, labelFont, pctFont, smallFont;
        const int BaseWidth = 260, BaseHeight = 222;

        int S(float v) { return (int)Math.Round(v * scale); }

        void ApplyScale(float newScale)
        {
            scale = newScale;
            foreach (var f in new[] { titleFont, labelFont, pctFont, smallFont }) if (f != null) f.Dispose();
            // ポイント指定だと GDI がシステム DPI で換算してしまうのでピクセル指定にする
            titleFont = new Font("Yu Gothic UI", 12f * scale, FontStyle.Bold, GraphicsUnit.Pixel);
            labelFont = new Font("Yu Gothic UI", 12f * scale, GraphicsUnit.Pixel);
            pctFont = new Font("Segoe UI", 13.33f * scale, FontStyle.Bold, GraphicsUnit.Pixel);
            smallFont = new Font("Yu Gothic UI", 10.67f * scale, GraphicsUnit.Pixel);
        }

        const int WM_DPICHANGED = 0x02E0;

        protected override void WndProc(ref Message m)
        {
            if (m.Msg == WM_DPICHANGED && !scaleForced)
            {
                int dpi = (int)((long)m.WParam >> 16) & 0xFFFF;
                var rc = (RECT)System.Runtime.InteropServices.Marshal.PtrToStructure(m.LParam, typeof(RECT));
                ApplyScale(dpi / 96f);
                Bounds = new Rectangle(rc.Left, rc.Top, S(BaseWidth), S(BaseHeight));
                Invalidate();
                return;
            }
            base.WndProc(ref m);
        }

        [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
        struct RECT { public int Left, Top, Right, Bottom; }

        const string RunKey = @"Software\Microsoft\Windows\CurrentVersion\Run";
        const string RunName = "ClaudeMeter";

        readonly string snapshotPath;

        // snapshotPath を指定すると1回取得して描画を PNG に保存し終了する（動作確認用）。
        // forcedScale > 0 ならモニターの拡大率の代わりにその倍率で描く。
        public MeterForm(string snapshotPath, float forcedScale)
        {
            this.snapshotPath = snapshotPath;
            settings = Settings.Load();

            Text = "Claude Meter";
            FormBorderStyle = FormBorderStyle.None;
            ShowInTaskbar = false;
            StartPosition = FormStartPosition.Manual;
            BackColor = Theme.Back;
            DoubleBuffered = true;
            AutoScaleMode = AutoScaleMode.None;
            TopMost = settings.TopMost;
            Opacity = settings.Opacity;
            Icon = MakeIcon();

            var wa = Screen.PrimaryScreen.WorkingArea;
            Point pos = new Point(settings.X, settings.Y);
            bool onScreen = false;
            foreach (var sc in Screen.AllScreens)
                if (sc.WorkingArea.Contains(new Rectangle(pos, new Size(40, 40)))) onScreen = true;
            scaleForced = forcedScale > 0;
            ApplyScale(forcedScale > 0 ? forcedScale : Dpi.ScaleAt(onScreen ? pos : new Point(wa.Right - 1, wa.Bottom - 1)));
            ClientSize = new Size(S(BaseWidth), S(BaseHeight));
            Location = onScreen ? pos : new Point(wa.Right - Width - S(16), wa.Bottom - Height - S(16));

            var menu = new ContextMenuStrip();
            menu.Items.Add("今すぐ更新", null, delegate { Refresh_(); });
            topMostItem = new ToolStripMenuItem("常に手前に表示", null, delegate { ToggleTopMost(); });
            topMostItem.Checked = settings.TopMost;
            menu.Items.Add(topMostItem);
            startupItem = new ToolStripMenuItem("Windows 起動時に開始", null, delegate { ToggleStartup(); });
            startupItem.Checked = IsStartupEnabled();
            menu.Items.Add(startupItem);
            menu.Items.Add("表示／非表示", null, delegate { ToggleVisible(); });
            menu.Items.Add("設定ファイルを開く", null, delegate { Settings.OpenInEditor(); });
            menu.Items.Add(new ToolStripSeparator());
            menu.Items.Add("終了", null, delegate { Close(); });
            ContextMenuStrip = menu;

            tray.Icon = Icon;
            tray.Text = "Claude Meter";
            tray.ContextMenuStrip = menu;
            tray.Visible = true;
            tray.MouseClick += delegate(object s, MouseEventArgs e) { if (e.Button == MouseButtons.Left) ToggleVisible(); };

            MouseDown += OnMouseDownDrag;
            MouseMove += OnMouseMoveDrag;
            MouseUp += delegate { SavePosition(); };
            MouseDoubleClick += delegate { Refresh_(); };

            refreshTimer.Interval = settings.RefreshMinutes * 60 * 1000;
            refreshTimer.Tick += delegate { Refresh_(); };
            refreshTimer.Start();

            clockTimer.Interval = 30 * 1000; // 残り時間とピーク表示の更新
            clockTimer.Tick += delegate { Invalidate(); UpdateTrayText(); };
            clockTimer.Start();

            Shown += delegate { Refresh_(); };
        }

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ExStyle |= 0x80; // WS_EX_TOOLWINDOW: Alt+Tab に出さない
                return cp;
            }
        }

        async void Refresh_()
        {
            if (fetching) return;
            fetching = true;
            Invalidate();
            try
            {
                var r = await UsageClient.FetchAsync();
                // 失敗時は前回値を残してエラーだけ差し替える
                if (r.Error != null && last != null && last.Error == null)
                {
                    last.Error = r.Error;
                }
                else last = r;
            }
            finally
            {
                fetching = false;
                Invalidate();
                UpdateTrayText();
                if (snapshotPath != null) SaveSnapshot();
            }
        }

        void SaveSnapshot()
        {
            using (var bmp = new Bitmap(ClientSize.Width, ClientSize.Height))
            {
                DrawToBitmap(bmp, new Rectangle(Point.Empty, ClientSize));
                bmp.Save(snapshotPath, System.Drawing.Imaging.ImageFormat.Png);
            }
            File.WriteAllText(snapshotPath + ".txt", "scale=" + scale + " monitor=" + Dpi.ScaleAt(Location) + " size=" + ClientSize + " " +(last.Error ?? "") + Environment.NewLine + (last.RawBody ?? ""), Encoding.UTF8);
            Close();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            int pad = S(12);
            int w = ClientSize.Width - pad * 2;

            using (var p = new Pen(Color.FromArgb(70, 70, 75), Math.Max(1, S(1))))
                g.DrawRectangle(p, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);

            // ヘッダー
            Draw(g, "Claude Meter", titleFont, Theme.Text, pad, S(8));
            string status = fetching ? "更新中…" : (last != null ? last.FetchedAt.ToString("HH:mm") + " 更新" : "");
            DrawRight(g, status, smallFont, Theme.Sub, pad + w, S(10));

            int y = S(34);
            DrawMeter(g, "5時間制限", last == null ? null : last.FiveHour, pad, y, w); y += S(46);
            DrawMeter(g, "週間制限", last == null ? null : last.Weekly, pad, y, w); y += S(46);
            DrawMeter(g, "週間制限（Fable）", last == null ? null : last.WeeklyFable, pad, y, w); y += S(46);

            // ピーク／オフピーク
            DateTime change;
            bool peak = PeakClock.IsPeak(settings, DateTime.UtcNow, out change);
            Color c = peak ? Theme.Peak : Theme.OffPeak;
            using (var b = new SolidBrush(c)) g.FillEllipse(b, pad, y + S(4), S(10), S(10));
            Draw(g, peak ? "ピークタイム" : "オフピーク", titleFont, c, pad + S(15), y);
            if (change != DateTime.MaxValue)
            {
                string when = (peak ? "終了 " : "開始 ") + FormatWhen(change) + "（" + FormatSpan(change - DateTime.Now) + "）";
                DrawRight(g, when, smallFont, Theme.Sub, pad + w, y + S(2));
            }

            if (last != null && last.Error != null)
            {
                var rect = new RectangleF(pad, ClientSize.Height - S(20), w, S(16));
                using (var b = new SolidBrush(Theme.Warn))
                using (var sf = new StringFormat { Trimming = StringTrimming.EllipsisCharacter, FormatFlags = StringFormatFlags.NoWrap })
                    g.DrawString(last.Error, smallFont, b, rect, sf);
            }
        }

        void DrawMeter(Graphics g, string label, UsageWindow win, int x, int y, int w)
        {
            Draw(g, label, labelFont, Theme.Text, x, y);
            bool has = win != null && win.Present;
            double pct = has ? win.Utilization : 0;
            DrawRight(g, has ? Math.Round(pct).ToString("0") + "%" : "—", pctFont, has ? Theme.ForPercent(pct) : Theme.Sub, x + w, y - S(2));

            int barH = S(7);
            var track = new Rectangle(x, y + S(20), w, barH);
            using (var b = new SolidBrush(Theme.Track)) FillRound(g, b, track);
            if (has && pct > 0)
            {
                int fw = (int)Math.Max(barH, Math.Min(w, w * pct / 100.0));
                using (var b = new SolidBrush(Theme.ForPercent(pct))) FillRound(g, b, new Rectangle(x, y + S(20), fw, barH));
            }

            string sub;
            if (win == null) sub = "";
            else if (!has) sub = "データなし";
            else if (win.ResetsAt.HasValue) sub = "リセット " + FormatWhen(win.ResetsAt.Value) + "（" + FormatSpan(win.ResetsAt.Value - DateTime.Now) + "）";
            else sub = "未使用";
            Draw(g, sub, smallFont, Theme.Sub, x, y + S(29));
        }

        static string FormatWhen(DateTime t)
        {
            var now = DateTime.Now;
            if (t.Date == now.Date) return t.ToString("HH:mm");
            string[] dow = { "日", "月", "火", "水", "木", "金", "土" };
            return t.ToString("M/d") + "(" + dow[(int)t.DayOfWeek] + ") " + t.ToString("HH:mm");
        }

        static string FormatSpan(TimeSpan s)
        {
            if (s.TotalMinutes < 1) return "まもなく";
            if (s.TotalHours < 1) return "あと" + (int)s.TotalMinutes + "分";
            if (s.TotalDays < 1) return "あと" + (int)s.TotalHours + "時間" + s.Minutes + "分";
            return "あと" + (int)s.TotalDays + "日" + s.Hours + "時間";
        }

        void Draw(Graphics g, string s, Font f, Color c, float x, float y)
        {
            TextRenderer.DrawText(g, s, f, new Point((int)x, (int)y), c, TextFormatFlags.NoPadding);
        }

        void DrawRight(Graphics g, string s, Font f, Color c, float right, float y)
        {
            var size = TextRenderer.MeasureText(g, s, f, Size.Empty, TextFormatFlags.NoPadding);
            TextRenderer.DrawText(g, s, f, new Point((int)right - size.Width, (int)y), c, TextFormatFlags.NoPadding);
        }

        static void FillRound(Graphics g, Brush b, Rectangle r)
        {
            int d = r.Height;
            using (var path = new GraphicsPath())
            {
                path.AddArc(r.X, r.Y, d, d, 90, 180);
                path.AddArc(r.Right - d, r.Y, d, d, 270, 180);
                path.CloseFigure();
                g.FillPath(b, path);
            }
        }

        void UpdateTrayText()
        {
            if (last == null) return;
            var sb = new StringBuilder("Claude");
            if (last.FiveHour.Present) sb.Append(" 5h:" + Math.Round(last.FiveHour.Utilization) + "%");
            if (last.Weekly.Present) sb.Append(" 週:" + Math.Round(last.Weekly.Utilization) + "%");
            if (last.WeeklyFable.Present) sb.Append(" Fable:" + Math.Round(last.WeeklyFable.Utilization) + "%");
            string t = sb.ToString();
            tray.Text = t.Length > 63 ? t.Substring(0, 63) : t;
        }

        void OnMouseDownDrag(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left) dragStart = e.Location;
        }

        void OnMouseMoveDrag(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
                Location = new Point(Left + e.X - dragStart.X, Top + e.Y - dragStart.Y);
        }

        void SavePosition()
        {
            settings.X = Left;
            settings.Y = Top;
            settings.Save();
        }

        void ToggleTopMost()
        {
            settings.TopMost = !settings.TopMost;
            TopMost = settings.TopMost;
            topMostItem.Checked = settings.TopMost;
            settings.Save();
        }

        void ToggleVisible()
        {
            if (Visible) Hide();
            else { Show(); Activate(); Refresh_(); }
        }

        // HKCU の Run キーなので管理者権限は不要
        static bool IsStartupEnabled()
        {
            using (var k = Registry.CurrentUser.OpenSubKey(RunKey, false))
                return k != null && k.GetValue(RunName) != null;
        }

        void ToggleStartup()
        {
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RunKey))
                {
                    if (IsStartupEnabled()) k.DeleteValue(RunName, false);
                    else k.SetValue(RunName, "\"" + Application.ExecutablePath + "\"");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("自動起動の設定に失敗しました: " + ex.Message, "Claude Meter");
            }
            startupItem.Checked = IsStartupEnabled();
        }

        static Icon MakeIcon()
        {
            using (var bmp = new Bitmap(32, 32))
            {
                using (var g = Graphics.FromImage(bmp))
                {
                    g.SmoothingMode = SmoothingMode.AntiAlias;
                    using (var b = new SolidBrush(Theme.Ok)) g.FillEllipse(b, 1, 1, 30, 30);
                    using (var p = new Pen(Color.White, 4f))
                    {
                        p.StartCap = LineCap.Round; p.EndCap = LineCap.Round;
                        g.DrawArc(p, 8, 8, 16, 16, 135, 270);
                        g.DrawLine(p, 16, 16, 22, 11);
                    }
                }
                return Icon.FromHandle(bmp.GetHicon());
            }
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            SavePosition();
            tray.Visible = false;
            tray.Dispose();
            base.OnFormClosing(e);
        }
    }
}
