#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Email tenants whose API key expires soon (or has already expired).

    python scripts/notify_expiring.py            # 7-day window
    python scripts/notify_expiring.py --days 14

Requires ``DATABASE_URL`` and revision 004 applied. Email delivery is a stub
(``src.notifications.email``), so this currently prints instead of sending —
safe to dry-run against production data.
"""
import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.tenants import list_tenants  # noqa: E402
from src.notifications.email import send_email  # noqa: E402

SUBJECT = "Vishap — renewal reminder"


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _body(tenant: dict, expires_at: datetime, now: datetime) -> str:
    if expires_at < now:
        state = f"expired on {expires_at.date().isoformat()}"
    else:
        state = f"expires on {expires_at.date().isoformat()}"
    return (
        f"Hello,\n\n"
        f"The API key for tenant {tenant['tenant_id']} ({tenant['plan']} plan) {state}.\n\n"
        f"To renew, reply to this message or write to support@vishap.dev. "
        f"Renewals are invoiced and paid by bank transfer.\n\n"
        f"— Vishap\n"
        f"support@vishap.dev\n"
    )


async def _load() -> list[dict]:
    return await list_tenants()


def main(days: int = 7) -> list[dict]:
    """Notify every tenant expiring within ``days``. Returns the notified rows."""
    now = datetime.now(UTC)
    soon = now + timedelta(days=days)
    notified: list[dict] = []

    for tenant in asyncio.run(_load()):
        expires_at = _as_datetime(tenant.get("expires_at"))
        if expires_at is None or expires_at > soon:
            continue
        if tenant.get("status") != "active":
            continue
        if send_email(
            to=tenant.get("email", ""),
            subject=SUBJECT,
            body=_body(tenant, expires_at, now),
        ):
            notified.append(tenant)

    print(f"Notified {len(notified)} tenant(s) expiring within {days} day(s).")
    return notified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remind tenants about key expiry.")
    parser.add_argument("--days", type=int, default=7, help="look-ahead window in days")
    args = parser.parse_args()

    try:
        main(days=args.days)
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        print(f"Failed: {exc}", file=sys.stderr)
        sys.exit(1)
