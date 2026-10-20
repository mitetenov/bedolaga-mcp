package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
	"time"
)

func TestStdioExecutable(t *testing.T) {
	path := filepath.Join(t.TempDir(), "bedolaga-mcp")
	build := exec.Command(filepath.Join(runtime.GOROOT(), "bin", "go"), "build", "-o", path, ".")
	if out, e := build.CombinedOutput(); e != nil {
		t.Fatalf("build: %s %v", out, e)
	}
	cmd := exec.Command(path, "stdio")
	cmd.Env = append(os.Environ(), "BEDOLAGA_API_URL=", "BEDOLAGA_API_KEY=")
	stdin, e := cmd.StdinPipe()
	if e != nil {
		t.Fatal(e)
	}
	stdout, e := cmd.StdoutPipe()
	if e != nil {
		t.Fatal(e)
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if e = cmd.Start(); e != nil {
		t.Fatal(e)
	}
	defer cmd.Process.Kill()
	scanner := bufio.NewScanner(stdout)
	send := func(v any) map[string]any {
		t.Helper()
		if e := json.NewEncoder(stdin).Encode(v); e != nil {
			t.Fatal(e)
		}
		if !scanner.Scan() {
			t.Fatal("missing stdio response", stderr.String())
		}
		var out map[string]any
		if json.Unmarshal(scanner.Bytes(), &out) != nil {
			t.Fatal("non-JSON stdout", scanner.Text())
		}
		return out
	}
	out := send(map[string]any{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": map[string]any{"protocolVersion": "2025-03-26", "capabilities": map[string]any{}, "clientInfo": map[string]any{"name": "process-test", "version": "1"}}})
	if out["error"] != nil {
		t.Fatal(out)
	}
	json.NewEncoder(stdin).Encode(map[string]any{"jsonrpc": "2.0", "method": "notifications/initialized"})
	out = send(map[string]any{"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
	tools := out["result"].(map[string]any)["tools"].([]any)
	if len(tools) != 8 {
		t.Fatal(out)
	}
	out = send(map[string]any{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": map[string]any{"name": "bedolaga_user_get", "arguments": map[string]any{"telegram_id": 1}}})
	result := out["result"].(map[string]any)
	content := result["content"].([]any)
	var envelope map[string]any
	json.Unmarshal([]byte(content[0].(map[string]any)["text"].(string)), &envelope)
	if envelope["ok"] != false || envelope["error"].(map[string]any)["code"] != "not_configured" {
		t.Fatal(out)
	}
	stdin.Close()
	done := make(chan error, 1)
	go func() { done <- cmd.Wait() }()
	select {
	case e := <-done:
		if e != nil {
			t.Fatal(e, stderr.String())
		}
	case <-time.After(5 * time.Second):
		t.Fatal("stdio failed to exit after EOF")
	}
}

func TestLaunchModes(t *testing.T) {
	if e := run([]string{"--version"}); e != nil {
		t.Fatal(e)
	}
	if e := run([]string{"invalid"}); e == nil {
		t.Fatal("invalid command accepted")
	}
	t.Setenv("BEDOLAGA_API_URL", "")
	t.Setenv("BEDOLAGA_API_KEY", "")
	if e := run([]string{"http"}); e == nil {
		t.Fatal("missing upstream configuration accepted")
	}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			t.Error(r.URL.Path)
		}
		w.WriteHeader(200)
	}))
	defer srv.Close()
	u, _ := url.Parse(srv.URL)
	port := strings.Split(u.Host, ":")[1]
	t.Setenv("MCP_HTTP_PORT", port)
	if e := run([]string{"healthcheck"}); e != nil {
		t.Fatal(e)
	}
	t.Setenv("MCP_HTTP_PORT", "")
	t.Setenv("PORT", port)
	if e := run([]string{"healthcheck"}); e != nil {
		t.Fatal(e)
	}
	t.Setenv("MCP_HTTP_PORT", "invalid")
	if e := run([]string{"healthcheck"}); e == nil {
		t.Fatal("invalid port accepted")
	}
}
