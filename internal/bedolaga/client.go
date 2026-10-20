package bedolaga

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
)

type Client struct {
	config Config
	http   *http.Client
}

func NewClient(c Config) *Client {
	return &Client{c, &http.Client{Timeout: c.Timeout, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}}
}
func (c *Client) Close() { c.http.CloseIdleConnections() }
func (c *Client) get(ctx context.Context, path string, params url.Values, shape string, lookup bool) (any, error) {
	target := c.config.APIURL + path
	if len(params) > 0 {
		target += "?" + params.Encode()
	}
	req, e := http.NewRequestWithContext(ctx, "GET", target, nil)
	if e != nil {
		return nil, domain("upstream_unavailable", "Bedolaga API request failed")
	}
	req.Header.Set("X-API-Key", c.config.APIKey)
	res, e := c.http.Do(req)
	if e != nil {
		var ne net.Error
		if errors.As(e, &ne) && ne.Timeout() {
			return nil, domain("upstream_timeout", "Bedolaga API request timed out")
		}
		return nil, domain("upstream_unavailable", "Bedolaga API is unreachable")
	}
	defer res.Body.Close()
	switch s := res.StatusCode; {
	case s == 404:
		if lookup {
			return nil, domain("user_not_found", "User not found")
		}
		return nil, domain("upstream_unavailable", "Requested Bedolaga resource is unavailable")
	case s == 401 || s == 403:
		return nil, domain("unauthorized", "Invalid or missing Bedolaga API credentials")
	case s == 429:
		return nil, domain("rate_limited", "Bedolaga API rate limit reached")
	case s == 422:
		return nil, domain("invalid_input", "Bedolaga API rejected the request parameters")
	case s >= 500:
		return nil, domain("upstream_unavailable", "Bedolaga API is unavailable")
	case s != 200:
		return nil, domain("upstream_unavailable", fmt.Sprintf("Unexpected Bedolaga API status %d", s))
	}
	data, e := io.ReadAll(res.Body)
	if e != nil {
		return nil, domain("upstream_unavailable", "Bedolaga API request failed")
	}
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.UseNumber()
	var v any
	if dec.Decode(&v) != nil {
		return nil, domain("invalid_upstream_response", "Bedolaga API returned an invalid response")
	}
	var trailing any
	if dec.Decode(&trailing) != io.EOF {
		return nil, domain("invalid_upstream_response", "Bedolaga API returned an invalid response")
	}
	switch shape {
	case "object":
		if _, ok := v.(map[string]any); !ok {
			return nil, domain("invalid_upstream_response", "Bedolaga API returned an unexpected response shape")
		}
	case "list":
		a, ok := v.([]any)
		if !ok {
			return nil, domain("invalid_upstream_response", "Bedolaga API returned an unexpected response shape")
		}
		for _, item := range a {
			if _, ok := item.(map[string]any); !ok {
				return nil, domain("invalid_upstream_response", "Bedolaga API returned an unexpected list item shape")
			}
		}
	}

	return v, nil
}
func params(owner any, limit int, kind string) url.Values {
	p := url.Values{"limit": {fmt.Sprint(limit)}, "offset": {"0"}}
	if owner != nil {
		p.Set("user_id", fmt.Sprint(owner))
	}
	if kind != "" {
		p.Set("type", kind)
	}
	return p
}
