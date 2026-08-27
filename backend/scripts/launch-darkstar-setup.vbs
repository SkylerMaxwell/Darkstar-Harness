Option Explicit
' SPDX-License-Identifier: Apache-2.0

Dim fso, shell
Dim scriptDirectory, backendDirectory, rootDirectory
Dim batchPath, commandProcessor, commandLine, exitCode
Dim forwardedArguments, argumentIndex

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
backendDirectory = fso.GetParentFolderName(scriptDirectory)
rootDirectory = fso.GetParentFolderName(backendDirectory)
batchPath = fso.BuildPath(rootDirectory, "Launch_Darkstar.bat")

If Not fso.FileExists(batchPath) Then
    MsgBox "Darkstar launcher is missing:" & vbCrLf & batchPath, vbCritical, "Darkstar"
    WScript.Quit 1
End If

commandProcessor = shell.ExpandEnvironmentStrings("%ComSpec%")
If Len(commandProcessor) = 0 Or commandProcessor = "%ComSpec%" Then
    commandProcessor = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\cmd.exe"
End If

If Not fso.FileExists(commandProcessor) Then
    MsgBox "Windows command processor could not be located:" & vbCrLf & commandProcessor, vbCritical, "Darkstar"
    WScript.Quit 1
End If

shell.CurrentDirectory = rootDirectory
' This helper exists only to make bootstrap visible. It must never carry the
' hidden-launch flag into the setup BAT.
shell.Environment("PROCESS")("DARKSTAR_HIDDEN_LAUNCH") = ""

forwardedArguments = ""
For argumentIndex = 0 To WScript.Arguments.Count - 1
    forwardedArguments = forwardedArguments & " " & Quote(WScript.Arguments(argumentIndex))
Next

' Window style 1 is visible. /c makes the console lifetime exactly the BAT
' lifetime, so it closes automatically once runtime provisioning hands off to
' the normal hidden launcher.
commandLine = Quote(commandProcessor) & " /d /c call " & Quote(batchPath) & forwardedArguments
exitCode = shell.Run(commandLine, 1, True)
WScript.Quit exitCode

Private Function Quote(ByVal value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
