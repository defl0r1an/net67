"""Скрипт PowerShell окна-продолжения установки (см. updater/install_splash.py).

Только ASCII: Windows PowerShell 5.1 читает файл без BOM как ANSI, и
кириллица внутри скрипта превращалась бы в кашу или ломала разбор. Все
русские тексты, цвета и пути окно берёт из JSON (UTF-8) — тест сверяет,
что в самом скрипте нет ни одного не-ASCII символа.

Как окно решает, что показывать:

* «Закрываем старую версию» — пока жив процесс старой программы.
* «Устанавливаем» — пока жив процесс установщика (его номер старая
  программа пишет в файл сразу после запуска). Кончился — смотрим журнал
  установщика: строка «Installation process succeeded» — успех, нет её —
  установка не удалась, окно говорит об этом и уходит.
* «Открываем новую версию» — до метки ready.txt новее запуска окна (её
  пишет новая версия, когда собрала окно) или до страховочного срока.

Пока старая программа на экране, окно поверх всех: иначе Windows могла
поставить его позади программы, и после её закрытия наверху оказалось бы
чужое окно. Как только старая закрылась, «поверх всех» снимается: если
установщик что-то спросит, его окно не должно оказаться под нашим.

``-SnapshotPath`` рисует один кадр в PNG и выходит: так внешний вид
проверяется без показа окна.
"""

from __future__ import annotations

#: Сколько ждать новую версию после конца установки, с.
READY_TIMEOUT_SECONDS = 90
#: Окно не висит дольше этого ни при каком исходе, с.
TOTAL_TIMEOUT_SECONDS = 15 * 60
#: Сколько окно показывает, что установка не удалась, прежде чем уйти, с.
FAILED_LINGER_SECONDS = 15

