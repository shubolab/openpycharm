// SPDX-License-Identifier: Apache-2.0
package main

import (
	"io"
	"net"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestPrivateArguments(t *testing.T) {
	exe := "/owned/fixture"
	if runtime.GOOS == "windows" {
		exe = `C:\owned\fixture.exe`
	}
	valid := []string{"--lease", "127.0.0.1:12345", "--nonce", strings.Repeat("a0", 32), "--", exe, "", "中文😀", `quote"tail\`}
	if got, err := parse(valid); err != nil || len(got.command) != 4 {
		t.Fatalf("valid argv: %+v %v", got, err)
	}
	for _, address := range []string{"0.0.0.0:1", "localhost:1", "[::1]:1", "127.0.0.1:0", "127.0.0.1:65536", "127.0.0.1:01", "192.0.2.1:1"} {
		args := append([]string(nil), valid...)
		args[1] = address
		if _, err := parse(args); err == nil {
			t.Errorf("accepted %q", address)
		}
	}
	for _, nonce := range []string{"", strings.Repeat("a", 63), strings.Repeat("z", 64), strings.Repeat("a", 66)} {
		args := append([]string(nil), valid...)
		args[3] = nonce
		if _, err := parse(args); err == nil {
			t.Errorf("accepted nonce %q", nonce)
		}
	}
	for _, command := range []string{"relative", "", exe + "\x00bad"} {
		args := append([]string(nil), valid...)
		args[5] = command
		if _, err := parse(args); err == nil {
			t.Errorf("accepted command %q", command)
		}
	}
}

func TestIndependentLease(t *testing.T) {
	for _, extra := range []bool{false, true} {
		listener, err := net.Listen("tcp4", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		o := options{address: listener.Addr().String(), nonce: strings.Repeat("ab", 32)}
		server := make(chan net.Conn, 1)
		go func() {
			c, err := listener.Accept()
			if err != nil {
				return
			}
			want := leaseGreeting + o.nonce + "\n"
			b := make([]byte, len(want))
			_, err = io.ReadFull(c, b)
			if err != nil || string(b) != want {
				c.Close()
				return
			}
			_, _ = io.WriteString(c, "OK\n")
			server <- c
		}()
		conn, done, err := connectLease(o)
		if err != nil {
			listener.Close()
			t.Fatal(err)
		}
		peer := <-server
		if extra {
			_, _ = peer.Write([]byte{'!'})
		} else {
			peer.Close()
		}
		select {
		case <-done:
		case <-time.After(time.Second):
			t.Error("independent lease did not cancel")
		}
		conn.Close()
		peer.Close()
		listener.Close()
	}
}

func TestLeaseRejectsWrongAcknowledgement(t *testing.T) {
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()
	go func() {
		c, err := listener.Accept()
		if err == nil {
			defer c.Close()
			_, _ = c.Write([]byte("NO\n"))
		}
	}()
	conn, _, err := connectLease(options{address: listener.Addr().String(), nonce: strings.Repeat("ab", 32)})
	if conn != nil || err == nil {
		t.Fatal("invalid lease was accepted")
	}
}
