import logging
import os

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transactions_server")

app = FastAPI(title="Transactions Server")

MOCK_TRANSACTIONS = [
    {"id": "txn-001", "amount": 150.00, "merchant": "Coffee Shop", "date": "2026-03-15", "category": "Food & Drink"},
    {"id": "txn-002", "amount": 2499.99, "merchant": "Electronics Store", "date": "2026-03-18", "category": "Shopping"},
    {"id": "txn-003", "amount": 45.50, "merchant": "Gas Station", "date": "2026-03-19", "category": "Transportation"},
    {"id": "txn-004", "amount": 12.99, "merchant": "Streaming Service", "date": "2026-03-20", "category": "Entertainment"},
    {"id": "txn-005", "amount": 89.00, "merchant": "Grocery Mart", "date": "2026-03-21", "category": "Groceries"},
]


def verify_obo_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ")
    try:
        claims = jwt.decode(
            token,
            os.environ["OBO_SECRET"],
            algorithms=["HS256"],
            audience="transactions_server",
        )
        logger.info(
            "Authenticated request: sub=%s, act=%s",
            claims.get("sub"),
            claims.get("act", {}).get("sub"),
        )
        return claims
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid OBO token: %s", e)
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


@app.get("/transactions")
async def list_transactions(claims: dict = Depends(verify_obo_token)):
    return {
        "transactions": MOCK_TRANSACTIONS,
        "on_behalf_of": claims["sub"],
    }


@app.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str, claims: dict = Depends(verify_obo_token)):
    txn = next((t for t in MOCK_TRANSACTIONS if t["id"] == txn_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "transaction": txn,
        "on_behalf_of": claims["sub"],
    }
