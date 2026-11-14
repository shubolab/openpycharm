//go:build darwin || linux

// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"syscall"
	"time"
)

// The outer guardian remains outside the private session. Only the persistent
// anchor ever signals its own process group. The launcher may exit before its
// children; the anchor keeps that PGID occupied until the final SIGKILL.
func owned(arguments []string, cancelled <-chan struct{}) (int, error) {
	self, err := os.Executable()
	if err != nil {
		return 1, err
	}
	controlR, controlW, err := os.Pipe()
	if err != nil {
		return 1, err
	}
	defer controlR.Close()
	defer controlW.Close()
	statusR, statusW, err := os.Pipe()
	if err != nil {
		return 1, err
	}
	defer statusR.Close()
	defer statusW.Close()
	cmd := exec.Command(self, append([]string{"--anchor", "--"}, arguments...)...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	cmd.ExtraFiles = []*os.File{controlR, statusW}
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	select {
	case <-cancelled:
		return 130, nil
	default:
	}
	if err := cmd.Start(); err != nil {
		return 1, fmt.Errorf("start private session anchor: %w", err)
	}
	_ = controlR.Close()
	_ = statusW.Close()
	wait := make(chan error, 1)
	go func() { wait <- cmd.Wait() }()
	ready := make(chan error, 1)
	go func() {
		var b [1]byte
		_, err := io.ReadFull(statusR, b[:])
		if err == nil && b[0] != 'R' {
			err = errors.New("invalid anchor readiness")
		}
		ready <- err
	}()
	// Before START the anchor cannot launch a command. Killing just this owned
	// process on startup failure therefore cannot leave a target behind.
	select {
	case err := <-ready:
		if err != nil {
			_ = controlW.Close()
			_ = cmd.Process.Kill()
			<-wait
			return 1, err
		}
	case <-cancelled:
		_ = controlW.Close()
		<-wait
		return 130, nil
	case <-time.After(3 * time.Second):
		_ = controlW.Close()
		_ = cmd.Process.Kill()
		<-wait
		return 1, errors.New("anchor readiness timeout")
	}
	select {
	case <-cancelled:
		_ = controlW.Close()
		<-wait
		return 130, nil
	default:
	}
	if _, err := controlW.Write([]byte{'S'}); err != nil {
		_ = controlW.Close()
		<-wait
		return 1, err
	}
	type result struct {
		code int
		err  error
	}
	status := make(chan result, 1)
	go func() {
		var b [5]byte
		_, err := io.ReadFull(statusR, b[:])
		if err == nil && b[0] != 'X' {
			err = errors.New("invalid anchor exit status")
		}
		status <- result{int(binary.BigEndian.Uint32(b[1:])), err}
	}()
	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(signals)
	var exit result
	select {
	case exit = <-status:
	case <-cancelled:
		exit.code = 130
	case <-signals:
		exit.code = 130
	}
	_ = controlW.Close() // independent of a blocked stdin/stdout/stderr pipe
	select {
	case <-wait:
	case <-time.After(5 * time.Second):
		return 1, errors.New("private anchor did not finish cleanup; ownership outcome unknown")
	}
	if exit.err != nil {
		return 1, fmt.Errorf("anchor failed before exit status: %w", exit.err)
	}
	return exit.code, nil
}

func anchor(arguments []string) (int, error) {
	if len(arguments) < 2 || arguments[0] != "--" {
		return 2, errors.New("invalid private anchor command")
	}
	pid := os.Getpid()
	if pid <= 1 || syscall.Getpgrp() != pid {
		return 1, errors.New("anchor is not its own private process group")
	}
	control := os.NewFile(3, "guardian-control")
	status := os.NewFile(4, "guardian-status")
	if control == nil || status == nil {
		return 1, errors.New("missing private anchor channels")
	}
	defer control.Close()
	defer status.Close()
	syscall.CloseOnExec(3)
	syscall.CloseOnExec(4)
	// Caught SIGTERM keeps the anchor alive during group TERM. exec resets this
	// caught disposition for the real target; it does not inherit SIG_IGN.
	term := make(chan os.Signal, 1)
	signal.Notify(term, syscall.SIGTERM, syscall.SIGINT)
	defer signal.Stop(term)
	if _, err := status.Write([]byte{'R'}); err != nil {
		return 1, err
	}
	var start [1]byte
	if _, err := io.ReadFull(control, start[:]); err != nil {
		return 130, nil
	}
	if start[0] != 'S' {
		return 2, errors.New("invalid anchor start token")
	}
	ended := make(chan struct{})
	go func() { var b [1]byte; _, _ = control.Read(b[:]); close(ended) }()
	select {
	case <-ended:
		return 130, nil
	default:
	}
	cmd := exec.Command(arguments[1], arguments[2:]...)
	cmd.Stdin, cmd.Stdout, cmd.Stderr = os.Stdin, os.Stdout, os.Stderr
	code := 1
	if err := cmd.Start(); err == nil {
		wait := make(chan error, 1)
		go func() { wait <- cmd.Wait() }()
		select {
		case err := <-wait:
			code = 0
			if err != nil {
				if e, ok := err.(*exec.ExitError); ok {
					code = e.ExitCode()
					if code < 0 {
						code = 128
					}
				} else {
					code = 1
				}
			}
		case <-ended:
			code = 130
		case <-term:
			code = 130
		}
	} else {
		fmt.Fprintln(os.Stderr, "guardian target:", err)
	}
	var message [5]byte
	message[0] = 'X'
	binary.BigEndian.PutUint32(message[1:], uint32(code))
	_, _ = status.Write(message[:]) // only 5 bytes; a dead outer guardian gives EPIPE
	// Still the live group leader here, so this PGID cannot have been recycled.
	if os.Getpid() != pid || syscall.Getpgrp() != pid {
		return 1, errors.New("private group changed; refusing group signal")
	}
	if err := syscall.Kill(-pid, syscall.SIGTERM); err != nil {
		return 1, err
	}
	time.Sleep(250 * time.Millisecond)
	if err := syscall.Kill(-pid, syscall.SIGKILL); err != nil {
		return 1, err
	}
	return 1, errors.New("private group SIGKILL unexpectedly returned")
}
