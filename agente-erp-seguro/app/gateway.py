"""Gateway: unico punto de entrada para cualquier accion sobre el ERP.

propose()  -> valida, deduplica, aplica politica y (si procede) ejecuta o encola.
approve()  -> un humano autoriza una accion pendiente; se ejecuta exactamente una vez.
reject()   -> un humano la descarta.
Todo queda en el log de auditoria.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .actions import ConfirmOrder, action_adapter, idempotency_key
from .config import Settings
from .executor import execute
from .odoo.base import BackendError, ERPBackend
from .policy import Decision, evaluate
from .store import DuplicateError, Store


class GatewayError(Exception):
    pass


@dataclass
class ProposalResult:
    id: int
    status: str
    reason: str
    duplicate: bool = False
    result: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Gateway:
    def __init__(self, backend: ERPBackend, store: Store, settings: Settings) -> None:
        self.backend, self.store, self.settings = backend, store, settings

    # -- helpers ---------------------------------------------------------
    def _amount(self, action) -> float:
        if isinstance(action, ConfirmOrder):
            order = self.backend.get_order(action.order_model, action.order_id)
            if order is None:
                raise GatewayError(f"{action.order_model} {action.order_id} no existe")
            return float(order["amount_total"])
        return float(action.amount)

    def _snapshot(self, action_id: int) -> ProposalResult:
        row = self.store.get(action_id)
        return ProposalResult(row["id"], row["status"], row["reason"] or "", False, row["result"])

    def _run(self, action_id: int, action, actor: str) -> ProposalResult:
        try:
            result = execute(self.backend, action)
        except Exception as e:  # el ERP puede fallar de muchas formas; nunca debe tumbar el flujo
            self.store.finish(action_id, "failed", {"error": str(e)})
            self.store.audit(actor, "execution_failed", action_id, str(e))
        else:
            self.store.finish(action_id, "executed", result)
            self.store.audit(actor, "executed", action_id, str(result))
        return self._snapshot(action_id)

    # -- API publica -----------------------------------------------------
    def propose(self, action, actor: str = "agent") -> ProposalResult:
        key = idempotency_key(action)
        payload = action.model_dump(mode="json")

        existing = self.store.find_active(key)
        if existing:
            self.store.audit(actor, "duplicate_proposal", existing["id"])
            return ProposalResult(existing["id"], existing["status"], "duplicada de una accion existente",
                                  True, existing["result"])

        def insert(status: str, reason: str, amount: float) -> int:
            return self.store.insert_action(key=key, kind=action.kind, payload=payload, amount=amount,
                                            status=status, reason=reason, requested_by=actor)

        try:
            amount = self._amount(action)
        except (GatewayError, BackendError) as e:
            aid = insert("failed", str(e), 0.0)
            self.store.audit(actor, "proposal_failed", aid, str(e))
            return self._snapshot(aid)

        verdict = evaluate(action, amount, self.settings)
        try:
            if verdict.decision is Decision.DENY:
                aid = insert("denied", verdict.reason, amount)
                self.store.audit(actor, "denied", aid, verdict.reason)
                return self._snapshot(aid)

            if verdict.decision is Decision.APPROVAL:
                aid = insert("pending", verdict.reason, amount)
                self.store.audit(actor, "pending_approval", aid, verdict.reason)
                return self._snapshot(aid)

            # AUTO
            if self.settings.dry_run:
                aid = insert("dry_run", verdict.reason, amount)
                self.store.finish(aid, "dry_run", {"would_execute": payload})
                self.store.audit(actor, "dry_run", aid, verdict.reason)
                return self._snapshot(aid)

            aid = insert("executing", verdict.reason, amount)
            self.store.audit(actor, "auto_approved", aid, verdict.reason)
            return self._run(aid, action, actor)
        except DuplicateError:  # carrera: otra peticion identica gano
            existing = self.store.find_active(key)
            return ProposalResult(existing["id"], existing["status"], "duplicada", True, existing["result"])

    def approve(self, action_id: int, approver: str) -> ProposalResult:
        row = self.store.get(action_id)
        if row is None:
            raise GatewayError(f"accion {action_id} no existe")
        if self.settings.dry_run:
            raise GatewayError("modo dry-run activo: la ejecucion esta deshabilitada")
        if not self.store.transition(action_id, "pending", "executing", approver):
            raise GatewayError(f"la accion {action_id} no esta pendiente (estado: {row['status']})")

        action = action_adapter.validate_python(row["payload"])
        self.store.audit(approver, "approved", action_id)

        # Revalidar al aprobar: el pedido pudo cambiar desde la propuesta.
        try:
            verdict = evaluate(action, self._amount(action), self.settings)
        except (GatewayError, BackendError) as e:
            self.store.finish(action_id, "failed", {"error": str(e)})
            self.store.audit(approver, "execution_failed", action_id, str(e))
            return self._snapshot(action_id)
        if verdict.decision is Decision.DENY:
            self.store.finish(action_id, "failed", {"error": verdict.reason})
            self.store.audit(approver, "denied_at_approval", action_id, verdict.reason)
            return self._snapshot(action_id)

        return self._run(action_id, action, approver)

    def reject(self, action_id: int, approver: str, reason: str = "") -> ProposalResult:
        row = self.store.get(action_id)
        if row is None:
            raise GatewayError(f"accion {action_id} no existe")
        if not self.store.transition(action_id, "pending", "rejected", approver):
            raise GatewayError(f"la accion {action_id} no esta pendiente (estado: {row['status']})")
        self.store.finish(action_id, "rejected", {"reason": reason}, reason=reason or None)
        self.store.audit(approver, "rejected", action_id, reason)
        return self._snapshot(action_id)
