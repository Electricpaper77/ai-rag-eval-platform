from __future__ import annotations
import json, os, secrets, time
import base64
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from .repository import create_org, create_project, create_run, get_run
from .oidc import OIDCConfig, MemorySessionStore, begin_login, consume_login_state, exchange_code, internal_user_key, verify_id_token
from .deployment import validate_deployment_configuration
from .lifecycle import export_tenant, delete_tenant

router=APIRouter(prefix="/saas",tags=["saas"])
LOGIN_STATES: dict[str, dict[str, object]] = {}
SESSIONS = MemorySessionStore()
def session_store():
    validate_deployment_configuration()
    policy = os.getenv("AGENTTRUST_DEPLOYMENT_POLICY", "").strip().lower()
    if policy in ("production", "staging"):
        from .postgres_repository import PostgresSessionStore, protected_connect
        return PostgresSessionStore(protected_connect)
    if os.getenv("AGENTTRUST_SAAS_DB", "").strip() or not os.getenv("AGENTTRUST_POSTGRES_URL", "").strip() or os.getenv("AGENTTRUST_SAAS_RUNTIME_MODE", "production").strip().lower() in ("local", "test"):
        return SESSIONS
    from .postgres_repository import PostgresSessionStore, protected_connect
    return PostgresSessionStore(protected_connect)

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
        store = session_store()
        session = store.get(sid, csrf=csrf) if sid and isinstance(store, MemorySessionStore) else (store.get(sid, csrf) if sid else None)
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
    response.set_cookie("agenttrust_session",sid,path="/",httponly=True,secure=True,samesite="lax",max_age=3600); response.set_cookie("agenttrust_csrf",csrf,path="/",httponly=False,secure=True,samesite="lax",max_age=3600); return {"authenticated":True,"csrf_token":csrf}
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
@router.post("/projects")
def projects(body: ProjectIn, request: Request, authorization: str|None=Header(default=None)):
    require_cookie_csrf(request); user=identity(authorization, request)
    try: return create_project(body.organization_id,user["user_id"],body.name)
    except PermissionError: raise HTTPException(403,"organization admin permission required")
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
@router.get("/evaluations/{run_id}")
def evaluation(run_id: str, request: Request, authorization: str|None=Header(default=None), x_organization_id: str|None=Header(default=None)):
    user=identity(authorization, request)
    try: row=get_run(org_id(user,x_organization_id),user["user_id"],run_id)
    except PermissionError: raise HTTPException(403,"organization membership required")
    if row is None: raise HTTPException(404,"evaluation not found")
    if isinstance(row["result_json"], str): row["result_json"]=json.loads(row["result_json"])
    if isinstance(row["evidence_metadata_json"], str): row["evidence_metadata_json"]=json.loads(row["evidence_metadata_json"])
    return row
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
