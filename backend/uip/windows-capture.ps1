param([switch]$Persistent) # SPDX-License-Identifier: GPL-3.0-only
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Drawing

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DarkstarWindowCaptureNative {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool PrintWindow(IntPtr hWnd, IntPtr hdcBlt, uint nFlags);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, IntPtr ignored);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("dwmapi.dll")] public static extern int DwmFlush();
    [DllImport("user32.dll", EntryPoint="SetThreadDpiAwarenessContext")]
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr dpiContext);
}
'@

function Read-Payload {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { return [pscustomobject]@{} }
    return $raw | ConvertFrom-Json
}

function Convert-Hwnd([object]$Value) {
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) { throw 'A window handle is required.' }
    [UInt64]$number = if ($text.StartsWith('0x', [System.StringComparison]::OrdinalIgnoreCase)) { [Convert]::ToUInt64($text.Substring(2), 16) } else { [Convert]::ToUInt64($text, 10) }
    $hwnd = [IntPtr]([Int64]$number)
    if ($hwnd -eq [IntPtr]::Zero -or -not [DarkstarWindowCaptureNative]::IsWindow($hwnd)) { throw 'The connected application window no longer exists.' }
    return $hwnd
}

function Invoke-PhysicalPixels([scriptblock]$Action) {
    $previous = [IntPtr]::Zero
    try { $previous = [DarkstarWindowCaptureNative]::SetThreadDpiAwarenessContext([IntPtr](-4)) } catch { }
    try { return & $Action }
    finally { if ($previous -ne [IntPtr]::Zero) { try { [void][DarkstarWindowCaptureNative]::SetThreadDpiAwarenessContext($previous) } catch { } } }
}

function Get-WindowRectangle([IntPtr]$Hwnd) {
    $rect = New-Object DarkstarWindowCaptureNative+RECT
    if (-not [DarkstarWindowCaptureNative]::GetWindowRect($Hwnd, [ref]$rect)) { throw 'Windows could not read the connected application bounds.' }
    $width = [int]($rect.Right - $rect.Left); $height = [int]($rect.Bottom - $rect.Top)
    if ($width -le 0 -or $height -le 0 -or $width -gt 16384 -or $height -gt 16384) { throw "The connected application has invalid capture bounds: ${width}x${height}." }
    return [pscustomobject]@{ x = [int]$rect.Left; y = [int]$rect.Top; width = $width; height = $height }
}

function New-OpaqueBitmap([int]$Width, [int]$Height) {
    return New-Object System.Drawing.Bitmap $Width, $Height, ([System.Drawing.Imaging.PixelFormat]::Format32bppRgb)
}

function Get-BitmapQuality([System.Drawing.Bitmap]$Bitmap) {
    $stepX = [Math]::Max(1, [int][Math]::Floor($Bitmap.Width / 96.0)); $stepY = [Math]::Max(1, [int][Math]::Floor($Bitmap.Height / 96.0))
    [int]$samples = 0; [int]$dark = 0; [int]$bright = 0
    for ($y = 0; $y -lt $Bitmap.Height; $y += $stepY) {
        for ($x = 0; $x -lt $Bitmap.Width; $x += $stepX) {
            $pixel = $Bitmap.GetPixel($x, $y); $peak = [Math]::Max([int]$pixel.R, [Math]::Max([int]$pixel.G, [int]$pixel.B)); $samples += 1
            if ($peak -le 8) { $dark += 1 }; if ($peak -ge 32) { $bright += 1 }
        }
    }
    $darkRatio = if ($samples) { [double]$dark / $samples } else { 1.0 }; $brightRatio = if ($samples) { [double]$bright / $samples } else { 0.0 }
    return [pscustomobject]@{ samples = $samples; darkRatio = $darkRatio; brightRatio = $brightRatio; suspiciousBlack = ($samples -ge 64 -and $darkRatio -ge 0.99 -and $brightRatio -le 0.01) }
}

function New-PrintWindowBitmap([IntPtr]$Hwnd, [object]$Rect) {
    $bitmap = New-OpaqueBitmap $Rect.width $Rect.height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap); $hdc = [IntPtr]::Zero
    try {
        $hdc = $graphics.GetHdc(); $success = [DarkstarWindowCaptureNative]::PrintWindow($Hwnd, $hdc, [UInt32]2)
        if (-not $success) { $graphics.ReleaseHdc($hdc); $hdc = [IntPtr]::Zero; $hdc = $graphics.GetHdc(); $success = [DarkstarWindowCaptureNative]::PrintWindow($Hwnd, $hdc, [UInt32]0) }
        if (-not $success) { $bitmap.Dispose(); return $null }
        return $bitmap
    } finally { if ($hdc -ne [IntPtr]::Zero) { $graphics.ReleaseHdc($hdc) }; $graphics.Dispose() }
}

