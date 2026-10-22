# syntax=docker/dockerfile:1.28.0
FROM --platform=$BUILDPLATFORM golang:1.27.3-alpine3.24 AS build

# Stable runtime files change independently of dependencies and application code.
RUN mkdir -p /runtime/etc/ssl/certs /runtime/app /runtime/tmp /runtime/home/appuser \
    && cp /etc/ssl/certs/ca-certificates.crt /runtime/etc/ssl/certs/ca-certificates.crt \
    && printf 'appuser:x:1000:1000:Application:/home/appuser:/sbin/nologin\n' > /runtime/etc/passwd \
    && printf 'appuser:x:1000:\n' > /runtime/etc/group \
    && chown 1000:1000 /runtime/home/appuser \
    && chmod 1777 /runtime/tmp

ENV GOTOOLCHAIN=local
WORKDIR /src
COPY go.mod go.sum ./
# Keep modules in an ordinary layer: external CI layer caches restore them even
# on fresh builders, where cache-mount contents are not available.
RUN go mod download
COPY cmd/bedolaga-mcp/*.go ./cmd/bedolaga-mcp/
COPY internal/bedolaga/*.go internal/bedolaga/tools.json ./internal/bedolaga/
ARG TARGETOS
ARG TARGETARCH
# The compiler cache is cumulative on the local builder; dependencies come from
# the preceding layer. A network-free compile verifies that layer is complete.
RUN --network=none \
    --mount=type=cache,id=bedolaga-go-build-${TARGETOS}-${TARGETARCH},target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=$TARGETOS GOARCH=$TARGETARCH \
    go build -trimpath -ldflags="-s -w" -o /out/bedolaga-mcp ./cmd/bedolaga-mcp

FROM scratch
COPY --from=build /runtime/ /
WORKDIR /app
COPY --from=build /out/bedolaga-mcp /app/bedolaga-mcp
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
USER appuser
EXPOSE 3100
CMD ["/app/bedolaga-mcp", "http"]
