param([switch]$Persistent) # SPDX-License-Identifier: Apache-2.0
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;

public static class DarkstarUIPNative {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool IsIconic(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool IsWindow(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode, SetLastError = true)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll", SetLastError = true)] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool AttachThreadInput(uint idAttach, uint idAttachTo, bool fAttach);
    [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")][return: MarshalAs(UnmanagedType.Bool)] public static extern bool GetCursorPos(out POINT lpPoint);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, uint dx, uint dy, uint dwData, UIntPtr dwExtraInfo);
    [DllImport("user32.dll", SetLastError=true)] public static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

    [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public InputUnion U; }
    [StructLayout(LayoutKind.Explicit)] public struct InputUnion { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
    [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public IntPtr dwExtraInfo; }
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
    [UInt64]$number = 0
    if ($text.StartsWith('0x', [System.StringComparison]::OrdinalIgnoreCase)) { $number = [Convert]::ToUInt64($text.Substring(2), 16) }
    else { $number = [Convert]::ToUInt64($text, 10) }
    return [IntPtr]([Int64]$number)
}

function Get-WindowRecords {
    $items = New-Object System.Collections.Generic.List[object]
    $callback = [DarkstarUIPNative+EnumWindowsProc]{
        param([IntPtr]$hWnd, [IntPtr]$lParam)
        try {
            if (-not [DarkstarUIPNative]::IsWindowVisible($hWnd)) { return $true }
            $length = [DarkstarUIPNative]::GetWindowTextLength($hWnd)
            if ($length -le 0) { return $true }
            $builder = New-Object System.Text.StringBuilder ($length + 1)
            [void][DarkstarUIPNative]::GetWindowText($hWnd, $builder, $builder.Capacity)
            $title = $builder.ToString()
            if ([string]::IsNullOrWhiteSpace($title)) { return $true }
            [UInt32]$windowProcessId = 0
            [void][DarkstarUIPNative]::GetWindowThreadProcessId($hWnd, [ref]$windowProcessId)
            $rect = New-Object DarkstarUIPNative+RECT
            [void][DarkstarUIPNative]::GetWindowRect($hWnd, [ref]$rect)
            $items.Add([pscustomobject]@{
                hwnd = ([UInt64]$hWnd.ToInt64()).ToString(); pid = [int]$windowProcessId; title = $title
                minimized = [bool][DarkstarUIPNative]::IsIconic($hWnd)
                bounds = [pscustomobject]@{ x = [int]$rect.Left; y = [int]$rect.Top; width = [Math]::Max(0, [int]($rect.Right - $rect.Left)); height = [Math]::Max(0, [int]($rect.Bottom - $rect.Top)) }
            })
        } catch { }
        return $true
    }
    [void][DarkstarUIPNative]::EnumWindows($callback, [IntPtr]::Zero)
    return $items.ToArray()
}

function Get-ProcessSnapshot {
    try { return @(Get-CimInstance Win32_Process | Select-Object ProcessId, ParentProcessId, Name, ExecutablePath, CommandLine) }
    catch { return @() }
}

function Get-DescendantPids([int]$RootPid, [object[]]$Processes) {
    # PowerShell enumerates IEnumerable return values. A one-item HashSet therefore
    # collapses to a bare Int32 at the caller and breaks set membership checks.
    # A hashtable is emitted as one object and gives us an unambiguous PID set.
    $selected = @{}
    $selected[$RootPid] = $true
    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($process in $Processes) {
            $processId = [int]$process.ProcessId; $parent = [int]$process.ParentProcessId
            if (-not $selected.ContainsKey($processId) -and $selected.ContainsKey($parent)) { $selected[$processId] = $true; $changed = $true }
        }
    }
    return $selected
}

function Public-Process([object]$Process) {
    return [pscustomobject]@{ pid = [int]$Process.ProcessId; parentPid = [int]$Process.ParentProcessId; name = [string]$Process.Name; path = [string]$Process.ExecutablePath; commandLine = [string]$Process.CommandLine }
}

function Get-WindowCatalog {
    $windows = @(Get-WindowRecords); $byPid = @{}
    foreach ($process in @(Get-ProcessSnapshot)) { $byPid[[int]$process.ProcessId] = $process }
    return @($windows | ForEach-Object {
        $process = $byPid[[int]$_.pid]
        [pscustomobject]@{ hwnd = $_.hwnd; pid = $_.pid; title = $_.title; minimized = $_.minimized; bounds = $_.bounds; processName = if ($process) { [string]$process.Name } else { '' }; path = if ($process) { [string]$process.ExecutablePath } else { '' } }
    })
}

function Get-ProcessCatalog {
    return @(Get-ProcessSnapshot | Where-Object { [int]$_.ProcessId -gt 0 -and -not [string]::IsNullOrWhiteSpace([string]$_.Name) } | ForEach-Object { Public-Process $_ })
}

function Describe-Process([object]$Payload) {
    $ownerPid = [int]$Payload.pid
    if ($ownerPid -le 0) { throw 'A live process id is required.' }
    $processes = @(Get-ProcessSnapshot)
    if (-not ($processes | Where-Object { [int]$_.ProcessId -eq $ownerPid } | Select-Object -First 1)) { throw 'The selected process is no longer running.' }
    $pids = Get-DescendantPids $ownerPid $processes
    return [pscustomobject]@{
        ownerPid = $ownerPid
        processes = @($processes | Where-Object { $pids.ContainsKey([int]$_.ProcessId) } | ForEach-Object { Public-Process $_ })
        windows = @(Get-WindowRecords | Where-Object { $pids.ContainsKey([int]$_.pid) })
    }
}

function Describe-Target([object]$Payload) {
    $hwnd = Convert-Hwnd $Payload.hwnd; [UInt32]$ownerPid = 0
    [void][DarkstarUIPNative]::GetWindowThreadProcessId($hwnd, [ref]$ownerPid)
    if ($ownerPid -le 0) { throw 'The selected window no longer has an owning process.' }
    $processes = @(Get-ProcessSnapshot); $pids = Get-DescendantPids ([int]$ownerPid) $processes
    return [pscustomobject]@{
        ownerPid = [int]$ownerPid
        processes = @($processes | Where-Object { $pids.ContainsKey([int]$_.ProcessId) } | ForEach-Object { Public-Process $_ })
        windows = @(Get-WindowRecords | Where-Object { $pids.ContainsKey([int]$_.pid) })
    }
}


function Get-AccessibilityPatterns([System.Windows.Automation.AutomationElement]$Element) {
    $names = New-Object System.Collections.Generic.List[string]
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $names.Add('invoke') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) { $names.Add('value') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { $names.Add('toggle') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $names.Add('select') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { $names.Add('expand-collapse') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$pattern)) { $names.Add('scroll-item') }
    return $names.ToArray()
}

function Convert-FiniteNumber([double]$Value) {
    if ([double]::IsNaN($Value) -or [double]::IsInfinity($Value)) { return $null }
    return $Value
}

function Public-AccessibilityElement([System.Windows.Automation.AutomationElement]$Element, [string]$Path, [int]$Depth) {
    $current = $Element.Current; $rect = $current.BoundingRectangle; $value = ''
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) {
        try { $value = [string]([System.Windows.Automation.ValuePattern]$pattern).Current.Value } catch { $value = '' }
    }
    return [pscustomobject]@{
        path = $Path; depth = $Depth; name = [string]$current.Name; value = $value
        automationId = [string]$current.AutomationId; className = [string]$current.ClassName
        controlType = ([string]$current.ControlType.ProgrammaticName).Replace('ControlType.', '')
        enabled = [bool]$current.IsEnabled; offscreen = [bool]$current.IsOffscreen; focusable = [bool]$current.IsKeyboardFocusable
        bounds = [pscustomobject]@{ x = Convert-FiniteNumber ([double]$rect.X); y = Convert-FiniteNumber ([double]$rect.Y); width = Convert-FiniteNumber ([double]$rect.Width); height = Convert-FiniteNumber ([double]$rect.Height) }
        patterns = @(Get-AccessibilityPatterns $Element)
    }
}

function Get-AccessibilityRoot([object]$Payload) {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
    $hwnd = Convert-Hwnd $Payload.hwnd
    $root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
    if (-not $root) { throw 'Chromium accessibility could not access the selected window.' }
    return $root
}

function Find-ElementAtPath([System.Windows.Automation.AutomationElement]$Root, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Root }
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker; $current = $Root
    foreach ($part in $Path.Split('/')) {
        if ($part -eq '') { continue }
        $wanted = [int]$part; $child = $walker.GetFirstChild($current); $index = 0
        while ($child -and $index -lt $wanted) { $child = $walker.GetNextSibling($child); $index += 1 }
        if (-not $child) { throw "Chromium accessibility path no longer exists: $Path" }
        $current = $child
    }
    return $current
}

