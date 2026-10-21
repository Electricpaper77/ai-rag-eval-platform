package main

import (
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"io"
	"sync/atomic"
	"time"
)

type service struct { requests, failures uint64; failAfter uint64 }
var peerURL string

func (s *service) log(event string, fields ...any) { args := append([]any{"event", event, "service", "agenttrust-worker"}, fields...); slog.Info("worker_event", args...) }

func (s *service) work(w http.ResponseWriter, r *http.Request) {
	start := time.Now(); n := atomic.AddUint64(&s.requests, 1)
	if s.failAfter > 0 && n > s.failAfter && n <= s.failAfter+3 {
		atomic.AddUint64(&s.failures, 1); s.log("injected_failure", "request_id", n); http.Error(w, "injected failure", http.StatusServiceUnavailable); return
	}
	latency := time.Since(start); s.log("request_complete", "request_id", n, "latency_ms", float64(latency.Microseconds())/1000, "gpu_event_source", "simulated")
	w.Header().Set("Content-Type", "application/json"); json.NewEncoder(w).Encode(map[string]any{"ok":true,"request_id":n,"latency_ms":float64(latency.Microseconds())/1000,"gpu_event_source":"simulated"})
}
func (s *service) health(w http.ResponseWriter, r *http.Request) { json.NewEncoder(w).Encode(map[string]any{"status":"ok","requests":atomic.LoadUint64(&s.requests),"failures":atomic.LoadUint64(&s.failures)}) }
func (s *service) fanout(w http.ResponseWriter, r *http.Request) {
	if peerURL == "" { http.Error(w, "peer not configured", http.StatusNotImplemented); return }
	resp, err := http.Get(peerURL + "/work"); if err != nil { http.Error(w, err.Error(), http.StatusBadGateway); return }; defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body); w.Header().Set("Content-Type", "application/json"); w.WriteHeader(resp.StatusCode); w.Write(body)
}
func main() {
	failAfter, _ := strconv.ParseUint(os.Getenv("FAIL_AFTER"), 10, 64)
	peerURL = os.Getenv("PEER_URL"); s := &service{failAfter: failAfter}; mux := http.NewServeMux(); mux.HandleFunc("/work", s.work); mux.HandleFunc("/healthz", s.health); mux.HandleFunc("/fanout", s.fanout)
	port := os.Getenv("PORT"); if port == "" { port = "8080" }; s.log("service_started", "port", port, "fail_after", failAfter)
	if err := http.ListenAndServe(":"+port, mux); err != nil { log.Fatal(err) }
}
