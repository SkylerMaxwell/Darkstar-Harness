param([switch]$Persistent) # SPDX-License-Identifier: GPL-3.0-only
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, WindowsBase

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
    if ($number -eq 0) { throw 'The UIA target window handle is invalid.' }
    return [IntPtr]([Int64]$number)
}

function Get-UiaRoot([object]$Payload) {
    $root = [System.Windows.Automation.AutomationElement]::FromHandle((Convert-Hwnd $Payload.hwnd))
    if (-not $root) { throw 'Windows UI Automation could not access the selected window.' }
    return $root
}

function Convert-FiniteNumber([double]$Value) {
    if ([double]::IsNaN($Value) -or [double]::IsInfinity($Value)) { return $null }
    return $Value
}

function Get-UiaPatternNames([object]$Element) {
    $result = New-Object System.Collections.Generic.List[string]
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref]$pattern)) { $result.Add('invoke') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$pattern)) { $result.Add('value') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref]$pattern)) { $result.Add('toggle') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern, [ref]$pattern)) { $result.Add('selection-item') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern, [ref]$pattern)) { $result.Add('expand-collapse') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern, [ref]$pattern)) { $result.Add('scroll-item') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.RangeValuePattern]::Pattern, [ref]$pattern)) { $result.Add('range-value') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.ScrollPattern]::Pattern, [ref]$pattern)) { $result.Add('scroll') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern, [ref]$pattern)) { $result.Add('window') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.TransformPattern]::Pattern, [ref]$pattern)) { $result.Add('transform') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$pattern)) { $result.Add('text') }
    $pattern = $null
    if ($Element.TryGetCurrentPattern([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern, [ref]$pattern)) { $result.Add('legacy-accessible') }
    return $result.ToArray()
}
function Get-Pattern([object]$Element, [object]$PatternId, [string]$DisplayName, [bool]$Required) {
    $pattern = $null
    if ($Element.TryGetCurrentPattern($PatternId, [ref]$pattern)) { return $pattern }
    if ($Required) { throw "Element does not support $DisplayName." }
    return $null
}

function Limit-Text([object]$Value, [int]$Maximum = 4096) {
    $text = [string]$Value
    if ($text.Length -le $Maximum) { return $text }
    return $text.Substring(0, $Maximum)
}

function Get-UiaText([object]$Element, [bool]$IsPassword) {
    if ($IsPassword) { return '' }
    $pattern = Get-Pattern $Element ([System.Windows.Automation.TextPattern]::Pattern) 'TextPattern' $false
    if (-not $pattern) { return '' }
    try {
        return Limit-Text (([System.Windows.Automation.TextPattern]$pattern).DocumentRange.GetText(4096)) 4096
    } catch { return '' }
}

