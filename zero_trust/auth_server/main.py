import logging
import os
import time

import jwt
from fastapi import FastAPI, Form, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth_server")

app = FastAPI(title="Auth Server - JWT Bearer Token Exchange")


@app.post("/token")
async def token_exchange(
    grant_type: str = Form(...),
    assertion: str = Form(...),
    scope: str = Form(default="transactions:read"),
):
    if grant_type != "urn:ietf:params:oauth:grant-type:jwt-bearer":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")

    jwt_secret = os.environ["JWT_SECRET"]
    obo_secret = os.environ["OBO_SECRET"]

    # Validate the caller's JWT assertion
    try:
        caller_claims = jwt.decode(
            assertion,
            jwt_secret,
            algorithms=["HS256"],
            audience="chat_agent",
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid assertion: %s", e)
        raise HTTPException(status_code=401, detail=f"invalid_assertion: {e}")

    logger.info(
        "Token exchange for sub=%s, scope=%s",
        caller_claims["sub"],
        scope,
    )

    # Issue OBO token scoped to transactions_server
    now = int(time.time())
    obo_payload = {
        "sub": caller_claims["sub"],
        "act": {"sub": "chat_agent"},
        "aud": "transactions_server",
        "scope": scope,
        "iat": now,
        "exp": now + 300,
    }
    obo_token = jwt.encode(obo_payload, obo_secret, algorithm="HS256")

    return {
        "access_token": obo_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }
