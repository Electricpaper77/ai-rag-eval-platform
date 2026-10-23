from __future__ import annotations
import json, os
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field
from .repository import create_org, create_project, create_run, get_run

router=APIRouter(prefix="/saas",tags=["saas"])
class OrgIn(BaseModel): name: str = Field(min_length=1,max_length=100)
class ProjectIn(BaseModel): organization_id: str; name: str = Field(min_length=1,max_length=100)
def identity(authorization: str | None) -> dict[str,Any]:
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401,"authentication required")
    mode=os.getenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production").strip().lower()
    raw=authorization[7:].strip(); configured_raw=os.getenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY", "{}")
    if mode not in ("local", "test") and configured_raw.strip() not in ("", "{}"):
        raise HTTPException(503,"local/test identities are disabled outside local/test runtime")
    try: configured=json.loads(configured_raw)
    except json.JSONDecodeError: raise HTTPException(503,"invalid local/test identity configuration")
    if not isinstance(configured,dict): raise HTTPException(503,"invalid local/test identity configuration")
    item=configured.get(raw)
    if not isinstance(item,dict) or not item.get("user_id"): raise HTTPException(401,"invalid identity")
    return item | {"token": raw}
def org_id(user: dict[str,Any], requested: str | None) -> str:
    value=requested or user.get("organization_id")
    if not value: raise HTTPException(400,"organization_id required")
    return str(value)
@router.post("/organizations")
def organizations(body: OrgIn, authorization: str|None=Header(default=None)): return create_org(identity(authorization)["user_id"],body.name)
@router.post("/projects")
def projects(body: ProjectIn, authorization: str|None=Header(default=None)):
    user=identity(authorization)
    try: return create_project(body.organization_id,user["user_id"],body.name)
    except PermissionError: raise HTTPException(403,"organization admin permission required")
@router.post("/projects/{project_id}/evaluations")
async def evaluations(project_id: str, request: Request, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None), idempotency_key: str|None=Header(default=None)):
    user=identity(authorization); org=org_id(user,x_organization_id)
    if not idempotency_key or len(idempotency_key)>100: raise HTTPException(400,"Idempotency-Key header required")
    raw=await request.body()
    if len(raw)>2_000_000: raise HTTPException(413,"dataset exceeds 2MB limit")
    rows=[]
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            try: value=json.loads(line)
            except json.JSONDecodeError: raise HTTPException(400,"dataset must be JSONL")
            if not isinstance(value,dict): raise HTTPException(400,"each JSONL row must be an object")
            rows.append(value)
    if not rows or len(rows)>1000: raise HTTPException(400,"dataset must contain 1-1000 rows")
    try: return create_run(org,user["user_id"],project_id,idempotency_key,rows,int(os.getenv("AGENTTRUST_FREE_QUOTA_UNITS","1000")))
    except KeyError: raise HTTPException(404,"project not found")
    except PermissionError as exc:
        if str(exc) == "organization membership required": raise HTTPException(403,"organization membership required")
        raise HTTPException(402,str(exc))
@router.get("/evaluations/{run_id}")
def evaluation(run_id: str, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None)):
    user=identity(authorization)
    try: row=get_run(org_id(user,x_organization_id),user["user_id"],run_id)
    except PermissionError: raise HTTPException(403,"organization membership required")
    if row is None: raise HTTPException(404,"evaluation not found")
    row["result_json"]=json.loads(row["result_json"]); row["evidence_metadata_json"]=json.loads(row["evidence_metadata_json"]); return row
