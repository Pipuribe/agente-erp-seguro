"""Backend real para Odoo via API externa XML-RPC (autenticacion con API key).

Funciona en versiones recientes de Odoo. La documentacion oficial indica que
XML-RPC/JSON-RPC se retiraran en una version futura a favor de la API JSON-2:
revisa la doc de tu version antes de usarlo en produccion.
"""
from __future__ import annotations

import xmlrpc.client

from .base import BackendError


class OdooXmlRpc:
    def __init__(self, url: str, db: str, user: str, api_key: str) -> None:
        self.db, self.api_key = db, api_key
        try:
            common = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/common")
            uid = common.authenticate(db, user, api_key, {})
        except (OSError, xmlrpc.client.Error) as e:
            raise BackendError(f"no se pudo conectar con Odoo: {e}") from e
        if not uid:
            raise BackendError("autenticacion en Odoo fallida (revisa usuario, BD y API key)")
        self.uid = uid
        self._models = xmlrpc.client.ServerProxy(f"{url.rstrip('/')}/xmlrpc/2/object")

    def _call(self, model: str, method: str, args: list, kwargs: dict | None = None):
        try:
            return self._models.execute_kw(self.db, self.uid, self.api_key, model, method, args, kwargs or {})
        except xmlrpc.client.Fault as e:
            raise BackendError(f"Odoo rechazo {model}.{method}: {e.faultString.splitlines()[-1]}") from e
        except OSError as e:
            raise BackendError(f"error de red con Odoo: {e}") from e

    def _search(self, model: str, query: str) -> list[dict]:
        if not query.strip():
            return []
        rows = self._call(model, "search_read", [[["name", "ilike", query]]], {"fields": ["id", "name"], "limit": 10})
        return [{"id": r["id"], "name": r["name"]} for r in rows]

    def search_partners(self, query: str) -> list[dict]:
        return self._search("res.partner", query)

    def search_products(self, query: str) -> list[dict]:
        return self._search("product.product", query)

    def create_lead(self, *, name, partner_name, email, expected_revenue, notes) -> int:
        vals = {"name": name, "partner_name": partner_name or False, "email_from": email or False,
                "expected_revenue": expected_revenue, "description": notes or False}
        return self._call("crm.lead", "create", [vals])

    def create_sale_order(self, partner_id: int, lines: list[dict]) -> int:
        vals = {"partner_id": partner_id, "order_line": [
            (0, 0, {"product_id": l["product_id"], "product_uom_qty": l["quantity"], "price_unit": l["unit_price"]})
            for l in lines]}
        return self._call("sale.order", "create", [vals])

    def create_purchase_order(self, partner_id: int, lines: list[dict]) -> int:
        vals = {"partner_id": partner_id, "order_line": [
            (0, 0, {"product_id": l["product_id"], "name": l["product_name"],
                    "product_qty": l["quantity"], "price_unit": l["unit_price"]})
            for l in lines]}
        return self._call("purchase.order", "create", [vals])

    def get_order(self, model: str, order_id: int) -> dict | None:
        rows = self._call(model, "search_read", [[["id", "=", order_id]]], {"fields": ["state", "amount_total"]})
        return rows[0] if rows else None

    def confirm_order(self, model: str, order_id: int) -> None:
        order = self.get_order(model, order_id)
        if order is None:
            raise BackendError(f"{model} {order_id} no existe")
        if order["state"] not in ("draft", "sent"):
            raise BackendError(f"{model} {order_id} no esta en borrador (estado: {order['state']})")
        method = "action_confirm" if model == "sale.order" else "button_confirm"
        self._call(model, method, [[order_id]])
