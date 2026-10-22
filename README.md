# Claude Meter

Claude の利用制限の使用状況を、デスクトップの隅に小さく常時表示する Windows アプリです。

- 5時間制限の使用率とリセット時刻
- 週間制限（全モデル）の使用率とリセット時刻
- 週間制限（Fable）の使用率とリセット時刻
- 今がピークタイムかオフピークか、次に切り替わる時刻

管理者権限は不要です。インストール作業もありません。

## 使い方

1. `bin\ClaudeMeter.exe` をダブルクリックして起動します。
2. 初回は Claude Code CLI でログインしておいてください（`claude` を起動して `/login`）。アプリはそのログイン情報（`%USERPROFILE%\.claude\.credentials.json`）を使います。

| 操作 | 内容 |
|---|---|
| ドラッグ | ウィンドウを移動（位置は保存されます） |
| ダブルクリック | 今すぐ更新 |
| 右クリック／タスクトレイのアイコン | メニュー（更新・常に手前・Windows 起動時に開始・設定・終了） |
| トレイアイコンを左クリック | 表示／非表示の切り替え |

データは5分ごとに自動更新します。バーの色は 70% 以上で黄色、90% 以上で赤になります。

## ビルド

Windows に標準で入っている .NET Framework 4.x の `csc.exe` でビルドします（SDK のインストール不要）。

```bash
build.bat
```

`bin\ClaudeMeter.exe` が作られます。

## 設定

右クリックメニューの「設定ファイルを開く」で `%APPDATA%\ClaudeMeter\settings.json` を編集できます。変更後はアプリを再起動してください。

| 項目 | 既定値 | 説明 |
|---|---|---|
| `refreshMinutes` | `5` | 自動更新の間隔（分） |
| `peakTimeZone` | `Pacific Standard Time` | ピーク時間の基準タイムゾーン（Windows のタイムゾーンID。夏時間は自動で考慮） |
| `peakStart` / `peakEnd` | `05:00` / `11:00` | ピークタイムの開始・終了（基準タイムゾーンでの時刻） |
| `peakWeekdaysOnly` | `true` | 平日のみピークとするか |
| `topMost` | `true` | 常に手前に表示 |
| `opacity` | `0.95` | ウィンドウの不透明度（0.3〜1.0） |

既定のピークタイムは「平日の米国太平洋時間 5:00〜11:00」（日本時間では夏時間中 21:00〜翌3:00、冬時間中 22:00〜翌4:00）です。Anthropic が定義を変えた場合はここを書き換えてください。

## 仕組み

- 使用状況は Claude Code の `/usage` と同じ `https://api.anthropic.com/api/oauth/usage` から取得します。Fable の週間枠は応答の `limits[]` のうち `scope.model.display_name` が `Fable` の項目です。
- アクセストークンが期限切れのときは、Claude Code と同じ方法でリフレッシュし、新しいトークンを `.credentials.json` に書き戻します（Claude Code CLI もそのまま使い続けられます）。
- 自動起動は `HKEY_CURRENT_USER\...\Run` に登録するので管理者権限は要りません。

## 注意

- Anthropic 非公式の個人製ツールです。Anthropic とは関係ありません。
- 使っている usage API は Anthropic の非公開エンドポイントです。仕様が変わると表示できなくなることがあります。
- ログイン情報は Claude Code CLI と共有しています。トークンの更新が Claude Code と同時に起きると、どちらかで再ログインが必要になる場合があります。
- リフレッシュトークンも期限切れになった場合は、`claude` で `/login` し直してください。
- トークンは `api.anthropic.com`（使用状況の取得）と `platform.claude.com`（トークン更新）以外には送信しません。
