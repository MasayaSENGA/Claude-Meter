# Claude Meter - Claude の利用制限の使用状況を常時表示する小さなウィンドウ（Python 版）
# 標準ライブラリ（tkinter + ctypes）だけで動く。署名済みの pythonw.exe で実行するので、
# 自作 exe を止める Smart App Control をオンにしたままでも起動できる。
import ctypes
import ctypes.wintypes as wt
import datetime as dt
import json
import math
import os
import queue
import re
import shutil
import struct
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.error
import urllib.request
import winreg
import zlib
from tkinter import messagebox, ttk

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(APP_DIR, "src", "app.ico")
UTC = dt.timezone.utc

# ---------- Win32 API ----------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore")
except OSError:
    shcore = None

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", RECT), ("rcWork", RECT), ("dwFlags", wt.DWORD)]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wt.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT), ("uFlags", wt.UINT),
                ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON), ("szTip", wt.WCHAR * 128),
                ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD), ("szInfo", wt.WCHAR * 256),
                ("uVersion", wt.UINT), ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


def _proto(fn, restype, *argtypes):
    fn.restype = restype
    fn.argtypes = argtypes


_proto(user32.MonitorFromPoint, ctypes.c_void_p, wt.POINT, wt.DWORD)
_proto(user32.GetMonitorInfoW, wt.BOOL, ctypes.c_void_p, ctypes.POINTER(MONITORINFO))
_proto(user32.GetWindowRect, wt.BOOL, wt.HWND, ctypes.POINTER(RECT))
_proto(user32.RegisterClassW, wt.ATOM, ctypes.POINTER(WNDCLASSW))
_proto(user32.CreateWindowExW, wt.HWND, wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD, ctypes.c_int, ctypes.c_int,
       ctypes.c_int, ctypes.c_int, wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID)
