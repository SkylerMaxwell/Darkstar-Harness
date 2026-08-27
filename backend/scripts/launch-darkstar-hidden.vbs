Option Explicit
' SPDX-License-Identifier: Apache-2.0

Dim fso, shell
Dim scriptDirectory, backendDirectory, rootDirectory
Dim batchPath, runtimeDirectory, logPath, commandProcessor
Dim commandLine, exitCode, logFile, message
Dim forwardedArguments, argumentIndex

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
backendDirectory = fso.GetParentFolderName(scriptDirectory)
rootDirectory = fso.GetParentFolderName(backendDirectory)
batchPath = fso.BuildPath(rootDirectory, "Launch_Darkstar.bat")
runtimeDirectory = fso.BuildPath(rootDirectory, ".darkstar-runtime")
logPath = fso.BuildPath(runtimeDirectory, "launcher.log")

If Not fso.FileExists(batchPath) Then
    MsgBox "Darkstar launcher is missing:" & vbCrLf & batchPath, vbCritical, "Darkstar"
    WScript.Quit 1
End If

If Not fso.FolderExists(runtimeDirectory) Then
    fso.CreateFolder runtimeDirectory
End If

Set logFile = fso.CreateTextFile(logPath, True)
logFile.Close
Set logFile = Nothing

commandProcessor = shell.ExpandEnvironmentStrings("%ComSpec%")
If Len(commandProcessor) = 0 Or commandProcessor = "%ComSpec%" Then
    commandProcessor = shell.ExpandEnvironmentStrings("%SystemRoot%") & "\System32\cmd.exe"
End If

If Not fso.FileExists(commandProcessor) Then
    MsgBox "Windows command processor could not be located:" & vbCrLf & commandProcessor, vbCritical, "Darkstar"
    WScript.Quit 1
End If

shell.CurrentDirectory = rootDirectory
shell.Environment("PROCESS")("DARKSTAR_HIDDEN_LAUNCH") = "1"

forwardedArguments = ""
For argumentIndex = 0 To WScript.Arguments.Count - 1
    forwardedArguments = forwardedArguments & " " & Quote(WScript.Arguments(argumentIndex))
Next

' This is the same hidden launch path validated in v4. Window style 0 keeps
' cmd.exe hidden for the full Darkstar session. The BAT remains the real entrypoint.
commandLine = Quote(commandProcessor) & " /d /c call " & Quote(batchPath) & _
              forwardedArguments & " >> " & Quote(logPath) & " 2>&1"
exitCode = shell.Run(commandLine, 0, True)

If exitCode <> 0 Then
    message = "Darkstar could not start (exit code " & CStr(exitCode) & ")." & vbCrLf & vbCrLf & _
              "Startup log:" & vbCrLf & logPath
    MsgBox message, vbCritical, "Darkstar"
End If

WScript.Quit exitCode

Private Function Quote(ByVal value)
    Quote = Chr(34) & Replace(CStr(value), Chr(34), Chr(34) & Chr(34)) & Chr(34)
End Function
