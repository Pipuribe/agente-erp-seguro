"""Traduce una accion YA validada y autorizada en llamadas al ERP.

Es la unica parte del sistema que escribe en el ERP. El LLM nunca llega aqui
directamente: solo el Gateway lo invoca.
"""
from __future__ import annotations

from .actions import ConfirmOrder, CreateLead, CreatePurchaseOrder, CreateSaleOrder
from .odoo.base import BackendError, ERPBackend


def _resolve(items: list[dict], query: str, what: str) -> dict:
    """Exactamente una coincidencia o error: nunca adivinamos entre candidatos."""
    exact = [i for i in items if i["name"].casefold() == query.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(items) == 1:
        return items[0]
    if not items:
        raise BackendError(f"{what} '{query}' no encontrado")
    names = ", ".join(i["name"] for i in items[:5])
    raise BackendError(f"{what} '{query}' es ambiguo: {names}")


def _lines(backend: ERPBackend, lines) -> list[dict]:
    out = []
    for l in lines:
        p = _resolve(backend.search_products(l.product), l.product, "producto")
        out.append({"product_id": p["id"], "product_name": p["name"],
                    "quantity": l.quantity, "unit_price": l.unit_price})
    return out


def execute(backend: ERPBackend, action) -> dict:
    if isinstance(action, CreateLead):
        lead_id = backend.create_lead(name=action.name, partner_name=action.partner_name, email=action.email,
                                      expected_revenue=action.expected_revenue, notes=action.notes)
        return {"odoo_model": "crm.lead", "odoo_id": lead_id}

    if isinstance(action, CreateSaleOrder):
        partner = _resolve(backend.search_partners(action.customer), action.customer, "cliente")
        oid = backend.create_sale_order(partner["id"], _lines(backend, action.lines))
        return {"odoo_model": "sale.order", "odoo_id": oid, "partner": partner["name"], "amount": action.amount}

    if isinstance(action, CreatePurchaseOrder):
        partner = _resolve(backend.search_partners(action.supplier), action.supplier, "proveedor")
        oid = backend.create_purchase_order(partner["id"], _lines(backend, action.lines))
        return {"odoo_model": "purchase.order", "odoo_id": oid, "partner": partner["name"], "amount": action.amount}

    if isinstance(action, ConfirmOrder):
        backend.confirm_order(action.order_model, action.order_id)
        return {"odoo_model": action.order_model, "odoo_id": action.order_id, "state": "confirmed"}

    raise BackendError(f"accion no soportada: {type(action).__name__}")