function Find-WebRoot([System.Windows.Automation.AutomationElement]$Root) {
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $queue = New-Object System.Collections.Queue
    $queue.Enqueue([pscustomobject]@{ element = $Root; path = ''; depth = 0 })
    $visited = 0
    while ($queue.Count -gt 0 -and $visited -lt 1500) {
        $item = $queue.Dequeue(); $visited += 1
        try {
            $current = $item.element.Current
            $type = ([string]$current.ControlType.ProgrammaticName).Replace('ControlType.', '')
            if ([string]$current.AutomationId -eq 'RootWebArea' -or $type -eq 'Document') { return $item }
        } catch { }
        if ($item.depth -ge 12) { continue }
        $child = $walker.GetFirstChild($item.element); $index = 0
        while ($child) {
            $path = if ([string]::IsNullOrEmpty($item.path)) { [string]$index } else { "$($item.path)/$index" }
            $queue.Enqueue([pscustomobject]@{ element = $child; path = $path; depth = ($item.depth + 1) })
            $child = $walker.GetNextSibling($child); $index += 1
        }
    }
    return [pscustomobject]@{ element = $Root; path = ''; depth = 0 }
}

function Inspect-ChromiumAccessibility([object]$Payload) {
    $root = Get-AccessibilityRoot $Payload; $start = [pscustomobject]@{ element = $root; path = ''; depth = 0 }
    if ($Payload.webOnly -eq $true) { $start = Find-WebRoot $root }
    $maxDepth = [Math]::Max(0, [Math]::Min(32, [int]$(if ($null -ne $Payload.maxDepth) { $Payload.maxDepth } else { 20 })))
    $maxElements = [Math]::Max(1, [Math]::Min(5000, [int]$(if ($null -ne $Payload.maxElements) { $Payload.maxElements } else { 2000 })))
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker; $output = New-Object System.Collections.Generic.List[object]
    function Walk-Accessibility([System.Windows.Automation.AutomationElement]$Element, [string]$Path, [int]$Depth) {
        if ($output.Count -ge $maxElements) { return }
        try { $output.Add((Public-AccessibilityElement $Element $Path $Depth)) } catch { return }
        if ($Depth -ge $maxDepth) { return }
        $child = $walker.GetFirstChild($Element); $index = 0
        while ($child -and $output.Count -lt $maxElements) {
            $childPath = if ([string]::IsNullOrEmpty($Path)) { [string]$index } else { "$Path/$index" }
            Walk-Accessibility $child $childPath ($Depth + 1)
            $child = $walker.GetNextSibling($child); $index += 1
        }
    }
    Walk-Accessibility $start.element $start.path 0
    $rootPublic = if ($output.Count -gt 0) { $output[0] } else { $null }
    return [pscustomobject]@{ elements = $output.ToArray(); truncated = ($output.Count -ge $maxElements); rootPath = $start.path; rootBounds = if ($rootPublic) { $rootPublic.bounds } else { $null } }
}

