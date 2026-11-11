from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app
from app.odoo.mock import MockOdoo
from tests.conftest import FakeLLM, resp, text, tool_use

ORDER = {"customer": "Solaris Energia S.L.", "lines": [{"product": "Panel solar 400W", "quantity": 10, "unit_price": 250}]}


def make_client(settings):
    backend = MockOdoo()
    llm = FakeLLM([
        resp([tool_use("propose_create_sale_order", ORDER)], "tool_use"),
        resp([text("pendiente de aprobacion")], "end_turn"),
    ])
    return TestClient(create_app(settings, backend, llm_client=llm)), backend


def test_chat_creates_pending_proposal(settings):
    c, backend = make_client(settings)
    r = c.post("/chat", json={"message": "presupuesto para Solaris"})
    assert r.status_code == 200
    assert r.json()["proposals"][0]["status"] == "pending"
    assert backend.orders == {}


def test_approval_requires_valid_token(settings):
    c, backend = make_client(settings)
    pid = c.post("/chat", json={"message": "x"}).json()["proposals"][0]["id"]
    body = {"approver": "ana"}
    assert c.post(f"/actions/{pid}/approve", json=body).status_code == 401
    assert c.post(f"/actions/{pid}/approve", json=body, headers={"X-Approval-Token": "mal"}).status_code == 401
    assert backend.orders == {}
    ok = c.post(f"/actions/{pid}/approve", json=body, headers={"X-Approval-Token": "secret"})
    assert ok.status_code == 200 and ok.json()["status"] == "executed"
    again = c.post(f"/actions/{pid}/approve", json=body, headers={"X-Approval-Token": "secret"})
    assert again.status_code == 409
    assert len(backend.orders) == 1


def test_approvals_disabled_when_no_token_configured(settings):
    c, backend = make_client(replace(settings, approval_token=""))
    pid = c.post("/chat", json={"message": "x"}).json()["proposals"][0]["id"]
    r = c.post(f"/actions/{pid}/approve", json={"approver": "ana"}, headers={"X-Approval-Token": ""})
    assert r.status_code == 503
    assert backend.orders == {}


def test_audit_endpoint(settings):
    c, _ = make_client(settings)
    c.post("/chat", json={"message": "x"})
    assert any(e["event"] == "pending_approval" for e in c.get("/audit").json())
