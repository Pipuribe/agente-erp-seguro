"""Politica de riesgo. Funcion pura: facil de testear y de auditar.

Principio: ante la duda, pedir aprobacion humana (fail closed).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .actions import ConfirmOrder, CreateLead, CreatePurchaseOrder, CreateSaleOrder
from .config import Settings


class Decision(str, Enum):
    AUTO = "auto"
    APPROVAL = "approval"
    DENY = "deny"


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    reason: str


def evaluate(action, amount: float, s: Settings) -> Verdict:
    if amount > s.hard_limit:
        return Verdict(Decision.DENY, f"importe {amount:.2f} supera el limite duro {s.hard_limit:.2f}")

    if isinstance(action, ConfirmOrder):
        return Verdict(Decision.APPROVAL, "confirmar un pedido compromete dinero: requiere aprobacion humana")

    if isinstance(action, (CreateSaleOrder, CreatePurchaseOrder)):
        if any(l.unit_price == 0 for l in action.lines):
            return Verdict(Decision.APPROVAL, "linea con precio 0: requiere revision")

    if isinstance(action, CreatePurchaseOrder):
        if amount > s.purchase_auto_limit:
            return Verdict(Decision.APPROVAL, f"compra de {amount:.2f} supera el limite automatico {s.purchase_auto_limit:.2f}")
        return Verdict(Decision.AUTO, "compra dentro del limite automatico (borrador)")

    if isinstance(action, CreateSaleOrder):
        if amount > s.sale_auto_limit:
            return Verdict(Decision.APPROVAL, f"venta de {amount:.2f} supera el limite automatico {s.sale_auto_limit:.2f}")
        return Verdict(Decision.AUTO, "venta dentro del limite automatico (borrador)")

    if isinstance(action, CreateLead):
        return Verdict(Decision.AUTO, "crear una oportunidad es reversible y no compromete dinero")

    return Verdict(Decision.APPROVAL, "accion desconocida: por defecto requiere aprobacion")