SPLASH_SCRIPT = r"""
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$SpecPath,
    [string]$SnapshotPath = '',
    [int]$SnapshotStage = 1,
    [switch]$SnapshotFailed
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
try {
    $spec = [System.IO.File]::ReadAllText($SpecPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
} catch {
    exit 2
}

function Write-Line([string]$message) {
    if ([string]::IsNullOrWhiteSpace([string]$spec.log_path)) { return }
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    try { [System.IO.File]::AppendAllText([string]$spec.log_path, "$stamp  $message`r`n", $utf8NoBom) } catch { }
}

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -Namespace Net67Splash -Name Native -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("user32.dll")]
public static extern bool SetProcessDPIAware();
'@
    [Net67Splash.Native]::SetProcessDPIAware() | Out-Null
} catch {
    Write-Line ("init failed: " + $_.Exception.Message)
    exit 3
}

$screenGraphics = [System.Drawing.Graphics]::FromHwnd([IntPtr]::Zero)
$scale = [Math]::Max(1.0, $screenGraphics.DpiX / 96.0)
$screenGraphics.Dispose()

function Px([double]$value) { return [float]($value * $scale) }
function Color-Of([string]$hex, [string]$fallback) {
    try { return [System.Drawing.ColorTranslator]::FromHtml($hex) } catch { return [System.Drawing.ColorTranslator]::FromHtml($fallback) }
}

$texts = $spec.texts
$colors = $spec.colors
$cBack = Color-Of ([string]$colors.background) '#272727'
$cCard = Color-Of ([string]$colors.card) '#2d2d2d'
$cText = Color-Of ([string]$colors.text) '#f3f3f3'
$cMuted = Color-Of ([string]$colors.muted) '#9aa0a6'
$cAccent = Color-Of ([string]$colors.accent) '#60cdff'
$cTrack = Color-Of ([string]$colors.track) '#3a3a3a'
$cFail = Color-Of ([string]$colors.fail) '#ff6b6b'
$family = [string]$spec.font_family
if ([string]::IsNullOrWhiteSpace($family)) { $family = 'Segoe UI' }

$fontTitle = New-Object System.Drawing.Font($family, (Px 22), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fontSub = New-Object System.Drawing.Font($family, (Px 12), [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$fontStage = New-Object System.Drawing.Font($family, (Px 14), [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)
$fontStageNow = New-Object System.Drawing.Font($family, (Px 14), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fontJoke = New-Object System.Drawing.Font($family, (Px 12), [System.Drawing.FontStyle]::Italic, [System.Drawing.GraphicsUnit]::Pixel)
$fontFoot = New-Object System.Drawing.Font($family, (Px 11), [System.Drawing.FontStyle]::Regular, [System.Drawing.GraphicsUnit]::Pixel)

$logo = $null
try {
    $bytes = [System.IO.File]::ReadAllBytes([string]$spec.logo_path)
    $logo = [System.Drawing.Image]::FromStream((New-Object System.IO.MemoryStream(, $bytes)))
} catch { $logo = $null }

$jokes = @($spec.jokes | ForEach-Object { [string]$_ } | Where-Object { $_.Trim() })
$S = [ordered]@{
    stage = 0
    failed = $false
    started = Get-Date
    oldGoneAt = $null
    installDoneAt = $null
    failedAt = $null
    closing = $false
    jokeIndex = 0
    jokeAt = Get-Date
    clock = [System.Diagnostics.Stopwatch]::StartNew()
    ticks = 0
}

function Test-Alive([int]$processId) {
    if ($processId -le 0) { return $false }
    try { $null = Get-Process -Id $processId -ErrorAction Stop; return $true } catch { return $false }
}

function Read-Pid([string]$path) {
    try {
        if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path)) { return 0 }
        return [int]([System.IO.File]::ReadAllText($path).Trim())
    } catch { return 0 }
}

function Test-SetupSucceeded {
    $path = [string]$spec.setup_log_path
    try {
        if (-not (Test-Path -LiteralPath $path)) { return $false }
        $item = Get-Item -LiteralPath $path
        if ($item.LastWriteTime -lt $S.started.AddSeconds(-5)) { return $false }
        return ([System.IO.File]::ReadAllText($path) -match 'Installation process succeeded')
    } catch { return $false }
}

function Test-Ready {
    $path = [string]$spec.ready_path
    try {
        if (-not (Test-Path -LiteralPath $path)) { return $false }
        return ((Get-Item -LiteralPath $path).LastWriteTime -ge $S.started.AddSeconds(-2))
    } catch { return $false }
}

function Close-Splash([string]$why) {
    if ($S.closing) { return }
    $S.closing = $true
    Write-Line ("close: " + $why)
    try { $form.Close() } catch { }
}

function Update-State {
    $now = Get-Date
    if (($now - $S.started).TotalSeconds -gt [double]$spec.total_timeout_seconds) { Close-Splash 'total timeout'; return }
    if (Test-Path -LiteralPath ([string]$spec.cancel_path)) { Close-Splash 'cancelled by the old app'; return }
    if ($S.failed) {
        if (($now - $S.failedAt).TotalSeconds -gt [double]$spec.failed_linger_seconds) { Close-Splash 'failure shown' }
        return
    }
    if ($S.stage -eq 0 -and -not (Test-Alive ([int]$spec.old_pid))) {
        $S.stage = 1
        $S.oldGoneAt = $now
        try { $form.TopMost = $false } catch { }
        Write-Line 'old app is gone'
    }
    if ($S.stage -eq 1) {
        $installerPid = Read-Pid ([string]$spec.installer_pid_path)
        $succeeded = Test-SetupSucceeded
        $installerGone = ($installerPid -gt 0) -and -not (Test-Alive $installerPid)
        if ($succeeded -and ($installerPid -le 0 -or $installerGone)) {
            $S.stage = 2
            $S.installDoneAt = $now
            Write-Line 'installer finished'
        } elseif ($installerGone) {
            # Installer ended without the success line: give the log a moment, then call it failed.
            Start-Sleep -Milliseconds 400
            if (Test-SetupSucceeded) {
                $S.stage = 2
                $S.installDoneAt = $now
                Write-Line 'installer finished'
            } else {
                $S.failed = $true
                $S.failedAt = $now
                Write-Line 'installer ended without success'
            }
        }
    }
    if ($S.stage -eq 2) {
        if (Test-Ready) { Close-Splash 'new version is ready'; return }
        if (($now - $S.installDoneAt).TotalSeconds -gt [double]$spec.ready_timeout_seconds) { Close-Splash 'ready timeout' }
    }
}

function New-RoundRect([float]$x, [float]$y, [float]$w, [float]$h, [float]$r) {
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $d = [Math]::Min($r * 2, [Math]::Min($w, $h))
    if ($d -le 0) { $path.AddRectangle((New-Object System.Drawing.RectangleF($x, $y, $w, $h))); return $path }
    $path.AddArc($x, $y, $d, $d, 180, 90)
    $path.AddArc($x + $w - $d, $y, $d, $d, 270, 90)
    $path.AddArc($x + $w - $d, $y + $h - $d, $d, $d, 0, 90)
    $path.AddArc($x, $y + $h - $d, $d, $d, 90, 90)
    $path.CloseFigure()
    return $path
}

function Draw-StageIcon($g, [float]$cx, [float]$cy, [int]$state, [double]$ms) {
    $r = Px 9
    if ($state -eq 2) {
        $brush = New-Object System.Drawing.SolidBrush($cAccent)
        $g.FillEllipse($brush, $cx - $r, $cy - $r, $r * 2, $r * 2)
        $brush.Dispose()
        $pen = New-Object System.Drawing.Pen($cBack, (Px 2.2))
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $g.DrawLine($pen, $cx - (Px 4.5), $cy, $cx - (Px 1.2), $cy + (Px 3.4))
        $g.DrawLine($pen, $cx - (Px 1.2), $cy + (Px 3.4), $cx + (Px 4.8), $cy - (Px 3.6))
        $pen.Dispose()
    } elseif ($state -eq 3) {
        $brush = New-Object System.Drawing.SolidBrush($cFail)
        $g.FillEllipse($brush, $cx - $r, $cy - $r, $r * 2, $r * 2)
        $brush.Dispose()
        $pen = New-Object System.Drawing.Pen($cBack, (Px 2.2))
        $g.DrawLine($pen, $cx - (Px 3.5), $cy - (Px 3.5), $cx + (Px 3.5), $cy + (Px 3.5))
        $g.DrawLine($pen, $cx + (Px 3.5), $cy - (Px 3.5), $cx - (Px 3.5), $cy + (Px 3.5))
        $pen.Dispose()
    } elseif ($state -eq 1) {
        $pen = New-Object System.Drawing.Pen($cTrack, (Px 2.4))
        $g.DrawEllipse($pen, $cx - $r, $cy - $r, $r * 2, $r * 2)
        $pen.Dispose()
        $pen = New-Object System.Drawing.Pen($cAccent, (Px 2.4))
        $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
        $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $angle = [float](($ms / 3.0) % 360)
        $g.DrawArc($pen, $cx - $r, $cy - $r, $r * 2, $r * 2, $angle, 110)
        $pen.Dispose()
    } else {
        $pen = New-Object System.Drawing.Pen($cMuted, (Px 1.6))
        $g.DrawEllipse($pen, $cx - $r, $cy - $r, $r * 2, $r * 2)
        $pen.Dispose()
    }
}

function Draw-Frame($g, [float]$w, [float]$h, [double]$ms) {
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::ClearTypeGridFit
    $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.Clear($cBack)
    $border = New-Object System.Drawing.Pen($cTrack, (Px 1))
    $g.DrawRectangle($border, 0, 0, $w - 1, $h - 1)
    $border.Dispose()

    $left = Px 48
    $right = $w - (Px 48)
    $textBrush = New-Object System.Drawing.SolidBrush($cText)
    $mutedBrush = New-Object System.Drawing.SolidBrush($cMuted)

    $title = [string]$texts.title
    if ($S.failed) { $title = [string]$texts.failed_title }
    $g.DrawString($title, $fontTitle, $textBrush, $left, (Px 44))
    $g.DrawString([string]$texts.subtitle, $fontSub, $mutedBrush, $left + (Px 1), (Px 80))

    # Hide button in the top right corner.
    $hx = $w - (Px 40)
    $hy = Px 22
    $pen = New-Object System.Drawing.Pen($cMuted, (Px 1.6))
    $g.DrawLine($pen, $hx, $hy + (Px 8), $hx + (Px 14), $hy + (Px 8))
    $pen.Dispose()

    $stages = @($texts.stages)
    for ($i = 0; $i -lt 3; $i++) {
        $y = (Px 128) + $i * (Px 36)
        $state = 0
        if ($i -lt $S.stage) { $state = 2 } elseif ($i -eq $S.stage) { $state = 1 }
        if ($S.failed -and $i -eq $S.stage) { $state = 3 }
        if ($S.stage -ge 3) { $state = 2 }
        Draw-StageIcon $g ($left + (Px 9)) ($y + (Px 10)) $state $ms
        $font = $fontStage
        $brush = $mutedBrush
        if ($state -eq 1 -or $state -eq 3) { $font = $fontStageNow; $brush = $textBrush }
        if ($state -eq 2) { $brush = $textBrush }
        $g.DrawString([string]$stages[$i], $font, $brush, $left + (Px 30), $y)
    }

    # Track with the logo running back and forth: the length of the install is unknown.
    $trackY = Px 262
    $trackH = Px 8
    $trackW = $right - $left
    $path = New-RoundRect $left $trackY $trackW $trackH ($trackH / 2)
    $brush = New-Object System.Drawing.SolidBrush($cTrack)
    $g.FillPath($brush, $path)
    $brush.Dispose()
    $path.Dispose()

    $fill = $cAccent
    if ($S.failed) { $fill = $cFail }
    $segment = $trackW * 0.28
    $phase = 0.5 - 0.5 * [Math]::Cos(2 * [Math]::PI * (($ms % 2200) / 2200.0))
    if ($S.failed) { $phase = 0 ; $segment = $trackW }
    $segLeft = $left + ($trackW - $segment) * $phase
    $path = New-RoundRect $segLeft $trackY $segment $trackH ($trackH / 2)
    $grad = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
        (New-Object System.Drawing.PointF($segLeft, $trackY)),
        (New-Object System.Drawing.PointF(($segLeft + $segment + 1), $trackY)),
        [System.Drawing.Color]::FromArgb(255, [int]($fill.R * 0.85), [int]($fill.G * 0.85), [int]($fill.B * 0.85)),
        [System.Drawing.Color]::FromArgb(255, [Math]::Min(255, [int]($fill.R * 1.15 + 20)), [Math]::Min(255, [int]($fill.G * 1.15 + 20)), [Math]::Min(255, [int]($fill.B * 1.15 + 20))))
    $g.FillPath($grad, $path)
    $grad.Dispose()
    $path.Dispose()

    if ($logo -ne $null) {
        $side = Px 30
        $stride = ($ms % 520) / 520.0
        $hop = 0.0
        if (-not $S.failed) { $hop = $side * 0.16 * [Math]::Abs([Math]::Sin([Math]::PI * $stride)) }
        $cx = $segLeft + $segment / 2
        $cx = [Math]::Max($left + $side / 2, [Math]::Min($right - $side / 2, $cx))
        $state = $g.Save()
        $g.TranslateTransform($cx, $trackY - (Px 2) - $hop - $side / 2)
        $angle = 9.0 * [Math]::Sin([Math]::PI * (($ms % 1040) / 520.0))
        if ($S.failed) { $angle = -16.0 }
        $g.RotateTransform([float]$angle)
        $g.DrawImage($logo, (-$side / 2), (-$side / 2), $side, $side)
        $g.Restore($state)
        if (-not $S.failed) {
            $direction = 1.0
            if ([Math]::Sin(2 * [Math]::PI * (($ms % 2200) / 2200.0)) -lt 0) { $direction = -1.0 }
            for ($k = 1; $k -le 4; $k++) {
                $alpha = [int](255 * [Math]::Max(0.0, 0.5 - $k * 0.1))
                $dot = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb($alpha, $fill))
                $dr = (Px 3.2) - $k * (Px 0.45)
                $dx = $cx - $direction * ($side * 0.35 + $k * (Px 7))
                $g.FillEllipse($dot, $dx - $dr, $trackY - (Px 5) - $dr, $dr * 2, $dr * 2)
                $dot.Dispose()
            }
        }
    }

    $line = ''
    if ($S.failed) { $line = [string]$texts.failed_body }
    elseif ($jokes.Count -gt 0) { $line = $jokes[$S.jokeIndex % $jokes.Count] }
    $lineTop = $trackY + (Px 22)
    $lineHeight = Px 40
    $rect = New-Object System.Drawing.RectangleF($left, $lineTop, $trackW, $lineHeight)
    $lineBrush = $mutedBrush
    if ($S.failed) { $lineBrush = $textBrush }
    $g.DrawString($line, $fontJoke, $lineBrush, $rect)
    if (-not $S.failed) { $g.DrawString([string]$texts.footer, $fontFoot, $mutedBrush, $left, $h - (Px 44)) }
    $textBrush.Dispose()
    $mutedBrush.Dispose()
}

$width = [int](Px 640)
$height = [int](Px 380)

if (-not [string]::IsNullOrWhiteSpace($SnapshotPath)) {
    $S.stage = $SnapshotStage
    if ($SnapshotFailed) { $S.failed = $true; $S.failedAt = Get-Date }
    $bitmap = New-Object System.Drawing.Bitmap($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    Draw-Frame $graphics $width $height 700
    $graphics.Dispose()
    $bitmap.Save($SnapshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bitmap.Dispose()
    exit 0
}

$form = New-Object System.Windows.Forms.Form
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
$form.ShowInTaskbar = $true
$form.TopMost = $true
$form.Text = [string]$texts.window_title
$form.BackColor = $cBack
$form.Size = New-Object System.Drawing.Size($width, $height)
$area = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$cx = [int]$spec.center_x
$cy = [int]$spec.center_y
if ($cx -le 0 -or $cy -le 0) { $cx = $area.Left + $area.Width / 2; $cy = $area.Top + $area.Height / 2 }
$form.Location = New-Object System.Drawing.Point([int]($cx - $width / 2), [int]($cy - $height / 2))
$buffered = [System.Windows.Forms.Control].GetProperty('DoubleBuffered', [System.Reflection.BindingFlags]'NonPublic,Instance')
$buffered.SetValue($form, $true, $null)
try { $form.Icon = [System.Drawing.Icon]::ExtractAssociatedIcon([string]$spec.icon_path) } catch { }

$form.Add_Paint({ param($sender, $e) Draw-Frame $e.Graphics $form.ClientSize.Width $form.ClientSize.Height $S.clock.Elapsed.TotalMilliseconds })
$form.Add_MouseDown({
    param($sender, $e)
    $hx = $form.ClientSize.Width - (Px 48)
    if ($e.X -ge $hx -and $e.Y -le (Px 52)) {
        $form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
    } elseif ($S.failed) {
        Close-Splash 'closed by click after failure'
    }
})
$form.Add_Shown({
    try { [System.IO.File]::WriteAllText([string]$spec.shown_path, 'shown', $utf8NoBom) } catch { }
    Write-Line 'shown'
})

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 33
$timer.Add_Tick({
    $S.ticks++
    if (($S.ticks % 9) -eq 0) { Update-State }
    if (((Get-Date) - $S.jokeAt).TotalSeconds -gt 3.5) { $S.jokeIndex++; $S.jokeAt = Get-Date }
    if ($form.WindowState -ne [System.Windows.Forms.FormWindowState]::Minimized) { $form.Invalidate() }
})
$timer.Start()
Write-Line ('start, old pid ' + [string]$spec.old_pid)
[System.Windows.Forms.Application]::Run($form)
$timer.Stop()
exit 0
"""

__all__ = ["FAILED_LINGER_SECONDS", "READY_TIMEOUT_SECONDS", "SPLASH_SCRIPT", "TOTAL_TIMEOUT_SECONDS"]
