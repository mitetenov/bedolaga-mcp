package main

import (
	"context"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/mitetenov/bedolaga-mcp/internal/bedolaga"
	"github.com/modelcontextprotocol/go-sdk/mcp"
)

func main() {
	if e := run(os.Args[1:]); e != nil {
		log.Print(e)
		os.Exit(1)
	}
}
func run(args []string) error {
	mode := "http"
	if len(args) > 0 {
		mode = args[0]
	}
	switch mode {
	case "--version", "version":
		fmt.Println(bedolaga.Version)
		return nil
	case "healthcheck":
		port := strings.TrimSpace(os.Getenv("MCP_HTTP_PORT"))
		if port == "" {
			port = strings.TrimSpace(os.Getenv("PORT"))
		}
		if port == "" {
			port = "3100"
		}
		if n, e := strconv.Atoi(port); e != nil || n < 1 || n > 65535 {
			return fmt.Errorf("healthcheck failed: invalid port")
		}
		client := &http.Client{Timeout: 5 * time.Second}
		res, e := client.Get("http://localhost:" + port + "/health")
		if e != nil {
			return fmt.Errorf("healthcheck failed")
		}
		defer res.Body.Close()
		if res.StatusCode != 200 {
			return fmt.Errorf("healthcheck failed")
		}
		io.Copy(io.Discard, res.Body)
		return nil
	case "http", "stdio":
	default:
		return fmt.Errorf("usage: bedolaga-mcp [http|stdio|healthcheck|--version]")
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	svc := bedolaga.NewService(func() (bedolaga.Config, error) { return bedolaga.EnvConfig(mode == "http") })
	defer svc.Close()
	server := bedolaga.NewServer(svc)
	if mode == "stdio" {
		return server.Run(ctx, &mcp.StdioTransport{})
	}
	config, e := bedolaga.EnvConfig(true)
	if e != nil {
		return e
	}
	httpServer := &http.Server{Addr: config.Address(), Handler: bedolaga.NewHTTPHandler(server), ReadHeaderTimeout: 10 * time.Second}
	done := make(chan error, 1)
	go func() { done <- httpServer.ListenAndServe() }()
	select {
	case e := <-done:
		if e == http.ErrServerClosed {
			return nil
		}
		return e
	case <-ctx.Done():
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		return httpServer.Shutdown(shutdown)
	}
}
