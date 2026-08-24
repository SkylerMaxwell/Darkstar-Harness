// SPDX-License-Identifier: GPL-3.0-only
package main

import (
	"strings"
	"testing"
)

func TestSplitLauncherArgs(t *testing.T) {
	console, forwarded := splitLauncherArgs([]string{"--alpha", "--console", "value", "--CONSOLE"})
	if !console {
		t.Fatal("--console must enable troubleshooting-console mode")
	}
	if got, want := strings.Join(forwarded, "|"), "--alpha|value"; got != want {
		t.Fatalf("forwarded args = %q, want %q", got, want)
	}
}

func TestBuildCommandProcessorLineUsesRelativeBatchEntrypoint(t *testing.T) {
	got, err := buildCommandProcessorLine(`C:\Windows\System32\cmd.exe`, []string{"--alpha", `C:\Model Files\model.gguf`})
	if err != nil {
		t.Fatal(err)
	}
	want := `"C:\Windows\System32\cmd.exe" /d /v:off /c call Darkstar.bat "--alpha" "C:\Model Files\model.gguf"`
	if got != want {
		t.Fatalf("command = %q, want %q", got, want)
	}
	if strings.Contains(got, `C:\Darkstar Harness\Darkstar.bat`) {
		t.Fatal("batch command must not embed the installation path; cmd.Dir owns that path")
	}
}

func TestBuildCommandProcessorLineRejectsWrongProcessor(t *testing.T) {
	if _, err := buildCommandProcessorLine(`C:\Windows\System32\powershell.exe`, nil); err == nil {
		t.Fatal("non-cmd command processor must be rejected")
	}
}

func TestBuildCommandProcessorLineRejectsCmdMetacharacters(t *testing.T) {
	bad := []string{`a&b`, `a|b`, `a>b`, `a<b`, `a^b`, `a%b`, "a\nb", `a"b`}
	for _, value := range bad {
		if _, err := buildCommandProcessorLine(`C:\Windows\System32\cmd.exe`, []string{value}); err == nil {
			t.Fatalf("argument %q must be rejected", value)
		}
	}
}
