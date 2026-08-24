// SPDX-License-Identifier: GPL-3.0-only
//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	createNoWindow = 0x08000000
	mbOK           = 0x00000000
	mbIconError    = 0x00000010
)

var (
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	allocConsole    = kernel32.NewProc("AllocConsole")
	setConsoleTitle = kernel32.NewProc("SetConsoleTitleW")
	user32          = syscall.NewLazyDLL("user32.dll")
	messageBoxWProc = user32.NewProc("MessageBoxW")
)

func main() {
	root, err := launcherRoot()
	if err != nil {
		showError("Darkstar Harness", fmt.Sprintf("Could not determine the Darkstar installation directory.\n\n%v", err))
		os.Exit(1)
	}

	console, forwarded := splitLauncherArgs(os.Args[1:])
	batPath := filepath.Join(root, "Darkstar.bat")
	if info, statErr := os.Stat(batPath); statErr != nil || info.IsDir() {
		showError("Darkstar Harness", "Darkstar.bat is missing from the application directory:\n\n"+batPath)
		os.Exit(1)
	}

	cmdPath, commandErr := resolveCommandProcessor()
	if commandErr != nil {
		showError("Darkstar Harness", commandErr.Error())
		os.Exit(2)
	}
	commandLine, commandErr := buildCommandProcessorLine(cmdPath, forwarded)
	if commandErr != nil {
		showError("Darkstar Harness", commandErr.Error())
		os.Exit(2)
	}
	cmd := exec.Command(cmdPath)
	// cmd.exe does not use CommandLineToArgvW-compatible parsing. Supplying
	// Args here would make os/exec apply the wrong quoting rules; use the raw
	// Windows command line instead.
	cmd.Args = nil
	cmd.Dir = root
	cmd.SysProcAttr = &syscall.SysProcAttr{CmdLine: commandLine}

	if console {
		if consoleErr := attachTroubleshootingConsole(); consoleErr != nil {
			showError("Darkstar Harness", fmt.Sprintf("Could not create the troubleshooting console.\n\n%v", consoleErr))
			os.Exit(1)
		}
		cmd.Stdin = os.Stdin
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
	} else {
		logPath, logFile, logErr := openLauncherLog(root)
		if logErr != nil {
			showError("Darkstar Harness", fmt.Sprintf("Could not create the hidden-launch log.\n\n%v", logErr))
			os.Exit(1)
		}
		defer logFile.Close()
		_, _ = fmt.Fprintf(logFile, "\r\n[%s] Darkstar.exe hidden launch started.\r\n", time.Now().Format(time.RFC3339))
		cmd.Stdout = logFile
		cmd.Stderr = logFile
		cmd.Stdin = nil
		cmd.Env = append(os.Environ(), "DARKSTAR_HIDDEN_LAUNCH=1", "DARKSTAR_LAUNCHER_LOG="+logPath)
		cmd.SysProcAttr.HideWindow = true
		cmd.SysProcAttr.CreationFlags |= createNoWindow
	}

	if err := cmd.Run(); err != nil {
		exitCode := 1
		if exitErr, ok := err.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		}
		if !console {
			logPath := filepath.Join(root, "backend", "Dev", "Diagnostics", "launcher.log")
			showError("Darkstar Harness", fmt.Sprintf("Darkstar exited with error code %d.\n\nDiagnostics were written to:\n%s\n\nRun \"Darkstar.exe --console\" for an interactive startup console.", exitCode, logPath))
		}
		os.Exit(exitCode)
	}
}

func resolveCommandProcessor() (string, error) {
	candidates := []string{os.Getenv("ComSpec")}
	if systemRoot := os.Getenv("SystemRoot"); systemRoot != "" {
		candidates = append(candidates, filepath.Join(systemRoot, "System32", "cmd.exe"))
	}
	for _, candidate := range candidates {
		if candidate == "" || !filepath.IsAbs(candidate) || !strings.EqualFold(filepath.Base(candidate), "cmd.exe") {
			continue
		}
		if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
			return filepath.Clean(candidate), nil
		}
	}
	return "", fmt.Errorf("Could not locate the Windows command processor (cmd.exe).")
}

func launcherRoot() (string, error) {
	executable, err := os.Executable()
	if err != nil {
		return "", err
	}
	executable, err = filepath.Abs(executable)
	if err != nil {
		return "", err
	}
	return filepath.Dir(executable), nil
}

func attachTroubleshootingConsole() error {
	result, _, callErr := allocConsole.Call()
	if result == 0 {
		return callErr
	}
	title, _ := syscall.UTF16PtrFromString("Darkstar Harness — Console")
	_, _, _ = setConsoleTitle.Call(uintptr(unsafe.Pointer(title)))

	input, err := os.OpenFile("CONIN$", os.O_RDONLY, 0)
	if err != nil {
		return err
	}
	output, err := os.OpenFile("CONOUT$", os.O_WRONLY, 0)
	if err != nil {
		_ = input.Close()
		return err
	}
	errors, err := os.OpenFile("CONOUT$", os.O_WRONLY, 0)
	if err != nil {
		_ = input.Close()
		_ = output.Close()
		return err
	}
	os.Stdin = input
	os.Stdout = output
	os.Stderr = errors
	return nil
}

func openLauncherLog(root string) (string, *os.File, error) {
	diagnosticsDir := filepath.Join(root, "backend", "Dev", "Diagnostics")
	if err := os.MkdirAll(diagnosticsDir, 0o755); err != nil {
		return "", nil, err
	}
	logPath := filepath.Join(diagnosticsDir, "launcher.log")
	file, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return "", nil, err
	}
	return logPath, file, nil
}

func showError(title, message string) {
	titlePtr, _ := syscall.UTF16PtrFromString(title)
	messagePtr, _ := syscall.UTF16PtrFromString(message)
	_, _, _ = messageBoxWProc.Call(0, uintptr(unsafe.Pointer(messagePtr)), uintptr(unsafe.Pointer(titlePtr)), mbOK|mbIconError)
}
