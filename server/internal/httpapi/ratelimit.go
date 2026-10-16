package httpapi

import (
	"crypto/sha256"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"net/netip"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"

	"github.com/DGitHub-Creator/ResearchPilot/server/internal/observability"
)

var rateCounter = redis.NewScript(`
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {count, ttl}
`)

// RateLimiter 只负责入口限流；跨实例计数在 Redis 原子更新，不静默降级放行。
type RateLimiter struct {
	client        *redis.Client
	prefix        string
	trusted       []netip.Prefix
	defaultCount  int
	defaultWindow time.Duration
}

func ParseRateLimit(raw string) (int, time.Duration, error) {
	if strings.TrimSpace(raw) == "" {
		return 0, 0, nil
	}
	parts := strings.Split(strings.ToLower(strings.TrimSpace(raw)), "/")
	if len(parts) != 2 {
		return 0, 0, fmt.Errorf("RATE_LIMIT 格式必须是 N/second、N/minute、N/hour 或 N/day")
	}
	count, err := strconv.Atoi(parts[0])
	units := map[string]time.Duration{"second": time.Second, "minute": time.Minute, "hour": time.Hour, "day": 24 * time.Hour}
	window, ok := units[parts[1]]
	if err != nil || count <= 0 || !ok {
		return 0, 0, fmt.Errorf("RATE_LIMIT 次数必须为正整数且单位有效")
	}
	return count, window, nil
}

func NewRateLimiter(redisURL, prefix, defaultSpec, trustedCIDRs string) (*RateLimiter, error) {
	options, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("REDIS_URL 格式无效")
	}
	count, window, err := ParseRateLimit(defaultSpec)
	if err != nil {
		return nil, err
	}
	trusted := []netip.Prefix{}
	if trustedCIDRs != "" {
		for _, raw := range strings.Split(trustedCIDRs, ",") {
			network, err := netip.ParsePrefix(strings.TrimSpace(raw))
			if err != nil {
				return nil, fmt.Errorf("TRUSTED_PROXY_CIDRS 包含无效网段")
			}
			trusted = append(trusted, network)
		}
	}
	options.DialTimeout, options.ReadTimeout, options.WriteTimeout = time.Second, time.Second, time.Second
	options.MaxRetries = -1
	options.ContextTimeoutEnabled = true
	return &RateLimiter{client: redis.NewClient(options), prefix: prefix + ":http-rate:", trusted: trusted, defaultCount: count, defaultWindow: window}, nil
}

func (l *RateLimiter) Close() error { return l.client.Close() }

func (l *RateLimiter) trustedIP(ip netip.Addr) bool {
	for _, network := range l.trusted {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func (l *RateLimiter) clientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		host = r.RemoteAddr
	}
	ip, err := netip.ParseAddr(host)
	if err != nil {
		return "unknown"
	}
	ip = ip.Unmap()
	if !l.trustedIP(ip) {
		return ip.String()
	}
	chain := strings.Split(r.Header.Get("X-Forwarded-For"), ",")
	for i := len(chain) - 1; i >= 0; i-- {
		forwarded, err := netip.ParseAddr(strings.TrimSpace(chain[i]))
		if err != nil {
			return ip.String()
		}
		ip = forwarded.Unmap()
		if !l.trustedIP(ip) {
			break
		}
	}
	return ip.String()
}

func (l *RateLimiter) Default(next http.HandlerFunc) http.HandlerFunc {
	if l.defaultCount == 0 {
		return next
	}
	return l.Wrap(next, l.defaultCount, l.defaultWindow)
}

func (l *RateLimiter) Wrap(next http.HandlerFunc, limit int, window time.Duration) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		if route := chi.RouteContext(r.Context()); route != nil {
			path = route.RoutePattern()
		}
		key := fmt.Sprintf("%s%x", l.prefix, sha256.Sum256([]byte(r.Method+":"+path+":"+l.clientIP(r)+":"+window.String()+":"+strconv.Itoa(limit))))
		values, err := rateCounter.Run(r.Context(), l.client, []string{key}, window.Milliseconds()).Int64Slice()
		if err != nil || len(values) != 2 {
			observability.WithTrace(slog.Default(), r.Context()).Error("限流计数不可用", "error", err)
			WriteError(w, http.StatusServiceUnavailable, "限流服务暂不可用")
			return
		}
		count, ttl := values[0], values[1]
		remaining := max(int64(limit)-count, 0)
		w.Header().Set("X-RateLimit-Limit", strconv.Itoa(limit))
		w.Header().Set("X-RateLimit-Remaining", strconv.FormatInt(remaining, 10))
		w.Header().Set("X-RateLimit-Reset", strconv.FormatInt(time.Now().Add(time.Duration(ttl)*time.Millisecond).Unix(), 10))
		if count > int64(limit) {
			w.Header().Set("Retry-After", strconv.FormatInt(max((ttl+999)/1000, 1), 10))
			WriteError(w, http.StatusTooManyRequests, fmt.Sprintf("Rate limit exceeded: %d/%s", limit, window))
			return
		}
		next(w, r)
	}
}
