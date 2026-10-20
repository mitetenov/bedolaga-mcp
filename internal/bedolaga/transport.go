package bedolaga

import (
	"bytes"
	"crypto/rand"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"sync"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func allowedHost(host string) bool {
	h := host
	if parsed, _, e := net.SplitHostPort(host); e == nil {
		h = parsed
	}
	h = strings.Trim(h, "[]")
	switch h {
	case "127.0.0.1", "localhost", "::1", Name:
		return true
	}
	return false
}
func httpRPCError(w http.ResponseWriter, status int, message, id string) {
	w.Header().Set("Content-Type", "application/json")
	if id != "" {
		w.Header().Set("Mcp-Session-Id", id)
	}
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(M{"jsonrpc": "2.0", "id": nil, "error": M{"code": -32600, "message": message}})
}
func NewHTTPHandler(server *mcp.Server) http.Handler {
	legacy := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return server }, &mcp.StreamableHTTPOptions{JSONResponse: true, DisableLocalhostProtection: true})
	modern := mcp.NewStreamableHTTPHandler(func(*http.Request) *mcp.Server { return server }, &mcp.StreamableHTTPOptions{JSONResponse: true, Stateless: true, DisableLocalhostProtection: true})
	var mu sync.Mutex
	sessions := map[string]bool{}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" && r.Method == "GET" {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(M{"status": "UP", "version": Version, "name": Name})
			return
		}
		if r.URL.Path != "/" {
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
			w.WriteHeader(404)
			io.WriteString(w, "Not Found")
			return
		}
		if !allowedHost(r.Host) {
			w.Header()["Content-Type"] = nil
			w.WriteHeader(421)
			io.WriteString(w, "Invalid Host header")
			return
		}
		if origin := r.Header.Get("Origin"); origin != "" {
			u, e := url.Parse(origin)
			if e != nil || u.Scheme != "http" || !allowedHost(u.Host) {
				w.Header()["Content-Type"] = nil
				w.WriteHeader(403)
				io.WriteString(w, "Invalid Origin header")
				return
			}
		}
		if r.Method != "POST" && r.Method != "GET" && r.Method != "DELETE" {
			httpRPCError(w, 405, "Method Not Allowed", rand.Text())
			return
		}
		var body []byte
		var msg struct {
			Method string `json:"method"`
		}
		if r.Method == "POST" {
			if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
				w.Header()["Content-Type"] = nil
				w.WriteHeader(400)
				io.WriteString(w, "Invalid Content-Type header")
				return
			}
			var e error
			body, e = io.ReadAll(r.Body)
			if e != nil {
				httpRPCError(w, 400, "Bad Request: Invalid request body", "")
				return
			}
			r.Body = io.NopCloser(bytes.NewReader(body))
			if err := json.Unmarshal(body, &msg); err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.Header().Set("Mcp-Session-Id", rand.Text())
				w.WriteHeader(400)
				message := "Parse error: " + err.Error()
				if strings.Contains(err.Error(), "object key string") {
					message = "Parse error: key must be a string at line 1 column 2"
				}
				json.NewEncoder(w).Encode(M{"jsonrpc": "2.0", "id": nil, "error": M{"code": -32700, "message": message}})
				return
			}
		}
		isModern := r.Header.Get("MCP-Protocol-Version") == "2026-07-28" || msg.Method == "server/discover"
		session := r.Header.Get("Mcp-Session-Id")
		if !isModern {
			if session != "" {
				mu.Lock()
				terminated, exists := sessions[session]
				mu.Unlock()
				if !exists {
					httpRPCError(w, 404, "Session not found", "")
					return
				}
				if terminated {
					httpRPCError(w, 404, "Not Found: Session has been terminated", session)
					return
				}
			}
			if session == "" && msg.Method != "initialize" {
				httpRPCError(w, 400, "Bad Request: Missing session ID", rand.Text())
				return
			}
			if r.Method == "POST" && !strings.Contains(r.Header.Get("Accept"), "application/json") {
				errorSession := session
				if errorSession == "" {
					errorSession = rand.Text()
				}
				httpRPCError(w, 406, "Not Acceptable: Client must accept application/json", errorSession)
				return
			}
		}
		// Python's JSON response mode accepts application/json alone. The Go SDK
		// additionally asks legacy clients for SSE Accept; supply it internally.
		if r.Method == "POST" && strings.Contains(r.Header.Get("Accept"), "application/json") && !strings.Contains(r.Header.Get("Accept"), "text/event-stream") {
			r = r.Clone(r.Context())
			r.Header.Set("Accept", r.Header.Get("Accept")+", text/event-stream")
		}
		if r.Method == "GET" && !isModern {
			w.Header().Set("Mcp-Session-Id", session)
			legacy.ServeHTTP(w, r)
			return
		}
		rec := newBufferedResponse()
		if isModern {
			modern.ServeHTTP(rec, r)
		} else {
			legacy.ServeHTTP(rec, r)
		}
		status := rec.Code
		data := rec.Body.Bytes()
		if !isModern {
			if newID := rec.Header().Get("Mcp-Session-Id"); newID != "" {
				session = newID
				mu.Lock()
				sessions[session] = false
				mu.Unlock()
			}
			if session != "" {
				rec.Header().Set("Mcp-Session-Id", session)
			}
			if r.Method == "DELETE" && status == 204 {
				status = 200
				rec.Header().Set("Content-Type", "application/json")
				mu.Lock()
				sessions[session] = true
				mu.Unlock()
			}
			if status == 202 {
				rec.Header().Set("Content-Type", "application/json")
			}
		}
		for k, values := range rec.Header() {
			for _, v := range values {
				w.Header().Add(k, v)
			}
		}
		w.WriteHeader(status)
		w.Write(data)
	})
}

// JSON response requests are finite; SSE GET bypasses this recorder and streams
// directly to the socket.
type bufferedResponse struct {
	headers http.Header
	Code    int
	Body    bytes.Buffer
}

func newBufferedResponse() *bufferedResponse {
	return &bufferedResponse{headers: make(http.Header), Code: 200}
}
func (r *bufferedResponse) Header() http.Header         { return r.headers }
func (r *bufferedResponse) WriteHeader(code int)        { r.Code = code }
func (r *bufferedResponse) Write(b []byte) (int, error) { return r.Body.Write(b) }
func (r *bufferedResponse) Flush()                      {}
