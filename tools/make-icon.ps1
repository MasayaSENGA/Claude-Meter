# exe に埋め込むアイコン (src\app.ico) を生成する。
# 絵柄はタスクトレイのアイコン（MeterForm.MakeIcon）と同じ。
Add-Type -AssemblyName System.Drawing

$out = Join-Path $PSScriptRoot "..\src\app.ico"
$sizes = 16, 20, 24, 32, 40, 48, 64, 256

function Draw-Icon([int]$size) {
    $bmp = New-Object System.Drawing.Bitmap $size, $size
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $k = $size / 32.0
    $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(217, 119, 87))
    $g.FillEllipse($brush, 1 * $k, 1 * $k, 30 * $k, 30 * $k)
    $pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), (4 * $k)
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawArc($pen, 8 * $k, 8 * $k, 16 * $k, 16 * $k, 135, 270)
    $g.DrawLine($pen, 16 * $k, 16 * $k, 22 * $k, 11 * $k)
    $pen.Dispose(); $brush.Dispose(); $g.Dispose()
    $ms = New-Object IO.MemoryStream
    if ($size -ge 256) {
        # 256px は PNG で格納するのが慣例
        $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    } else {
        # 小さいサイズは互換性の高い BMP (DIB) 形式: BITMAPINFOHEADER + BGRA(下から上) + AND マスク
        $bw = New-Object IO.BinaryWriter $ms
        $maskRow = [int]([Math]::Ceiling($size / 32.0) * 4)
        $bw.Write([UInt32]40); $bw.Write([Int32]$size); $bw.Write([Int32]($size * 2))
        $bw.Write([UInt16]1); $bw.Write([UInt16]32); $bw.Write([UInt32]0)
        $bw.Write([UInt32]($size * $size * 4 + $maskRow * $size))
        $bw.Write([Int32]0); $bw.Write([Int32]0); $bw.Write([UInt32]0); $bw.Write([UInt32]0)
        for ($y = $size - 1; $y -ge 0; $y--) {
            for ($x = 0; $x -lt $size; $x++) {
                $c = $bmp.GetPixel($x, $y)
                $bw.Write([byte]$c.B); $bw.Write([byte]$c.G); $bw.Write([byte]$c.R); $bw.Write([byte]$c.A)
            }
        }
        $bw.Write((New-Object byte[] ($maskRow * $size))) # 透過はアルファで表すのでマスクは全て 0
        $bw.Flush()
    }
    $bmp.Dispose()
    return , $ms.ToArray()
}

# ICO 形式: ヘッダー + 各サイズのディレクトリ + 画像データ
$images = @($sizes | ForEach-Object { , (Draw-Icon $_) })
$fs = [IO.File]::Create($out)
$w = New-Object IO.BinaryWriter $fs
$w.Write([UInt16]0); $w.Write([UInt16]1); $w.Write([UInt16]$sizes.Count)
$offset = 6 + 16 * $sizes.Count
for ($i = 0; $i -lt $sizes.Count; $i++) {
    $s = $sizes[$i]
    $dim = if ($s -ge 256) { 0 } else { $s }
    $w.Write([byte]$dim); $w.Write([byte]$dim); $w.Write([byte]0); $w.Write([byte]0)
    $w.Write([UInt16]1); $w.Write([UInt16]32)
    $w.Write([UInt32]$images[$i].Length); $w.Write([UInt32]$offset)
    $offset += $images[$i].Length
}
foreach ($img in $images) { $w.Write($img) }
$w.Close()
Write-Host "Created: $out"
