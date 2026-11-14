//go:build windows

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"errors"
	"fmt"
	"os"
	"sync"
	"unsafe"

	"golang.org/x/sys/windows"
)

// Official WinBase.h ProcThreadAttributeJobList, Windows 10 / Server 2016+.
const attributeJobList = 0x0002000d

func anchor([]string) (int, error) { return 2, errors.New("private anchor is POSIX-only") }

func owned(arguments []string, cancelled <-chan struct{}) (int, error) {
	application, err := windows.UTF16PtrFromString(arguments[0])
	if err != nil {
		return 1, err
	}
	command, err := windows.UTF16PtrFromString(windows.ComposeCommandLine(arguments))
	if err != nil {
		return 1, err
	}
	job, err := windows.CreateJobObject(nil, nil)
	if err != nil {
		return 1, fmt.Errorf("create private job: %w", err)
	}
	// The job has exactly one noninherited handle. Owner death closes it in the
	// kernel. Closing it cannot race CreateProcess and leave a reused raw handle.
	var mu sync.Mutex
	closed := false
	closeJob := func() {
		mu.Lock()
		defer mu.Unlock()
		if !closed {
			closed = true
			_ = windows.CloseHandle(job)
		}
	}
	defer closeJob()
	limits := windows.JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	limits.BasicLimitInformation.LimitFlags = windows.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	if _, err := windows.SetInformationJobObject(job, windows.JobObjectExtendedLimitInformation, uintptr(unsafe.Pointer(&limits)), uint32(unsafe.Sizeof(limits))); err != nil {
		return 1, fmt.Errorf("set kill-on-close job limit: %w", err)
	}
	attributes, err := windows.NewProcThreadAttributeList(2)
	if err != nil {
		return 1, err
	}
	defer attributes.Delete()
	jobs := []windows.Handle{job}
	if err := attributes.Update(attributeJobList, unsafe.Pointer(&jobs[0]), unsafe.Sizeof(jobs[0])); err != nil {
		return 1, fmt.Errorf("atomic job assignment unsupported; refusing unowned fallback: %w", err)
	}
	current, err := windows.GetCurrentProcess()
	if err != nil {
		return 1, err
	}
	handles := make([]windows.Handle, 3)
	defer func() {
		for _, h := range handles {
			if h != 0 {
				_ = windows.CloseHandle(h)
			}
		}
	}()
	for i, file := range []*os.File{os.Stdin, os.Stdout, os.Stderr} {
		if err := windows.DuplicateHandle(current, windows.Handle(file.Fd()), current, &handles[i], 0, true, windows.DUPLICATE_SAME_ACCESS); err != nil {
			return 1, fmt.Errorf("duplicate standard stream: %w", err)
		}
	}
	if err := attributes.Update(windows.PROC_THREAD_ATTRIBUTE_HANDLE_LIST, unsafe.Pointer(&handles[0]), uintptr(len(handles))*unsafe.Sizeof(handles[0])); err != nil {
		return 1, err
	}
	startup := windows.StartupInfoEx{}
	startup.Cb = uint32(unsafe.Sizeof(startup))
	startup.Flags = windows.STARTF_USESTDHANDLES
	startup.StdInput, startup.StdOutput, startup.StdErr = handles[0], handles[1], handles[2]
	startup.ProcThreadAttributeList = attributes.List()
	process := windows.ProcessInformation{}
	go func() { <-cancelled; closeJob() }()
	mu.Lock()
	if closed {
		mu.Unlock()
		return 130, nil
	}
	select {
	case <-cancelled:
		closed = true
		_ = windows.CloseHandle(job)
		mu.Unlock()
		return 130, nil
	default:
	}
	// No BREAKAWAY flags and no post-spawn AssignProcessToJobObject path. Only
	// these three duplicated standard handles, never lease/job handles, inherit.
	err = windows.CreateProcess(application, command, nil, nil, true, windows.EXTENDED_STARTUPINFO_PRESENT|windows.CREATE_NO_WINDOW, nil, nil, &startup.StartupInfo, &process)
	mu.Unlock()
	if err != nil {
		return 1, fmt.Errorf("start atomically owned command: %w", err)
	}
	defer windows.CloseHandle(process.Process)
	defer windows.CloseHandle(process.Thread)
	state, err := windows.WaitForSingleObject(process.Process, windows.INFINITE)
	if err != nil || state != windows.WAIT_OBJECT_0 {
		return 1, fmt.Errorf("wait owned command state %d: %v", state, err)
	}
	var code uint32
	if err := windows.GetExitCodeProcess(process.Process, &code); err != nil {
		return 1, err
	}
	closeJob() // natural launcher exit also terminates descendants holding pipes
	return int(code), nil
}
