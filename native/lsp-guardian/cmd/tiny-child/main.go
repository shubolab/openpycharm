// SPDX-License-Identifier: Apache-2.0
// Owned integration fixture only. Never used by the product helper.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

func publish(path string, value any) {
	data, err := json.Marshal(value)
	if err == nil {
		err = os.WriteFile(path+".pending", data, 0600)
	}
	if err == nil {
		err = os.Rename(path+".pending", path)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(98)
	}
}

func ready(dir, name string) {
	publish(filepath.Join(dir, name+".json"), identity())
}

func main() {
	if len(os.Args) < 3 {
		os.Exit(2)
	}
	dir, mode := os.Args[1], os.Args[2]
	switch mode {
	case "echo":
		cwd, _ := os.Getwd()
		publish(filepath.Join(dir, "args.json"), map[string]any{"args": os.Args[3:], "cwd": cwd, "env": os.Getenv("OPC_GUARDIAN_TEST")})
		if _, err := io.Copy(os.Stdout, os.Stdin); err != nil {
			os.Exit(97)
		}
		fmt.Fprint(os.Stderr, "separate stderr 中文😀\r\n")
		os.Exit(7)
	case "tree", "orphan":
		ready(dir, "root")
		self, _ := os.Executable()
		child := exec.Command(self, dir, "sleeper")
		child.Stdin, child.Stdout, child.Stderr = os.Stdin, os.Stdout, os.Stderr
		if err := child.Start(); err != nil {
			os.Exit(96)
		}
		for deadline := time.Now().Add(5 * time.Second); ; {
			if _, err := os.Stat(filepath.Join(dir, "child.json")); err == nil {
				break
			}
			if time.Now().After(deadline) {
				os.Exit(95)
			}
			time.Sleep(time.Millisecond)
		}
		ready(dir, "ready")
		if mode == "orphan" {
			os.Exit(0)
		}
		_ = child.Wait()
	case "sleeper", "sentinel", "leaf":
		ignoreTermination() // ensures final KILL, rather than just TERM, is tested
		name := "child"
		if mode == "sentinel" {
			name = "sentinel"
		}
		if mode == "leaf" {
			name = "grandchild"
		}
		if mode == "sleeper" {
			self, _ := os.Executable()
			leaf := exec.Command(self, dir, "leaf")
			leaf.Stdin, leaf.Stdout, leaf.Stderr = os.Stdin, os.Stdout, os.Stderr
			if err := leaf.Start(); err != nil {
				os.Exit(94)
			}
			for deadline := time.Now().Add(5 * time.Second); ; {
				if _, err := os.Stat(filepath.Join(dir, "grandchild.json")); err == nil {
					break
				}
				if time.Now().After(deadline) {
					os.Exit(93)
				}
				time.Sleep(time.Millisecond)
			}
		}
		ready(dir, name)
		time.Sleep(45 * time.Second)
	case "blocked":
		ignoreTermination()
		ready(dir, "root")
		// The fixture deliberately never reads protocol stdin.
		time.Sleep(45 * time.Second)
	case "blocked-output":
		ignoreTermination()
		ready(dir, "root")
		b := make([]byte, 65536)
		for {
			if _, err := os.Stdout.Write(b); err != nil {
				os.Exit(0)
			}
		}
	default:
		os.Exit(2)
	}
}
