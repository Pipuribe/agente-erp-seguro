import pytest

from app.actions import ConfirmOrder, CreateLead, CreatePurchaseOrder, CreateSaleOrder, OrderLine
from app.gateway import GatewayError


def sale(customer="Solaris Energia S.L.", qty=10, price=250.0, **kw):
    return CreateSaleOrder(customer=customer, lines=[OrderLine(product="Panel solar 400W", quantity=qty, unit_price=price)], **kw)


def test_small_sale_executes_automatically(gateway, backend):
    r = gateway.propose(sale(qty=2, price=100))
    assert r.status == "executed"
    assert ("sale.order", 1) in backend.orders


def test_large_sale_waits_for_approval_and_does_not_touch_erp(gateway, backend):
    r = gateway.propose(sale())  # 2.500
    assert r.status == "pending"
    assert backend.orders == {}


def test_approve_executes_exactly_once(gateway, backend):
    r = gateway.propose(sale())
    ok = gateway.approve(r.id, "ana")
    assert ok.status == "executed"
    assert len(backend.orders) == 1
    with pytest.raises(GatewayError):
        gateway.approve(r.id, "ana")  # segundo intento
    assert len(backend.orders) == 1


def test_reject_never_executes(gateway, backend):
    r = gateway.propose(sale())
    assert gateway.reject(r.id, "ana", "no procede").status == "rejected"
    with pytest.raises(GatewayError):
        gateway.approve(r.id, "ana")
    assert backend.orders == {}


def test_duplicate_proposal_returns_same_action(gateway, backend):
    first = gateway.propose(sale(qty=2, price=100))
    again = gateway.propose(sale(qty=2, price=100))
    assert again.duplicate and again.id == first.id
    assert len(backend.orders) == 1


def test_client_ref_allows_intentional_repeat(gateway, backend):
    gateway.propose(sale(qty=2, price=100))
    gateway.propose(sale(qty=2, price=100, client_ref="segundo-pedido"))
    assert len(backend.orders) == 2


def test_hard_limit_is_denied_and_cannot_be_approved(gateway, backend):
    r = gateway.propose(sale(qty=1000, price=100))
    assert r.status == "denied"
    with pytest.raises(GatewayError):
        gateway.approve(r.id, "ana")
    assert backend.orders == {}


def test_ambiguous_customer_fails_instead_of_guessing(gateway, backend):
    r = gateway.propose(sale(customer="Acme", qty=1, price=10))
    assert r.status == "failed"
    assert "ambiguo" in r.result["error"]
    assert backend.orders == {}


def test_unknown_product_fails(gateway):
    a = CreateSaleOrder(customer="Solaris", lines=[OrderLine(product="Cohete", quantity=1, unit_price=1)])
    assert gateway.propose(a).status == "failed"


def test_confirm_requires_approval_and_changes_state(gateway, backend):
    gateway.propose(sale(qty=2, price=100))  # pedido 1, borrador
    r = gateway.propose(ConfirmOrder(order_model="sale.order", order_id=1))
    assert r.status == "pending"
    assert backend.orders[("sale.order", 1)]["state"] == "draft"
    gateway.approve(r.id, "ana")
    assert backend.orders[("sale.order", 1)]["state"] == "confirmed"


def test_confirm_nonexistent_order_fails(gateway):
    assert gateway.propose(ConfirmOrder(order_model="sale.order", order_id=99)).status == "failed"


def test_dry_run_never_writes(make_gateway, backend):
    gw = make_gateway(dry_run=True)
    r = gw.propose(sale(qty=2, price=100))
    assert r.status == "dry_run"
    assert backend.orders == {}
    p = gw.propose(sale())
    with pytest.raises(GatewayError):
        gw.approve(p.id, "ana")


def test_audit_log_records_the_flow(gateway, store):
    r = gateway.propose(sale())
    gateway.approve(r.id, "ana")
    events = [e["event"] for e in store.list_audit()]
    assert "pending_approval" in events and "approved" in events and "executed" in events


def test_lead_and_purchase(gateway, backend):
    assert gateway.propose(CreateLead(name="Interesado en paneles")).status == "executed"
    buy = CreatePurchaseOrder(supplier="Suministros Levante", lines=[OrderLine(product="Tornillo M8", quantity=100, unit_price=0.1)])
    assert gateway.propose(buy).status == "executed"
    assert len(backend.leads) == 1 and ("purchase.order", 1) in backend.orders
