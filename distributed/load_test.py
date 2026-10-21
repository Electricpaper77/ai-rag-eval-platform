"""Local, dependency-free load test; emits measured JSON and no synthetic metrics."""
import argparse, concurrent.futures, json, statistics, time, urllib.error, urllib.request

def main():
    p=argparse.ArgumentParser(); p.add_argument("--url", required=True); p.add_argument("--requests", type=int, default=100); p.add_argument("--concurrency", type=int, default=10); a=p.parse_args()
    def one(_):
        t=time.perf_counter()
        try:
            with urllib.request.urlopen(a.url, timeout=5) as r: r.read(); ok=200 <= r.status < 300
        except (urllib.error.URLError, TimeoutError): ok=False
        return (time.perf_counter()-t)*1000, ok
    start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.concurrency) as ex: rows=list(ex.map(one, range(a.requests)))
    elapsed=time.perf_counter()-start; values=sorted(x[0] for x in rows); n=len(values)
    q=lambda x: values[min(n-1, int(n*x))]
    out={"requests":a.requests,"concurrency":a.concurrency,"p50_ms":q(.50),"p95_ms":q(.95),"p99_ms":q(.99),"throughput_rps":a.requests/elapsed,"error_rate":sum(not ok for _,ok in rows)/a.requests,"elapsed_s":elapsed}
    print(json.dumps(out, indent=2))
if __name__ == "__main__": main()
