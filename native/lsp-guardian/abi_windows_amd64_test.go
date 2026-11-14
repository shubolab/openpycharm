//go:build windows && amd64

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"golang.org/x/sys/windows"
	"testing"
	"unsafe"
)

// Bidirectional constant-array bounds check the actual pinned x/sys layout at
// cross-compile time. This is not a Windows runtime Job ownership assertion.
var _ [112 - int(unsafe.Sizeof(windows.StartupInfoEx{}))]byte
var _ [int(unsafe.Sizeof(windows.StartupInfoEx{})) - 112]byte
var _ [144 - int(unsafe.Sizeof(windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}))]byte
var _ [int(unsafe.Sizeof(windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{})) - 144]byte
var _ [104 - int(unsafe.Offsetof(windows.StartupInfoEx{}.ProcThreadAttributeList))]byte
var _ [int(unsafe.Offsetof(windows.StartupInfoEx{}.ProcThreadAttributeList)) - 104]byte

func TestWindowsOwnershipABI(t *testing.T) {
	if attributeJobList != 0x2000d || windows.PROC_THREAD_ATTRIBUTE_HANDLE_LIST != 0x20002 || windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE != 0x2000 {
		t.Fatal("unexpected public Windows ownership constants")
	}
}