_proto(user32.DefWindowProcW, LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_proto(user32.GetMessageW, wt.BOOL, ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT)
_proto(user32.TranslateMessage, wt.BOOL, ctypes.POINTER(wt.MSG))
_proto(user32.DispatchMessageW, LRESULT, ctypes.POINTER(wt.MSG))
_proto(user32.RegisterWindowMessageW, wt.UINT, wt.LPCWSTR)
_proto(user32.CreatePopupMenu, wt.HMENU)
_proto(user32.AppendMenuW, wt.BOOL, wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR)
_proto(user32.TrackPopupMenu, ctypes.c_int, wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HWND,
       ctypes.c_void_p)
_proto(user32.DestroyMenu, wt.BOOL, wt.HMENU)
_proto(user32.GetCursorPos, wt.BOOL, ctypes.POINTER(wt.POINT))
_proto(user32.SetForegroundWindow, wt.BOOL, wt.HWND)
_proto(user32.PostMessageW, wt.BOOL, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_proto(user32.LoadImageW, wt.HANDLE, wt.HINSTANCE, wt.LPCWSTR, wt.UINT, ctypes.c_int, ctypes.c_int, wt.UINT)
_proto(user32.LoadIconW, wt.HICON, wt.HINSTANCE, ctypes.c_void_p)
_proto(user32.GetSystemMetrics, ctypes.c_int, ctypes.c_int)
_proto(user32.GetDC, wt.HDC, wt.HWND)
_proto(user32.ReleaseDC, ctypes.c_int, wt.HWND, wt.HDC)
_proto(shell32.Shell_NotifyIconW, wt.BOOL, wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_proto(kernel32.CreateMutexW, wt.HANDLE, wt.LPVOID, wt.BOOL, wt.LPCWSTR)
_proto(kernel32.GetModuleHandleW, wt.HMODULE, wt.LPCWSTR)
_proto(gdi32.CreateCompatibleDC, wt.HDC, wt.HDC)
_proto(gdi32.CreateCompatibleBitmap, wt.HBITMAP, wt.HDC, ctypes.c_int, ctypes.c_int)
_proto(gdi32.SelectObject, wt.HGDIOBJ, wt.HDC, wt.HGDIOBJ)
_proto(gdi32.BitBlt, wt.BOOL, wt.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.HDC, ctypes.c_int,
       ctypes.c_int, wt.DWORD)
_proto(gdi32.GetDIBits, ctypes.c_int, wt.HDC, wt.HBITMAP, wt.UINT, wt.UINT, ctypes.c_void_p, ctypes.c_void_p, wt.UINT)
_proto(gdi32.DeleteObject, wt.BOOL, wt.HGDIOBJ)
_proto(gdi32.DeleteDC, wt.BOOL, wt.HDC)
_proto(advapi32.RegLoadMUIStringW, wt.LONG, ctypes.c_void_p, wt.LPCWSTR, wt.LPWSTR, wt.DWORD, ctypes.c_void_p,
       wt.DWORD, wt.LPCWSTR)
if shcore is not None:
    _proto(shcore.GetDpiForMonitor, ctypes.c_long, ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(wt.UINT),
           ctypes.POINTER(wt.UINT))


# ---------- 設定 ----------
def to_bool(v):
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return bool(v)


class Settings:
    DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ClaudeMeter")
    FILE = os.path.join(DIR, "settings.json")

    def __init__(self):
        self.refresh_minutes = 5
        self.peak_time_zone = "Pacific Standard Time"
        self.peak_start = "05:00"
        self.peak_end = "11:00"
        self.peak_weekdays_only = True
        self.top_most = True
        self.opacity = 0.95
        self.style = "bar"  # "bar" または "gauge"（スピードメーター）
        self.gauge_vertical = False  # スピードメーターを縦に並べる
        self.show_fable = True  # Fable を使えないプランでは非表示にできる
        self.gauge_sweep = True  # スピードメーター表示で起動時に針をスイープさせる
        self.x = -1
        self.y = -1

    # exe 版と同じファイル・同じキーを使うので設定はそのまま引き継がれる
    @classmethod
    def load(cls):
        s = cls()
        try:
            if os.path.exists(cls.FILE):
                with open(cls.FILE, encoding="utf-8-sig") as f:
                    d = json.load(f)
                if "refreshMinutes" in d: s.refresh_minutes = max(1, int(d["refreshMinutes"]))
                if "peakTimeZone" in d: s.peak_time_zone = str(d["peakTimeZone"])
                if "peakStart" in d: s.peak_start = str(d["peakStart"])
                if "peakEnd" in d: s.peak_end = str(d["peakEnd"])
                if "peakWeekdaysOnly" in d: s.peak_weekdays_only = to_bool(d["peakWeekdaysOnly"])
                if "topMost" in d: s.top_most = to_bool(d["topMost"])
                if "style" in d: s.style = "gauge" if str(d["style"]) == "gauge" else "bar"
                if "gaugeVertical" in d: s.gauge_vertical = to_bool(d["gaugeVertical"])
                if "showFable" in d: s.show_fable = to_bool(d["showFable"])
                if "gaugeSweep" in d: s.gauge_sweep = to_bool(d["gaugeSweep"])
                if "opacity" in d: s.opacity = min(1.0, max(0.3, float(d["opacity"])))
                if "x" in d: s.x = int(d["x"])
                if "y" in d: s.y = int(d["y"])
        except Exception:
            pass
        s.save()
        return s

    def save(self):
        try:
            os.makedirs(self.DIR, exist_ok=True)
            d = {
                "refreshMinutes": self.refresh_minutes,
                "peakTimeZone": self.peak_time_zone,
                "peakStart": self.peak_start,
                "peakEnd": self.peak_end,
                "peakWeekdaysOnly": self.peak_weekdays_only,
                "style": self.style,
                "gaugeVertical": self.gauge_vertical,
                "showFable": self.show_fable,
                "gaugeSweep": self.gauge_sweep,
                "topMost": self.top_most,
                "opacity": self.opacity,
                "x": self.x,
                "y": self.y,
            }
            # 手編集しやすいよう1項目1行にする
            with open(self.FILE, "w", encoding="utf-8", newline="\r\n") as f:
                f.write(json.dumps(d, indent=2, ensure_ascii=False))
        except Exception:
            pass


# ---------- 使用状況の取得 ----------
class UsageWindow:
    def __init__(self):
        self.present = False
        self.utilization = 0.0  # 0-100
        self.resets_at = None  # ローカル時刻（naive）


class UsageResult:
    def __init__(self):
        self.five_hour = UsageWindow()
        self.weekly = UsageWindow()
        self.weekly_fable = UsageWindow()
        self.error = None
        self.raw_body = None
        self.fetched_at = dt.datetime.now()


class UsageClient:
    ENDPOINT = "https://api.anthropic.com/api/oauth/usage"
    TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
    CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # Claude Code の公開クライアントID
    USER_AGENT = "ClaudeMeter/1.0"
    _cred_lock = threading.Lock()

    @staticmethod
    def credentials_path():
        d = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        return os.path.join(d, ".credentials.json")

    @classmethod
    def _read_credentials(cls):
        """(全体, claudeAiOauth, エラー) を返す"""
        path = cls.credentials_path()
        if not os.path.exists(path):
            return None, None, "Claude Code のログイン情報が見つかりません（claude で /login してください）"
        try:
            with open(path, encoding="utf-8-sig") as f:
                d = json.load(f)
            oauth = d.get("claudeAiOauth")
            if not isinstance(oauth, dict) or "accessToken" not in oauth:
                return None, None, "ログイン情報にアクセストークンがありません（claude で /login してください）"
            return d, oauth, None
        except Exception as ex:
            return None, None, "ログイン情報を読めません: " + str(ex)

    # 毎回ファイルを読み直し、期限切れ（または force）ならリフレッシュして書き戻す。
    # 書き戻すことで Claude Code CLI 側も新しいトークンをそのまま使える。
    @classmethod
    def _get_access_token(cls, force):
        """(トークン, エラー) を返す"""
        with cls._cred_lock:
            all_, oauth, err = cls._read_credentials()
            if all_ is None:
                return None, err

            expires_at = int(oauth.get("expiresAt") or 0)
            now_ms = int(time.time() * 1000)
            if not force and expires_at > now_ms + 60000:
                return str(oauth["accessToken"]), None

            rt = oauth.get("refreshToken")
            if not rt:
                return None, "トークンの期限切れ（claude で /login してください）"
            try:
                body = {"grant_type": "refresh_token", "refresh_token": str(rt), "client_id": cls.CLIENT_ID}
                scopes = oauth.get("scopes")
                if isinstance(scopes, list) and scopes:
                    body["scope"] = " ".join(str(s) for s in scopes)
                res = json.loads(cls._request(cls.TOKEN_URL, data=json.dumps(body).encode("utf-8"),
                                              headers={"Content-Type": "application/json"}, timeout=30))
                at = res.get("access_token")
                if not at:
                    return None, "トークン更新に失敗（claude で /login してください）"
                oauth["accessToken"] = str(at)
                if res.get("refresh_token"):
                    oauth["refreshToken"] = str(res["refresh_token"])
                if res.get("expires_in") is not None:
                    oauth["expiresAt"] = now_ms + int(res["expires_in"]) * 1000
                if res.get("refresh_token_expires_in") is not None:
                    oauth["refreshTokenExpiresAt"] = now_ms + int(res["refresh_token_expires_in"]) * 1000
                cls._write_credentials(all_)
                return str(at), None
            except urllib.error.HTTPError as ex:
                if ex.code in (400, 401):
                    return None, "ログインの有効期限切れ（claude で /login してください）"
                return None, "トークン更新の通信エラー: " + str(ex)
            except urllib.error.URLError as ex:
                return None, "トークン更新の通信エラー: " + str(ex.reason)
            except Exception as ex:
                return None, "トークン更新に失敗: " + str(ex)

    @classmethod
    def _write_credentials(cls, all_):
        path = cls.credentials_path()
        tmp = path + ".claudemeter.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(all_, ensure_ascii=False, separators=(",", ":")))
            shutil.copyfile(tmp, path)
        finally:
            # トークンを含む一時ファイルを失敗時にも残さない
            try:
                os.remove(tmp)
            except OSError:
                pass

    @classmethod
    def _request(cls, url, data=None, headers=None, timeout=15):
        h = {"Accept": "application/json", "User-Agent": cls.USER_AGENT}
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")

    @classmethod
    def _get_usage(cls, token):
        return cls._request(cls.ENDPOINT, headers={"Authorization": "Bearer " + token,
                                                   "anthropic-beta": "oauth-2025-04-20"})

    @classmethod
    def fetch(cls):
        r = UsageResult()
        token, err = cls._get_access_token(False)
        if token is None:
            r.error = err
            return r
        try:
            try:
                body = cls._get_usage(token)
            except urllib.error.HTTPError as ex:
                # 期限内でも失効していることがあるので1回だけ更新して再試行
                if ex.code != 401:
                    raise
                token, err = cls._get_access_token(True)
                if token is None:
                    r.error = err
                    return r
                body = cls._get_usage(token)
            r.raw_body = body
            cls._parse(body, r)
        except urllib.error.HTTPError as ex:
            if ex.code == 401:
                r.error = "認証エラー（claude で /login してください）"
            elif ex.code == 429:
                r.error = "取得回数の制限中（しばらく待ってください）"
            else:
                r.error = "取得失敗: HTTP %d" % ex.code
        except urllib.error.URLError as ex:
            r.error = "通信エラー: " + str(ex.reason)
        except Exception as ex:
            r.error = "取得失敗: " + str(ex)
        return r

    @classmethod
    def _parse(cls, body, r):
        d = json.loads(body)
        r.five_hour = cls._to_window(d, "five_hour")
        r.weekly = cls._to_window(d, "seven_day")

        # モデル別の週間枠は limits[] に { scope: { model: { display_name } }, percent, resets_at } で入っている
        limits = d.get("limits")
        if isinstance(limits, list):
            for o in limits:
                if not isinstance(o, dict):
                    continue
                name = dig(o, "scope", "model", "display_name")
                if name is None or "fable" not in str(name).lower():
                    continue
                w = UsageWindow()
                if o.get("percent") is not None:
                    w.present = True
                    w.utilization = float(o["percent"])
                if "resets_at" in o:
                    w.resets_at = to_local_time(o["resets_at"])
                if w.present:
                    r.weekly_fable = w
                    return
        # 念のため seven_day_fable のようなキーでも探す
        for key in d:
            if "fable" in key.lower():
                w = cls._to_window(d, key)
                if w.present:
                    r.weekly_fable = w
                    return

    @staticmethod
    def _to_window(d, key):
        w = UsageWindow()
        o = d.get(key)
        if not isinstance(o, dict):
            return w
        if o.get("utilization") is not None:
            w.present = True
            w.utilization = float(o["utilization"])
        if "resets_at" in o:
            w.resets_at = to_local_time(o["resets_at"])
        return w


def dig(o, *keys):
    for k in keys:
        if not isinstance(o, dict) or o.get(k) is None:
            return None
        o = o[k]
    return o


# resets_at は ISO 文字列か UNIX 秒
def to_local_time(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return dt.datetime.fromtimestamp(v)
    try:
        s = str(v).strip()
        if s.endswith(("Z", "z")):
            s = s[:-1] + "+00:00"
        # 古い Python の fromisoformat は小数秒が3桁か6桁でないと読めない
        s = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), s)
        t = dt.datetime.fromisoformat(s)
        return t if t.tzinfo is None else t.astimezone().replace(tzinfo=None)
    except ValueError:
        return None


def utc_to_machine(u):
    """naive UTC → この PC のローカル時刻（naive）"""
    return u.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


def utc_now():
    return dt.datetime.now(UTC).replace(tzinfo=None)


# ---------- タイムゾーン ----------
# exe 版の設定と互換にするため、Windows のタイムゾーン ID（"Pacific Standard Time" など）を
# レジストリの定義からそのまま使う（zoneinfo は Windows では tzdata の追加が要るため使わない）。
TZ_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Time Zones"


def _mui_string(key, name):
    try:
        buf = ctypes.create_unicode_buffer(512)
        if advapi32.RegLoadMUIStringW(key.handle, name, buf, ctypes.sizeof(buf), None, 0, None) == 0:
            return buf.value
    except Exception:
        pass
    return None


def _parse_tzi(b):
    bias, std_bias, dlt_bias = struct.unpack_from("<3l", b, 0)
    return bias, std_bias, dlt_bias, struct.unpack_from("<8H", b, 12), struct.unpack_from("<8H", b, 28)


class WinZone:
    def __init__(self, zid):
        self.id = zid
        self._dynamic = {}
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TZ_KEY + "\\" + zid) as k:
            self.display = _mui_string(k, "MUI_Display") or winreg.QueryValueEx(k, "Display")[0]
            self._tzi = _parse_tzi(winreg.QueryValueEx(k, "TZI")[0])
            try:
                with winreg.OpenKey(k, "Dynamic DST") as d:
                    first = winreg.QueryValueEx(d, "FirstEntry")[0]
                    last = winreg.QueryValueEx(d, "LastEntry")[0]
                    for y in range(first, last + 1):
                        try:
                            self._dynamic[y] = _parse_tzi(winreg.QueryValueEx(d, str(y))[0])
                        except OSError:
                            pass
            except OSError:
                pass
        if self._dynamic:
            self._first, self._last = min(self._dynamic), max(self._dynamic)
        self._years = {}

    @property
    def base_bias(self):
        return self._rule(dt.date.today().year)[0]

    def _rule(self, year):
        # 年ごとの定義（Dynamic DST）があれば使い、範囲外の年は端の年の定義を使う
        if not self._dynamic:
            return self._tzi
        return self._dynamic.get(min(max(year, self._first), self._last), self._tzi)

    @staticmethod
    def _transition(year, st):
        w_year, month, dow, day, hour, minute, sec, ms = st
        if w_year != 0:
            base = dt.datetime(year, month, day)
        else:
            # day 番目（5 は最終）の dow 曜日（0 = 日曜）
            first = dt.date(year, month, 1)
            d = 1 + (dow - (first.weekday() + 1) % 7) % 7 + (day - 1) * 7
            nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
            while d > (nxt - first).days:
                d -= 7
            base = dt.datetime(year, month, d)
        return base + dt.timedelta(hours=hour, minutes=minute, seconds=sec, milliseconds=ms)

    def _year(self, year):
        """(bias, std_bias, dlt_bias, 夏時間開始 UTC, 夏時間終了 UTC)。夏時間なしなら開始・終了は None"""
        c = self._years.get(year)
        if c is None:
            bias, sb, db, std, dlt = self._rule(year)
            if std[1] == 0 or dlt[1] == 0:
                c = (bias, sb, db, None, None)
            else:
                start = self._transition(year, dlt) + dt.timedelta(minutes=bias + sb)
                end = self._transition(year, std) + dt.timedelta(minutes=bias + db)
                c = (bias, sb, db, start, end)
            self._years[year] = c
        return c

    def to_local(self, u):
        """naive UTC → このゾーンの時刻（naive）"""
        bias, sb, db, start, end = self._year((u - dt.timedelta(minutes=self._rule(u.year)[0])).year)
        if start is None:
            dst = False
        elif start < end:
            dst = start <= u < end
        else:
            dst = not (end <= u < start)
        return u - dt.timedelta(minutes=bias + (db if dst else sb))

    def to_utc(self, local):
        """このゾーンの時刻（naive）→ naive UTC。重複する時刻は標準時、欠けた時刻は1時間後として扱う"""
        bias, sb, db, _, _ = self._year(local.year)
        for off in (bias + sb, bias + db):
            u = local + dt.timedelta(minutes=off)
            if self.to_local(u) == local:
                return u
        return self.to_utc(local + dt.timedelta(hours=1))


class LocalZone:
    """タイムゾーン定義を読めないときの代わり（この PC の時刻）"""
    id = ""
    display = "この PC のタイムゾーン"
    base_bias = 0

    @staticmethod
    def to_local(u):
        return utc_to_machine(u)

    @staticmethod
    def to_utc(local):
        return local.astimezone(UTC).replace(tzinfo=None)


def find_zone(zid):
    try:
        return WinZone(zid)
    except OSError:
        return LocalZone()


def system_zones():
    zones = []
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TZ_KEY) as k:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(k, i)
            except OSError:
                break
            i += 1
            try:
                zones.append(WinZone(name))
            except OSError:
                pass
    zones.sort(key=lambda z: (-z.base_bias, z.display))
    return zones


