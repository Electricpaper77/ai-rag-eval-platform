from __future__ import annotations
import argparse, concurrent.futures, hashlib, json, os, subprocess, time, uuid
from pathlib import Path
from . import SCHEMA_VERSION
from .artifacts import write_run
from .metrics import summarize
from .providers import MockProvider, OpenAICompatibleProvider, NvidiaNimProvider
from .schema import HARD_MAX_CONCURRENCY, HARD_MAX_REQUESTS, HARD_MAX_RETRIES, PROFILES, bounded_int
from .telemetry import AmdSmiTelemetry

def build_parser():
    p=argparse.ArgumentParser(description="Controlled AgentTrust GPU Reliability Lab")
    p.add_argument("--provider",choices=["mock","openai_compatible","nvidia_nim"],required=True); p.add_argument("--mode",choices=["offline-validation","mock-benchmark","authenticated-smoke","authenticated-benchmark"],required=True)
    p.add_argument("--profile",choices=PROFILES,default="moderate"); p.add_argument("--suite",default="eval/nvidia_nemotron_pack.jsonl"); p.add_argument("--model"); p.add_argument("--max-requests",type=int); p.add_argument("--concurrency",type=int); p.add_argument("--retries",type=int,default=2); p.add_argument("--allow-network",action="store_true"); p.add_argument("--confirm-performance-run",action="store_true"); p.add_argument("--resume",action="store_true"); p.add_argument("--telemetry",choices=["none","amd_smi"],default="none"); return p
def validate(args):
    if args.profile=="performance" and not(args.allow_network and args.confirm_performance_run): raise ValueError("performance requires --allow-network and --confirm-performance-run")
    if args.provider!="mock" and not args.allow_network: raise ValueError("authenticated providers require --allow-network")
    if args.provider!="mock" and not args.model: raise ValueError("authenticated providers require --model")
    if args.provider=="mock" and args.mode!="mock-benchmark": raise ValueError("mock provider requires mock-benchmark mode")
    args.max_requests=bounded_int(args.max_requests,"GPU_LAB_MAX_REQUESTS",PROFILES[args.profile].default_requests,HARD_MAX_REQUESTS); args.concurrency=bounded_int(args.concurrency,"GPU_LAB_MAX_CONCURRENCY",PROFILES[args.profile].default_concurrency,HARD_MAX_CONCURRENCY)
    if not 0<=args.retries<=HARD_MAX_RETRIES: raise ValueError("retries must be between 0 and 2")
    return args
