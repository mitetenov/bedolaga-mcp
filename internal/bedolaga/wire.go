package bedolaga

import (
	"context"
	"encoding/json"
	"strings"

	"github.com/modelcontextprotocol/go-sdk/mcp"
)

// The official Go/Python SDKs differ in their default metadata. This wrapper
// preserves the original published wire contract in both protocol eras while
// the official SDK continues to own message handling and transport lifecycle.
type wireResult struct {
	mcp.Result
	value M
}

func (r wireResult) MarshalJSON() ([]byte, error) { return json.Marshal(r.value) }
func legacyWire(next mcp.MethodHandler) mcp.MethodHandler {
	return func(ctx context.Context, method string, req mcp.Request) (mcp.Result, error) {
		var res mcp.Result
		var e error
		if method == "tools/call" {
			if call, ok := req.(*mcp.CallToolRequest); ok {
				known := false
				for _, t := range Tools() {
					if t.Name == call.Params.Name {
						known = true
						break
					}
				}
				if !known {
					res = &mcp.CallToolResult{IsError: true, Content: []mcp.Content{&mcp.TextContent{Text: "Unknown tool: " + call.Params.Name}}}
				}
			}
		}
		if res == nil {
			res, e = next(ctx, method, req)
		}
		if e != nil || res == nil {
			return res, e
		}
		modern := method == "server/discover"
		if v, ok := req.(interface{ ProtocolVersion() string }); ok && v.ProtocolVersion() == "2026-07-28" {
			modern = true
		}
		if !modern && method != "initialize" && !strings.HasSuffix(method, "/list") {
			return res, nil
		}
		b, e := json.Marshal(res)
		if e != nil {
			return nil, e
		}
		var out M
		if e = json.Unmarshal(b, &out); e != nil {
			return nil, e
		}
		if modern {
			out["resultType"] = "complete"
			out["_meta"] = M{"io.modelcontextprotocol/serverInfo": M{"name": Name, "version": Version}}
			if method == "server/discover" || strings.HasSuffix(method, "/list") {
				out["cacheScope"] = "private"
				out["ttlMs"] = 0
			}
			if method == "server/discover" {
				delete(out, "serverInfo")
				out["supportedVersions"] = []string{"2026-07-28"}
				out["capabilities"] = M{"prompts": M{"listChanged": true}, "resources": M{"listChanged": true, "subscribe": true}, "tools": M{"listChanged": true}}
			}
		} else {
			delete(out, "cacheScope")
			delete(out, "ttlMs")
			if method == "initialize" {
				out["capabilities"] = M{"experimental": M{}, "prompts": M{"listChanged": false}, "resources": M{"subscribe": false, "listChanged": false}, "tools": M{"listChanged": false}}
			}
		}
		return wireResult{res, out}, nil
	}
}
