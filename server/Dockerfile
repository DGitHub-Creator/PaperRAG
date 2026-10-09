# syntax=docker/dockerfile:1
# go-api 与 go-worker 共用一个镜像，靠 compose 的 command 区分进程（02 §2 是两个进程、一份代码）。
# 构建上下文是 server/：docker compose 里写 build: {context: ./server, dockerfile: Dockerfile}。

FROM golang:1.25-alpine AS build
WORKDIR /src

# 中国大陆网络下 proxy.golang.org 不可达（本机实测超时）。默认走官方源，
# 需要镜像时在 build 时传 --build-arg GOPROXY=https://goproxy.cn,direct，不在仓库里写死。
ARG GOPROXY=https://proxy.golang.org,direct
ENV GOPROXY=${GOPROXY}

# 先只拷依赖清单：源码改动不会让 go mod download 这一层失效
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 go build -o /out/go-api ./cmd/api \
 && CGO_ENABLED=0 go build -o /out/go-worker ./cmd/worker

FROM alpine:3.20
RUN apk add --no-cache ca-certificates \
 && adduser -D -u 10001 app
WORKDIR /app
COPY --from=build /out/go-api /out/go-worker /app/
USER app
EXPOSE 8080
# 用 CMD 而不是 ENTRYPOINT，go-worker 服务直接覆盖 command 即可
CMD ["/app/go-api"]
