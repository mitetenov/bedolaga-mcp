package bedolaga

import (
	"bytes"
	"context"
	_ "embed"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"sync"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

//go:embed tools.json
var definitions []byte

type Tool struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	InputSchema M      `json:"inputSchema"`
}

func Tools() []Tool {
	var defs []Tool
	if e := json.Unmarshal(definitions, &defs); e != nil {
		panic(e)
	}
	return defs
}

type Service struct {
	mu     sync.Mutex
	client *Client
	config func() (Config, error)
}

func NewService(config func() (Config, error)) *Service { return &Service{config: config} }
func (s *Service) Close() {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.client != nil {
		s.client.Close()
		s.client = nil
	}
}
func (s *Service) getClient() (*Client, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.client == nil {
		c, e := s.config()
		if e != nil {
			return nil, e
		}
		s.client = NewClient(c)
	}
	return s.client, nil
}
func (s *Service) Call(ctx context.Context, name string, args M) M {
	c, e := s.getClient()
	if e != nil {
		return ErrorEnvelope(name, e)
	}
	data, e := s.execute(ctx, c, name, args)
	if e != nil {
		return ErrorEnvelope(name, e)
	}
	return Success(name, data)
}
func (s *Service) execute(ctx context.Context, c *Client, name string, args M) (M, error) {

	limit := 20
	if name == "bedolaga_tickets_get" {
		limit = 10
	}
	if name == "bedolaga_payment_status_get" {
		limit = 5
	}
	if n, ok := integer(args["limit"]); ok {
		limit = int(n)
	}
	code, _ := args["code"].(string)
	if name == "bedolaga_promocode_check" && trim(code) == "" {
		return nil, domain("invalid_input", "code must be a non-empty string")
	}
	code = strings.ToUpper(trim(code))
	tid, uid := args["telegram_id"], args["user_id"]
	if (tid == nil) == (uid == nil) {
		return nil, domain("invalid_input", "Provide exactly one of telegram_id or user_id")
	}
	key, val := "telegram_id", tid
	if uid != nil {
		key, val = "user_id", uid
	}
	n, ok := integer(val)
	if !ok || n <= 0 {
		return nil, domain("invalid_input", key+" must be a positive integer")
	}
	path := "/users/" + strconv.FormatInt(n, 10)
	if key == "telegram_id" {
		path = "/users/by-telegram-id/" + strconv.FormatInt(n, 10)
	}
	v, e := c.get(ctx, path, nil, "object", true)
	if e != nil {
		return nil, e
	}
	user := obj(v)
	if name == "bedolaga_user_get" {
		return userData(user), nil
	}
	owner := user["id"]
	if n, ok := integer(owner); !ok || n <= 0 {
		return nil, domain("identity_unavailable", "User identity cannot be resolved to a Bedolaga account")
	}
	get := func(path string, limit int, kind, shape string) (any, error) {
		return c.get(ctx, path, params(owner, limit, kind), shape, false)
	}
	switch name {
	case "bedolaga_billing_get":
		pages := []any{}
		for _, kind := range []string{"", "deposit", "subscription_payment"} {
			v, e := get("/transactions", 200, kind, "object")
			if e != nil {
				return nil, e
			}
			pages = append(pages, v)
		}
		return billingData(user, merge(pages), limit), nil
	case "bedolaga_payment_status_get":
		pages := []any{}
		for _, kind := range []string{"deposit", "subscription_payment", "gift_payment", "refund", "failed_refund"} {
			v, e := get("/transactions", limit, kind, "object")
			if e != nil {
				return nil, e
			}
			pages = append(pages, v)
		}
		return paymentData(merge(pages), owner, limit, false), nil
	case "bedolaga_gifts_get":
		v, e := get("/transactions", limit, "gift_payment", "object")
		if e != nil {
			return nil, e
		}
		return paymentData(v, owner, limit, true), nil
	case "bedolaga_subscription_get":
		v, e := get("/subscriptions", 200, "", "list")
		if e != nil {
			return nil, e
		}
		return subscriptionData(user, v, owner), nil
	case "bedolaga_tickets_get":
		v, e := get("/tickets", limit, "", "list")
		if e != nil {
			return nil, e
		}
		return ticketsData(v, owner), nil
	case "bedolaga_referrals_get":
		v, e := c.get(ctx, fmt.Sprintf("/partners/referrers/%v", owner), params(nil, 1, ""), "object", false)
		if e != nil {
			return nil, e
		}
		rewards, e := get("/transactions", 20, "referral_reward", "object")
		if e != nil {
			return nil, e
		}
		return referralData(obj(v), user, rewards), nil
	case "bedolaga_promocode_check":
		var found M
		incomplete := true
		for page := 0; page < 5; page++ {
			p := params(nil, 200, "")
			p.Set("offset", strconv.Itoa(page*200))
			res, e := c.get(ctx, "/promo-codes", p, "object", false)
			if e != nil {
				return nil, e
			}
			m := obj(res)
			items := arr(m["items"])
			total, ok := integer(m["total"])
			if !ok {
				total = int64(len(items))
			}
			for _, v := range items {
				item := obj(v)
				if s, ok := item["code"].(string); ok && strings.ToUpper(trim(s)) == code {
					found = item
					break
				}
			}
			if found != nil {
				incomplete = false
				break
			}
			if len(items) < 200 || page*200+len(items) >= int(total) {
				incomplete = false
				break
			}
		}
		return promoData(found, code, incomplete), nil
	}
	return nil, domain("internal_error", "Internal error")
}
func merge(pages []any) M {
	out := []any{}
	seen := map[string]bool{}
	for _, p := range pages {
		for _, v := range arr(obj(p)["items"]) {
			m, ok := v.(map[string]any)
			if !ok {
				continue
			}
			if id := m["id"]; id != nil {
				key := ident(id)
				if seen[key] {
					continue
				}
				seen[key] = true
			}
			out = append(out, m)
		}
	}
	return M{"items": out}
}

