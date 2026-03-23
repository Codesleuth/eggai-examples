import logging
import os
import secrets
import time

import jwt
from fastapi import FastAPI, Form, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth_server")

app = FastAPI(title="Auth Server (Identity Provider)")

# ---------------------------------------------------------------------------
# Demo users — in production this would be a database / external IdP
# ---------------------------------------------------------------------------
DEMO_USERS = {
    "alice": {"password": "password", "name": "Alice", "email": "alice@example.com"},
    "bob": {"password": "password", "name": "Bob", "email": "bob@example.com"},
}

# ---------------------------------------------------------------------------
# App registry — mirrors Azure AD "App Registrations".
# Each app has a client_id and client_secret. The client_secret serves double
# duty: the auth server uses it to SIGN access tokens targeted at that app,
# and the app itself uses the same secret to VALIDATE incoming tokens.
# (In production with RS256, the IdP signs with its private key and apps
# validate with the public key — but with HS256 this is the equivalent.)
# ---------------------------------------------------------------------------
APP_REGISTRY: dict[str, dict] = {}


@app.on_event("startup")
def _load_app_registry():
    APP_REGISTRY["chat-agent"] = {
        "client_secret": os.environ["CHAT_AGENT_CLIENT_SECRET"],
        "display_name": "Chat Agent",
        "allowed_scopes": [
            "api://chat-agent/Chat.ReadWrite",
            "api://transactions-server/Transactions.Read",
        ],
    }
    APP_REGISTRY["transactions-server"] = {
        "client_secret": os.environ["TRANSACTIONS_SERVER_CLIENT_SECRET"],
        "display_name": "Transactions Server",
        "allowed_scopes": [
            "api://transactions-server/Transactions.Read",
        ],
    }
    logger.info(
        "Loaded %d app registrations: %s",
        len(APP_REGISTRY),
        list(APP_REGISTRY.keys()),
    )


def _authenticate_client(client_id: str, client_secret: str) -> dict:
    """Validate client credentials against the app registry."""
    registration = APP_REGISTRY.get(client_id)
    if not registration:
        raise HTTPException(status_code=401, detail="invalid_client: unknown client_id")
    if not secrets.compare_digest(registration["client_secret"], client_secret):
        raise HTTPException(status_code=401, detail="invalid_client: bad client_secret")
    return registration


def _validate_scopes(registration: dict, requested_scope: str):
    """Check that every requested scope is in the app's allowed_scopes."""
    requested = requested_scope.split() if requested_scope else []
    allowed = set(registration["allowed_scopes"])
    denied = [s for s in requested if s not in allowed]
    if denied:
        raise HTTPException(
            status_code=403,
            detail=f"invalid_scope: {' '.join(denied)} not permitted for this client",
        )


def _resolve_target_audience(scope: str) -> str:
    """Derive the target app from the scope (api://<app-id>/Permission)."""
    target_audiences = {s.split("/")[2] for s in scope.split() if s.startswith("api://")}
    if len(target_audiences) != 1:
        raise HTTPException(
            status_code=400,
            detail="invalid_scope: scopes must target exactly one API audience",
        )
    return target_audiences.pop()


def _sign_access_token(claims: dict, target_app_id: str) -> str:
    """Sign an access token using the target app's client_secret."""
    registration = APP_REGISTRY.get(target_app_id)
    if not registration:
        raise HTTPException(
            status_code=400, detail=f"invalid_audience: unknown app '{target_app_id}'"
        )
    return jwt.encode(claims, registration["client_secret"], algorithm="HS256")


# ---------------------------------------------------------------------------
# POST /auth/login  — user authentication → id_token
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# POST /auth/token  — token exchange (two grant types)
# ---------------------------------------------------------------------------
@app.post("/auth/token")
async def token_exchange(
    grant_type: str = Form(...),
    assertion: str = Form(...),
    scope: str = Form(default=""),
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
    requested_token_use: str = Form(default=""),
):
    """
    Issue scoped tokens. Mirrors the Microsoft Identity Platform /oauth2/v2.0/token
    endpoint. Supports two grant types:

    1. grant_type=urn:ietf:params:oauth:grant-type:token-exchange
       Pre-authorized exchange: a public client (e.g. CLI) exchanges an id_token
       for a scoped access_token. No client_secret required.
       Requires: assertion (id_token), client_id (target app), scope

    2. grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
       OBO exchange: a confidential client exchanges a user's access_token for a
       new access_token targeting a downstream API.
       Requires: assertion (user's access_token), client_id, client_secret,
                 scope, requested_token_use=on_behalf_of
    """
    if grant_type == "urn:ietf:params:oauth:grant-type:token-exchange":
        return _handle_id_token_exchange(assertion, client_id, scope)
    elif grant_type == "urn:ietf:params:oauth:grant-type:jwt-bearer":
        if requested_token_use != "on_behalf_of":
            raise HTTPException(
                status_code=400,
                detail="invalid_request: requested_token_use must be 'on_behalf_of'",
            )
        return _handle_obo_exchange(assertion, client_id, client_secret, scope)
    else:
        raise HTTPException(status_code=400, detail="unsupported_grant_type")


