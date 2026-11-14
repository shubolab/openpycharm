//go:build windows

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"golang.org/x/sys/windows"
	"os"
)

func identity() map[string]uint64 {
	current, _ := windows.GetCurrentProcess()
	var created, exited, kernel, user windows.Filetime
	_ = windows.GetProcessTimes(current, &created, &exited, &kernel, &user)
	return map[string]uint64{"pid": uint64(os.Getpid()), "ppid": uint64(os.Getppid()), "created": uint64(created.HighDateTime)<<32 | uint64(created.LowDateTime)}
}
func ignoreTermination() {}
