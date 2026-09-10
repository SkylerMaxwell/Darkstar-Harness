//go:build windows

package main

import (
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	_ "embed"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

// The production build stages gzip-compressed copies of the two Darkstar
// monoliths beside this source before invoking `go build`.
//
//go:embed embedded/Darkstar_Core.js.gz
var embeddedCoreGzip []byte

//go:embed embedded/Darkstar_Renderer.js.gz
var embeddedRendererGzip []byte

const (
	maxPathChars       = 32768
	createNewConsole   = 0x00000010
	compiledBuildLabel = "Darkstar compiled-core launcher"
)

type previousFile struct {
	path    string
	existed bool
	data    []byte
	mode    os.FileMode
}

func main() {
	runtime.LockOSThread()

	root, err := executableRoot()
	if err != nil {
		fatalDialog("Could not resolve the Darkstar executable directory.\n\n" + err.Error())
		return
	}
	if err := os.Chdir(root); err != nil {
		fatalDialog("Could not enter the Darkstar installation directory.\n\n" + err.Error())
		return
	}

	core, err := ungzipEmbedded(embeddedCoreGzip)
	if err != nil {
		fatalDialog("The embedded Darkstar Core payload is invalid.\n\n" + err.Error())
		return
	}
	renderer, err := ungzipEmbedded(embeddedRendererGzip)
	if err != nil {
		fatalDialog("The embedded Darkstar Renderer payload is invalid.\n\n" + err.Error())
		return
	}

	corePath := filepath.Join(root, "backend", "Darkstar_Core.js")
	rendererPath := filepath.Join(root, "backend", "Darkstar_Renderer.js")

	corePrevious, err := materialize(corePath, core)
	if err != nil {
		fatalDialog("Could not materialize the embedded Darkstar Core.\n\n" + err.Error())
		return
	}
	rendererPrevious, err := materialize(rendererPath, renderer)
	if err != nil {
		_ = restore(corePrevious)
		fatalDialog("Could not materialize the embedded Darkstar Renderer.\n\n" + err.Error())
		return
	}

	// Restore developer copies if they existed before launch; otherwise remove
	// the runtime materializations after Electron exits.
	defer restoreQuiet(rendererPrevious)
	defer restoreQuiet(corePrevious)

	if err := ensureRuntime(root); err != nil {
		fatalDialog(err.Error())
		return
	}

	electron := filepath.Join(root, "backend", "vendor", "electron", "win32-x64", "electron.exe")
	if !isFile(electron) {
		fatalDialog("Darkstar Electron runtime is missing after bootstrap.")
		return
	}

	appPath := filepath.Join(root, "backend", "shell")
	args := append([]string{appPath}, os.Args[1:]...)
	cmd := exec.Command(electron, args...)
	cmd.Dir = root
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

	if err := cmd.Run(); err != nil {
		if exitErr, ok := err.(*exec.ExitError); ok && exitErr.ExitCode() != 0 {
			fatalDialog(fmt.Sprintf("Darkstar exited unexpectedly (exit code %d).", exitErr.ExitCode()))
			return
		}
		fatalDialog("Could not start Darkstar Electron runtime.\n\n" + err.Error())
	}
}

func executableRoot() (string, error) {
	exe, err := os.Executable()
	if err != nil {
		return "", err
	}
	exe, err = filepath.Abs(exe)
	if err != nil {
		return "", err
	}
	if len(exe) > maxPathChars {
		return "", fmt.Errorf("installation path exceeds %d characters", maxPathChars)
	}
	return filepath.Dir(exe), nil
}

func ungzipEmbedded(payload []byte) ([]byte, error) {
	reader, err := gzip.NewReader(bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	return io.ReadAll(reader)
}

func materialize(path string, data []byte) (previousFile, error) {
	previous := previousFile{path: path}
	if info, err := os.Stat(path); err == nil {
		previous.existed = true
		previous.mode = info.Mode()
		previous.data, err = os.ReadFile(path)
		if err != nil {
			return previous, err
		}
	} else if !os.IsNotExist(err) {
		return previous, err
	}

	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return previous, err
	}

	tmp := path + fmt.Sprintf(".embedded-%d.tmp", time.Now().UnixNano())
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return previous, err
	}
	_ = os.Remove(path)
	if err := os.Rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return previous, err
	}
	return previous, nil
}

