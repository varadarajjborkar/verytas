"""Operator commands that need the database itself, not the API.

    python -m verytas.cli issue-token admin@acme.io
    python -m verytas.cli seed-showcase --db showcase.db --write-env ../web/.env.local

Tokens are stored only as hashes, so a lost one can't be read back. This
replaces it with a new one (the old one stops working) and prints it once.
Whoever can run this can already read the database; it grants nothing more.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from verytas.api.deps import new_token
from verytas.config import Settings
from verytas.db import Database
from verytas.models import User, utcnow
from verytas.security.audit import append


def _positive(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return n


async def issue_token(email: str) -> str:
    db = Database(Settings().database_url)
    try:
        async with db.sessionmaker() as session:
            user = await session.scalar(select(User).where(User.email == email))
            if user is None:
                raise SystemExit(f"no user with email {email}")
            token, token_hash = new_token()
            user.token_hash = token_hash
            if user.password_hash:  # the new token gets a full lifetime (api/deps.py)
                user.token_issued_at = utcnow()
            await append(session, workspace_id=user.workspace_id, actor="operator:cli", action="user.token_issued",
                         object_type="user", object_id=user.id, detail={})
            await session.commit()
            return token
    finally:
        await db.dispose()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="verytas.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("issue-token", help="replace a user's API token and print the new one")
    issue.add_argument("email")
    demo = sub.add_parser("seed-showcase", help="build a demo workspace with a brand team and many creators")
    demo.add_argument("--db", type=Path, default=Path("showcase.db"))
    demo.add_argument("--keys-dir", type=Path, default=Path(".keys-showcase"))
    demo.add_argument("--write-env", type=Path, default=None,
                      help="env file to receive VERYTAS_API_TOKEN and VERYTAS_CREATOR_TOKEN (never printed)")
    demo.add_argument("--write-demo-accounts", type=Path, default=None,
                      help="JSON file of the demo sign-in page's accounts and their tokens (server-side only)")
    demo.add_argument("--companies", nargs="+", default=None, help="seed only these companies (module names)")
    demo.add_argument("--pieces", type=_positive, default=None, help="cap the pieces seeded per company")
    args = parser.parse_args(argv)
    if args.command == "issue-token":
        sys.stdout.write(asyncio.run(issue_token(args.email)) + "\n")
    elif args.command == "seed-showcase":
        from verytas.showcase import seed

        counts = seed(args.db, args.keys_dir, args.write_env, args.write_demo_accounts,
                      companies=args.companies, limit=args.pieces)
        sys.stdout.write(f"{args.db}: {counts['pieces']} pieces, {counts['escalations']} escalations\n")


if __name__ == "__main__":
    main()
