from __future__ import annotations
import csv, io, json, os, secrets, time
import base64
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from .repository import create_org, create_project, create_run, get_run, list_orgs, list_projects, search_runs, use_postgres
from .oidc import OIDCConfig, MemorySessionStore, begin_login, consume_login_state, exchange_code, internal_user_key, verify_id_token
from .deployment import validate_deployment_configuration
from .lifecycle import export_tenant, delete_tenant

router=APIRouter(prefix="/saas",tags=["saas"])
LOGIN_STATES: dict[str, dict[str, object]] = {}
SESSIONS = MemorySessionStore()
def session_store():
    validate_deployment_configuration()
    if use_postgres():
        from .postgres_repository import PostgresSessionStore, protected_connect
        return PostgresSessionStore(protected_connect)
    return SESSIONS

def login_state_store():
    policy = os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower()
    if policy in ("production", "staging"):
        from .postgres_repository import PostgresLoginStateStore, connect
        key = os.getenv("AGENTTRUST_OIDC_STATE_ENCRYPTION_KEY", "").strip().encode()
        if not key:
            raise RuntimeError("OIDC state encryption key is required by deployment policy")
        try:
            base64.urlsafe_b64decode(key)
        except Exception as exc:
            raise RuntimeError("OIDC state encryption key is invalid") from exc
        return PostgresLoginStateStore(connect, key)
    return LOGIN_STATES
class OrgIn(BaseModel): name: str = Field(min_length=1,max_length=100)
class ProjectIn(BaseModel): organization_id: str; name: str = Field(min_length=1,max_length=100)
def identity(authorization: str | None, request: Request | None = None) -> dict[str,Any]:
    if request is not None:
        sid = request.cookies.get("agenttrust_session")
        csrf = request.headers.get("x-csrf-token") if sid else None
        try:
            store = session_store()
            session = store.get(sid, csrf=csrf) if sid and isinstance(store, MemorySessionStore) else (store.get(sid, csrf) if sid else None)
        except PermissionError as exc:
            raise HTTPException(503, "database target is quarantined") from exc
        if session is not None: return session | {"auth_source": "oidc-session", "session_id": sid}
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401,"authentication required")
    mode=os.getenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production").strip().lower()
    raw=authorization[7:].strip(); configured_raw=os.getenv("AGENTTRUST_SAAS_IDENTITIES_LOCAL_TEST_ONLY", "{}")
    if mode in ("local", "test"):
        try: configured=json.loads(configured_raw)
        except json.JSONDecodeError: raise HTTPException(503,"invalid local/test identity configuration")
        if not isinstance(configured,dict): raise HTTPException(503,"invalid local/test identity configuration")
        item=configured.get(raw)
        if not isinstance(item,dict) or not item.get("user_id"): raise HTTPException(401,"invalid identity")
        return item | {"token": raw, "auth_source": "local-test-only"}
    if configured_raw.strip() not in ("", "{}"):
        raise HTTPException(503,"local/test identities are disabled outside local/test runtime")
    try:
        claims=verify_id_token(raw, OIDCConfig.from_env())
    except Exception as exc:
        raise HTTPException(401,"invalid OIDC identity") from exc
    return {"user_id": internal_user_key(claims), "issuer": claims["issuer"], "subject": claims["subject"], "auth_source": "oidc"}
def org_id(user: dict[str,Any], requested: str | None) -> str:
    value=requested or user.get("organization_id")
    if not value: raise HTTPException(400,"organization_id required")
    return str(value)
def require_cookie_csrf(request: Request) -> None:
    if request.cookies.get("agenttrust_session"):
        origin = request.headers.get("origin", "").rstrip("/")
        allowed = os.getenv("AGENTTRUST_PUBLIC_ORIGIN", "").rstrip("/")
        token = request.headers.get("x-csrf-token")
        if not origin or not allowed or origin != allowed or not token: raise HTTPException(403, "CSRF validation failed")