# ---------- ピーク／オフピーク判定 ----------
def parse_hm(s, fallback):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s or "")
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        return int(m.group(1)) * 60 + int(m.group(2))
    return fallback


class PeakClock:
    # 切り替わり時刻の探索は重いので、次の切り替わりまでは結果を使い回す
    def __init__(self):
        self._key = None
        self._valid_until = None
        self._result = None

    def is_peak(self, s, now_utc):
        """(ピーク中か, 次に状態が切り替わるこの PC の時刻 または None)"""
        key = (s.peak_time_zone, s.peak_start, s.peak_end, s.peak_weekdays_only)
        if key == self._key and self._valid_until is not None and now_utc < self._valid_until:
            return self._result
        zone = find_zone(s.peak_time_zone)
        start = parse_hm(s.peak_start, 5 * 60)
        end = parse_hm(s.peak_end, 11 * 60)
        now = self._in_peak(s, zone, now_utc, start, end)

        # 状態が変わる時刻を1分刻みで探す（最大8日先）
        t = now_utc.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
        limit = now_utc + dt.timedelta(days=8)
        change = None
        while t < limit:
            if self._in_peak(s, zone, t, start, end) != now:
                change = t
                break
            t += dt.timedelta(minutes=1)
        self._key = key
        self._valid_until = change or now_utc + dt.timedelta(hours=1)
        self._result = (now, utc_to_machine(change) if change else None)
        return self._result

    @staticmethod
    def _in_peak(s, zone, u, start, end):
        z = zone.to_local(u)
        if s.peak_weekdays_only and z.weekday() >= 5:
            return False
        tod = z.hour * 60 + z.minute
        if start <= end:
            return start <= tod < end
        return tod >= start or tod < end  # 日付をまたぐ設定


# ---------- 高DPI対応 ----------
# DPI 非対応のままだと拡大率 100% 超で Windows がビットマップ拡大してぼやけるため、
# モニターごとの DPI 対応を宣言し、描画は自前でスケーリングする。
def enable_dpi_awareness():
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # PER_MONITOR_AWARE_V2
            return
    except Exception:
        pass
    try:
        if shcore is not None and shcore.SetProcessDpiAwareness(2) == 0:  # PER_MONITOR_DPI_AWARE
            return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def _monitor(x, y, flags=2):  # MONITOR_DEFAULTTONEAREST
    return user32.MonitorFromPoint(wt.POINT(int(x), int(y)), flags)


def scale_at(x, y):
    """指定位置のモニターの拡大率（1.0 = 100%）"""
    try:
        dx, dy = wt.UINT(), wt.UINT()
        if shcore is not None and shcore.GetDpiForMonitor(_monitor(x, y), 0, ctypes.byref(dx), ctypes.byref(dy)) == 0 \
                and dx.value > 0:
            return dx.value / 96.0
    except Exception:
        pass
    return 1.0


def work_area(x, y, flags=2):
    """(left, top, right, bottom)"""
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(_monitor(x, y, flags), ctypes.byref(mi))
    r = mi.rcWork
    return r.left, r.top, r.right, r.bottom


def primary_work_area():
    return work_area(0, 0, 1)  # MONITOR_DEFAULTTOPRIMARY


def is_on_screen(x, y):
    if not _monitor(x, y, 0):  # MONITOR_DEFAULTTONULL
        return False
    l, t, r, b = work_area(x, y)
    return l <= x and t <= y and x + 40 <= r and y + 40 <= b


def window_rect(hwnd):
    rc = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top


# ---------- タスクトレイ・メニュー ----------
MF_STRING, MF_CHECKED, MF_SEPARATOR = 0x0, 0x8, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x2, 0x100


def popup_menu(owner, items):
    """ネイティブのメニューをカーソル位置に出し、選ばれた項目の ID（なければ 0）を返す。
    表示先モニターの拡大率に合わせて Windows が描く。items は (ID, 文字, チェック) か None（区切り線）"""
    menu = user32.CreatePopupMenu()
    try:
        for item in items:
            if item is None:
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            else:
                cmd, text, checked = item
                user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if checked else 0), cmd, text)
        pt = wt.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(owner)  # これがないとメニューの外をクリックしても閉じない
        cmd = user32.TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, pt.x, pt.y, 0, owner, None)
        user32.PostMessageW(owner, 0, 0, 0)  # WM_NULL
        return cmd
    finally:
        user32.DestroyMenu(menu)


def load_icon(size_metric):
    size = user32.GetSystemMetrics(size_metric)
    h = None
    if os.path.exists(ICON_PATH):
        h = user32.LoadImageW(None, ICON_PATH, 1, size, size, 0x10)  # IMAGE_ICON, LR_LOADFROMFILE
    return h or user32.LoadIconW(None, ctypes.c_void_p(32512))  # IDI_APPLICATION


