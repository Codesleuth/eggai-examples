import logging
import os

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transactions_server")

app = FastAPI(title="Transactions Server")

MOCK_TRANSACTIONS = [
    # March 1
    {"id": "txn-001", "amount": 4.50,   "merchant": "Coffee Shop",        "date": "2026-03-01", "category": "Food & Drink"},
    {"id": "txn-002", "amount": 54.20,  "merchant": "Grocery Mart",        "date": "2026-03-01", "category": "Groceries"},
    # March 3
    {"id": "txn-003", "amount": 45.50,  "merchant": "Gas Station",         "date": "2026-03-03", "category": "Transportation"},
    {"id": "txn-004", "amount": 12.99,  "merchant": "Streaming Service",   "date": "2026-03-03", "category": "Entertainment"},
    {"id": "txn-005", "amount": 8.75,   "merchant": "Coffee Shop",         "date": "2026-03-03", "category": "Food & Drink"},
    # March 5
    {"id": "txn-006", "amount": 2499.99,"merchant": "Electronics Store",   "date": "2026-03-05", "category": "Shopping"},
    {"id": "txn-007", "amount": 34.00,  "merchant": "Pharmacy",            "date": "2026-03-05", "category": "Health"},
    # March 7
    {"id": "txn-008", "amount": 62.40,  "merchant": "Grocery Mart",        "date": "2026-03-07", "category": "Groceries"},
    {"id": "txn-009", "amount": 18.50,  "merchant": "Restaurant",          "date": "2026-03-07", "category": "Food & Drink"},
    # March 10
    {"id": "txn-010", "amount": 9.99,   "merchant": "Music Streaming",     "date": "2026-03-10", "category": "Entertainment"},
    {"id": "txn-011", "amount": 44.00,  "merchant": "Gas Station",         "date": "2026-03-10", "category": "Transportation"},
    {"id": "txn-012", "amount": 150.00, "merchant": "Coffee Shop",         "date": "2026-03-10", "category": "Food & Drink"},
    # March 12
    {"id": "txn-013", "amount": 29.99,  "merchant": "Book Store",          "date": "2026-03-12", "category": "Shopping"},
    {"id": "txn-014", "amount": 75.00,  "merchant": "Gym Membership",      "date": "2026-03-12", "category": "Health"},
    # March 14
    {"id": "txn-015", "amount": 58.30,  "merchant": "Grocery Mart",        "date": "2026-03-14", "category": "Groceries"},
    {"id": "txn-016", "amount": 22.00,  "merchant": "Restaurant",          "date": "2026-03-14", "category": "Food & Drink"},
    {"id": "txn-017", "amount": 14.99,  "merchant": "Streaming Service",   "date": "2026-03-14", "category": "Entertainment"},
    # March 15
    {"id": "txn-018", "amount": 5.25,   "merchant": "Coffee Shop",         "date": "2026-03-15", "category": "Food & Drink"},
    {"id": "txn-019", "amount": 89.99,  "merchant": "Clothing Store",      "date": "2026-03-15", "category": "Shopping"},
    # March 17
    {"id": "txn-020", "amount": 46.00,  "merchant": "Gas Station",         "date": "2026-03-17", "category": "Transportation"},
    {"id": "txn-021", "amount": 12.50,  "merchant": "Pharmacy",            "date": "2026-03-17", "category": "Health"},
    # March 18
    {"id": "txn-022", "amount": 67.10,  "merchant": "Grocery Mart",        "date": "2026-03-18", "category": "Groceries"},
    {"id": "txn-023", "amount": 35.00,  "merchant": "Restaurant",          "date": "2026-03-18", "category": "Food & Drink"},
    # March 19
    {"id": "txn-024", "amount": 199.00, "merchant": "Electronics Store",   "date": "2026-03-19", "category": "Shopping"},
    {"id": "txn-025", "amount": 6.00,   "merchant": "Coffee Shop",         "date": "2026-03-19", "category": "Food & Drink"},
    # March 20
    {"id": "txn-026", "amount": 9.99,   "merchant": "Music Streaming",     "date": "2026-03-20", "category": "Entertainment"},
    {"id": "txn-027", "amount": 48.75,  "merchant": "Gas Station",         "date": "2026-03-20", "category": "Transportation"},
    # March 21
    {"id": "txn-028", "amount": 89.00,  "merchant": "Grocery Mart",        "date": "2026-03-21", "category": "Groceries"},
    {"id": "txn-029", "amount": 27.50,  "merchant": "Restaurant",          "date": "2026-03-21", "category": "Food & Drink"},
    {"id": "txn-030", "amount": 49.99,  "merchant": "Clothing Store",      "date": "2026-03-21", "category": "Shopping"},
]


def validate_access_token(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ")
    try:
        claims = jwt.decode(
            token,
            os.environ["TRANSACTIONS_SERVER_CLIENT_SECRET"],
            algorithms=["HS256"],
            audience="transactions-server",
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
async def list_transactions(claims: dict = Depends(validate_access_token)):
    return {
        "transactions": MOCK_TRANSACTIONS,
        "on_behalf_of": claims["sub"],
    }


@app.get("/transactions/{txn_id}")
async def get_transaction(txn_id: str, claims: dict = Depends(validate_access_token)):
    txn = next((t for t in MOCK_TRANSACTIONS if t["id"] == txn_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {
        "transaction": txn,
        "on_behalf_of": claims["sub"],
    }