def lifecycle_connection():
    validate_deployment_configuration()
    from .postgres_repository import protected_connect
    return protected_connect()
def _detail_payload(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    result = item.get("result_json")
    evidence = item.get("evidence_metadata_json")
    if isinstance(result, str):
        try: result = json.loads(result)
        except json.JSONDecodeError: result = None
    if isinstance(evidence, str):
        try: evidence = json.loads(evidence)
        except json.JSONDecodeError: evidence = None
    item["result"] = result
    item["evidence"] = evidence
    item["missing_evidence"] = [name for name, value in (("result", result), ("evidence", evidence)) if value in (None, {}, [])]
    return item
def _csv_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _csv_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_csv_safe_value(item) for item in value]
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value

def _csv_value(value: Any) -> str:
    value = _csv_safe_value(value)
    text = json.dumps(value, default=str, sort_keys=True) if isinstance(value, (dict, list)) else str(value if value is not None else "")
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
@router.get("/auth/login")
def login(response: Response):
    config=OIDCConfig.from_env(); store=login_state_store(); local={}; url,state=begin_login(config, local)
    if store is not LOGIN_STATES: store.put(state, local[state], config, float(local[state]["expires_at"]))
    else: LOGIN_STATES.update(local)
    response.status_code=307; response.headers["location"]=url; return {"state":state}
@router.get("/auth/callback")
def callback(code: str, state: str, response: Response):
    config=OIDCConfig.from_env(); store=login_state_store()
    item=store.consume(state, config) if store is not LOGIN_STATES else consume_login_state(LOGIN_STATES,state)
    token=exchange_code(config,code,str(item["verifier"]))
    claims=verify_id_token(token,config,expected_nonce=str(item["nonce"]))
    sid=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32); store=session_store(); user={"user_id":internal_user_key(claims),"issuer":claims["issuer"],"subject":claims["subject"]}
    if isinstance(store, MemorySessionStore): store.put(sid,user | {"csrf":csrf},time.time()+3600)
    else: store.put(sid,user,time.time()+3600,csrf)
    secure_cookie = os.getenv("AGENTTRUST_TEST_HTTP_COOKIES", "").strip().lower() != "true"
    response.set_cookie("agenttrust_session",sid,path="/",httponly=True,secure=secure_cookie,samesite="lax",max_age=3600); response.set_cookie("agenttrust_csrf",csrf,path="/",httponly=False,secure=secure_cookie,samesite="lax",max_age=3600); return {"authenticated":True,"csrf_token":csrf}
@router.post("/auth/logout")
def logout(request: Request, response: Response):
    require_cookie_csrf(request)
    sid=request.cookies.get("agenttrust_session")
    if sid:
        store=session_store(); store.revoke(sid) if hasattr(store, "revoke") else store.delete(sid)
    response.delete_cookie("agenttrust_session"); response.delete_cookie("agenttrust_csrf"); return {"logged_out":True}
@router.post("/organizations")
def organizations(body: OrgIn, request: Request, authorization: str|None=Header(default=None)):
    require_cookie_csrf(request)
    try: return create_org(identity(authorization, request)["user_id"],body.name)
    except PermissionError as exc: raise HTTPException(503, "database target is quarantined") from exc
@router.get("/organizations")
def organizations_list(request: Request, authorization: str|None=Header(default=None)):
    user = identity(authorization, request)
    try: return {"organizations": list_orgs(user["user_id"])}
    except PermissionError as exc: raise HTTPException(503, "database target is quarantined") from exc
@router.post("/projects")
def projects(body: ProjectIn, request: Request, authorization: str|None=Header(default=None)):
    require_cookie_csrf(request); user=identity(authorization, request)
    try: return create_project(body.organization_id,user["user_id"],body.name)
    except PermissionError: raise HTTPException(403,"organization admin permission required")
