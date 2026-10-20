package bedolaga

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"strings"
	"sync"
	"testing"
	"time"
)

func testConfig(api string) Config {
	return Config{APIURL: api, APIKey: "test-secret-never-return", Host: "127.0.0.1", Port: 3100, Timeout: time.Second}
}
func TestConfig(t *testing.T) {
	base := map[string]string{"BEDOLAGA_API_URL": " https://example.invalid/api/ ", "BEDOLAGA_API_KEY": " key ", "MCP_HTTP_HOST": "localhost", "MCP_HTTP_PORT": "3100"}
	env := func(k string) string { return base[k] }
	c, e := LoadConfig(env, false)
	if e != nil || c.APIURL != "https://example.invalid/api" || c.APIKey != "key" || c.Timeout != 10*time.Second {
		t.Fatalf("config: %#v %v", c, e)
	}
	for key, values := range map[string][]string{"BEDOLAGA_API_URL": {"", "ftp://invalid", "https://"}, "BEDOLAGA_API_KEY": {""}, "BEDOLAGA_TIMEOUT_MS": {"-1", "0", "no"}, "MCP_HTTP_HOST": {""}, "MCP_HTTP_PORT": {"0", "65536", "invalid", ""}} {
		for _, value := range values {
			t.Run(key+"="+value, func(t *testing.T) {
				old := base[key]
				base[key] = value
				defer func() { base[key] = old }()
				if _, e := LoadConfig(env, false); e == nil {
					t.Fatal("expected validation error")
				}
			})
		}
	}
	delete(base, "MCP_HTTP_HOST")
	delete(base, "MCP_HTTP_PORT")
	c, e = LoadConfig(env, true)
	if e != nil || c.Host != "0.0.0.0" || c.Port != 3100 {
		t.Fatal(c, e)
	}
	base["HOST"] = "127.0.0.1"
	base["PORT"] = "3200"
	c, e = LoadConfig(env, true)
	if e != nil || c.Host != "127.0.0.1" || c.Port != 3200 {
		t.Fatal(c, e)
	}
}
func TestClientStatusAndShape(t *testing.T) {
	for _, tc := range []struct {
		status            int
		body, shape, code string
		lookup            bool
	}{{404, `{}`, "object", "user_not_found", true}, {404, `{}`, "object", "upstream_unavailable", false}, {401, `{}`, "object", "unauthorized", false}, {403, `{}`, "object", "unauthorized", false}, {429, `{}`, "object", "rate_limited", false}, {422, `{}`, "object", "invalid_input", false}, {500, `{}`, "object", "upstream_unavailable", false}, {302, `{}`, "object", "upstream_unavailable", false}, {400, `{}`, "object", "upstream_unavailable", false}, {200, `not-json-secret`, "object", "invalid_upstream_response", false}, {200, `{} {}`, "object", "invalid_upstream_response", false}, {200, `[]`, "object", "invalid_upstream_response", false}, {200, `{}`, "list", "invalid_upstream_response", false}, {200, `["secret"]`, "list", "invalid_upstream_response", false}, {200, `[]`, "list", "", false}, {200, `{}`, "object", "", false}} {
		t.Run(fmt.Sprintf("%d/%s/%s/%v", tc.status, tc.body, tc.shape, tc.lookup), func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if r.Method != "GET" || r.Header.Get("X-API-Key") != "test-secret-never-return" || r.Header.Get("Authorization") != "" {
					t.Error("upstream contract", r.Method, r.Header)
				}
				w.WriteHeader(tc.status)
				io.WriteString(w, tc.body)
			}))
			defer server.Close()
			c := NewClient(testConfig(server.URL))
			defer c.Close()
			_, e := c.get(context.Background(), "/contract", nil, tc.shape, tc.lookup)
			if tc.code == "" {
				if e != nil {
					t.Fatal(e)
				}
			} else {
				de, ok := e.(*DomainError)
				if !ok || de.Code != tc.code {
					t.Fatalf("want %s got %v", tc.code, e)
				}
				if strings.Contains(fmt.Sprint(ErrorEnvelope("tool", e)), "test-secret") {
					t.Fatal("secret leak")
				}
			}
		})
	}
}
func TestTimeoutAndNetwork(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(25 * time.Millisecond)
		io.WriteString(w, `{}`)
	}))
	defer srv.Close()
	config := testConfig(srv.URL)
	config.Timeout = time.Millisecond
	c := NewClient(config)
	_, e := c.get(context.Background(), "/", nil, "object", false)
	if e.(*DomainError).Code != "upstream_timeout" {
		t.Fatal(e)
	}
	c.Close()
	srv.Close()
	c = NewClient(testConfig(srv.URL))
	_, e = c.get(context.Background(), "/", nil, "object", false)
	if e.(*DomainError).Code != "upstream_unavailable" {
		t.Fatal(e)
	}
}
func TestEveryToolReadOnlyRequestPlan(t *testing.T) {
	var mu sync.Mutex
	requests := []string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		requests = append(requests, r.URL.Path+"?"+r.URL.RawQuery)
		mu.Unlock()
		if r.Method != "GET" || r.Header.Get("Authorization") != "" || r.Header.Get("X-API-Key") != "test-secret-never-return" {
			t.Error("unsafe upstream request")
		}
		w.Header().Set("Content-Type", "application/json")
		switch {
		case strings.HasPrefix(r.URL.Path, "/users/"):
			io.WriteString(w, `{"id":42,"telegram_id":7,"email":"private@example.invalid","balance_kopeks":1234}`)
		case r.URL.Path == "/subscriptions" || r.URL.Path == "/tickets":
			io.WriteString(w, `[]`)
		case strings.HasPrefix(r.URL.Path, "/partners/"):
			io.WriteString(w, `{"referrer":{}}`)
		default:
			io.WriteString(w, `{"items":[],"total":0}`)
		}
	}))
	defer srv.Close()
	svc := NewService(func() (Config, error) { return testConfig(srv.URL), nil })
	defer svc.Close()
	for _, tool := range Tools() {
		t.Run(tool.Name, func(t *testing.T) {
			requests = nil
			out := svc.Call(context.Background(), tool.Name, M{"telegram_id": json.Number("7"), "code": "NOPE"})
			if out["ok"] != true {
				t.Fatal(out)
			}
			if strings.Contains(fmt.Sprint(out), "private@example.invalid") {
				t.Fatal("privacy leak")
			}
			count := map[string]int{"bedolaga_user_get": 1, "bedolaga_billing_get": 4, "bedolaga_referrals_get": 3, "bedolaga_subscription_get": 2, "bedolaga_tickets_get": 2, "bedolaga_payment_status_get": 6, "bedolaga_promocode_check": 2, "bedolaga_gifts_get": 2}[tool.Name]
			if len(requests) != count {
				t.Fatalf("got %v", requests)
			}
			for _, request := range requests[1:] {
				u, _ := url.Parse(request)
				if tool.Name != "bedolaga_promocode_check" && strings.HasPrefix(u.Path, "/transactions") && u.Query().Get("user_id") != "42" {
					t.Fatal("unresolved identity", request)
				}
				if u.Query().Get("offset") != "0" {
					t.Fatal("offset", request)
				}
			}
		})
	}
	if len(Tools()) != 8 {
		t.Fatal("committed tool count")
	}
}
func TestIdentityBoundary(t *testing.T) {
	for _, args := range []M{{}, {"telegram_id": 1, "user_id": 2}, {"telegram_id": 0}, {"user_id": -1}} {
		c := NewClient(testConfig("http://invalid.invalid"))
		svc := NewService(nil)
		_, e := svc.execute(context.Background(), c, "bedolaga_user_get", args)
		if e == nil || e.(*DomainError).Code != "invalid_input" {
			t.Fatalf("%v: %v", args, e)
		}
	}
	svc := NewService(func() (Config, error) { return Config{}, domain("not_configured", "Missing configuration") })
	out := svc.Call(context.Background(), "bedolaga_user_get", M{"telegram_id": 1})
	if obj(out["error"])["code"] != "not_configured" {
		t.Fatal(out)
	}
	svc.Close()
	svc.Close()
}
func TestIdentityUnavailableStopsSecondaryCalls(t *testing.T) {
	for _, id := range []string{`null`, `true`, `0`, `-1`, `"42"`} {
		count := 0
		srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { count++; io.WriteString(w, `{"id":`+id+`}`) }))
		svc := NewService(func() (Config, error) { return testConfig(srv.URL), nil })
		out := svc.Call(context.Background(), "bedolaga_billing_get", M{"user_id": 1})
		if obj(out["error"])["code"] != "identity_unavailable" || count != 1 {
			t.Fatal(out, count)
		}
		svc.Close()
		srv.Close()
	}
}
func TestPromoPaginationBound(t *testing.T) {
	calls := []string{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasPrefix(r.URL.Path, "/users/") {
			io.WriteString(w, `{"id":42}`)
			return
		}
		calls = append(calls, r.URL.Query().Get("offset"))
		items := []any{}
		for i := 0; i < 200; i++ {
			items = append(items, M{"code": "OTHER"})
		}
		json.NewEncoder(w).Encode(M{"items": items, "total": 2000})
	}))
	defer srv.Close()
	svc := NewService(func() (Config, error) { return testConfig(srv.URL), nil })
	defer svc.Close()
	out := svc.Call(context.Background(), "bedolaga_promocode_check", M{"telegram_id": 1, "code": "missing"})
	if !reflect.DeepEqual(calls, []string{"0", "200", "400", "600", "800"}) || obj(out["data"])["reason_code"] != "lookup_incomplete" {
		t.Fatal(out, calls)
	}
}
func TestErrorCatalog(t *testing.T) {
	if len(errorCodes) != 10 {
		t.Fatal(errorCodes)
	}
	for code, retryable := range errorCodes {
		out := ErrorEnvelope("tool", domain(code, "message"))
		if obj(out["error"])["retryable"] != retryable {
			t.Fatal(out)
		}
	}
	out := ErrorEnvelope("tool", fmt.Errorf("secret"))
	if obj(out["error"])["message"] != "Internal error" {
		t.Fatal(out)
	}
}