def cache_key(provider,model,prompt,parameters): return hashlib.sha256(json.dumps({"provider":provider,"model":model,"prompt":prompt,"parameters":parameters},sort_keys=True,separators=(",",":")).encode()).hexdigest()
def _cases(path,limit):
    rows=[json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else [{"prompt":"deterministic GPU reliability fixture"} for _ in range(limit)]
    return rows[:limit]
def _provider(name): return MockProvider() if name=="mock" else NvidiaNimProvider() if name=="nvidia_nim" else OpenAICompatibleProvider()
def _prices():
    def value(n):
        try:return float(os.getenv(n,""))
        except ValueError:return None
    return value("GPU_LAB_INPUT_COST_PER_MILLION"),value("GPU_LAB_OUTPUT_COST_PER_MILLION"),value("GPU_LAB_MAX_COST_USD")
def _estimate(result,prices):
    inp,out,_=prices
    if inp is None or out is None or result.get("input_tokens") is None or result.get("output_tokens") is None:return None
    return (result["input_tokens"]*inp+result["output_tokens"]*out)/1_000_000
def _execute(seq,case,provider,args,cache_dir):
    prompt=str(case.get("prompt") or case.get("input") or ""); params={"temperature":0}; key=cache_key(args.provider,args.model or "mock",prompt,params); cached=cache_dir/(key+".json")
    record={"sequence":seq,"request_id":str(case.get("id",seq)),"completed":True,"success":False,"cache_hit":False,"retries":0,"warmup":False,"started_monotonic":time.monotonic()}
    if cached.exists() and args.resume:
        try:
            payload=json.loads(cached.read_text(encoding="utf-8"));
            if not isinstance(payload,dict) or not payload.get("text"): raise ValueError("malformed cache entry")
            record.update(success=True,cache_hit=True,input_tokens=payload.get("input_tokens"),output_tokens=payload.get("output_tokens")); record["ended_monotonic"]=time.monotonic(); record["latency_seconds"]=None; return record
        except Exception: cached.unlink(missing_ok=True)
    for attempt in range(args.retries+1):
        try:
            result=provider.complete(prompt,args.model or "mock")
            if not result.get("text"): raise ValueError("malformed response")
            record.update(success=True,input_tokens=result.get("input_tokens"),output_tokens=result.get("output_tokens"),ttft_seconds=result.get("ttft_seconds")); cached.parent.mkdir(parents=True,exist_ok=True); cached.write_text(json.dumps({k:result.get(k) for k in ("text","input_tokens","output_tokens")}),encoding="utf-8"); break
        except Exception as exc:
            text=_sanitize(str(exc)); record.update(error=text,failure_type=_failure_type(text),retries=attempt)
            if any(code in text for code in ("401","403","400")): break
            if attempt<args.retries: time.sleep(min(.25*2**attempt,1))
    record["ended_monotonic"]=time.monotonic(); record["latency_seconds"]=record["ended_monotonic"]-record["started_monotonic"]; return record
def run(args):
    args=validate(args); started_wall=time.time(); started_mono=time.monotonic(); run_id="gpu-lab-"+uuid.uuid4().hex[:12]; suite=Path(args.suite); cases=_cases(suite,args.max_requests); root_base=Path(os.getenv("AGENTTRUST_ARTIFACT_DIR","artifacts")); cache_dir=root_base/"gpu-lab"/"cache"; provider=_provider(args.provider); telemetry=AmdSmiTelemetry().capabilities() if args.telemetry=="amd_smi" else {"telemetry_status":"unavailable","reason":"not requested"}; prices=_prices(); projected=0.0; records=[]; stop_reason=None
    # A configured budget has no provider-supplied token estimate before the
    # first completion. Serialize dispatch in that state so a batch cannot
    # overspend before its first measured configured estimate is available.
    dispatch_concurrency = 1 if prices[2] is not None else args.concurrency
    with concurrent.futures.ThreadPoolExecutor(max_workers=dispatch_concurrency) as pool:
        pending={}; next_seq=0
        while next_seq<len(cases) or pending:
            while next_seq<len(cases) and len(pending)<dispatch_concurrency and stop_reason is None:
                future=pool.submit(_execute,next_seq,cases[next_seq],provider,args,cache_dir); pending[future]=next_seq; next_seq+=1
            if not pending: break
            done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                record=future.result(); pending.pop(future); cost=None if record.get("cache_hit") else _estimate(record,prices); record["estimated_api_cost_usd"]=cost; projected+=cost or 0; records.append(record)
                if record.get("success") is False and sum(not r.get("success") for r in records[-5:])>=5: stop_reason="consecutive_failures"
                if prices[2] is not None and projected>=prices[2]: stop_reason="cost_budget_reached"
    records.sort(key=lambda r:r["sequence"]); summary=summarize(records); summary.update(benchmark_wall_clock_seconds=time.monotonic()-started_mono,new_provider_requests=sum(not r["cache_hit"] for r in records),estimated_total_api_cost_usd=projected if prices[0] is not None and prices[1] is not None else None,cost_status="configured_estimate" if prices[0] is not None and prices[1] is not None else "not_configured")
    try:commit=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,timeout=2).stdout.strip() or None
    except Exception:commit=None
    manifest={"schema_version":SCHEMA_VERSION,"run_id":run_id,"start_timestamp":started_wall,"end_timestamp":time.time(),"git_commit_sha":commit,"suite_path":str(suite),"suite_sha256":hashlib.sha256(suite.read_bytes()).hexdigest() if suite.exists() else None,"provider":args.provider,"provider_mode":provider.mode,"run_mode":args.mode,"resource_profile":args.profile,"model":args.model or "mock","sanitized_endpoint_host":getattr(provider,"endpoint_host",None),"requested_concurrency":args.concurrency,"effective_concurrency":args.concurrency,"request_limit":args.max_requests,"new_provider_request_count":summary["new_provider_requests"],"cache_hit_count":summary["cache_hits"],"retry_count":summary["retry_count"],"warmup_count":0,"completed_count":summary["completed_requests"],"success_count":summary["successful_requests"],"run_status":"completed" if not stop_reason and summary["failed_requests"]==0 else "partial","network_enabled":args.allow_network,**telemetry,"cost_configuration_status":summary["cost_status"],"stop_reason":stop_reason,"sanitized_command_configuration":{"provider":args.provider,"mode":args.mode,"profile":args.profile,"model":args.model or "mock"}}
    return write_run(root_base/"gpu-lab"/run_id,manifest,records,summary)
def _sanitize(text):
    for secret in (os.getenv("GPU_LAB_API_KEY",""),os.getenv("NVIDIA_API_KEY","")):
        if secret:text=text.replace(secret,"[REDACTED]")
    return text[:300]
def _failure_type(text): return "provider_api_failure" if "HTTP" in text or "429" in text else "parser_failure" if "malformed" in text else "provider_failure"
def main():print(run(build_parser().parse_args()))
if __name__=="__main__":main()