function Act-ChromiumAccessibility([object]$Payload) {
    $root = Get-AccessibilityRoot $Payload; $element = Find-ElementAtPath $root ([string]$Payload.elementPath)
    $action = ([string]$Payload.action).ToLowerInvariant(); $pattern = $null
    switch ($action) {
        'focus' { $element.SetFocus() }
        'invoke' {
            if (-not $element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { throw 'Element does not support InvokePattern.' }
            $previousForeground = [DarkstarUIPNative]::GetForegroundWindow()
            ([System.Windows.Automation.InvokePattern]$pattern).Invoke()
            if ($previousForeground -ne [IntPtr]::Zero -and [DarkstarUIPNative]::GetForegroundWindow() -ne $previousForeground) { [void](Set-WindowForeground $previousForeground $false) }
        }
        'scroll_into_view' {
            if ($element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$pattern)) { ([System.Windows.Automation.ScrollItemPattern]$pattern).ScrollIntoView() }
        }
        default { throw "Unsupported Chromium accessibility action: $action" }
    }
    return [pscustomobject]@{ success = $true; element = (Public-AccessibilityElement $element ([string]$Payload.elementPath) 0) }
}

function HitTest-ChromiumAccessibility([object]$Payload) {
    Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase
    $point = New-Object System.Windows.Point -ArgumentList @([double]$Payload.x, [double]$Payload.y)
    $element = [System.Windows.Automation.AutomationElement]::FromPoint($point)
    if (-not $element) { return [pscustomobject]@{ ok = $false } }
    return [pscustomobject]@{ ok = $true; element = (Public-AccessibilityElement $element '' 0) }
}

