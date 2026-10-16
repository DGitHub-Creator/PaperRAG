package httpapi

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestRateLimitDoesNotTrustUnverifiedForwardedHeaders(t *testing.T) {
	l, err := NewRateLimiter("redis://localhost:6379", "test", "", "10.0.0.0/8")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.RemoteAddr = "192.0.2.5:1000"
	r.Header.Set("X-Forwarded-For", "203.0.113.1")
	if got := l.clientIP(r); got != "192.0.2.5" {
		t.Fatalf("伪造代理头被采纳: %s", got)
	}
	r.RemoteAddr = "10.0.0.1:1000"
	r.Header.Set("X-Forwarded-For", "203.0.113.99, 192.0.2.5, 10.0.0.2")
	if got := l.clientIP(r); got != "192.0.2.5" {
		t.Fatalf("没有从右侧剥离可信代理: %s", got)
	}
}

func TestRedisRateCounterIsSharedAndAtomic(t *testing.T) {
	url := os.Getenv("REFACTOR_TEST_REDIS_URL")
	if url == "" {
		t.Skip("需 REFACTOR_TEST_REDIS_URL 验证真实 Redis")
	}
	prefix := fmt.Sprintf("quality-%d", time.Now().UnixNano())
	a, err := NewRateLimiter(url, prefix, "", "")
	if err != nil {
		t.Fatal(err)
	}
	b, err := NewRateLimiter(url, prefix, "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer a.Close()
	defer b.Close()
	defer func() {
		keys, _ := a.client.Keys(context.Background(), prefix+":*").Result()
		if len(keys) > 0 {
			_ = a.client.Del(context.Background(), keys...).Err()
		}
	}()
	var allowed atomic.Int32
	var rejected atomic.Int32
	var wg sync.WaitGroup
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(http.StatusCreated) })
	for i := 0; i < 20; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			limiter := a
			if i%2 == 0 {
				limiter = b
			}
			r := httptest.NewRequest(http.MethodPost, "/login", nil)
			r.RemoteAddr = "192.0.2.1:1000"
			r.Header.Set("X-Forwarded-For", fmt.Sprintf("203.0.113.%d", i))
			w := httptest.NewRecorder()
			limiter.Wrap(next, 10, time.Minute)(w, r)
			switch w.Code {
			case http.StatusCreated:
				allowed.Add(1)
			case http.StatusTooManyRequests:
				rejected.Add(1)
				if w.Header().Get("Retry-After") == "" || w.Header().Get("X-RateLimit-Remaining") != "0" {
					t.Error("429 缺少限流头")
				}
			default:
				t.Errorf("意外状态码: %d, %s", w.Code, w.Body.String())
			}
		}(i)
	}
	wg.Wait()
	if allowed.Load() != 10 || rejected.Load() != 10 {
		t.Fatalf("并发计数漂移: allowed=%d rejected=%d", allowed.Load(), rejected.Load())
	}
}

func TestRateStoreFailureDoesNotDisableAuthenticationProtection(t *testing.T) {
	l, err := NewRateLimiter("redis://127.0.0.1:1", "test", "", "")
	if err != nil {
		t.Fatal(err)
	}
	defer l.Close()
	called := false
	w := httptest.NewRecorder()
	l.Wrap(func(http.ResponseWriter, *http.Request) { called = true }, 10, time.Minute)(w, httptest.NewRequest(http.MethodPost, "/login", nil))
	if called || w.Code != http.StatusServiceUnavailable {
		t.Fatalf("计数失败却放行: called=%v status=%d", called, w.Code)
	}
}
