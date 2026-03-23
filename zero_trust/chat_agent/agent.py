import logging
import os

import httpx

from lite_llm_agent import LiteLlmAgent

logger = logging.getLogger("chat_agent")

chat_agent = LiteLlmAgent(
    name="ChatAgent",
    system_message=(
        "You are a helpful financial assistant. When a user asks about their "
        "transactions, spending, or account activity, use the get_transactions tool "
        "to fetch their data. Summarize the results in a clear, friendly way."
    ),
    model=os.environ.get("CHAT_AGENT_MODEL", "openai/gpt-4o-mini"),
)

# Stores the current caller's access token so tools can access it for OBO exchange.
# Acceptable for a single-user demo where messages are processed sequentially.
_current_caller_jwt: str | None = None


async def exchange_token_obo(caller_jwt: str) -> str:
    """Perform an On-Behalf-Of token exchange, mirroring the Microsoft Identity
    Platform OBO flow.

    Sends:
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
                "scope": "api://transactions-server/Transactions.Read",
                "requested_token_use": "on_behalf_of",
            },
        )
        resp.raise_for_status()
        token_data = resp.json()
        logger.info("OBO token exchange successful")
        return token_data["access_token"]


@chat_agent.tool(
    name="get_transactions",
    description="Fetch the user's recent transactions from the transactions server",
)
async def get_transactions():
    """Fetch the user's recent transactions from the transactions server."""
    global _current_caller_jwt
    if not _current_caller_jwt:
        return {"error": "No authenticated session"}

    try:
        obo_token = await exchange_token_obo(_current_caller_jwt)
    except httpx.HTTPStatusError as e:
        logger.error("OBO token exchange failed: %s", e)
        return {"error": f"Token exchange failed: {e.response.status_code}"}

    transactions_url = os.environ["TRANSACTIONS_SERVER_URL"]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{transactions_url}/transactions",
                headers={"Authorization": f"Bearer {obo_token}"},
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Fetched %d transactions on behalf of %s",
                len(data.get("transactions", [])),
                data.get("on_behalf_of"),
            )
            return data
    except httpx.HTTPStatusError as e:
        logger.error("Transactions request failed: %s", e)
        return {"error": f"Transactions request failed: {e.response.status_code}"}