class TrayIcon:
    """タスクトレイのアイコン。専用スレッドで隠しウィンドウとメッセージループを持つ。
    on_left / on_right はそのスレッドから呼ばれる（on_right には隠しウィンドウのハンドルを渡す）"""
    WM_TRAY = 0x8001  # WM_APP + 1
    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4

    def __init__(self, tip, on_left, on_right):
        self._tip = tip
        self._on_left = on_left
        self._on_right = on_right
        self.hwnd = None
        self._icon = load_icon(49)  # SM_CXSMICON
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(5)

    def _data(self, flags):
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = flags
        nid.uCallbackMessage = self.WM_TRAY
        nid.hIcon = self._icon
        nid.szTip = self._tip[:127]
        return nid

    def _add(self):
        nid = self._data(self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP)
        shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(nid))

    def _run(self):
        self._proc = WNDPROC(self._wndproc)  # GC されないよう保持する
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "ClaudeMeterTray"
        user32.RegisterClassW(ctypes.byref(wc))
        # エクスプローラーが再起動したらアイコンを登録し直す（ウィンドウ作成中にも _wndproc が呼ばれるので先に用意する）
        self._taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hwnd = user32.CreateWindowExW(0, "ClaudeMeterTray", "Claude Meter", 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        self._add()
        self._ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            event = lparam & 0xFFFF
            if event == 0x0202:  # WM_LBUTTONUP
                self._on_left()
            elif event == 0x0205:  # WM_RBUTTONUP
                self._on_right(hwnd)
            return 0
        if msg == self._taskbar_created:
            self._add()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def set_tip(self, tip):
        self._tip = tip
        if self.hwnd:
            nid = self._data(self.NIF_TIP)
            shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(nid))

    def remove(self):
        if self.hwnd:
            nid = self._data(0)
            shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(nid))


# ---------- 自動起動 ----------
# HKCU の Run キーなので管理者権限は不要
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "ClaudeMeter"
SCRIPT_PATH = os.path.abspath(__file__)


def startup_command():
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")  # コンソール窓を出さない
    if os.path.exists(pyw):
        exe = pyw
    return '"%s" "%s"' % (exe, SCRIPT_PATH)


def is_startup_enabled():
    # exe 版が登録した値（同じ名前）は、このスクリプトを起動しないので未登録として扱う
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            value = winreg.QueryValueEx(k, RUN_NAME)[0]
        return SCRIPT_PATH.lower() in str(value).lower()
    except OSError:
        return False


def is_store_python():
    # Microsoft Store 版の Python はレジストリへの書き込みが自分専用の領域に振り向けられ、Run キーに登録できない
    return "\\windowsapps\\" in sys.executable.lower()


def set_startup(enable):
    if enable and is_store_python():
        messagebox.showwarning("Claude Meter", "Microsoft Store 版の Python では「Windows 起動時に開始」を使えません。\n"
                                               "python.org のインストーラーで入れた Python で起動してください。")
        return
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if enable:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
    except OSError as ex:
        messagebox.showerror("Claude Meter", "自動起動の設定に失敗しました: " + str(ex))


# ---------- 動作確認用の画面保存 ----------
def capture_png(path, x, y, w, h):
    """画面の指定範囲を PNG に保存する"""
    screen = user32.GetDC(None)
    mem = gdi32.CreateCompatibleDC(screen)
    bmp = gdi32.CreateCompatibleBitmap(screen, w, h)
    old = gdi32.SelectObject(mem, bmp)
    try:
        gdi32.BitBlt(mem, 0, 0, w, h, screen, x, y, 0x00CC0020)  # SRCCOPY
        bi = BITMAPINFOHEADER()
        bi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.biWidth, bi.biHeight, bi.biPlanes, bi.biBitCount = w, -h, 1, 32
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    finally:
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)
    raw = buf.raw
    rgb = bytearray(w * h * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = raw[2::4], raw[1::4], raw[0::4]
    stride = w * 3
    data = b"".join(b"\x00" + bytes(rgb[i * stride:(i + 1) * stride]) for i in range(h))

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(data, 9)) + chunk(b"IEND", b""))


