from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    backend: str = "mock"  # "mock" | "odoo"
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_user: str = ""
    odoo_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    db_path: str = "agent.db"
    dry_run: bool = False
    sale_auto_limit: float = 1000.0
    purchase_auto_limit: float = 500.0
    hard_limit: float = 50000.0
    approval_token: str = ""  # vacio => aprobaciones deshabilitadas (fail closed)

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.getenv
        return cls(
            backend=e("ERP_BACKEND", "mock"),
            odoo_url=e("ODOO_URL", ""),
            odoo_db=e("ODOO_DB", ""),
            odoo_user=e("ODOO_USER", ""),
            odoo_api_key=e("ODOO_API_KEY", ""),
            anthropic_model=e("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
            db_path=e("DB_PATH", "agent.db"),
            dry_run=_bool("DRY_RUN", False),
            sale_auto_limit=float(e("SALE_AUTO_LIMIT", "1000")),
            purchase_auto_limit=float(e("PURCHASE_AUTO_LIMIT", "500")),
            hard_limit=float(e("HARD_LIMIT", "50000")),
            approval_token=e("APPROVAL_TOKEN", ""),
        )