function Set-WindowForeground([IntPtr]$Hwnd, [bool]$ThrowOnFailure) {
    if ($Hwnd -eq [IntPtr]::Zero -or -not [DarkstarUIPNative]::IsWindow($Hwnd)) { if ($ThrowOnFailure) { throw 'UIP target window no longer exists.' }; return $false }
    if ([DarkstarUIPNative]::IsIconic($Hwnd)) { [void][DarkstarUIPNative]::ShowWindow($Hwnd, 9) }
    [UInt32]$targetPid = 0; $targetThread = [DarkstarUIPNative]::GetWindowThreadProcessId($Hwnd, [ref]$targetPid)
    $currentThread = [DarkstarUIPNative]::GetCurrentThreadId(); $attached = $false
    try {
        if ($targetThread -ne 0 -and $targetThread -ne $currentThread) { $attached = [DarkstarUIPNative]::AttachThreadInput($currentThread, $targetThread, $true) }
        [void][DarkstarUIPNative]::BringWindowToTop($Hwnd); [void][DarkstarUIPNative]::SetForegroundWindow($Hwnd)
    } finally {
        if ($attached) { [void][DarkstarUIPNative]::AttachThreadInput($currentThread, $targetThread, $false) }
    }
    for ($i = 0; $i -lt 12; $i += 1) {
        if ([DarkstarUIPNative]::GetForegroundWindow() -eq $Hwnd) { return $true }
        Start-Sleep -Milliseconds 5
    }
    if ($ThrowOnFailure) { throw 'UIP could not bring the selected Chromium/Electron window to the foreground for real input.' }
    return $false
}

function New-KeyInput([UInt16]$VirtualKey, [UInt16]$Scan, [UInt32]$Flags) {
    $input = New-Object DarkstarUIPNative+INPUT; $input.type = 1
    $ki = New-Object DarkstarUIPNative+KEYBDINPUT; $ki.wVk = $VirtualKey; $ki.wScan = $Scan; $ki.dwFlags = $Flags; $ki.time = 0; $ki.dwExtraInfo = [IntPtr]::Zero
    $union = New-Object DarkstarUIPNative+InputUnion; $union.ki = $ki; $input.U = $union; return $input
}

