import json, os, time, uuid
from datetime import datetime, timezone
from typing import Any
import httpx
from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse
app=FastAPI(title="AgentTrust Gate 19 Incident Replay Gateway")
WORKERS={"worker-a":os.getenv("WORKER_A_URL","http://worker-a:8080"),"worker-b":os.getenv("WORKER_B_URL","http://worker-b:8080")}
def log(event:str,**fields:Any)->None: print(json.dumps({"ts":datetime.now(timezone.utc).isoformat(),"service":"gate19-gateway","event":event,**fields}),flush=True)
@app.get("/healthz")
async def healthz()->dict:
 results={}
 async with httpx.AsyncClient(timeout=1.0) as client:
  for name,url in WORKERS.items():
   try: response=await client.get(url+"/healthz"); results[name]={"status_code":response.status_code,"body":response.json()}
   except Exception as exc: results[name]={"error":type(exc).__name__}
 return {"status":"ok","workers":results}
@app.get("/incident/work")
async def incident_work(target:str=Query("worker-a"),x_trace_id:str|None=Header(default=None),x_correlation_id:str|None=Header(default=None))->JSONResponse:
 target=target if target in WORKERS else "worker-a"; trace_id=x_trace_id or x_correlation_id or uuid.uuid4().hex; started=time.perf_counter(); status=502; body:dict[str,Any]={"error":"unavailable"}
 try:
  async with httpx.AsyncClient(timeout=2.0) as client: response=await client.get(WORKERS[target]+"/work",headers={"X-Trace-ID":trace_id,"X-Correlation-ID":trace_id}); status=response.status_code; body=response.json()
 except Exception as exc: body={"error":type(exc).__name__}
 latency_ms=(time.perf_counter()-started)*1000; log("request_complete",trace_id=trace_id,target=target,status_code=status,latency_ms=latency_ms); body.update({"trace_id":trace_id,"target":target,"gateway_latency_ms":latency_ms})
 return JSONResponse(status_code=status,content=body,headers={"X-Trace-ID":trace_id,"X-Correlation-ID":trace_id})
