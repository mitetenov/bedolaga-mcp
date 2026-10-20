package bedolaga

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

const Version = "1.2.0"
const Name = "bedolaga-mcp"

type Config struct {
	APIURL, APIKey, Host string
	Timeout              time.Duration
	Port                 int
}
type DomainError struct{ Code, Message string }

func (e *DomainError) Error() string    { return e.Message }
func domain(code, message string) error { return &DomainError{code, message} }

var errorCodes = map[string]bool{"invalid_input": false, "not_configured": false, "identity_unavailable": false, "user_not_found": false, "unauthorized": false, "rate_limited": true, "upstream_timeout": true, "upstream_unavailable": true, "invalid_upstream_response": false, "internal_error": false}

func LoadConfig(env func(string) string, httpMode bool) (Config, error) {
	var c Config
	require := func(key, purpose string) (string, error) {
		v := strings.TrimSpace(env(key))
		if v == "" {
			return "", domain("not_configured", key+" is required ("+purpose+")")
		}
		return v, nil
	}
	var e error
	c.APIURL, e = require("BEDOLAGA_API_URL", "Bedolaga Web API base URL")
	if e != nil {
		return c, e
	}
	scheme, rest, ok := strings.Cut(c.APIURL, "://")
	if !ok || (strings.ToLower(scheme) != "http" && strings.ToLower(scheme) != "https") || strings.TrimSpace(rest) == "" {
		return c, domain("not_configured", "BEDOLAGA_API_URL must be an http(s) URL")
	}
	c.APIURL = strings.TrimRight(c.APIURL, "/")
	c.APIKey, e = require("BEDOLAGA_API_KEY", "Bedolaga Web API key")
	if e != nil {
		return c, e
	}
	raw := strings.TrimSpace(env("BEDOLAGA_TIMEOUT_MS"))
	if raw == "" {
		raw = "10000"
	}
	ms, e := strconv.Atoi(raw)
	if e != nil || ms <= 0 {
		return c, domain("not_configured", "BEDOLAGA_TIMEOUT_MS must be a positive integer (milliseconds)")
	}
	c.Timeout = time.Duration(ms) * time.Millisecond
	c.Host = strings.TrimSpace(env("MCP_HTTP_HOST"))
	port := strings.TrimSpace(env("MCP_HTTP_PORT"))
	if httpMode {
		if c.Host == "" {
			c.Host = strings.TrimSpace(env("HOST"))
			if c.Host == "" {
				c.Host = "0.0.0.0"
			}
		}
		if port == "" {
			port = strings.TrimSpace(env("PORT"))
			if port == "" {
				port = "3100"
			}
		}
	}
	if c.Host == "" {
		return c, domain("not_configured", "MCP_HTTP_HOST is required (HTTP bind host)")
	}
	if port == "" {
		return c, domain("not_configured", "MCP_HTTP_PORT is required (HTTP bind port)")
	}
	c.Port, e = strconv.Atoi(port)
	if e != nil || c.Port < 1 || c.Port > 65535 {
		return c, domain("not_configured", "MCP_HTTP_PORT must be an integer between 1 and 65535")
	}
	return c, nil
}
func EnvConfig(httpMode bool) (Config, error) { return LoadConfig(os.Getenv, httpMode) }
func Success(tool string, data M) M {
	return M{"ok": true, "source": Name, "tool": tool, "data": data, "meta": nil}
}
func ErrorEnvelope(tool string, e error) M {
	de, ok := e.(*DomainError)
	if !ok {
		de = &DomainError{"internal_error", "Internal error"}
	}
	return M{"ok": false, "source": Name, "tool": tool, "error": M{"code": de.Code, "message": de.Message, "retryable": errorCodes[de.Code]}}
}
func (c Config) Address() string {
	return fmt.Sprintf("%s:%d", c.Host, c.Port)
}
