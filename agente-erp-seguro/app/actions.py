"""Acciones tipadas que el agente puede *proponer*.

Todo lo que el LLM quiera hacer pasa por estos esquemas: campos extra prohibidos,
rangos acotados y tipos estrictos. Si no valida, no existe.
"""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_ref: str | None = Field(
        default=None,
        max_length=64,
        description="Referencia opcional para repetir a proposito una accion identica.",
    )


class OrderLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product: str = Field(min_length=1, max_length=120)
    quantity: float = Field(gt=0, le=10_000)
    unit_price: float = Field(ge=0, le=1_000_000)


def _total(lines: list[OrderLine]) -> float:
    return round(sum(l.quantity * l.unit_price for l in lines), 2)


class CreateLead(_Base):
    """Crea una oportunidad en el CRM."""

    kind: Literal["create_lead"] = "create_lead"
    name: str = Field(min_length=3, max_length=200)
    partner_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    expected_revenue: float = Field(default=0, ge=0, le=10_000_000)
    notes: str | None = Field(default=None, max_length=2000)

    @property
    def amount(self) -> float:
        return 0.0  # una oportunidad no compromete dinero


class CreateSaleOrder(_Base):
    """Crea un presupuesto (borrador) de venta."""

    kind: Literal["create_sale_order"] = "create_sale_order"
    customer: str = Field(min_length=1, max_length=200)
    lines: list[OrderLine] = Field(min_length=1, max_length=50)

    @property
    def amount(self) -> float:
        return _total(self.lines)


class CreatePurchaseOrder(_Base):
    """Crea una solicitud de presupuesto (borrador) de compra."""

    kind: Literal["create_purchase_order"] = "create_purchase_order"
    supplier: str = Field(min_length=1, max_length=200)
    lines: list[OrderLine] = Field(min_length=1, max_length=50)

    @property
    def amount(self) -> float:
        return _total(self.lines)


class ConfirmOrder(_Base):
    """Confirma un pedido de venta o compra existente (compromete dinero)."""

    kind: Literal["confirm_order"] = "confirm_order"
    order_model: Literal["sale.order", "purchase.order"]
    order_id: int = Field(gt=0)


Action = Annotated[
    Union[CreateLead, CreateSaleOrder, CreatePurchaseOrder, ConfirmOrder],
    Field(discriminator="kind"),
]
action_adapter: TypeAdapter[Action] = TypeAdapter(Action)

PROPOSAL_TOOLS: dict[str, type[BaseModel]] = {
    "propose_create_lead": CreateLead,
    "propose_create_sale_order": CreateSaleOrder,
    "propose_create_purchase_order": CreatePurchaseOrder,
    "propose_confirm_order": ConfirmOrder,
}


def idempotency_key(action: BaseModel) -> str:
    """Hash canonico de la accion: la misma accion produce la misma clave."""
    canon = json.dumps(action.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()
