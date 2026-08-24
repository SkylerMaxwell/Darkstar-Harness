// SPDX-License-Identifier: GPL-3.0-only
package main

import (
	"fmt"
	"path"
	"strings"
)

const batchEntrypoint = "Darkstar.bat"

func splitLauncherArgs(args []string) (bool, []string) {
	console := false
	forwarded := make([]string, 0, len(args))
	for _, arg := range args {
		if strings.EqualFold(arg, "--console") {
			console = true
			continue
		}
		forwarded = append(forwarded, arg)
	}
	return console, forwarded
}

// buildCommandProcessorLine returns the exact command line passed to Windows
// CreateProcess for cmd.exe. Go's normal os/exec argument quoting is deliberately
// not used here: cmd.exe and batch files use different unquoting rules from
// CommandLineToArgvW. The batch file is addressed relative to cmd.Dir, keeping
// the /C payload independent of spaces in the Darkstar installation path.
func buildCommandProcessorLine(cmdPath string, args []string) (string, error) {
	if strings.ContainsAny(cmdPath, "\x00\r\n\"") {
		return "", fmt.Errorf("invalid command processor path %q", cmdPath)
	}
	if !strings.EqualFold(path.Base(strings.ReplaceAll(cmdPath, `\`, `/`)), "cmd.exe") {
		return "", fmt.Errorf("unsupported command processor %q", cmdPath)
	}

	parts := []string{`"` + cmdPath + `"`, "/d", "/v:off", "/c", "call", batchEntrypoint}
	for _, arg := range args {
		quoted, err := quoteCmdArgument(arg)
		if err != nil {
			return "", err
		}
		parts = append(parts, quoted)
	}
	return strings.Join(parts, " "), nil
}

func quoteCmdArgument(value string) (string, error) {
	// Percent expansion occurs even inside quotes; the other characters below
	// can change cmd.exe syntax. Fail closed instead of trying to emulate the
	// command processor's multiple expansion phases.
	if strings.ContainsAny(value, "\x00\r\n\"&|<>^%") {
		return "", fmt.Errorf("unsupported command-line character in argument %q", value)
	}
	return `"` + value + `"`, nil
}
