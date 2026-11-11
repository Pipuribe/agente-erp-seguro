"""API HTTP. Arranque:  uvicorn app.main:create_app --factory --reload"""
from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .agent import Agent
from .config import Settings
from .gateway import Gateway, GatewayError
from .odoo.base import ERPBackend
from .odoo.mock import MockOdoo
from .store import Store


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class DecisionIn(BaseModel):
    approver: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=500)


def build_backend(s: Settings) -> ERPBackend:
    if s.backend == "odoo":
        from .odoo.xmlrpc_client import OdooXmlRpc

        return OdooXmlRpc(s.odoo_url, s.odoo_db, s.odoo_user, s.odoo_api_key)
    return MockOdoo()


def create_app(settings: Settings | None = None, backend: ERPBackend | None = None,
               llm_client=None) -> FastAPI:
    s = settings or Settings.from_env()
    backend = backend or build_backend(s)
    store = Store(s.db_path)
    gateway = Gateway(backend, store, s)
    agent = Agent(gateway, backend, client=llm_client, model=s.anthropic_model)

    app = FastAPI(title="agente-erp-seguro", version="0.1.0")
    app.state.gateway, app.state.store, app.state.backend = gateway, store, backend

    def require_approver(x_approval_token: str = Header(default="")) -> None:
        if not s.approval_token:  # fail closed
            raise HTTPException(503, "aprobaciones deshabilitadas: define APPROVAL_TOKEN")
        if not secrets.compare_digest(x_approval_token, s.approval_token):
            raise HTTPException(401, "token de aprobacion invalido")

    @app.get("/health")
    def health():
        return {"status": "ok", "backend": s.backend, "dry_run": s.dry_run}

    @app.post("/chat")
    def chat(body: ChatIn):
        out = agent.run(body.message)
        return {"reply": out.reply, "proposals": out.proposals}

    @app.get("/actions")
    def list_actions(status: str | None = None):
        return store.list_actions(status)

    @app.post("/actions/{action_id}/approve", dependencies=[Depends(require_approver)])
    def approve(action_id: int, body: DecisionIn):
        try:
            return gateway.approve(action_id, body.approver).to_dict()
        except GatewayError as e:
            raise HTTPException(409, str(e))

    @app.post("/actions/{action_id}/reject", dependencies=[Depends(require_approver)])
    def reject(action_id: int, body: DecisionIn):
        try:
            return gateway.reject(action_id, body.approver, body.reason).to_dict()
        except GatewayError as e:
            raise HTTPException(409, str(e))

    @app.get("/audit")
    def audit(limit: int = 100):
        return store.list_audit(min(max(limit, 1), 500))

    return app