function Public-UiaElement([object]$Element, [string]$Path, [int]$Depth) {
    $current = $Element.Current
    $rect = $current.BoundingRectangle
    $isPassword = [bool]$current.IsPassword
    $value = ''
    $valueReadOnly = $null
    $range = $null
    $toggleState = ''
    $selected = $null
    $expandCollapseState = ''
    $windowState = ''
    $transform = $null
    $legacyRole = 0
    $defaultAction = ''

    if (-not $isPassword) {
        $pattern = Get-Pattern $Element ([System.Windows.Automation.ValuePattern]::Pattern) 'ValuePattern' $false
        if ($pattern) {
            try {
                $valuePattern = [System.Windows.Automation.ValuePattern]$pattern
                $value = Limit-Text ($valuePattern.Current.Value) 4096
                $valueReadOnly = [bool]$valuePattern.Current.IsReadOnly
            } catch { }
        }
    }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.RangeValuePattern]::Pattern) 'RangeValuePattern' $false
    if ($pattern) {
        try {
            $rangePattern = [System.Windows.Automation.RangeValuePattern]$pattern
            $range = [pscustomobject]@{
                value = [double]$rangePattern.Current.Value
                minimum = [double]$rangePattern.Current.Minimum
                maximum = [double]$rangePattern.Current.Maximum
                smallChange = [double]$rangePattern.Current.SmallChange
                largeChange = [double]$rangePattern.Current.LargeChange
                readOnly = [bool]$rangePattern.Current.IsReadOnly
            }
        } catch { $range = $null }
    }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.TogglePattern]::Pattern) 'TogglePattern' $false
    if ($pattern) { try { $toggleState = [string]([System.Windows.Automation.TogglePattern]$pattern).Current.ToggleState } catch { } }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.SelectionItemPattern]::Pattern) 'SelectionItemPattern' $false
    if ($pattern) { try { $selected = [bool]([System.Windows.Automation.SelectionItemPattern]$pattern).Current.IsSelected } catch { } }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'ExpandCollapsePattern' $false
    if ($pattern) { try { $expandCollapseState = [string]([System.Windows.Automation.ExpandCollapsePattern]$pattern).Current.ExpandCollapseState } catch { } }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.WindowPattern]::Pattern) 'WindowPattern' $false
    if ($pattern) { try { $windowState = [string]([System.Windows.Automation.WindowPattern]$pattern).Current.WindowVisualState } catch { } }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.TransformPattern]::Pattern) 'TransformPattern' $false
    if ($pattern) {
        try {
            $transformPattern = [System.Windows.Automation.TransformPattern]$pattern
            $transform = [pscustomobject]@{ canMove = [bool]$transformPattern.Current.CanMove; canResize = [bool]$transformPattern.Current.CanResize; canRotate = [bool]$transformPattern.Current.CanRotate }
        } catch { $transform = $null }
    }

    $pattern = Get-Pattern $Element ([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern) 'LegacyIAccessiblePattern' $false
    if ($pattern) {
        try {
            $legacyPattern = [System.Windows.Automation.LegacyIAccessiblePattern]$pattern
            $legacyRole = [int]$legacyPattern.Current.Role
            $defaultAction = Limit-Text ([string]$legacyPattern.Current.DefaultAction) 512
            if (-not $isPassword -and -not $value) { $value = Limit-Text ($legacyPattern.Current.Value) 4096 }
        } catch { }
    }

    return [pscustomobject]@{
        path = $Path
        depth = $Depth
        name = Limit-Text ([string]$current.Name) 512
        value = $value
        text = Get-UiaText $Element $isPassword
        automationId = Limit-Text ([string]$current.AutomationId) 512
        className = Limit-Text ([string]$current.ClassName) 512
        frameworkId = Limit-Text ([string]$current.FrameworkId) 128
        controlType = ([string]$current.ControlType.ProgrammaticName).Replace('ControlType.', '')
        localizedControlType = Limit-Text ([string]$current.LocalizedControlType) 256
        processId = [int]$current.ProcessId
        enabled = [bool]$current.IsEnabled
        offscreen = [bool]$current.IsOffscreen
        focusable = [bool]$current.IsKeyboardFocusable
        hasKeyboardFocus = [bool]$current.HasKeyboardFocus
        password = $isPassword
        helpText = Limit-Text ([string]$current.HelpText) 1024
        acceleratorKey = Limit-Text ([string]$current.AcceleratorKey) 128
        accessKey = Limit-Text ([string]$current.AccessKey) 128
        bounds = [pscustomobject]@{
            x = Convert-FiniteNumber ([double]$rect.X)
            y = Convert-FiniteNumber ([double]$rect.Y)
            width = Convert-FiniteNumber ([double]$rect.Width)
            height = Convert-FiniteNumber ([double]$rect.Height)
        }
        patterns = @(Get-UiaPatternNames $Element)
        valueReadOnly = $valueReadOnly
        range = $range
        toggleState = $toggleState
        selected = $selected
        expandCollapseState = $expandCollapseState
        windowState = $windowState
        transform = $transform
        legacyRole = $legacyRole
        defaultAction = $defaultAction
    }
}

function Find-UiaElementAtPath([object]$Root, [string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Root }
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $current = $Root
    foreach ($part in $Path.Split('/')) {
        if ($part -eq '') { continue }
        [int]$wanted = 0
        if (-not [int]::TryParse($part, [ref]$wanted) -or $wanted -lt 0) { throw "Invalid UIA element path: $Path" }
        $child = $walker.GetFirstChild($current)
        $index = 0
        while ($child -and $index -lt $wanted) { $child = $walker.GetNextSibling($child); $index += 1 }
        if (-not $child) { throw "UIA element path no longer exists: $Path" }
        $current = $child
    }
    return $current
}

function Assert-UiaElementIdentity([object]$Element, [object]$Expected) {
    if (-not $Expected) { return }
    $current = $Element.Current
    $actualControlType = ([string]$current.ControlType.ProgrammaticName).Replace('ControlType.', '')
    $expectedAutomationId = [string]$Expected.automationId
    $expectedControlType = [string]$Expected.controlType
    $matches = $false
    if (-not [string]::IsNullOrEmpty($expectedAutomationId)) {
        $matches = ([string]$current.AutomationId -ceq $expectedAutomationId) -and ($actualControlType -ceq $expectedControlType)
    } else {
        $matches = ($actualControlType -ceq $expectedControlType) -and
            ([string]$current.Name -ceq [string]$Expected.name) -and
            ([string]$current.ClassName -ceq [string]$Expected.className)
    }
    if (-not $matches) { throw 'Windows UIA element changed before the action could be applied. Take a new snapshot and retry.' }
}

