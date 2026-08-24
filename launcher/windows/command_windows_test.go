// SPDX-License-Identifier: GPL-3.0-only
//go:build windows

package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"testing"
)

func testBatchCommand(t *testing.T, root string, args []string) *exec.Cmd {
	t.Helper()
	cmdPath, err := resolveCommandProcessor()
	if err != nil {
		t.Fatal(err)
	}
	raw, err := buildCommandProcessorLine(cmdPath, args)
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(cmdPath)
	cmd.Args = nil
	cmd.Dir = root
	cmd.SysProcAttr = &syscall.SysProcAttr{CmdLine: raw, HideWindow: true, CreationFlags: createNoWindow}
	return cmd
}

func TestRawCmdLineActuallyRunsDarkstarBatchFromPathWithSpaces(t *testing.T) {
	root := filepath.Join(t.TempDir(), "Darkstar Harness With Spaces")
	if err := os.MkdirAll(root, 0o755); err != nil {
		t.Fatal(err)
	}
	marker := filepath.Join(root, "launcher-marker.txt")
	batch := "@echo off\r\n" +
		"setlocal DisableDelayedExpansion\r\n" +
		"if not \"%~1\"==\"alpha beta\" exit /b 31\r\n" +
		"if not \"%~2\"==\"gamma\" exit /b 32\r\n" +
		">\"%DARKSTAR_TEST_MARKER%\" echo launched\r\n" +
		"exit /b 0\r\n"
	if err := os.WriteFile(filepath.Join(root, batchEntrypoint), []byte(batch), 0o644); err != nil {
		t.Fatal(err)
	}

	cmd := testBatchCommand(t, root, []string{"alpha beta", "gamma"})
	cmd.Env = append(os.Environ(), "DARKSTAR_TEST_MARKER="+marker)
	if output, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("batch invocation failed: %v\n%s", err, output)
	}
	if data, err := os.ReadFile(marker); err != nil || string(data) != "launched\r\n" {
		t.Fatalf("marker = %q, err = %v", data, err)
	}
}

func TestRawCmdLinePreservesBatchExitCode(t *testing.T) {
	root := filepath.Join(t.TempDir(), "Darkstar Harness Exit Code")
	if err := os.MkdirAll(root, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, batchEntrypoint), []byte("@echo off\r\nexit /b 37\r\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	err := testBatchCommand(t, root, nil).Run()
	exitErr, ok := err.(*exec.ExitError)
	if !ok || exitErr.ExitCode() != 37 {
		t.Fatalf("exit error = %#v, want code 37", err)
	}
}
