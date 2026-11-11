"""Persistencia SQLite: cola de acciones, idempotencia y log de auditoria."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS actions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  amount REAL NOT NULL,
  status TEXT NOT NULL,
  reason TEXT,
  requested_by TEXT,
  decided_by TEXT,
  result TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
-- Idempotencia: no puede haber dos acciones activas/ejecutadas con la misma clave.
CREATE UNIQUE INDEX IF NOT EXISTS ux_active_key ON actions(key)
  WHERE status IN ('pending','executing','executed');
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  event TEXT NOT NULL,
  action_id INTEGER,
  detail TEXT
);
"""


class DuplicateError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str = ":memory:"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    # -- acciones ---------------------------------------------------------
    def insert_action(self, *, key, kind, payload, amount, status, reason, requested_by) -> int:
        now = _now()
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO actions(key,kind,payload,amount,status,reason,requested_by,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (key, kind, json.dumps(payload), amount, status, reason, requested_by, now, now),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as e:
                raise DuplicateError(key) from e
            return cur.lastrowid

    def get(self, action_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
        return self._d(row)

    def find_active(self, key: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM actions WHERE key=? AND status IN ('pending','executing','executed')", (key,)
            ).fetchone()
        return self._d(row)

    def list_actions(self, status: str | None = None) -> list[dict]:
        q, args = "SELECT * FROM actions", ()
        if status:
            q, args = q + " WHERE status=?", (status,)
        with self._lock:
            rows = self._conn.execute(q + " ORDER BY id", args).fetchall()
        return [self._d(r) for r in rows]

    def transition(self, action_id: int, from_status: str, to_status: str, by: str | None = None) -> bool:
        """Cambio de estado atomico: solo uno gana si dos aprueban a la vez."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE actions SET status=?, decided_by=COALESCE(?,decided_by), updated_at=? WHERE id=? AND status=?",
                (to_status, by, _now(), action_id, from_status),
            )
            self._conn.commit()
            return cur.rowcount == 1

    def finish(self, action_id: int, status: str, result: dict | None = None, reason: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE actions SET status=?, result=?, reason=COALESCE(?,reason), updated_at=? WHERE id=?",
                (status, json.dumps(result) if result is not None else None, reason, _now(), action_id),
            )
            self._conn.commit()

    # -- auditoria --------------------------------------------------------
    def audit(self, actor: str, event: str, action_id: int | None = None, detail: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit(ts,actor,event,action_id,detail) VALUES(?,?,?,?,?)",
                (_now(), actor, event, action_id, detail),
            )
            self._conn.commit()

    def list_audit(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _d(row) -> dict | None:
        if row is None:
            return None
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["result"] = json.loads(d["result"]) if d["result"] else None
        return d