function Set-CaptureForeground([IntPtr]$Hwnd) {
    if ([DarkstarWindowCaptureNative]::GetForegroundWindow() -eq $Hwnd) { return $true }
    [void][DarkstarWindowCaptureNative]::BringWindowToTop($Hwnd)
    if ([DarkstarWindowCaptureNative]::SetForegroundWindow($Hwnd)) { return $true }
    $foreground = [DarkstarWindowCaptureNative]::GetForegroundWindow(); if ($foreground -eq [IntPtr]::Zero) { return $false }
    $targetThread = [DarkstarWindowCaptureNative]::GetWindowThreadProcessId($Hwnd, [IntPtr]::Zero); $foregroundThread = [DarkstarWindowCaptureNative]::GetWindowThreadProcessId($foreground, [IntPtr]::Zero); $currentThread = [DarkstarWindowCaptureNative]::GetCurrentThreadId()
    $attachedTarget = $targetThread -ne 0 -and $targetThread -ne $currentThread -and [DarkstarWindowCaptureNative]::AttachThreadInput($currentThread, $targetThread, $true)
    $attachedForeground = $foregroundThread -ne 0 -and $foregroundThread -ne $currentThread -and $foregroundThread -ne $targetThread -and [DarkstarWindowCaptureNative]::AttachThreadInput($currentThread, $foregroundThread, $true)
    try { [void][DarkstarWindowCaptureNative]::BringWindowToTop($Hwnd); return [DarkstarWindowCaptureNative]::SetForegroundWindow($Hwnd) -or [DarkstarWindowCaptureNative]::GetForegroundWindow() -eq $Hwnd }
    finally { if ($attachedForeground) { [void][DarkstarWindowCaptureNative]::AttachThreadInput($currentThread, $foregroundThread, $false) }; if ($attachedTarget) { [void][DarkstarWindowCaptureNative]::AttachThreadInput($currentThread, $targetThread, $false) } }
}

function Copy-VisibleWindowPixels([IntPtr]$Hwnd) {
    $rect = Get-WindowRectangle $Hwnd
    $bitmap = New-OpaqueBitmap $rect.width $rect.height; $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    try { $graphics.CopyFromScreen($rect.x, $rect.y, 0, 0, (New-Object System.Drawing.Size $rect.width, $rect.height), [System.Drawing.CopyPixelOperation]::SourceCopy) } finally { $graphics.Dispose() }
    return $bitmap
}

function New-ScreenBitmap([IntPtr]$Hwnd) {
    $previousForeground = [DarkstarWindowCaptureNative]::GetForegroundWindow(); $wasMinimized = [DarkstarWindowCaptureNative]::IsIconic($Hwnd)
    try {
        if ($wasMinimized) { [void][DarkstarWindowCaptureNative]::ShowWindow($Hwnd, 9); Start-Sleep -Milliseconds 140 }
        if (-not (Set-CaptureForeground $Hwnd)) { throw 'Windows would not foreground the target for the visible-pixel capture fallback.' }
        for ($attempt = 0; $attempt -lt 2; $attempt += 1) {
            try { [void][DarkstarWindowCaptureNative]::DwmFlush() } catch { }
            Start-Sleep -Milliseconds $(if ($attempt -eq 0) { 100 } else { 140 })
            $bitmap = Copy-VisibleWindowPixels $Hwnd; $quality = Get-BitmapQuality $bitmap
            if (-not $quality.suspiciousBlack) { return $bitmap }
            $bitmap.Dispose()
        }
        throw 'Windows visible-pixel capture remained effectively black after foregrounding and compositor synchronization. The target may be protected from capture.'
    } finally {
        if ($wasMinimized) { [void][DarkstarWindowCaptureNative]::ShowWindow($Hwnd, 6) }
        if ($previousForeground -ne [IntPtr]::Zero -and $previousForeground -ne $Hwnd) { try { [void](Set-CaptureForeground $previousForeground) } catch { } }
    }
}

function Convert-BitmapResult([System.Drawing.Bitmap]$Bitmap, [string]$Mode) {
    $quality = Get-BitmapQuality $Bitmap; $stream = New-Object System.IO.MemoryStream
    try {
        $Bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        return [pscustomobject]@{ base64 = [Convert]::ToBase64String($stream.ToArray()); width = $Bitmap.Width; height = $Bitmap.Height; captureMode = $Mode; suspiciousBlack = [bool]$quality.suspiciousBlack; darkRatio = $quality.darkRatio; brightRatio = $quality.brightRatio }
    } finally { $stream.Dispose() }
}

function Capture-Window([object]$Payload) {
    $hwnd = Convert-Hwnd $Payload.hwnd
    return Invoke-PhysicalPixels {
        $rect = Get-WindowRectangle $hwnd; $printed = New-PrintWindowBitmap $hwnd $rect
        if ($printed) {
            try { $quality = Get-BitmapQuality $printed; if (-not $quality.suspiciousBlack) { return Convert-BitmapResult $printed 'win32-printwindow' } } finally { $printed.Dispose() }
        }
        $visible = New-ScreenBitmap $hwnd
        try { return Convert-BitmapResult $visible 'win32-visible-pixels' } finally { $visible.Dispose() }
    }
}

function Invoke-DarkstarPayload([object]$Payload) {
    switch (([string]$Payload.operation).ToLowerInvariant()) {
        'capture_window_bitmap' { return Capture-Window $Payload }
        default { throw "Unsupported window capture operation: $($Payload.operation)" }
    }
}

if ($Persistent) {
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }; $requestId = ''
        try { $request = $line | ConvertFrom-Json; $requestId = [string]$request.id; $response = [pscustomobject]@{ id = $requestId; ok = $true; value = (Invoke-DarkstarPayload $request.payload) } }
        catch { $response = [pscustomobject]@{ id = $requestId; ok = $false; error = $_.Exception.Message } }
        [Console]::Out.WriteLine(($response | ConvertTo-Json -Depth 8 -Compress)); [Console]::Out.Flush()
    }
    exit 0
}

try { (Invoke-DarkstarPayload (Read-Payload)) | ConvertTo-Json -Depth 8 -Compress }
catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }
