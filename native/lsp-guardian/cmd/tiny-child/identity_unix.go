//go:build darwin || linux

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"os"
	"os/signal"
	"syscall"
)

func identity() map[string]int {
	return map[string]int{"pid": os.Getpid(), "ppid": os.Getppid(), "pgid": syscall.Getpgrp()}
}
func ignoreTermination() { signal.Ignore(syscall.SIGTERM, syscall.SIGINT) }
