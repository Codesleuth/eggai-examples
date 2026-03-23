import logging
import os

import httpx

from lite_llm_agent import LiteLlmAgent

logger = logging.getLogger("chat_agent")

chat_agent = LiteLlmAgent(
    name="ChatAgent",
    system_message=(
        "You are a helpful financial assistant. "
        "The user may have multiple accounts (e.g. Current Account, Savings, Cash ISA). "
        "Use get_accounts to list their accounts, then get_transactions with a specific "
        "account_id to fetch transactions for that account. "
        "Summarize results clearly and helpfully."
    ),
    model=os.environ.get("CHAT_AGENT_MODEL", "openai/gpt-4o-mini"),
)


async def _exchange_token_obo(caller_jwt: str) -> str:
    """Perform an On-Behalf-Of token exchange for the accounts service.

    Mirrors the Microsoft Identity Platform OBO flow:
      - grant_type = urn:ietf:params:oauth:grant-type:jwt-bearer
      - client_id + client_secret  (proves this app's identity)
      - assertion = user's access_token  (delegated user identity)
      - scope = target API scope
      - requested_token_use = on_behalf_of
    """
    auth_server_url = os.environ["AUTH_SERVER_URL"]
    client_id = os.environ["CHAT_AGENT_CLIENT_ID"]
    client_secret = os.environ["CHAT_AGENT_CLIENT_SECRET"]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{auth_server_url}/auth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "client_id": client_id,
                "client_secret": client_secret,
                "assertion": caller_jwt,
                "scope": "api://accounts-service/Accounts.Read",
                "requested_token_use": "on_behalf_of",
            },
        )
        resp.raise_for_status()
        logger.info("OBO token exchange successful")
        return resp.json()["access_token"]


async def _accounts_get(path: str, caller_jwt: str, log_msg: str) -> dict:
    """Obtain an OBO token and call the accounts service. Returns a structured
    error dict on any failure so tool calls degrade gracefully."""
    try:
        obo_token = await _exchange_token_obo(caller_jwt)
    except KeyError as e:
        logger.error("Missing environment variable: %s", e)
        return {"error": f"Configuration error: missing env var {e}"}
    except httpx.RequestError as e:
        logger.error("Auth server unreachable: %s", e)
        return {"error": f"Auth server unreachable: {type(e).__name__}"}
    except httpx.HTTPStatusError as e:
        logger.error("OBO exchange failed: %s", e)
        return {"error": f"Token exchange failed: {e.response.status_code}"}

    try:
        accounts_url = os.environ["ACCOUNTS_SERVICE_URL"]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{accounts_url}{path}",
                headers={"Authorization": f"Bearer {obo_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(log_msg, data.get("on_behalf_of"))
            return data
    except KeyError as e:
        logger.error("Missing environment variable: %s", e)
        return {"error": f"Configuration error: missing env var {e}"}
    except httpx.RequestError as e:
        logger.error("Accounts service unreachable: %s", e)
        return {"error": f"Accounts service unreachable: {type(e).__name__}"}
    except httpx.HTTPStatusError as e:
        logger.error("Accounts service request failed: %s", e)
        return {"error": f"Request failed: {e.response.status_code}"}


@chat_agent.tool(
    name="get_accounts",
    description="List all accounts belonging to the authenticated user",
)
async def get_accounts(context: dict):
    """List the user's accounts (e.g. Current Account, Savings, Cash ISA).

    The accounts returned are determined by the authenticated user identity —
    no parameters are accepted from the LLM.
    """
    caller_jwt = context.get("caller_jwt")
    if not caller_jwt:
        return {"error": "No authenticated session"}

    return await _accounts_get(
        "/me/accounts",
        caller_jwt,
        "Fetched accounts on behalf of %s",
    )


@chat_agent.tool(
    name="get_transactions",
    description="Fetch transactions for a specific account by account_id",
)
async def get_transactions(account_id: str, context: dict):
    """Fetch transactions for the given account_id.

    :param account_id: The account ID to fetch transactions for (e.g. ACC-001)

    The accounts service validates that the authenticated user owns the requested
    account — if account_id does not belong to the JWT subject, the request is
    rejected with 403 regardless of what the LLM supplies.
    """
    caller_jwt = context.get("caller_jwt")
    if not caller_jwt:
        return {"error": "No authenticated session"}

    return await _accounts_get(
        f"/me/accounts/{account_id}/transactions",
        caller_jwt,
        f"Fetched transactions for account_id={account_id} on behalf of %s",
    )
