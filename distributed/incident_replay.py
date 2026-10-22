import concurrent.futures, json, os, statistics, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

BASE=os.getenv("GATEWAY_URL","http://127.0.0.1:18082"); OUT=os.getenv("EVIDENCE_DIR","evidence")
def request(target):
 trace=f"gate19-{time.time_ns()}"; started=time.perf_counter(); status=0; returned=""; error=""
 try:
  req=urllib.request.Request(f"{BASE}/incident/work?target={target}",headers={"X-Trace-ID":trace,"X-Correlation-ID":trace})
  with urllib.request.urlopen(req,timeout=5) as r: status=r.status; body=json.loads(r.read()); returned=body.get("trace_id","")
 except urllib.error.HTTPError as exc:
  status=exc.code
  try: returned=json.loads(exc.read()).get("trace_id","")
  except Exception: pass
 except Exception as exc: error=type(exc).__name__
 return {"trace_id":trace,"returned_trace_id":returned,"status":status,"ok":200<=status<300 and returned==trace,"latency_ms":(time.perf_counter()-started)*1000,"error":error,"ts":datetime.now(timezone.utc).isoformat()}
def run(name,target,count,concurrency):
 start=time.perf_counter()
 with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool: rows=list(pool.map(lambda _:request(target),range(count)))
 elapsed=time.perf_counter()-start; values=sorted(r["latency_ms"] for r in rows); q=lambda p: values[min(len(values)-1,int(len(values)*p))]
 result={"name":name,"target":target,"requests":count,"sample_count":len(rows),"concurrency":concurrency,"duration_s":elapsed,"p50_ms":q(.50),"p95_ms":q(.95),"p99_ms":q(.99),"throughput_rps":count/elapsed,"error_rate":sum(not r["ok"] for r in rows)/count,"trace_continuity_rate":sum(r["returned_trace_id"]==r["trace_id"] for r in rows)/count,"rows":rows}
 return result
def main():
 os.makedirs(OUT,exist_ok=True); timeline=[]; started=time.time(); baseline=run("healthy_baseline","worker-a",40,4); timeline.append({"event":"baseline_complete","ts":time.time()})
 degraded=run("injected_failure","worker-b",40,4); timeline.append({"event":"fault_complete","ts":time.time()})
 recovery_start=time.perf_counter(); recovery_probe=None
 for _ in range(20):
  probe=request("worker-b")
  if probe["ok"]: recovery_probe=probe; break
  time.sleep(.05)
 recovery_ms=(time.perf_counter()-recovery_start)*1000; timeline.append({"event":"recovery_observed","ts":time.time(),"recovery_probe_duration_ms":recovery_ms})
 recovered=run("recovered","worker-a",20,4)
 report={"schema_version":1,"incident_id":"gate19-local-incident-replay","started_at":datetime.fromtimestamp(started,timezone.utc).isoformat(),"environment":{"gateway":BASE,"gpu_telemetry":"simulated labels only; no physical DCGM measurement","runtime":"local Docker Compose"},"timeline":timeline,"baseline":baseline,"degraded":degraded,"recovered":recovered,"recovery":{"observed":recovery_probe is not None,"probe_duration_ms":recovery_ms},"root_cause":"deterministic worker-b FAIL_AFTER=20 bounded injected 503 responses","mitigation":"route subsequent probes to healthy worker-a","limitations":["local containers are not production infrastructure","GPU telemetry is simulated, not physical NVIDIA DCGM"]}
 with open(os.path.join(OUT,"incident_report.json"),"w",encoding="utf-8") as f: json.dump(report,f,indent=2)
 with open(os.path.join(OUT,"incident_report.html"),"w",encoding="utf-8") as f: f.write("<html><body><h1>AgentTrust IQ Gate 19 Incident Replay</h1><p>Simulated GPU labels only; no physical DCGM measurement.</p><pre>"+json.dumps({k:report[k] for k in ('timeline','baseline','degraded','recovered','recovery','root_cause','mitigation')},indent=2)+"</pre></body></html>")
 with open(os.path.join(OUT,"trace_continuity.json"),"w",encoding="utf-8") as f: json.dump({"baseline":baseline["trace_continuity_rate"],"degraded":degraded["trace_continuity_rate"],"recovered":recovered["trace_continuity_rate"]},f,indent=2)
 print(json.dumps({k:report[k] for k in ('baseline','degraded','recovered','recovery')},indent=2)); return 0 if degraded["error_rate"]>0 and report["recovery"]["observed"] and all(x["trace_continuity_rate"]==1 for x in (baseline,degraded,recovered)) else 1
if __name__=="__main__": sys.exit(main())