def _handle_id_token_exchange(assertion: str, client_id: str, scope: str) -> dict:
    """Pre-authorized exchange: validate an id_token and issue a scoped access_token.

    The CLI is a public client — it presents the user's id_token and the
    client_id of the target app. The access_token is signed with the target
    app's client_secret so that app can validate it.

    Security constraints:
      - The scope's audience must match client_id; a public client cannot mint
        tokens for an audience other than the one it explicitly identifies.
      - Requested scopes are validated against the target app's allowed_scopes.
    """
    id_secret = os.environ["ID_SECRET"]

    if not client_id:
        raise HTTPException(status_code=400, detail="invalid_request: client_id required")

    if not scope:
        raise HTTPException(status_code=400, detail="invalid_request: scope required")

    # Derive target audience from scope and enforce it matches client_id.
    # This prevents a caller from using client_id=chat-agent while requesting
    # a token scoped to a different API (e.g. transactions-server).
    target_app_id = _resolve_target_audience(scope)
    if target_app_id != client_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid_scope: scope audience '{target_app_id}' must match "
                f"client_id '{client_id}'"
            ),
        )

    # Validate the requested scopes against the target app's allowed_scopes.
    target_registration = APP_REGISTRY.get(target_app_id)
    if not target_registration:
        raise HTTPException(
            status_code=400, detail=f"invalid_audience: unknown app '{target_app_id}'"
        )
    _validate_scopes(target_registration, scope)

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
        "aud": target_app_id,
        "scp": scope,
        "azp": "cli",
        "iat": now,
        "exp": now + 300,
    }
    access_token = _sign_access_token(access_payload, target_app_id)

    logger.info(
        "Issued access_token: sub=%s, aud=%s, scp=%s",
        id_claims["sub"],
        target_app_id,
        scope,
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }


def _handle_obo_exchange(
    assertion: str, client_id: str, client_secret: str, scope: str
) -> dict:
    """On-Behalf-Of token exchange — mirrors Microsoft Identity Platform.

    The calling app (e.g. chat-agent) presents:
      - its own client_id + client_secret  (proves app identity)
      - the user's access_token as assertion  (proves delegated user identity)
      - the scope it needs on the downstream API

    The auth server:
      1. Authenticates the calling app via client credentials
      2. Validates the scope is allowed for this app
      3. Validates the user's access_token assertion (signed with the calling
         app's secret, since the token's audience is the calling app)
      4. Issues a new access_token signed with the TARGET app's secret
    """
    # Step 1: Authenticate the calling app
    registration = _authenticate_client(client_id, client_secret)

    # Step 2: Validate requested scopes
    _validate_scopes(registration, scope)

    # Step 3: Validate the user's access_token assertion.
    # The assertion was signed with the calling app's secret (aud = calling app).
    try:
        caller_claims = jwt.decode(
            assertion,
            registration["client_secret"],
            algorithms=["HS256"],
            audience=client_id,
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid assertion for OBO: %s", e)
        raise HTTPException(status_code=401, detail=f"invalid_assertion: {e}")

    # Step 4: Derive target audience and issue new access_token
    target_app_id = _resolve_target_audience(scope)

    now = int(time.time())
    obo_payload = {
        "sub": caller_claims["sub"],
        "name": caller_claims.get("name"),
        "email": caller_claims.get("email"),
        "aud": target_app_id,
        "azp": client_id,
        "act": {"sub": client_id},
        "scp": scope,
        "iat": now,
        "exp": now + 300,
    }
    obo_token = _sign_access_token(obo_payload, target_app_id)

    logger.info(
        "OBO exchange: sub=%s, client=%s, target=%s, scp=%s",
        caller_claims["sub"],
        client_id,
        target_app_id,
        scope,
    )
    return {
        "access_token": obo_token,
        "token_type": "Bearer",
        "expires_in": 300,
    }
