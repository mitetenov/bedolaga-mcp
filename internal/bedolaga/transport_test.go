package bedolaga

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func rpcPost(t *testing.T, c *http.Client, base, session, version string, body M) (*http.Response, M) {
	t.Helper()
	if version == "2026-07-28" {
		params := obj(body["params"])
		params["_meta"] = M{"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": M{}}
		body["params"] = params
	}
	b, _ := json.Marshal(body)
	req, _ := http.NewRequest("POST", base+"/", bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json, text/event-stream")
	if session != "" {
		req.Header.Set("Mcp-Session-Id", session)
	}
	if version != "" {
		req.Header.Set("MCP-Protocol-Version", version)
		if version == "2026-07-28" {
			req.Header.Set("Mcp-Method", body["method"].(string))
			if body["method"] == "tools/call" {
				req.Header.Set("Mcp-Name", obj(body["params"])["name"].(string))
			}
		}
	}
	res, e := c.Do(req)
	if e != nil {
		t.Fatal(e)
	}
	defer res.Body.Close()
	raw, _ := io.ReadAll(res.Body)
	var out M
	json.Unmarshal(raw, &out)
	if res.StatusCode == 200 && out == nil {
		t.Fatalf("invalid JSON response: %s", raw)
	}
	return res, out
}
func TestHTTPTransportLifecycle(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `{"id":42,"telegram_id":1,"balance_kopeks":1234}`)
	}))
	defer upstream.Close()
	svc := NewService(func() (Config, error) { return testConfig(upstream.URL), nil })
	defer svc.Close()
	srv := httptest.NewServer(NewHTTPHandler(NewServer(svc)))
	defer srv.Close()
	client := srv.Client()
	initialize := M{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": M{"protocolVersion": "2025-03-26", "capabilities": M{}, "clientInfo": M{"name": "contract-test", "version": "1"}}}
	sessions := []string{}
	for i := 0; i < 2; i++ {
		res, msg := rpcPost(t, client, srv.URL, "", "", initialize)
		id := res.Header.Get("Mcp-Session-Id")
		if res.StatusCode != 200 || id == "" || obj(obj(msg["result"])["serverInfo"])["version"] != Version {
			t.Fatal(res.StatusCode, msg)
		}
		sessions = append(sessions, id)
	}
	if sessions[0] == sessions[1] {
		t.Fatal("session reuse")
	}
	call := M{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": M{"name": "bedolaga_user_get", "arguments": M{"telegram_id": 1}}}
	res, msg := rpcPost(t, client, srv.URL, sessions[0], "", call)
	result := obj(msg["result"])
	if res.StatusCode != 200 || result["structuredContent"] != nil || len(arr(result["content"])) != 1 {
		t.Fatal(msg)
	}
	var envelope M
	json.Unmarshal([]byte(obj(arr(result["content"])[0])["text"].(string)), &envelope)
	if envelope["ok"] != true {
		t.Fatal(envelope)
	}
	req, _ := http.NewRequest("DELETE", srv.URL+"/", nil)
	req.Header.Set("Mcp-Session-Id", sessions[0])
	del, e := client.Do(req)
	if e != nil {
		t.Fatal(e)
	}
	del.Body.Close()
	if del.StatusCode != 200 {
		t.Fatal(del.StatusCode)
	}
	res, _ = rpcPost(t, client, srv.URL, sessions[0], "", call)
	if res.StatusCode != 404 {
		t.Fatal("deleted session still active")
	}
	res, _ = rpcPost(t, client, srv.URL, sessions[1], "", call)
	if res.StatusCode != 200 {
		t.Fatal("sibling session lost")
	}
	discover := M{"jsonrpc": "2.0", "id": 3, "method": "server/discover", "params": M{}}
	res, msg = rpcPost(t, client, srv.URL, "", "2026-07-28", discover)
	if res.StatusCode != 200 || res.Header.Get("Mcp-Session-Id") != "" || obj(msg["result"])["resultType"] != "complete" {
		t.Fatal(res.StatusCode, msg)
	}
	res, msg = rpcPost(t, client, srv.URL, "", "2026-07-28", M{"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
	if res.StatusCode != 200 || len(arr(obj(msg["result"])["tools"])) != 8 {
		t.Fatal(res.StatusCode, msg)
	}
	res, msg = rpcPost(t, client, srv.URL, "", "2026-07-28", call)
	if res.StatusCode != 200 || obj(msg["result"])["structuredContent"] != nil {
		t.Fatal(res.StatusCode, msg)
	}
}
func TestHTTPHostOriginAndHealth(t *testing.T) {
	svc := NewService(func() (Config, error) { t.Error("health contacted upstream"); return Config{}, nil })
	defer svc.Close()
	handler := NewHTTPHandler(NewServer(svc))
	for _, host := range []string{"127.0.0.1:3100", "localhost:3100", "[::1]:3100", "bedolaga-mcp:3100", "attacker.invalid:3100"} {
		req := httptest.NewRequest("POST", "http://"+host+"/", strings.NewReader(`{}`))
		req.Host = host
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if host == "attacker.invalid:3100" {
			if rec.Code != 421 || rec.Body.String() != "Invalid Host header" {
				t.Fatal(rec.Code, rec.Body)
			}
		} else if rec.Code == 421 {
			t.Fatal(host, rec.Body)
		}
	}
	req := httptest.NewRequest("POST", "http://localhost:3100/", strings.NewReader(`{}`))
	req.Header.Set("Origin", "https://attacker.invalid")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != 403 {
		t.Fatal(rec.Code)
	}
	req = httptest.NewRequest("GET", "http://localhost:3100/health", nil)
	rec = httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	var health M
	json.Unmarshal(rec.Body.Bytes(), &health)
	if rec.Code != 200 || len(health) != 3 || health["name"] != Name || health["status"] != "UP" {
		t.Fatal(rec.Code, health)
	}
}