function Send-KeyInput([UInt16]$VirtualKey, [bool]$Down) {
    $flags = if ($Down) { [UInt32]0 } else { [UInt32]2 }
    $input = New-KeyInput $VirtualKey 0 $flags; [void][DarkstarUIPNative]::SendInput(1, @($input), [Runtime.InteropServices.Marshal]::SizeOf([type][DarkstarUIPNative+INPUT]))
}

function Send-UnicodeText([string]$Text) {
    foreach ($character in $Text.ToCharArray()) {
        $code = [UInt16][char]$character
        $down = New-KeyInput 0 $code 4; $up = New-KeyInput 0 $code 6
        [void][DarkstarUIPNative]::SendInput(2, @($down, $up), [Runtime.InteropServices.Marshal]::SizeOf([type][DarkstarUIPNative+INPUT]))
    }
}

function Get-VirtualKey([string]$Key) {
    $k = $Key.ToLowerInvariant()
    $map = @{
        'enter'=0x0D; 'tab'=0x09; 'escape'=0x1B; 'esc'=0x1B; 'backspace'=0x08; 'delete'=0x2E; 'space'=0x20
        'arrowleft'=0x25; 'arrowup'=0x26; 'arrowright'=0x27; 'arrowdown'=0x28; 'home'=0x24; 'end'=0x23; 'pageup'=0x21; 'pagedown'=0x22
        'ctrl'=0x11; 'control'=0x11; 'alt'=0x12; 'shift'=0x10; 'meta'=0x5B; 'win'=0x5B
        'f1'=0x70; 'f2'=0x71; 'f3'=0x72; 'f4'=0x73; 'f5'=0x74; 'f6'=0x75; 'f7'=0x76; 'f8'=0x77; 'f9'=0x78; 'f10'=0x79; 'f11'=0x7A; 'f12'=0x7B
    }
    if ($map.ContainsKey($k)) { return [UInt16]$map[$k] }
    if ($Key.Length -eq 1) {
        $c = [char]$Key.ToUpperInvariant()[0]; $n = [int]$c
        if (($n -ge 48 -and $n -le 57) -or ($n -ge 65 -and $n -le 90)) { return [UInt16]$n }
    }
    throw "Unsupported Chromium input key: $Key"
}

function Modifier-Keys([object]$Modifiers) {
    $result = New-Object System.Collections.Generic.List[UInt16]
    foreach ($modifier in @($Modifiers)) {
        switch (([string]$modifier).ToLowerInvariant()) {
            'ctrl' { $result.Add([UInt16]0x11) }
            'alt' { $result.Add([UInt16]0x12) }
            'shift' { $result.Add([UInt16]0x10) }
            'meta' { $result.Add([UInt16]0x5B) }
        }
    }
    return $result.ToArray()
}

function Mouse-Flag([string]$Button, [bool]$Down) {
    switch ($Button.ToLowerInvariant()) {
        'right' { return [UInt32]$(if ($Down) { 0x0008 } else { 0x0010 }) }
        'middle' { return [UInt32]$(if ($Down) { 0x0020 } else { 0x0040 }) }
        default { return [UInt32]$(if ($Down) { 0x0002 } else { 0x0004 }) }
    }
}

