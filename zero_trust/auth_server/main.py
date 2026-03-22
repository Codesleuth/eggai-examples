import logging
import os
import time
from typing import Optional

import jwt
from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth_server")

app = FastAPI(title="Auth Server")

# Demo users — in production this would be a database / identity provider
DEMO_USERS = {
    "alice": {"password": "password", "name": "Alice", "email": "alice@example.com"},
    "bob": {"password": "password", "name": "Bob", "email": "bob@example.com"},
}


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/auth/login")
async def login(req: LoginRequest):
    """Authenticate a user and return an identity token."""
    user = DEMO_USERS.get(req.username)
    if not user or user["password"] != req.password:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    id_secret = os.environ["ID_SECRET"]
    now = int(time.time())
    id_payload = {
        "sub": req.username,
        "name": user["name"],
        "email": user["email"],
        "aud": "auth_server",
        "iat": now,
        "exp": now + 3600,
    }
    id_token = jwt.encode(id_payload, id_secret, algorithm="HS256")

    logger.info("Login successful for user=%s", req.username)
    return {
        "id_token": id_token,
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@app.post("/auth/token")
async def token_exchange(
    grant_type: str = Form(...),
    assertion: str = Form(...),
    audience: str = Form(...),
    scope: str = Form(default=""),
):
    """
    Issue scoped tokens. Supports two grant types:

    1. grant_type=urn:ietf:params:oauth:grant-type:id-token
       Exchange an id_token for a scoped access_token targeting a specific audience.

    2. grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
       Exchange an access_token (assertion) for an OBO token targeting a downstream service.
    """
    if grant_type == "urn:ietf:params:oauth:grant-type:id-token":
        return _handle_id_token_exchange(assertion, audience, scope)
    elif grant_type == "urn:ietf:params:oauth:grant-type:jwt-bearer":
        return _handle_obo_exchange(assertion, audience, scope)
    else:
        raise HTTPException(status_code=400, detail="unsupported_grant_type")


def _handle_id_token_exchange(assertion: str, audience: str, scope: str) -> dict:
    """Validate an id_token and issue a scoped access_token."""
    id_secret = os.environ["ID_SECRET"]
    access_secret = os.environ["ACCESS_SECRET"]

    try:
        id_claims = jwt.decode(
            assertion, id_secret, algorithms=["HS256"], audience="auth_server"
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid id_token: %s", e)
        raise HTTPException(status_code=401, detail=f"invalid_assertion: {e}")

    now = int(time.time())
    access_payload = {
        "sub": id_claims["sub"],
        "name": id_claims.get("name"),
        "email": id_claims.get("email"),
        "aud": audience,
        "scope": scope,
        "iat": now,
        "exp": now + 300,
    }
    access_token = jwt.encode(access_payload, access_secret, algorithm="HS256")

    logger.info(
        "Issued access_token for sub=%s, aud=%s, scope=%s",
        id_claims["sub"],
        audience,
        scope,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }


def _handle_obo_exchange(assertion: str, audience: str, scope: str) -> dict:
    """Validate an access_token and issue an OBO token for a downstream service."""
    access_secret = os.environ["ACCESS_SECRET"]
    obo_secret = os.environ["OBO_SECRET"]

    try:
        caller_claims = jwt.decode(
            assertion, access_secret, algorithms=["HS256"],
            # The assertion's audience is the calling service, not us — skip aud check
            options={"verify_aud": False},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid assertion for OBO: %s", e)
        raise HTTPException(status_code=401, detail=f"invalid_assertion: {e}")

    # The caller's audience tells us who is making the OBO request
    actor = caller_claims.get("aud", "unknown")

    now = int(time.time())
    obo_payload = {
        "sub": caller_claims["sub"],
        "act": {"sub": actor},
        "aud": audience,
        "scope": scope,
        "iat": now,
        "exp": now + 300,
    }
    obo_token = jwt.encode(obo_payload, obo_secret, algorithm="HS256")

    logger.info(
        "OBO exchange: sub=%s, actor=%s, target_aud=%s, scope=%s",
        caller_claims["sub"],
        actor,
        audience,
        scope,
    )
    return {
        "access_token": obo_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }
