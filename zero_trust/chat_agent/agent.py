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

    try:
        obo_token = await _exchange_token_obo(caller_jwt)
    except httpx.HTTPStatusError as e:
        logger.error("OBO exchange failed: %s", e)
        return {"error": f"Token exchange failed: {e.response.status_code}"}

    accounts_url = os.environ["ACCOUNTS_SERVICE_URL"]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{accounts_url}/me/accounts",
                headers={"Authorization": f"Bearer {obo_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Fetched %d accounts on behalf of %s",
                len(data.get("accounts", [])),
                data.get("on_behalf_of"),
            )
            return data
    except httpx.HTTPStatusError as e:
        logger.error("Account list request failed: %s", e)
        return {"error": f"Account list failed: {e.response.status_code}"}


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

    try:
        obo_token = await _exchange_token_obo(caller_jwt)
    except httpx.HTTPStatusError as e:
        logger.error("OBO exchange failed: %s", e)
        return {"error": f"Token exchange failed: {e.response.status_code}"}

    accounts_url = os.environ["ACCOUNTS_SERVICE_URL"]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{accounts_url}/me/accounts/{account_id}/transactions",
                headers={"Authorization": f"Bearer {obo_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Fetched %d transactions for account_id=%s on behalf of %s",
                len(data.get("transactions", [])),
                account_id,
                data.get("on_behalf_of"),
            )
            return data
    except httpx.HTTPStatusError as e:
        logger.error("Transactions request failed: %s", e)
        return {"error": f"Transactions request failed: {e.response.status_code}"}
