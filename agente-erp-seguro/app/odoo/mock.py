"""ERP simulado en memoria con datos de ejemplo. Permite ejecutar todo sin Odoo."""
from __future__ import annotations

from .base import BackendError


class MockOdoo:
    def __init__(self) -> None:
        self.partners = [
            {"id": 1, "name": "Acme Industrial S.L."},
            {"id": 2, "name": "Acme Logistica S.L."},  # a proposito: "Acme" es ambiguo
            {"id": 3, "name": "Suministros Levante S.A."},
            {"id": 4, "name": "Solaris Energia S.L."},
        ]
        self.products = [
            {"id": 1, "name": "Tornillo M8"},
            {"id": 2, "name": "Panel solar 400W"},
            {"id": 3, "name": "Inversor 5kW"},
        ]
        self.leads: list[dict] = []
        self.orders: dict[tuple[str, int], dict] = {}
        self._seq = {"sale.order": 0, "purchase.order": 0, "crm.lead": 0}

    @staticmethod
    def _like(items: list[dict], q: str) -> list[dict]:
        q = q.casefold().strip()
        return [dict(i) for i in items if q and q in i["name"].casefold()]

    def search_partners(self, query: str) -> list[dict]:
        return self._like(self.partners, query)

    def search_products(self, query: str) -> list[dict]:
        return self._like(self.products, query)

    def create_lead(self, *, name, partner_name, email, expected_revenue, notes) -> int:
        self._seq["crm.lead"] += 1
        lead = {"id": self._seq["crm.lead"], "name": name, "partner_name": partner_name,
                "email": email, "expected_revenue": expected_revenue, "notes": notes}
        self.leads.append(lead)
        return lead["id"]

    def _create_order(self, model: str, partner_id: int, lines: list[dict]) -> int:
        if not any(p["id"] == partner_id for p in self.partners):
            raise BackendError(f"partner {partner_id} no existe")
        self._seq[model] += 1
        oid = self._seq[model]
        total = round(sum(l["quantity"] * l["unit_price"] for l in lines), 2)
        self.orders[(model, oid)] = {"id": oid, "partner_id": partner_id, "lines": lines,
                                     "state": "draft", "amount_total": total}
        return oid

    def create_sale_order(self, partner_id: int, lines: list[dict]) -> int:
        return self._create_order("sale.order", partner_id, lines)

    def create_purchase_order(self, partner_id: int, lines: list[dict]) -> int:
        return self._create_order("purchase.order", partner_id, lines)

    def get_order(self, model: str, order_id: int) -> dict | None:
        o = self.orders.get((model, order_id))
        return dict(o) if o else None

    def confirm_order(self, model: str, order_id: int) -> None:
        o = self.orders.get((model, order_id))
        if o is None:
            raise BackendError(f"{model} {order_id} no existe")
        if o["state"] != "draft":
            raise BackendError(f"{model} {order_id} no esta en borrador (estado: {o['state']})")
        o["state"] = "confirmed"