function Invoke-ChromiumInputAction([object]$Action) {
    $type = ([string]$Action.type).ToLowerInvariant(); $button = [string]$(if ($Action.button) { $Action.button } else { 'left' })
    switch ($type) {
        'text' { Send-UnicodeText ([string]$Action.text) }
        'key' {
            $mods = @(Modifier-Keys $Action.modifiers); foreach ($vk in $mods) { Send-KeyInput $vk $true }
            try { $vk = Get-VirtualKey ([string]$Action.key); Send-KeyInput $vk $true; Send-KeyInput $vk $false }
            finally { [array]::Reverse($mods); foreach ($vk in $mods) { Send-KeyInput $vk $false } }
        }
        'key_down' { Send-KeyInput (Get-VirtualKey ([string]$Action.key)) $true }
        'key_up' { Send-KeyInput (Get-VirtualKey ([string]$Action.key)) $false }
        'move' { [void][DarkstarUIPNative]::SetCursorPos([int][Math]::Round([double]$Action.x), [int][Math]::Round([double]$Action.y)) }
        'mouse_down' { [void][DarkstarUIPNative]::SetCursorPos([int]$Action.x, [int]$Action.y); [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $true), 0, 0, 0, [UIntPtr]::Zero) }
        'mouse_up' { [void][DarkstarUIPNative]::SetCursorPos([int]$Action.x, [int]$Action.y); [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $false), 0, 0, 0, [UIntPtr]::Zero) }
        'click' {
            $mods = @(Modifier-Keys $Action.modifiers); foreach ($vk in $mods) { Send-KeyInput $vk $true }
            try {
                [void][DarkstarUIPNative]::SetCursorPos([int][Math]::Round([double]$Action.x), [int][Math]::Round([double]$Action.y))
                $count = [Math]::Max(1, [Math]::Min(3, [int]$(if ($Action.clickCount) { $Action.clickCount } else { 1 })))
                for ($i = 0; $i -lt $count; $i += 1) { [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $true),0,0,0,[UIntPtr]::Zero); [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $false),0,0,0,[UIntPtr]::Zero); if ($count -gt 1) { Start-Sleep -Milliseconds 60 } }
            } finally { [array]::Reverse($mods); foreach ($vk in $mods) { Send-KeyInput $vk $false } }
        }
        'drag' {
            $sx=[double]$Action.startX; $sy=[double]$Action.startY; $ex=[double]$Action.endX; $ey=[double]$Action.endY
            $steps=[Math]::Max(2,[Math]::Min(60,[int]$(if($Action.steps){$Action.steps}else{12}))); $duration=[Math]::Max(0,[Math]::Min(5000,[int]$(if($Action.durationMs){$Action.durationMs}else{300})))
            [void][DarkstarUIPNative]::SetCursorPos([int][Math]::Round($sx),[int][Math]::Round($sy)); [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $true),0,0,0,[UIntPtr]::Zero)
            try { for($i=1;$i -le $steps;$i+=1){ $r=[double]$i/$steps; [void][DarkstarUIPNative]::SetCursorPos([int][Math]::Round($sx+($ex-$sx)*$r),[int][Math]::Round($sy+($ey-$sy)*$r)); if($duration -gt 0){Start-Sleep -Milliseconds ([Math]::Max(1,[int]($duration/$steps)))}} }
            finally { [DarkstarUIPNative]::mouse_event((Mouse-Flag $button $false),0,0,0,[UIntPtr]::Zero) }
        }
        'wheel' { [void][DarkstarUIPNative]::SetCursorPos([int]$Action.x,[int]$Action.y); [DarkstarUIPNative]::mouse_event(0x0800,0,0,[UInt32][int](-1 * [double]$Action.deltaY),[UIntPtr]::Zero) }
        'release_all' { foreach($vk in @([UInt16]0x10,[UInt16]0x11,[UInt16]0x12,[UInt16]0x5B)){Send-KeyInput $vk $false}; foreach($b in @('left','right','middle')){[DarkstarUIPNative]::mouse_event((Mouse-Flag $b $false),0,0,0,[UIntPtr]::Zero)} }
        default { throw "Unsupported Chromium input operation: $type" }
    }
}