# ---------- 設定画面 ----------
class TimeInput(ttk.Frame):
    """HH:MM を時・分のスピンボックスで入力する"""

    def __init__(self, master, font, on_change):
        super().__init__(master)
        self.hour = tk.StringVar()
        self.minute = tk.StringVar()
        ttk.Spinbox(self, from_=0, to=23, wrap=True, width=3, format="%02.0f", font=font,
                    textvariable=self.hour).pack(side="left")
        ttk.Label(self, text=":").pack(side="left")
        ttk.Spinbox(self, from_=0, to=59, wrap=True, width=3, format="%02.0f", font=font,
                    textvariable=self.minute).pack(side="left")
        self.hour.trace_add("write", lambda *_: on_change())
        self.minute.trace_add("write", lambda *_: on_change())

    @staticmethod
    def _num(var, hi):
        try:
            return min(hi, max(0, int(float(var.get()))))
        except ValueError:
            return 0

    def get(self):
        return "%02d:%02d" % (self._num(self.hour, 23), self._num(self.minute, 59))

    def set(self, hm):
        m = parse_hm(hm, 0)
        self.hour.set("%02d" % (m // 60))
        self.minute.set("%02d" % (m % 60))


class SettingsDialog(tk.Toplevel):
    # 表示先モニターの拡大率でフォントと寸法を決める（tk の自動スケールはシステム DPI 基準のため）
    def __init__(self, master, s, startup_enabled, anchor, on_done):
        super().__init__(master)
        self.withdraw()
        self.title("Claude Meter の設定")
        self.resizable(False, False)
        self.attributes("-topmost", True)  # 常に手前のメーターの裏に隠れないように
        self.ok = False
        self._on_done = on_done
        self._building = True

        wa = work_area(*anchor)
        self.scale = scale_at((wa[0] + wa[2]) // 2, (wa[1] + wa[3]) // 2)
        self.font = tkfont.Font(self, family="Yu Gothic UI", size=-self.S(12))
        self.bold = tkfont.Font(self, family="Yu Gothic UI", size=-self.S(12), weight="bold")
        style = ttk.Style(self)
        style.configure("CM.TLabel", font=self.font)
        style.configure("CMBold.TLabel", font=self.bold)
        style.configure("CMGray.TLabel", font=self.font, foreground="gray40")
        style.configure("CM.TCheckbutton", font=self.font)
        style.configure("CM.TRadiobutton", font=self.font)
        style.configure("CM.TButton", font=self.font)
        self.option_add("*TCombobox*Listbox.font", self.font)

        self.zones = system_zones()
        self._build()
        self._load(s, startup_enabled)
        self._building = False
        self._update_local_peak()

        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry("+%d+%d" % (wa[0] + max(0, (wa[2] - wa[0] - w) // 2), wa[1] + max(0, (wa[3] - wa[1] - h) // 2)))
        self.deiconify()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.grab_set()
        self.focus_force()

    def S(self, v):
        return int(round(v * self.scale))

    def _build(self):
        S = self.S
        f = ttk.Frame(self, padding=S(12))
        f.pack(fill="both", expand=True)
        self._row = 0

        def section(title):
            ttk.Label(f, text=title, style="CMBold.TLabel").grid(
                row=self._row, column=0, columnspan=2, sticky="w", pady=(0 if self._row == 0 else S(12), S(4)))
            self._row += 1

        def row(label, widget):
            ttk.Label(f, text=label, style="CM.TLabel").grid(row=self._row, column=0, sticky="w",
                                                              padx=(S(12), S(12)), pady=S(3))
            widget.grid(row=self._row, column=1, sticky="w", pady=S(3))
            self._row += 1

        def flow(*widgets_fn):
            p = ttk.Frame(f)
            for fn in widgets_fn:
                fn(p).pack(side="left", padx=(0, S(6)))
            return p

        def check(text, var):
            return ttk.Checkbutton(f, text=text, variable=var, style="CM.TCheckbutton")

        self.refresh = tk.StringVar()
        self.tz_box = ttk.Combobox(f, state="readonly", width=56, font=self.font,
                                   values=[z.display for z in self.zones])
        self.weekdays_only = tk.BooleanVar()
        self.style_var = tk.StringVar()
        self.layout_var = tk.StringVar()
        self.gauge_sweep = tk.BooleanVar()
        self.show_fable = tk.BooleanVar()
        self.top_most = tk.BooleanVar()
        self.opacity = tk.DoubleVar()
        self.startup = tk.BooleanVar()

        section("更新")
        row("更新間隔", flow(
            lambda p: ttk.Spinbox(p, from_=1, to=60, width=4, font=self.font, textvariable=self.refresh),
            lambda p: ttk.Label(p, text="分ごと", style="CM.TLabel")))

        section("ピークタイム")
        row("基準タイムゾーン", self.tz_box)
        times = ttk.Frame(f)
        self.peak_start = TimeInput(times, self.font, self._update_local_peak)
        self.peak_start.pack(side="left")
        ttk.Label(times, text=" 〜 ", style="CM.TLabel").pack(side="left")
        self.peak_end = TimeInput(times, self.font, self._update_local_peak)
        self.peak_end.pack(side="left")
        row("時間帯", times)
        row("", check("平日のみ（土日はオフピーク）", self.weekdays_only))
        self.local_peak = ttk.Label(f, style="CMGray.TLabel")
        row("", self.local_peak)

        section("表示")
        row("表示形式", flow(
            lambda p: ttk.Radiobutton(p, text="バー", value="bar", variable=self.style_var, style="CM.TRadiobutton"),
            lambda p: ttk.Radiobutton(p, text="スピードメーター", value="gauge", variable=self.style_var,
                                      style="CM.TRadiobutton")))
        layout = ttk.Frame(f)
        self.layout_h = ttk.Radiobutton(layout, text="横並び", value="h", variable=self.layout_var,
                                        style="CM.TRadiobutton")
        self.layout_v = ttk.Radiobutton(layout, text="縦並び", value="v", variable=self.layout_var,
                                        style="CM.TRadiobutton")
        self.layout_h.pack(side="left", padx=(0, S(6)))
        self.layout_v.pack(side="left")
        row("メーターの並び", layout)
        self.sweep_check = check("起動時に針を最大まで振り切る（スイープ）", self.gauge_sweep)
        row("", self.sweep_check)
        row("", check("週間制限（Fable）を表示", self.show_fable))
        row("", check("常に手前に表示", self.top_most))
        op = ttk.Frame(f)
        ttk.Scale(op, from_=30, to=100, length=S(200), variable=self.opacity,
                  command=lambda v: self._update_opacity_label()).pack(side="left")
        self.opacity_label = ttk.Label(op, style="CM.TLabel")
        self.opacity_label.pack(side="left", padx=(S(6), 0))
        row("不透明度", op)
        row("", check("Windows 起動時に開始", self.startup))

        buttons = ttk.Frame(f)
        buttons.grid(row=self._row, column=0, columnspan=2, sticky="e", pady=(S(12), 0))
        for text, cmd in (("キャンセル", self._cancel), ("OK", self._ok), ("既定に戻す", self._reset)):
            ttk.Button(buttons, text=text, command=cmd, style="CM.TButton", width=10).pack(side="right", padx=(S(6), 0))

        self.tz_box.bind("<<ComboboxSelected>>", lambda e: self._update_local_peak())
        self.weekdays_only.trace_add("write", lambda *_: self._update_local_peak())
        self.style_var.trace_add("write", lambda *_: self._update_layout_enabled())

    def _load(self, s, startup_enabled):
        self.refresh.set(str(min(60, max(1, s.refresh_minutes))))
        idx = next((i for i, z in enumerate(self.zones) if z.id == s.peak_time_zone), 0)
        if self.zones:
            self.tz_box.current(idx)
        self.peak_start.set(s.peak_start)
        self.peak_end.set(s.peak_end)
        self.weekdays_only.set(s.peak_weekdays_only)
        self.style_var.set(s.style)
        self.layout_var.set("v" if s.gauge_vertical else "h")
        self.show_fable.set(s.show_fable)
        self.gauge_sweep.set(s.gauge_sweep)
        self.top_most.set(s.top_most)
        self.opacity.set(round(min(1.0, max(0.3, s.opacity)) * 100))
        self._update_opacity_label()
        self.startup.set(startup_enabled)
        self._update_layout_enabled()

    def apply_to(self, s):
        try:
            s.refresh_minutes = min(60, max(1, int(float(self.refresh.get()))))
        except ValueError:
            pass
        if self.zones and self.tz_box.current() >= 0:
            s.peak_time_zone = self.zones[self.tz_box.current()].id
        s.peak_start = self.peak_start.get()
        s.peak_end = self.peak_end.get()
        s.peak_weekdays_only = self.weekdays_only.get()
        s.style = "gauge" if self.style_var.get() == "gauge" else "bar"
        s.gauge_vertical = self.layout_var.get() == "v"
        s.show_fable = self.show_fable.get()
        s.gauge_sweep = self.gauge_sweep.get()
        s.top_most = self.top_most.get()
        s.opacity = int(round(self.opacity.get())) / 100.0

    @property
    def startup_enabled(self):
        return self.startup.get()

    def _update_opacity_label(self):
        self.opacity_label.configure(text="%d%%" % int(round(self.opacity.get())))

    # 並びとスイープの指定はスピードメーターのときだけ意味がある
    def _update_layout_enabled(self):
        state = ["!disabled"] if self.style_var.get() == "gauge" else ["disabled"]
        for w in (self.layout_h, self.layout_v, self.sweep_check):
            w.state(state)

    # 選んだタイムゾーンの時間帯が、この PC の時刻で今日何時になるかを示す
    def _update_local_peak(self):
        if self._building:
            return
        if not self.zones or self.tz_box.current() < 0:
            self.local_peak.configure(text="")
            return
        zone = self.zones[self.tz_box.current()]
        today_there = zone.to_local(utc_now()).date()
        ps, pe = parse_hm(self.peak_start.get(), 0), parse_hm(self.peak_end.get(), 0)
        base = dt.datetime.combine(today_there, dt.time())
        s = utc_to_machine(zone.to_utc(base + dt.timedelta(minutes=ps)))
        e = utc_to_machine(zone.to_utc(base + dt.timedelta(minutes=pe)))
        if e <= s:
            e += dt.timedelta(days=1)
        self.local_peak.configure(
            text="この PC の時刻では " + s.strftime("%H:%M") + "〜" + ("翌" if e.date() > s.date() else "")
            + e.strftime("%H:%M") + ("（基準タイムゾーンの平日のみ）" if self.weekdays_only.get() else "（毎日）"))

    def _reset(self):
        self._building = True
        self._load(Settings(), self.startup.get())
        self._building = False
        self._update_local_peak()

    def _ok(self):
        self.ok = True
        self._close()

    def _cancel(self):
        self._close()

    def _close(self):
        self.grab_release()
        self.withdraw()
        self._on_done(self)
        self.destroy()


# ---------- GDI+ ----------
# tk のキャンバスは図形をアンチエイリアスしないので、図形は GDI+ で画像に描いてキャンバスに貼る
gdiplus = ctypes.WinDLL("gdiplus")
_F = ctypes.c_float
_P = ctypes.c_void_p
_PP = ctypes.POINTER(ctypes.c_void_p)


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [("GdiplusVersion", ctypes.c_uint32), ("DebugEventCallback", ctypes.c_void_p),
                ("SuppressBackgroundThread", wt.BOOL), ("SuppressExternalCodecs", wt.BOOL)]


for _name, _args in (("GdiplusStartup", (ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput), _P)),
                     ("GdipCreateBitmapFromScan0", (ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _P, _PP)),
                     ("GdipGetImageGraphicsContext", (_P, _PP)),
                     ("GdipSetSmoothingMode", (_P, ctypes.c_int)),
                     ("GdipGraphicsClear", (_P, ctypes.c_uint32)),
                     ("GdipCreatePen1", (ctypes.c_uint32, _F, ctypes.c_int, _PP)),
                     ("GdipSetPenStartCap", (_P, ctypes.c_int)),
                     ("GdipSetPenEndCap", (_P, ctypes.c_int)),
                     ("GdipCreateSolidFill", (ctypes.c_uint32, _PP)),
                     ("GdipCreatePath", (ctypes.c_int, _PP)),
                     ("GdipAddPathArc", (_P, _F, _F, _F, _F, _F, _F)),
                     ("GdipClosePathFigure", (_P,)),
                     ("GdipDrawRectangle", (_P, _P, _F, _F, _F, _F)),
                     ("GdipDrawArc", (_P, _P, _F, _F, _F, _F, _F, _F)),
                     ("GdipDrawLine", (_P, _P, _F, _F, _F, _F)),
                     ("GdipFillEllipse", (_P, _P, _F, _F, _F, _F)),
                     ("GdipFillPath", (_P, _P, _P)),
                     ("GdipDeletePen", (_P,)),
                     ("GdipDeleteBrush", (_P,)),
                     ("GdipDeletePath", (_P,)),
                     ("GdipDeleteGraphics", (_P,)),
                     ("GdipDisposeImage", (_P,))):
    _proto(getattr(gdiplus, _name), ctypes.c_int, *_args)

_gdiplus_token = None


def argb(c, a=255):
    return (a << 24) | (c[0] << 16) | (c[1] << 8) | c[2]


class Painter:
    """GDI+ でアンチエイリアスをかけて図形を描き、tk の PhotoImage にする"""

    def __init__(self, w, h, back):
        global _gdiplus_token
        if _gdiplus_token is None:
            token = ctypes.c_size_t()
            gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(GdiplusStartupInput(1, None, False, False)), None)
            _gdiplus_token = token
        self.w, self.h = w, h
        self.buf = (ctypes.c_ubyte * (w * h * 4))()
        self.bmp, self.g = _P(), _P()
        gdiplus.GdipCreateBitmapFromScan0(w, h, w * 4, 0x26200A, self.buf, ctypes.byref(self.bmp))  # 32bppARGB
        gdiplus.GdipGetImageGraphicsContext(self.bmp, ctypes.byref(self.g))
        gdiplus.GdipSetSmoothingMode(self.g, 4)  # AntiAlias
        gdiplus.GdipGraphicsClear(self.g, argb(back))

    def _pen(self, c, width, alpha=255, round_cap=False):
        p = _P()
        gdiplus.GdipCreatePen1(argb(c, alpha), width, 0, ctypes.byref(p))  # UnitWorld
        if round_cap:
            gdiplus.GdipSetPenStartCap(p, 2)  # LineCapRound
            gdiplus.GdipSetPenEndCap(p, 2)
        return p

    def _brush(self, c):
        b = _P()
        gdiplus.GdipCreateSolidFill(argb(c), ctypes.byref(b))
        return b

    def rectangle(self, x, y, w, h, c, width):
        p = self._pen(c, width)
        gdiplus.GdipDrawRectangle(self.g, p, x, y, w, h)
        gdiplus.GdipDeletePen(p)

    def arc(self, x, y, w, h, start, sweep, c, width, alpha=255):
        p = self._pen(c, width, alpha)
        gdiplus.GdipDrawArc(self.g, p, x, y, w, h, start, sweep)
        gdiplus.GdipDeletePen(p)

    def line(self, x1, y1, x2, y2, c, width, round_cap=False):
        p = self._pen(c, width, round_cap=round_cap)
        gdiplus.GdipDrawLine(self.g, p, x1, y1, x2, y2)
        gdiplus.GdipDeletePen(p)

    def ellipse(self, x, y, w, h, c):
        b = self._brush(c)
        gdiplus.GdipFillEllipse(self.g, b, x, y, w, h)
        gdiplus.GdipDeleteBrush(b)

    def round_rect(self, x, y, w, h, c):
        b, path = self._brush(c), _P()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        gdiplus.GdipAddPathArc(path, x, y, h, h, 90, 180)
        gdiplus.GdipAddPathArc(path, x + w - h, y, h, h, 270, 180)
        gdiplus.GdipClosePathFigure(path)
        gdiplus.GdipFillPath(self.g, b, path)
        gdiplus.GdipDeletePath(path)
        gdiplus.GdipDeleteBrush(b)

    def to_photo(self, master):
        gdiplus.GdipDeleteGraphics(self.g)
        gdiplus.GdipDisposeImage(self.bmp)
        bgra = bytes(self.buf)
        rgb = bytearray(self.w * self.h * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
        return tk.PhotoImage(master=master, data=b"P6 %d %d 255\n" % (self.w, self.h) + bytes(rgb), format="ppm")


# ---------- 表示 ----------
class Theme:
    BACK = (30, 30, 32)
    TRACK = (58, 58, 62)
    TEXT = (235, 235, 235)
    SUB = (150, 150, 155)
    BORDER = (70, 70, 75)
    OK = (70, 150, 230)  # 70% 未満は青
    WARN = (230, 180, 60)
    DANGER = (225, 80, 80)
    PEAK = (225, 95, 80)
    OFF_PEAK = (90, 190, 120)

    @staticmethod
    def for_percent(p):
        if p >= 90:
            return Theme.DANGER
        if p >= 70:
            return Theme.WARN
        return Theme.OK


def color(c):
    return "#%02x%02x%02x" % c


DOW = "月火水木金土日"


def format_when(t):
    if t.date() == dt.datetime.now().date():
        return t.strftime("%H:%M")
    return "%d/%d(%s) %s" % (t.month, t.day, DOW[t.weekday()], t.strftime("%H:%M"))


def format_span(d):
    s = d.total_seconds()
    if s < 60:
        return "まもなく"
    if s < 3600:
        return "あと%d分" % (s // 60)
    if s < 86400:
        return "あと%d時間%d分" % (s // 3600, s // 60 % 60)
    return "あと%d日%d時間" % (s // 86400, s // 3600 % 24)


class MeterApp:
    GAUGE_CELL, GAUGE_ROW = 130, 134
    # 起動時のスイープ（針が一度最大まで振り切ってから実際の値に戻る）
    SWEEP_UP, SWEEP_HOLD, SWEEP_DOWN = 0.7, 0.2, 0.8  # 秒
    # スピードメーター: 左下(0%)から右下(100%)まで 240° の文字盤と針（角度は時計回り、3時方向が 0°）
    GAUGE_START, GAUGE_SWEEP = 150.0, 240.0
    CMD_REFRESH, CMD_TOPMOST, CMD_STARTUP, CMD_TOGGLE, CMD_SETTINGS, CMD_EXIT = range(1, 7)

    # snapshot_path を指定すると1回取得して描画を PNG に保存し終了する（動作確認用）。
    # forced_scale > 0 ならモニターの拡大率の代わりにその倍率で描く。
    # snapshot_style は表示形式の上書き（例: "gauge,vertical,nofable"。保存はしない）。
    def __init__(self, root, snapshot_path=None, forced_scale=0.0, snapshot_style=None):
        self.root = root
        self.snapshot_path = snapshot_path
        self.settings = Settings.load()
        if snapshot_style is not None:
            opts = snapshot_style.split(",")
            self.settings.style = "gauge" if "gauge" in opts else "bar"
            self.settings.gauge_vertical = "vertical" in opts
            self.settings.show_fable = "nofable" not in opts
        self.events = queue.Queue()  # 別スレッド（取得・トレイ）から tk スレッドへの受け渡し
        self.last = None
        self.fetching = False
        self.sweeping = False
        self.sweep_t0 = 0.0
        self._sweep_job = None
        self._refresh_job = None
        self._drag = (0, 0)
        self.peak = PeakClock()
        self.settings_dialog = None
        self.scale_forced = forced_scale > 0
        self.scale = 1.0
        self.fonts = {k: tkfont.Font(root) for k in ("title", "label", "pct", "small")}

        root.title("Claude Meter")
        root.overrideredirect(True)  # 枠なし。タスクバーと Alt+Tab にも出ない
        root.configure(bg=color(Theme.BACK))
        try:
            root.iconbitmap(default=ICON_PATH)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(root, bg=color(Theme.BACK), highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        s = self.settings
        on_screen = is_on_screen(s.x, s.y)
        wa = primary_work_area()
        self.apply_scale(forced_scale if forced_scale > 0
                         else scale_at(*((s.x, s.y) if on_screen else (wa[2] - 1, wa[3] - 1))))
        w, h = self.size()
        x, y = (s.x, s.y) if on_screen else (wa[2] - w - self.S(16), wa[3] - h - self.S(16))
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.attributes("-topmost", s.top_most)
        root.attributes("-alpha", 1.0 if snapshot_path else s.opacity)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Double-Button-1>", lambda e: self.refresh())
        self.canvas.bind("<ButtonRelease-3>", lambda e: self._window_menu())

        self.tray = None
        if snapshot_path is None:
            self.tray = TrayIcon("Claude Meter", lambda: self.events.put(self.CMD_TOGGLE), self._tray_menu)

        self._schedule_refresh()
        root.after(30 * 1000, self._on_clock)  # 残り時間とピーク表示の更新
        root.after(100, self._poll_events)
        root.after(0, self._on_shown)

    # 座標とフォントは 100% 時の値で書き、S() で現在の拡大率に合わせる
    def S(self, v):
        return int(round(v * self.scale))

    @property
    def is_gauge(self):
        return self.settings.style == "gauge"

    @property
    def is_vertical(self):
        return self.is_gauge and self.settings.gauge_vertical

    @property
    def meter_count(self):
        return 3 if self.settings.show_fable else 2

    def size(self):
        if not self.is_gauge:
            w, h = 260, 34 + 46 * self.meter_count + 50
        elif self.is_vertical:
            # メーター部の下にピーク表示（縦並びは2行）とエラー行が入る
            w, h = 24 + 146, 34 + self.GAUGE_ROW * self.meter_count + 56
        else:
            w, h = 24 + self.GAUGE_CELL * self.meter_count, 214
        return self.S(w), self.S(h)

    def apply_scale(self, scale):
        self.scale = scale
        # 負のサイズはピクセル指定（ポイント指定だとシステム DPI で換算されてしまう）
        self.fonts["title"].configure(family="Yu Gothic UI", size=-self.S(12), weight="bold")
        self.fonts["label"].configure(family="Yu Gothic UI", size=-self.S(12), weight="normal")
        self.fonts["pct"].configure(family="Segoe UI", size=-self.S(13.33), weight="bold")
        self.fonts["small"].configure(family="Yu Gothic UI", size=-self.S(10.67), weight="normal")

    def frame_hwnd(self):
        return int(self.root.wm_frame(), 16)

    # ---- イベント ----
    def _on_shown(self):
        self.start_sweep()
        self.refresh()

    def _poll_events(self):
        try:
            while True:
                ev = self.events.get_nowait()
                if isinstance(ev, UsageResult):
                    self._on_result(ev)
                else:
                    self.run_command(ev)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _schedule_refresh(self):
        if self._refresh_job is not None:
            self.root.after_cancel(self._refresh_job)
        self._refresh_job = self.root.after(self.settings.refresh_minutes * 60 * 1000, self._on_refresh_timer)

    def _on_refresh_timer(self):
        self._refresh_job = None
        self.refresh()
        self._schedule_refresh()

    def _on_clock(self):
        self.check_dpi()
        self.redraw()
        self.update_tray_text()
        self.root.after(30 * 1000, self._on_clock)

    def refresh(self):
        if self.fetching:
            return
        self.fetching = True
        self.redraw()
        threading.Thread(target=lambda: self.events.put(UsageClient.fetch()), daemon=True).start()

    def _on_result(self, r):
        # 失敗時は前回値を残してエラーだけ差し替える
        if r.error is not None and self.last is not None and self.last.error is None:
            self.last.error = r.error
        else:
            self.last = r
        self.fetching = False
        self.redraw()
        self.update_tray_text()
        if self.snapshot_path:
            self.root.after(500, self.save_snapshot)

    def save_snapshot(self):
        self.root.update()
        x, y, w, h = window_rect(self.frame_hwnd())
        capture_png(self.snapshot_path, x, y, w, h)
        with open(self.snapshot_path + ".txt", "w", encoding="utf-8") as f:
            f.write("scale=%s monitor=%s size=%dx%d %s\n%s" % (self.scale, scale_at(x, y), w, h,
                                                               self.last.error or "", self.last.raw_body or ""))
        self.exit()

    def menu_items(self):
        return [(self.CMD_REFRESH, "今すぐ更新", False),
                (self.CMD_TOPMOST, "常に手前に表示", self.settings.top_most),
                (self.CMD_STARTUP, "Windows 起動時に開始", is_startup_enabled()),
                (self.CMD_TOGGLE, "表示／非表示", False),
                (self.CMD_SETTINGS, "設定...", False),
                None,
                (self.CMD_EXIT, "終了", False)]

    def _tray_menu(self, hwnd):
        # トレイのスレッドで呼ばれるので、結果はキュー経由で tk スレッドに渡す
        cmd = popup_menu(hwnd, self.menu_items())
        if cmd:
            self.events.put(cmd)

    def _window_menu(self):
        cmd = popup_menu(self.frame_hwnd(), self.menu_items())
        if cmd:
            self.run_command(cmd)

    def run_command(self, cmd):
        if cmd == self.CMD_REFRESH:
            self.refresh()
        elif cmd == self.CMD_TOPMOST:
            self.toggle_top_most()
        elif cmd == self.CMD_STARTUP:
            set_startup(not is_startup_enabled())
        elif cmd == self.CMD_TOGGLE:
            self.toggle_visible()
        elif cmd == self.CMD_SETTINGS:
            self.show_settings()
        elif cmd == self.CMD_EXIT:
            self.exit()

    def _on_press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _on_motion(self, e):
        self.root.geometry("+%d+%d" % (e.x_root - self._drag[0], e.y_root - self._drag[1]))

    def _on_release(self, e):
        self.check_dpi()
        self.save_position()

    # 拡大率の違うモニターへ移ったら描き直す（tk は WM_DPICHANGED を扱わないため位置から判断する）
    def check_dpi(self):
        if self.scale_forced:
            return
        x, y, w, h = window_rect(self.frame_hwnd())
        new = scale_at(x + w // 2, y + h // 2)
        if abs(new - self.scale) > 0.01:
            self.apply_scale(new)
            self.resize()

    def resize(self):
        w, h = self.size()
        self.root.geometry("%dx%d" % (w, h))
        self.redraw()

    def save_position(self):
        if self.snapshot_path:
            return  # 動作確認では設定を書き換えない
        self.settings.x = self.root.winfo_x()
        self.settings.y = self.root.winfo_y()
        self.settings.save()

    def toggle_top_most(self):
        self.settings.top_most = not self.settings.top_most
        self.root.attributes("-topmost", self.settings.top_most)
        self.settings.save()

    def toggle_visible(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
            self.root.attributes("-topmost", self.settings.top_most)
            self.root.lift()
            self.refresh()
        else:
            self.root.withdraw()

    # 表示形式の切り替えで大きさが変わったとき、画面外にはみ出さないよう戻す
    def keep_on_screen(self):
        self.root.update_idletasks()
        x, y, w, h = window_rect(self.frame_hwnd())
        l, t, r, b = work_area(x + w // 2, y + h // 2)
        nx = max(l, min(x, r - w))
        ny = max(t, min(y, b - h))
        self.root.geometry("+%d+%d" % (nx, ny))
        self.save_position()

    def show_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.lift()
            self.settings_dialog.focus_force()
            return
        x, y, w, h = window_rect(self.frame_hwnd())
        self.settings_dialog = SettingsDialog(self.root, self.settings, is_startup_enabled(),
                                              (x + w // 2, y + h // 2), self._settings_done)

    def _settings_done(self, dlg):
        self.settings_dialog = None
        if not dlg.ok:
            return
        was_gauge = self.is_gauge
        dlg.apply_to(self.settings)
        self.settings.save()
        self._schedule_refresh()
        self.root.attributes("-topmost", self.settings.top_most)
        self.root.attributes("-alpha", self.settings.opacity)
        self.peak = PeakClock()
        self.resize()
        self.keep_on_screen()
        if not was_gauge and self.is_gauge:
            self.start_sweep()
        if dlg.startup_enabled != is_startup_enabled():
            set_startup(dlg.startup_enabled)

    def exit(self):
        if self.tray:
            self.tray.remove()
        self.save_position()
        self.root.destroy()

    def update_tray_text(self):
        if self.last is None or self.tray is None:
            return
        t = "Claude"
        if self.last.five_hour.present:
            t += " 5h:%d%%" % round(self.last.five_hour.utilization)
        if self.last.weekly.present:
            t += " 週:%d%%" % round(self.last.weekly.utilization)
        if self.settings.show_fable and self.last.weekly_fable.present:
            t += " Fable:%d%%" % round(self.last.weekly_fable.utilization)
        self.tray.set_tip(t)

    # ---- スイープ ----
    def start_sweep(self):
        if not self.is_gauge or not self.settings.gauge_sweep or self.snapshot_path:
            return
        self.sweeping = True
        self.sweep_t0 = time.perf_counter()
        if self._sweep_job is None:
            self._sweep_tick()

    def _sweep_tick(self):
        if time.perf_counter() - self.sweep_t0 >= self.SWEEP_UP + self.SWEEP_HOLD + self.SWEEP_DOWN:
            self.sweeping = False
            self._sweep_job = None
        else:
            self._sweep_job = self.root.after(15, self._sweep_tick)
        self.redraw()

    # 経過時間に応じた針の位置。上りは 0→100%、下りは 100%→target
    def sweep_value(self, target):
        t = time.perf_counter() - self.sweep_t0
        if t < self.SWEEP_UP:
            return 100 * self._ease(t / self.SWEEP_UP)
        if t < self.SWEEP_UP + self.SWEEP_HOLD:
            return 100
        k = min(1.0, (t - self.SWEEP_UP - self.SWEEP_HOLD) / self.SWEEP_DOWN)
        return 100 + (target - 100) * self._ease(k)

    @staticmethod
    def _ease(x):
        return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2  # easeInOutCubic

    # ---- 描画 ----
    def text(self, s, font, c, x, y, anchor="nw"):
        self.canvas.create_text(x, y, text=s, font=self.fonts[font], fill=color(c), anchor=anchor)

    def redraw(self):
        S = self.S
        cv = self.canvas
        cv.delete("all")
        cw_, ch_ = self.size()
        pad = S(12)
        w = cw_ - pad * 2

        # 図形は self.painter に描き、最後に文字より下の画像として貼る
        self.painter = Painter(cw_, ch_, Theme.BACK)
        shapes = cv.create_image(0, 0, anchor="nw")
        self.painter.rectangle(0, 0, cw_ - 1, ch_ - 1, Theme.BORDER, max(1, S(1)))

        # ヘッダー
        self.text("Claude Meter", "title", Theme.TEXT, pad, S(8))
        status = "更新中…" if self.fetching else (self.last.fetched_at.strftime("%H:%M") + " 更新" if self.last else "")
        self.text(status, "small", Theme.SUB, pad + w, S(10), "ne")

        labels = ["5時間制限", "週間制限"]
        wins = [self.last.five_hour if self.last else None, self.last.weekly if self.last else None]
        if self.settings.show_fable:
            labels.append("週間制限（Fable）")
            wins.append(self.last.weekly_fable if self.last else None)

        y = S(34)
        if self.is_gauge:
            cw = w if self.is_vertical else w // len(labels)
            for i, label in enumerate(labels):
                if self.is_vertical:
                    self.draw_gauge(label, wins[i], pad, y, cw)
                    y += S(self.GAUGE_ROW)
                else:
                    self.draw_gauge(label, wins[i], pad + cw * i, y, cw)
            if not self.is_vertical:
                y += S(self.GAUGE_ROW)
        else:
            for i, label in enumerate(labels):
                self.draw_meter(label, wins[i], pad, y, w)
                y += S(46)

        # ピーク／オフピーク
        peak, change = self.peak.is_peak(self.settings, utc_now())
        c = Theme.PEAK if peak else Theme.OFF_PEAK
        self.painter.ellipse(pad, y + S(4), S(10), S(10), c)
        self.text("ピークタイム" if peak else "オフピーク", "title", c, pad + S(15), y)
        if change is not None:
            when = ("終了 " if peak else "開始 ") + format_when(change) + "（" + format_span(change - dt.datetime.now()) + "）"
            # 縦並びは幅が狭いので2行目に出す
            if self.is_vertical:
                self.text(when, "small", Theme.SUB, pad + S(15), y + S(19))
            else:
                self.text(when, "small", Theme.SUB, pad + w, y + S(2), "ne")

        if self.last is not None and self.last.error is not None:
            self.text(self.ellipsis(self.last.error, "small", w), "small", Theme.WARN, pad, ch_ - S(20))

        self.photo = self.painter.to_photo(self.root)  # キャンバスが画像を参照している間は保持しておく
        cv.itemconfigure(shapes, image=self.photo)

    def ellipsis(self, s, font, width):
        f = self.fonts[font]
        if f.measure(s) <= width:
            return s
        while s and f.measure(s + "…") > width:
            s = s[:-1]
        return s + "…"

    def draw_meter(self, label, win, x, y, w):
        S = self.S
        self.text(label, "label", Theme.TEXT, x, y)
        has = win is not None and win.present
        pct = win.utilization if has else 0.0
        self.text("%d%%" % round(pct) if has else "—", "pct", Theme.for_percent(pct) if has else Theme.SUB,
                  x + w, y - S(2), "ne")

        bar_h = S(7)
        self.painter.round_rect(x, y + S(20), w, bar_h, Theme.TRACK)
        if has and pct > 0:
            fw = int(max(bar_h, min(w, w * pct / 100.0)))
            self.painter.round_rect(x, y + S(20), fw, bar_h, Theme.for_percent(pct))

        if win is None:
            sub = ""
        elif not has:
            sub = "データなし"
        elif win.resets_at is not None:
            sub = "リセット " + format_when(win.resets_at) + "（" + format_span(win.resets_at - dt.datetime.now()) + "）"
        else:
            sub = "未使用"
        self.text(sub, "small", Theme.SUB, x, y + S(29))

    def angle(self, pct):
        return self.GAUGE_START + self.GAUGE_SWEEP * pct / 100

    def arc(self, cx, cy, r, start, sweep, c, width, alpha=255):
        self.painter.arc(cx - r, cy - r, r * 2, r * 2, start, sweep, c, width, alpha)

    def draw_gauge(self, label, win, x, y, cw):
        S = self.S
        pt = self.painter
        has = win is not None and win.present
        pct = max(0.0, min(100.0, win.utilization)) if has else 0.0
        lit = has or self.sweeping  # スイープ中はデータ未取得でも文字盤を点灯させる
        if self.sweeping:
            pct = self.sweep_value(pct)
        r = S(44)
        cx, cy = x + cw / 2, y + r + S(4)

        # 目盛りの外側に 70〜90% を黄、90〜100% を赤の帯で示す
        zr = r + S(4)
        self.arc(cx, cy, zr, self.angle(70), self.GAUGE_SWEEP * 0.2, Theme.WARN, S(2), 150)
        self.arc(cx, cy, zr, self.angle(90), self.GAUGE_SWEEP * 0.1, Theme.DANGER, S(2), 170)

        self.arc(cx, cy, r, self.GAUGE_START, self.GAUGE_SWEEP, Theme.TRACK, S(7))
        value_sweep = self.GAUGE_SWEEP * pct / 100
        if lit and value_sweep >= 0.5:  # GDI+ は極小角度の DrawArc で失敗することがある
            self.arc(cx, cy, r, self.GAUGE_START, value_sweep, Theme.for_percent(pct), S(7))

        # 10% ごとの目盛り（0・50・100% は長く）
        for i in range(11):
            major = i % 5 == 0
            a = math.radians(self.angle(i * 10))
            r1, r2 = r - S(15 if major else 11), r - S(6)
            pt.line(cx + math.cos(a) * r1, cy + math.sin(a) * r1, cx + math.cos(a) * r2, cy + math.sin(a) * r2,
                    Theme.TEXT if major else Theme.SUB, S(2) if major else max(1, S(1)))

        # 針
        na = math.radians(self.angle(pct))
        nl = r - S(13)
        pt.line(cx, cy, cx + math.cos(na) * nl, cy + math.sin(na) * nl, Theme.TEXT if lit else Theme.SUB,
                max(2, S(2.5)), round_cap=True)
        hub = S(5)
        pt.ellipse(cx - hub, cy - hub, hub * 2, hub * 2, Theme.for_percent(pct) if lit else Theme.SUB)

        self.text("%d%%" % round(pct) if lit else "—", "pct", Theme.for_percent(pct) if lit else Theme.SUB,
                  cx, cy + S(12), "n")
        self.text(label, "label", Theme.TEXT, cx, cy + S(32), "n")
        if win is not None:
            if not has:
                self.text("データなし", "small", Theme.SUB, cx, cy + S(50), "n")
            elif win.resets_at is not None:
                self.text("リセット " + format_when(win.resets_at), "small", Theme.SUB, cx, cy + S(50), "n")
                self.text(format_span(win.resets_at - dt.datetime.now()), "small", Theme.SUB, cx, cy + S(64), "n")
            else:
                self.text("未使用", "small", Theme.SUB, cx, cy + S(50), "n")


def main():
    # exe 版と同じ名前のミューテックスで、どちらか一方だけが動くようにする
    mutex = kernel32.CreateMutexW(None, True, "ClaudeMeter_SingleInstance")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        return
    enable_dpi_awareness()
    args = sys.argv[1:]
    root = tk.Tk()

    if len(args) >= 2 and args[0] == "--snapshot-settings":
        # 設定画面を PNG に保存して終了する（動作確認用）
        # 3つ目・4つ目の引数で開く位置（モニター）を指定できる
        root.withdraw()
        at = (int(args[2]), int(args[3])) if len(args) >= 4 else (0, 0)
        dlg = SettingsDialog(root, Settings.load(), False, at, lambda d: None)

        def shot():
            dlg.update()
            capture_png(args[1], *window_rect(int(dlg.wm_frame(), 16)))
            root.destroy()

        root.after(800, shot)
        root.mainloop()
        return

    snapshot = args[1] if len(args) >= 2 and args[0] == "--snapshot" else None
    forced = float(args[2]) if snapshot and len(args) >= 3 else 0.0
    style = args[3] if snapshot and len(args) >= 4 else None
    MeterApp(root, snapshot, forced, style)
    root.mainloop()
    del mutex


if __name__ == "__main__":
    main()
