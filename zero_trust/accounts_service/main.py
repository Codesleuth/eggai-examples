import logging
import os
import sqlite3

import jwt
from db import get_db
from fastapi import Depends, FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("accounts_service")


app = FastAPI(title="Accounts Service")

# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------
def validate_access_token(request: Request) -> dict:
    # In production, JWT validation would be handled by an API gateway or
    # sidecar proxy (e.g. Envoy, Kong, AWS API Gateway) before the request
    # reaches this service. It is done inline here for demo clarity.
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ")
    try:
        claims = jwt.decode(
            token,
            os.environ["ACCOUNTS_SERVICE_CLIENT_SECRET"],
            algorithms=["HS256"],
            audience="accounts-service",
            leeway=5,
        )
        logger.info(
            "Authenticated: sub=%s azp=%s",
            claims.get("sub"),
            claims.get("azp"),
        )
        return claims
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        raise HTTPException(status_code=401, detail="Invalid token")


def _verify_ownership(db: sqlite3.Connection, sub: str, account_id: str):
    """Raise 403 if account_id does not belong to the JWT subject."""
    row = db.execute(
        "SELECT owner FROM accounts WHERE account_id = ?", (account_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Account not found")
    if row["owner"] != sub:
        logger.warning(
            "Ownership check failed: sub=%s tried to access account_id=%s (owner=%s)",
            sub, account_id, row["owner"],
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: account does not belong to the authenticated user",
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/me/accounts")
def list_accounts(
    claims: dict = Depends(validate_access_token),
    db: sqlite3.Connection = Depends(get_db),
):
    """Return all accounts owned by the authenticated user (derived from JWT sub)."""
    rows = db.execute(
        "SELECT account_id, name FROM accounts WHERE owner = ?", (claims["sub"],)
    ).fetchall()
    return {
        "accounts": [dict(r) for r in rows],
        "on_behalf_of": claims["sub"],
    }


@app.get("/me/accounts/{account_id}/transactions")
def list_transactions(
    account_id: str,
    claims: dict = Depends(validate_access_token),
    db: sqlite3.Connection = Depends(get_db),
):
    """Return transactions for an account. Ownership is validated against the JWT sub."""
    _verify_ownership(db, claims["sub"], account_id)
    rows = db.execute(
        "SELECT * FROM transactions WHERE account_id = ? ORDER BY date DESC",
        (account_id,),
    ).fetchall()
    return {
        "transactions": [dict(r) for r in rows],
        "account_id": account_id,
        "on_behalf_of": claims["sub"],
    }
