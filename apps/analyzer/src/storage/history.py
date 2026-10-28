# -*- coding: utf-8 -*-
"""
Хранилище историй анализов Vishap.
"""
import json
import threading
from datetime import UTC, datetime

from src.api.job_store import DEFAULT_TENANT, get_tenant
from src.config import DATA_DIR

HISTORY_FILE = DATA_DIR / "history.json"

# Thread lock for safe concurrent writes (batch mode)
_HISTORY_LOCK = threading.Lock()


def _tenant_of(entry: dict) -> str:
    """Tenant of a history entry; legacy entries (pre-v6.3) belong to 'public'."""
    return entry.get("tenant_id") or DEFAULT_TENANT


def load_history(tenant_id: str | None = None) -> list:
    """Load history entries, optionally scoped to one tenant.

    With ``tenant_id=None`` every entry is returned (internal callers such as
    ``find_done_by_hash``). With a tenant, only that tenant's entries plus the
    legacy 'public' ones are returned.
    """
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            entries = data if isinstance(data, list) else []
    except Exception as e:
        print(f"[Vishap] Ошибка чтения истории: {e}")
        return []

    if tenant_id is None:
        return entries
    return [entry for entry in entries if _tenant_of(entry) == tenant_id]


def save_history(history: list) -> None:
    try:
        HISTORY_FILE.parent.mkdir(exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Vishap] Ошибка сохранения истории: {e}")


def add_entry(entry: dict, tenant_id: str | None = None) -> dict:
    """Append a history entry, tagged with the caller's tenant.

    ``tenant_id`` wins; otherwise the tenant bound to the current request/task
    (``tenant_scope``) is used; otherwise the default tenant.
    """
    with _HISTORY_LOCK:
        history = load_history()
        entry["tenant_id"] = tenant_id or get_tenant() or DEFAULT_TENANT
        entry["timestamp"] = datetime.now(UTC).isoformat()
        history.append(entry)
        save_history(history)
        return entry


def clear_history(tenant_id: str | None = None) -> int:
    """Delete history entries; returns how many were removed.

    With a tenant, only that tenant's entries are removed and other tenants'
    history is preserved.
    """
    with _HISTORY_LOCK:
        history = load_history()
        if tenant_id is None:
            save_history([])
            return len(history)
        keep = [entry for entry in history if _tenant_of(entry) != tenant_id]
        removed = len(history) - len(keep)
        save_history(keep)
        return removed


def find_done_by_hash(material_hash: str) -> dict | None:
    """Возвращает последнюю завершённую запись с таким material_hash, или None.

    Завершённая = есть verdict (pipeline дошёл до audit).
    """
    if not material_hash:
        return None
    history = load_history()
    # Идём с конца — последняя запись приоритетнее
    for entry in reversed(history):
        if entry.get("material_hash") == material_hash and entry.get("verdict"):
            return entry
    return None
