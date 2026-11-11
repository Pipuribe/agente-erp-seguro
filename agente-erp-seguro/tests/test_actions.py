import pytest
from pydantic import ValidationError

from app.actions import CreateLead, CreateSaleOrder, OrderLine, action_adapter, idempotency_key


def test_rejects_negative_and_absurd_values():
    with pytest.raises(ValidationError):
        OrderLine(product="x", quantity=-1, unit_price=10)
    with pytest.raises(ValidationError):
        OrderLine(product="x", quantity=1, unit_price=-5)
    with pytest.raises(ValidationError):
        OrderLine(product="x", quantity=1_000_000, unit_price=1)


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        CreateLead(name="Lead", is_admin=True)


def test_rejects_bad_email():
    with pytest.raises(ValidationError):
        CreateLead(name="Lead", email="no-es-un-email")


def test_rejects_empty_order():
    with pytest.raises(ValidationError):
        CreateSaleOrder(customer="Acme", lines=[])


def test_idempotency_key_is_stable_and_sensitive():
    a = CreateSaleOrder(customer="Acme", lines=[OrderLine(product="x", quantity=1, unit_price=10)])
    b = CreateSaleOrder(customer="Acme", lines=[OrderLine(product="x", quantity=1, unit_price=10)])
    c = CreateSaleOrder(customer="Acme", lines=[OrderLine(product="x", quantity=2, unit_price=10)])
    d = CreateSaleOrder(customer="Acme", client_ref="otra", lines=[OrderLine(product="x", quantity=1, unit_price=10)])
    assert idempotency_key(a) == idempotency_key(b)
    assert idempotency_key(a) != idempotency_key(c)
    assert idempotency_key(a) != idempotency_key(d)


def test_discriminated_union_roundtrip():
    a = CreateLead(name="Lead de prueba")
    assert action_adapter.validate_python(a.model_dump(mode="json")) == a