function Inspect-Uia([object]$Payload) {
    $root = Get-UiaRoot $Payload
    $maxDepth = [Math]::Max(0, [Math]::Min(32, [int]$(if ($null -ne $Payload.maxDepth) { $Payload.maxDepth } else { 20 })))
    $maxElements = [Math]::Max(1, [Math]::Min(5000, [int]$(if ($null -ne $Payload.maxElements) { $Payload.maxElements } else { 1200 })))
    $includeOffscreen = [bool]$Payload.includeOffscreen
    $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
    $output = New-Object System.Collections.Generic.List[object]
    $state = [pscustomobject]@{ visited = 0 }

    function Walk-Uia([object]$Element, [string]$Path, [int]$Depth) {
        if ($state.visited -ge $maxElements) { return }
        $state.visited += 1
        try {
            $public = Public-UiaElement $Element $Path $Depth
            if ($includeOffscreen -or -not $public.offscreen -or $Depth -eq 0) { $output.Add($public) }
        } catch { }
        if ($Depth -ge $maxDepth -or $state.visited -ge $maxElements) { return }
        $child = $null
        try { $child = $walker.GetFirstChild($Element) } catch { return }
        $index = 0
        while ($child -and $state.visited -lt $maxElements) {
            $childPath = if ([string]::IsNullOrEmpty($Path)) { [string]$index } else { "$Path/$index" }
            Walk-Uia $child $childPath ($Depth + 1)
            try { $child = $walker.GetNextSibling($child) } catch { $child = $null }
            $index += 1
        }
    }

    Walk-Uia $root '' 0
    $rootPublic = if ($output.Count -gt 0) { $output[0] } else { Public-UiaElement $root '' 0 }
    return [pscustomobject]@{
        elements = $output.ToArray()
        truncated = ($state.visited -ge $maxElements)
        visited = $state.visited
        rootBounds = $rootPublic.bounds
    }
}

function Convert-ScrollAmount([object]$Value) {
    switch (([string]$Value).ToLowerInvariant()) {
        'large_decrement' { return [System.Windows.Automation.ScrollAmount]::LargeDecrement }
        'small_decrement' { return [System.Windows.Automation.ScrollAmount]::SmallDecrement }
        'small_increment' { return [System.Windows.Automation.ScrollAmount]::SmallIncrement }
        'large_increment' { return [System.Windows.Automation.ScrollAmount]::LargeIncrement }
        default { return [System.Windows.Automation.ScrollAmount]::NoAmount }
    }
}

function Convert-WindowState([object]$Value) {
    switch (([string]$Value).ToLowerInvariant()) {
        'minimized' { return [System.Windows.Automation.WindowVisualState]::Minimized }
        'maximized' { return [System.Windows.Automation.WindowVisualState]::Maximized }
        'normal' { return [System.Windows.Automation.WindowVisualState]::Normal }
        default { throw 'window_state must be normal, minimized, or maximized.' }
    }
}