func restore(previous previousFile) error {
	if previous.existed {
		mode := previous.mode.Perm()
		if mode == 0 {
			mode = 0o644
		}
		return os.WriteFile(previous.path, previous.data, mode)
	}
	if err := os.Remove(previous.path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func restoreQuiet(previous previousFile) {
	_ = restore(previous)
}

func ensureRuntime(root string) error {
	if !pythonPresent(root) {
		script := filepath.Join(root, "backend", "scripts", "bootstrap-python.ps1")
		if !isFile(script) {
			return fmt.Errorf("Python bootstrap helper is missing: %s", script)
		}
		if err := runPowerShell(root, script); err != nil {
			return fmt.Errorf("Darkstar Python bootstrap failed.\n\n%w", err)
		}
	}

	probes := []struct {
		relative string
		script   string
		label    string
	}{
		{"backend/vendor/electron/win32-x64/electron.exe", "backend/scripts/bootstrap-electron.ps1", "Electron"},
		{"backend/bin/backends/cpu/llama-server.exe", "backend/scripts/bootstrap-llamacpp.ps1", "native runtime"},
		{"backend/bin/backends/vulkan/llama-server.exe", "backend/scripts/bootstrap-llamacpp.ps1", "native runtime"},
		{"backend/bin/backends/cuda/llama-server.exe", "backend/scripts/bootstrap-llamacpp.ps1", "native runtime"},
		{"backend/bin/diffusion/cpu/sd-cli.exe", "backend/scripts/bootstrap-llamacpp.ps1", "diffusion runtime"},
		{"backend/bin/diffusion/vulkan/sd-cli.exe", "backend/scripts/bootstrap-llamacpp.ps1", "diffusion runtime"},
	}

	for _, probe := range probes {
		target := filepath.Join(root, filepath.FromSlash(probe.relative))
		if isFile(target) {
			continue
		}
		script := filepath.Join(root, filepath.FromSlash(probe.script))
		if !isFile(script) {
			return fmt.Errorf("Darkstar %s bootstrap helper is missing: %s", probe.label, script)
		}
		if err := runPowerShell(root, script); err != nil {
			return fmt.Errorf("Darkstar %s bootstrap failed.\n\n%w", probe.label, err)
		}
	}
	return nil
}

func pythonPresent(root string) bool {
	if isFile(filepath.Join(root, ".darkstar-runtime", "python-install.json")) {
		return true
	}
	if candidate := strings.TrimSpace(os.Getenv("DARKSTAR_PYTHON")); candidate != "" && isFile(candidate) {
		return true
	}
	if local := strings.TrimSpace(os.Getenv("LOCALAPPDATA")); local != "" {
		if isFile(filepath.Join(local, "Programs", "Python", "Python311", "python.exe")) {
			return true
		}
	}
	if programFiles := strings.TrimSpace(os.Getenv("ProgramFiles")); programFiles != "" {
		if isFile(filepath.Join(programFiles, "Python311", "python.exe")) {
			return true
		}
	}
	return false
}

func runPowerShell(root, script string) error {
	cmd := exec.Command(
		"powershell.exe",
		"-NoLogo",
		"-NoProfile",
		"-ExecutionPolicy", "Bypass",
		"-File", script,
	)
	cmd.Dir = root
	cmd.Stdin = nil
	cmd.Stdout = nil
	cmd.Stderr = nil
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: createNewConsole}
	return cmd.Run()
}

func isFile(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func payloadHash(data []byte) string {
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:])
}

func fatalDialog(message string) {
	// Also write a deterministic diagnostic file for headless/support cases.
	if root, err := executableRoot(); err == nil {
		logLine := fmt.Sprintf("%s\r\n%s\r\n", compiledBuildLabel, message)
		_ = os.WriteFile(filepath.Join(root, "Darkstar-launch-error.txt"), []byte(logLine), 0o644)
	}

	user32 := syscall.NewLazyDLL("user32.dll")
	proc := user32.NewProc("MessageBoxW")
	text, _ := syscall.UTF16PtrFromString(message)
	title, _ := syscall.UTF16PtrFromString("Darkstar")
	const mbOKIconError = 0x00000010
	proc.Call(0, uintptr(unsafe.Pointer(text)), uintptr(unsafe.Pointer(title)), mbOKIconError)
}

// Keep the hash helper linked into the build so post-build tooling can compare
// the executable's embedded payload manifest logic with the staged source.
var _ = payloadHash
