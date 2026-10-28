#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Create a tenant and API key for a customer who pays by bank transfer.

    python scripts/generate_key.py client@example.com
    python scripts/generate_key.py client@example.com --plan enterprise --days 730

Requires ``DATABASE_URL`` in the environment and revision 004 applied
(``alembic upgrade head``). The key is printed once — store it in your password
manager before sending it to the customer; only a hash-free copy exists in the
database, so it cannot be recovered, only rotated.
"""
import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow `python scripts/generate_key.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from src.api.tenants import (  # noqa: E402  (after sys.path tweak)
    create_tenant,
    generate_api_key,
    generate_tenant_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a tenant and API key.")
    parser.add_argument("email", help="Customer email")
    parser.add_argument("--plan", default="pro", choices=["free", "pro", "enterprise"])
    parser.add_argument("--days", type=int, default=365, help="Days until expiry")
    parser.add_argument("--tenant-id", default=None)
    args = parser.parse_args()

    tenant_id = args.tenant_id or generate_tenant_id()
    api_key = generate_api_key()
    expires_at = datetime.now(UTC) + timedelta(days=args.days)

    try:
        tenant = asyncio.run(
            create_tenant(
                tenant_id=tenant_id,
                api_key=api_key,
                plan=args.plan,
                email=args.email,
                expires_at=expires_at,
            )
        )
    except Exception as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        return 1

    print(f"Tenant created: {tenant_id}")
    print(f"Email: {args.email}")
    print(f"API Key: {api_key}")
    print(f"Expires: {expires_at.isoformat()}")
    print()
    print("Add to the customer's .env:")
    print(f"  CONVEYOR_API_KEY={api_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