function Send-ChromiumInput([object]$Payload) {
    $hwnd = Convert-Hwnd $Payload.hwnd
    $type = ([string]$Payload.type).ToLowerInvariant()
    $requiresForeground = if ($null -ne $Payload.requiresForeground) { [bool]$Payload.requiresForeground } else { $type -ne 'move' }
    $previous = if ($Payload.restoreForegroundHwnd) { Convert-Hwnd $Payload.restoreForegroundHwnd } else { [DarkstarUIPNative]::GetForegroundWindow() }
    $cursor = New-Object DarkstarUIPNative+POINT
    if ($null -ne $Payload.restoreCursorX -and $null -ne $Payload.restoreCursorY) { $cursor.X = [int]$Payload.restoreCursorX; $cursor.Y = [int]$Payload.restoreCursorY }
    else { [void][DarkstarUIPNative]::GetCursorPos([ref]$cursor) }
    $movesCursor = @('click','drag','wheel','mouse_up').Contains($type)
    $holdLease = [bool]$Payload.holdFocusLease
    try {
        if ($requiresForeground) { [void](Set-WindowForeground $hwnd $true) }
        if ($Payload.elementPath) {
            $root = Get-AccessibilityRoot ([pscustomobject]@{ hwnd = $Payload.hwnd })
            $element = Find-ElementAtPath $root ([string]$Payload.elementPath)
            $element.SetFocus()
        }
        if ($type -eq 'sequence') { foreach ($action in @($Payload.actions)) { Invoke-ChromiumInputAction $action } }
        else { Invoke-ChromiumInputAction $Payload }
    } finally {
        if (-not $holdLease) {
            if ($movesCursor -or [bool]$Payload.releaseFocusLease) { [void][DarkstarUIPNative]::SetCursorPos($cursor.X, $cursor.Y) }
            if ($previous -ne [IntPtr]::Zero -and $previous -ne $hwnd) { [void](Set-WindowForeground $previous $false) }
        }
    }
    return [pscustomobject]@{
        success = $true; type = $type; focusLeaseHeld = $holdLease
        previousForegroundHwnd = if ($previous -eq [IntPtr]::Zero) { '' } else { ([UInt64]$previous.ToInt64()).ToString() }
        previousCursor = [pscustomobject]@{ x = [int]$cursor.X; y = [int]$cursor.Y }
        foregroundRestored = (-not $holdLease -and ($previous -eq [IntPtr]::Zero -or [DarkstarUIPNative]::GetForegroundWindow() -eq $previous))
    }
}

function Invoke-DarkstarPayload([object]$Payload) {
    $operation = ([string]$Payload.operation).ToLowerInvariant()
    $result = switch ($operation) {
        'enumerate_windows' { Get-WindowCatalog }
        'enumerate_processes' { Get-ProcessCatalog }
        'describe_process' { Describe-Process $Payload }
        'describe_target' { Describe-Target $Payload }
        'chromium_accessibility_inspect' { Inspect-ChromiumAccessibility $Payload }
        'chromium_accessibility_action' { Act-ChromiumAccessibility $Payload }
        'chromium_accessibility_hit_test' { HitTest-ChromiumAccessibility $Payload }
        'chromium_input' { Send-ChromiumInput $Payload }
        default { throw "Unsupported UIP Windows operation: $operation" }
    }
    return $result
}

if ($Persistent) {
    while ($null -ne ($line = [Console]::In.ReadLine())) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $requestId = ''
        try {
            $request = $line | ConvertFrom-Json
            $requestId = [string]$request.id
            $response = [pscustomobject]@{ id = $requestId; ok = $true; value = (Invoke-DarkstarPayload $request.payload) }
        } catch {
            $response = [pscustomobject]@{ id = $requestId; ok = $false; error = $_.Exception.Message }
        }
        [Console]::Out.WriteLine(($response | ConvertTo-Json -Depth 12 -Compress)); [Console]::Out.Flush()
    }
    exit 0
}

try {
    (Invoke-DarkstarPayload (Read-Payload)) | ConvertTo-Json -Depth 10 -Compress
} catch {
    [Console]::Error.WriteLine($_.Exception.Message); exit 1
}
