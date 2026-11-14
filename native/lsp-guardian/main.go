// SPDX-License-Identifier: Apache-2.0
// Experimental helper, not registered or packaged in OpenPyCharm.
package main

import (
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const leaseGreeting = "OPC-LSP-LEASE/1 "

type options struct {
	address string
	nonce   string
	command []string
}

func parse(arguments []string) (options, error) {
	var o options
	if len(arguments) < 6 || arguments[0] != "--lease" || arguments[2] != "--nonce" || arguments[4] != "--" {
		return o, errors.New("expected --lease 127.0.0.1:port --nonce 64-hex -- absolute-executable [arguments]")
	}
	o.address, o.nonce, o.command = arguments[1], arguments[3], arguments[5:]
	host, port, err := net.SplitHostPort(o.address)
	if err != nil || host != "127.0.0.1" {
		return o, errors.New("lease must use a numeric IPv4 loopback address")
	}
	p, err := strconv.Atoi(port)
	if err != nil || p < 1 || p > 65535 || strconv.Itoa(p) != port {
		return o, errors.New("invalid lease port")
	}
	if raw, err := hex.DecodeString(o.nonce); err != nil || len(raw) != 32 || len(o.nonce) != 64 {
		return o, errors.New("lease nonce must contain exactly 32 random bytes as hex")
	}
	if !filepath.IsAbs(o.command[0]) {
		return o, errors.New("owned executable must be absolute; no shell or PATH lookup")
	}
	for _, arg := range o.command {
		if strings.ContainsRune(arg, 0) {
			return o, errors.New("command argument contains NUL")
		}
	}
	return o, nil
}

// The caller owns the listening socket and its accepted connection. It checks
// the nonce and sends OK\n once. No protocol bytes pass over this socket. A
// separate reader observes EOF (or unexpected data) even when LSP pipes block.
func connectLease(o options) (net.Conn, <-chan struct{}, error) {
	conn, err := net.DialTimeout("tcp4", o.address, 3*time.Second)
	if err != nil {
		return nil, nil, fmt.Errorf("connect owned lease: %w", err)
	}
	fail := func(err error) (net.Conn, <-chan struct{}, error) { _ = conn.Close(); return nil, nil, err }
	if err := conn.SetDeadline(time.Now().Add(3 * time.Second)); err != nil {
		return fail(err)
	}
	if _, err := io.WriteString(conn, leaseGreeting+o.nonce+"\n"); err != nil {
		return fail(err)
	}
	var ack [3]byte
	if _, err := io.ReadFull(conn, ack[:]); err != nil {
		return fail(fmt.Errorf("lease acknowledgement: %w", err))
	}
	if string(ack[:]) != "OK\n" {
		return fail(errors.New("lease acknowledgement rejected"))
	}
	if err := conn.SetDeadline(time.Time{}); err != nil {
		return fail(err)
	}
	done := make(chan struct{})
	go func() {
		var invalid [1]byte
		_, _ = conn.Read(invalid[:])
		close(done)
	}()
	return conn, done, nil
}

func main() {
	if len(os.Args) > 1 && os.Args[1] == "--anchor" {
		code, err := anchor(os.Args[2:])
		if err != nil {
			fmt.Fprintln(os.Stderr, "guardian anchor:", err)
		}
		os.Exit(code)
	}
	o, err := parse(os.Args[1:])
	if err != nil {
		fmt.Fprintln(os.Stderr, "guardian:", err)
		os.Exit(2)
	}
	lease, cancelled, err := connectLease(o)
	if err != nil {
		fmt.Fprintln(os.Stderr, "guardian:", err)
		os.Exit(1)
	}
	code, err := owned(o.command, cancelled)
	_ = lease.Close()
	if err != nil {
		fmt.Fprintln(os.Stderr, "guardian:", err)
	}
	os.Exit(code)
}