// The Python public schema accepts Pydantic's ordinary scalar coercion and
// ignores extra properties. Keep this at the MCP boundary; domain identity
// validation below still rejects nonpositive identifiers.
func validateArgs(tool Tool, raw json.RawMessage) (M, error) {
	args := M{}
	if len(raw) > 0 {
		d := json.NewDecoder(bytes.NewReader(raw))
		d.UseNumber()
		if d.Decode(&args) != nil {
			return nil, fmt.Errorf("arguments must be an object")
		}
	}
	if args == nil {
		args = M{}
	}
	out := M{}
	props := obj(tool.InputSchema["properties"])
	for name, def := range props {
		schema := obj(def)
		v, exists := args[name]
		if !exists {
			if d, ok := schema["default"]; ok {
				out[name] = d
				continue
			}
			return nil, fmt.Errorf("%s is required", name)
		}
		if v == nil {
			if name == "telegram_id" || name == "user_id" {
				out[name] = nil
				continue
			}
			return nil, fmt.Errorf("%s must not be null", name)
		}
		if name == "code" {
			s, ok := v.(string)
			if !ok || len(s) == 0 {
				return nil, fmt.Errorf("code must be a non-empty string")
			}
			out[name] = s
			continue
		}
		n, ok := coerceInteger(v)
		if !ok {
			return nil, fmt.Errorf("%s must be an integer", name)
		}
		if name == "limit" {
			max := int64(50)
			if tool.Name == "bedolaga_payment_status_get" {
				max = 20
			}
			if n < 1 || n > max {
				kind, words, boundary := "less_than_equal", "less than or equal to", max
				if n < 1 {
					kind, words, boundary = "greater_than_equal", "greater than or equal to", 1
				}
				return nil, fmt.Errorf("1 validation error for %s\nlimit\n  Input should be %s %d [type=%s, input_value=%v, input_type=int]\n    For further information visit https://errors.pydantic.dev/2.13/v/%s", tool.InputSchema["title"], words, boundary, kind, v, kind)
			}
		}
		out[name] = json.Number(strconv.FormatInt(n, 10))
	}
	return out, nil
}
func coerceInteger(v any) (int64, bool) {
	if n, ok := integer(v); ok {
		return n, true
	}
	switch x := v.(type) {
	case bool:
		if x {
			return 1, true
		}
		return 0, true
	case string:
		f, e := strconv.ParseFloat(trim(x), 64)
		if e == nil && float64(int64(f)) == f {
			return int64(f), true
		}
	case json.Number:
		f, e := x.Float64()
		if e == nil && float64(int64(f)) == f {
			return int64(f), true
		}
	}
	return 0, false
}
func NewServer(svc *Service) *mcp.Server {
	server := mcp.NewServer(&mcp.Implementation{Name: Name, Version: Version}, &mcp.ServerOptions{Capabilities: &mcp.ServerCapabilities{Tools: &mcp.ToolCapabilities{}, Prompts: &mcp.PromptCapabilities{}, Resources: &mcp.ResourceCapabilities{}}})
	for _, def := range Tools() {
		server.AddTool(&mcp.Tool{Name: def.Name, Description: def.Description, InputSchema: def.InputSchema}, func(ctx context.Context, req *mcp.CallToolRequest) (*mcp.CallToolResult, error) {
			args, e := validateArgs(def, req.Params.Arguments)
			if e != nil {
				return &mcp.CallToolResult{IsError: true, Content: []mcp.Content{&mcp.TextContent{Text: "Error executing tool " + def.Name + ": " + e.Error()}}}, nil
			}
			payload := svc.Call(ctx, def.Name, args)
			data, e := json.Marshal(payload)
			if e != nil {
				return nil, e
			}
			return &mcp.CallToolResult{Content: []mcp.Content{&mcp.TextContent{Text: string(data)}}}, nil
		})
	}
	server.AddReceivingMiddleware(legacyWire)
	return server
}