@router.get("/projects")
def projects_list(organization_id: str, request: Request, authorization: str|None=Header(default=None)):
    user = identity(authorization, request)
    try: return {"projects": list_projects(organization_id, user["user_id"])}
    except PermissionError as exc: raise HTTPException(403, "organization membership required") from exc
@router.get("/evaluations")
def evaluations_list(organization_id: str, request: Request, authorization: str|None=Header(default=None), project_id: str|None=None, search: str = "", status: str = "", page: int = 1, page_size: int = 20):
    user = identity(authorization, request)
    try: return search_runs(organization_id, user["user_id"], project_id, search[:100], status[:40], page, page_size)
    except PermissionError as exc: raise HTTPException(403, "organization membership required") from exc
@router.post("/projects/{project_id}/evaluations")
async def evaluations(project_id: str, request: Request, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None), idempotency_key: str|None=Header(default=None)):
    require_cookie_csrf(request); user=identity(authorization, request); org=org_id(user,x_organization_id)
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
@router.get("/evaluations/compare")
def evaluations_compare(organization_id: str, run_id_a: str, run_id_b: str, request: Request, authorization: str|None=Header(default=None)):
    user = identity(authorization, request)
    try:
        first = get_run(organization_id, user["user_id"], run_id_a)
        second = get_run(organization_id, user["user_id"], run_id_b)
    except PermissionError as exc: raise HTTPException(403, "organization membership required") from exc
    if first is None or second is None: raise HTTPException(404, "evaluation not found")
    return {"runs": [_detail_payload(first), _detail_payload(second)], "comparison": {"same_project": first["project_id"] == second["project_id"], "sample_count_delta": first["sample_count"] - second["sample_count"], "status_match": first["status"] == second["status"]}}
@router.get("/evaluations/{run_id}")
def evaluation(run_id: str, request: Request, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None), organization_id: str|None=None):
    user=identity(authorization, request)
    try: row=get_run(org_id(user, organization_id or x_organization_id),user["user_id"],run_id)
    except PermissionError: raise HTTPException(403,"organization membership required")
    if row is None: raise HTTPException(404,"evaluation not found")
    return _detail_payload(row)
@router.get("/evaluations/{run_id}/export")
def evaluation_export(run_id: str, request: Request, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None), organization_id: str|None=None, format: str = "json"):
    user=identity(authorization, request)
    try: row=get_run(org_id(user, organization_id or x_organization_id),user["user_id"],run_id)
    except PermissionError: raise HTTPException(403,"organization membership required")
    if row is None: raise HTTPException(404,"evaluation not found")
    payload = _detail_payload(row)
    if format.lower() == "json":
        return Response(content=json.dumps(payload, default=str), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{run_id}.json"'})
    if format.lower() != "csv": raise HTTPException(400, "format must be json or csv")
    output=io.StringIO(); writer=csv.writer(output); writer.writerow(["field", "value"])
    for key, value in payload.items(): writer.writerow([key, _csv_value(value)])
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{run_id}.csv"'})
@router.get("/organizations/{organization_id}/export")
def organization_export(organization_id: str, request: Request, authorization: str|None=Header(default=None)):
    user = identity(authorization, request)
    try:
        with lifecycle_connection() as conn:
            return export_tenant(conn, organization_id, user["user_id"])
    except PermissionError as exc: raise HTTPException(403, str(exc))
    except KeyError as exc: raise HTTPException(404, str(exc))
@router.delete("/organizations/{organization_id}")
def organization_delete(organization_id: str, request: Request, confirmation: str|None=Header(default=None, alias="X-Deletion-Confirmation"), authorization: str|None=Header(default=None)):
    require_cookie_csrf(request); user = identity(authorization, request)
    try:
        with lifecycle_connection() as conn:
            return delete_tenant(conn, organization_id, user["user_id"], confirmation or "")
    except PermissionError as exc: raise HTTPException(403, str(exc))
    except KeyError as exc: raise HTTPException(404, str(exc))