function Invoke-UiaAction([object]$Payload) {
    $root = Get-UiaRoot $Payload
    $path = [string]$Payload.elementPath
    $element = Find-UiaElementAtPath $root $path
    Assert-UiaElementIdentity $element $Payload.expectedIdentity
    $action = ([string]$Payload.action).ToLowerInvariant()
    $pattern = $null

    switch ($action) {
        'focus' { $element.SetFocus() }
        'invoke' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.InvokePattern]::Pattern) 'InvokePattern' $false
            if ($pattern) { ([System.Windows.Automation.InvokePattern]$pattern).Invoke() }
            else {
                $pattern = Get-Pattern $element ([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern) 'InvokePattern or LegacyIAccessiblePattern' $true
                ([System.Windows.Automation.LegacyIAccessiblePattern]$pattern).DoDefaultAction()
            }
        }
        'default_action' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern) 'LegacyIAccessiblePattern' $true
            ([System.Windows.Automation.LegacyIAccessiblePattern]$pattern).DoDefaultAction()
        }
        'set_value' {
            $value = [string]$Payload.value
            $pattern = Get-Pattern $element ([System.Windows.Automation.ValuePattern]::Pattern) 'ValuePattern' $false
            if ($pattern) {
                $typed = [System.Windows.Automation.ValuePattern]$pattern
                if ($typed.Current.IsReadOnly) { throw 'Element ValuePattern is read-only.' }
                $typed.SetValue($value)
            } else {
                $pattern = Get-Pattern $element ([System.Windows.Automation.LegacyIAccessiblePattern]::Pattern) 'ValuePattern or LegacyIAccessiblePattern' $true
                ([System.Windows.Automation.LegacyIAccessiblePattern]$pattern).SetValue($value)
            }
        }
        'toggle' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.TogglePattern]::Pattern) 'TogglePattern' $true
            ([System.Windows.Automation.TogglePattern]$pattern).Toggle()
        }
        'select' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.SelectionItemPattern]::Pattern) 'SelectionItemPattern' $true
            ([System.Windows.Automation.SelectionItemPattern]$pattern).Select()
        }
        'add_to_selection' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.SelectionItemPattern]::Pattern) 'SelectionItemPattern' $true
            ([System.Windows.Automation.SelectionItemPattern]$pattern).AddToSelection()
        }
        'remove_from_selection' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.SelectionItemPattern]::Pattern) 'SelectionItemPattern' $true
            ([System.Windows.Automation.SelectionItemPattern]$pattern).RemoveFromSelection()
        }
        'expand' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'ExpandCollapsePattern' $true
            ([System.Windows.Automation.ExpandCollapsePattern]$pattern).Expand()
        }
        'collapse' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.ExpandCollapsePattern]::Pattern) 'ExpandCollapsePattern' $true
            ([System.Windows.Automation.ExpandCollapsePattern]$pattern).Collapse()
        }
        'scroll_into_view' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.ScrollItemPattern]::Pattern) 'ScrollItemPattern' $true
            ([System.Windows.Automation.ScrollItemPattern]$pattern).ScrollIntoView()
        }
        'set_range_value' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.RangeValuePattern]::Pattern) 'RangeValuePattern' $true
            $typed = [System.Windows.Automation.RangeValuePattern]$pattern
            if ($typed.Current.IsReadOnly) { throw 'Element RangeValuePattern is read-only.' }
            $typed.SetValue([double]$Payload.numberValue)
        }
        'scroll' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.ScrollPattern]::Pattern) 'ScrollPattern' $true
            ([System.Windows.Automation.ScrollPattern]$pattern).Scroll((Convert-ScrollAmount $Payload.horizontalAmount), (Convert-ScrollAmount $Payload.verticalAmount))
        }
        'set_window_state' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.WindowPattern]::Pattern) 'WindowPattern' $true
            ([System.Windows.Automation.WindowPattern]$pattern).SetWindowVisualState((Convert-WindowState $Payload.windowState))
        }
        'close_window' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.WindowPattern]::Pattern) 'WindowPattern' $true
            ([System.Windows.Automation.WindowPattern]$pattern).Close()
            return [pscustomobject]@{ success = $true; action = $action; closed = $true }
        }
        'move' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.TransformPattern]::Pattern) 'TransformPattern' $true
            $typed = [System.Windows.Automation.TransformPattern]$pattern
            if (-not $typed.Current.CanMove) { throw 'Element TransformPattern does not allow moving.' }
            $typed.Move([double]$Payload.x, [double]$Payload.y)
        }
        'resize' {
            $pattern = Get-Pattern $element ([System.Windows.Automation.TransformPattern]::Pattern) 'TransformPattern' $true
            $typed = [System.Windows.Automation.TransformPattern]$pattern
            if (-not $typed.Current.CanResize) { throw 'Element TransformPattern does not allow resizing.' }
            $typed.Resize([double]$Payload.width, [double]$Payload.height)
        }
        default { throw "Unsupported Windows UIA action: $action" }
    }

    Start-Sleep -Milliseconds 20
    $publicElement = $null
    try { $publicElement = Public-UiaElement $element $path 0 } catch { }
    return [pscustomobject]@{ success = $true; action = $action; element = $publicElement }
}

function Invoke-DarkstarPayload([object]$Payload) {
    $operation = ([string]$Payload.operation).ToLowerInvariant()
    $result = switch ($operation) {
        'uia_inspect' { Inspect-Uia $Payload }
        'uia_action' { Invoke-UiaAction $Payload }
        default { throw "Unsupported Windows UIA operation: $operation" }
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
        [Console]::Out.WriteLine(($response | ConvertTo-Json -Depth 14 -Compress)); [Console]::Out.Flush()
    }
    exit 0
}

try {
    (Invoke-DarkstarPayload (Read-Payload)) | ConvertTo-Json -Depth 12 -Compress
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
