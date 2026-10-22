package main

import (
	"net/http"
	"net/http/httptest"
	"net/url"

	"strings"
	"testing"
)

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
