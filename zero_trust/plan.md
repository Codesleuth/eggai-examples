# Zero-Trust JWT Bearer (OBO) Example

## Context

Build a self-contained Docker example demonstrating `urn:ietf:params:oauth:grant-type:jwt-bearer` (On-Behalf-Of token exchange) within the EggAI multi-agent framework. Shows how agents securely call downstream services by exchanging caller tokens for scoped OBO tokens. Uses eggai ~0.1.x to match existing examples, with stateful conversation history.

## Architecture

```
Host                          Docker Network
─────                         ──────────────
main.py ──JWT──► Redpanda ◄── chat_agent ──assertion──► auth_server
 (CLI)           (Kafka)       (EggAI)                     │
                                  │                    OBO token
                                  │                        │
                                  └──── OBO token ──► transactions_server
```

**Token flow:**
1. `main.py` signs a JWT (aud=`chat_agent`, sub=`user@example.com`) and publishes it with chat_messages to Kafka
2. `chat_agent` validates the caller JWT, then uses LLM tool calling to decide when to fetch transactions
3. When `get_transactions` tool fires, `chat_agent` POSTs the caller JWT as `assertion` to `auth_server` with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`
4. `auth_server` validates the assertion, issues OBO token (aud=`transactions_server`, act.sub=`chat_agent`)
5. `chat_agent` calls `transactions_server` with the OBO Bearer token
6. `transactions_server` validates the OBO token and returns data

## File Structure

```
zero_trust/
├── .env.example                 # Template with all required secrets
├── docker-compose.yml           # Redpanda + auth_server + transactions_server + chat_agent
├── requirements.txt             # Host-side deps (main.py)
├── main.py                      # Host CLI: creates JWT, chat loop, display agent
├── shared.py                    # Channel definitions (shared by host + chat_agent)
├── lite_llm_agent.py            # Copied from multi_agent_conversation (reuse)
├── jwt_utils.py                 # JWT create/validate helpers (shared by multiple components)
├── chat_agent/
│   ├── Dockerfile               # Context=zero_trust/ to include shared files
│   ├── requirements.txt         # eggai, litellm, PyJWT, httpx, python-dotenv
│   ├── main.py                  # Entrypoint: subscribes to channel, validates JWT, runs agent
│   └── agent.py                 # LiteLlmAgent with get_transactions tool + OBO exchange
├── auth_server/
│   ├── Dockerfile
│   ├── requirements.txt         # fastapi, uvicorn, PyJWT, python-multipart
│   └── main.py                  # FastAPI: POST /token (JWT Bearer exchange)
└── transactions_server/
    ├── Dockerfile
    ├── requirements.txt         # fastapi, uvicorn, PyJWT
    └── main.py                  # FastAPI: GET /transactions (validates OBO token)
```

## Implementation Steps

### Step 1: `.env.example`
```
JWT_SECRET=change-me-caller-secret-min-32-chars
OBO_SECRET=change-me-obo-secret-min-32-chars
OPENAI_API_KEY=sk-...
CHAT_AGENT_MODEL=openai/gpt-4o-mini
```

### Step 2: Shared utilities

**`shared.py`** — Channel definitions (pattern from `multi_agent_conversation/shared.py`):
```python
from eggai import Channel
agents_channel = Channel("zt.agents")
humans_channel = Channel("zt.humans")
```

**`jwt_utils.py`** — JWT helpers (HS256, PyJWT):
- `create_jwt(subject, audience, secret, expires_in=300)` → signed token string
- `validate_jwt(token, audience, secret)` → decoded claims dict (raises on failure)

**`lite_llm_agent.py`** — Copy unchanged from `multi_agent_conversation/lite_llm_agent.py`

### Step 3: `auth_server/main.py` (FastAPI, port 8000)

`POST /token` accepting form data:
- `grant_type` — must equal `urn:ietf:params:oauth:grant-type:jwt-bearer`
- `assertion` — caller's JWT
- `scope` — optional, defaults to `transactions:read`

Logic:
1. Validate assertion JWT against `JWT_SECRET` with aud=`chat_agent`
2. Issue OBO token signed with `OBO_SECRET`: sub=original caller, act.sub=`chat_agent`, aud=`transactions_server`
3. Return `{access_token, token_type: "Bearer", expires_in: 300}`

### Step 4: `transactions_server/main.py` (FastAPI, port 8001)

- `GET /transactions` — lists mock transactions
- `GET /transactions/{txn_id}` — single transaction
- FastAPI `Depends()` middleware validates Bearer token against `OBO_SECRET` with aud=`transactions_server`
- Returns data with `on_behalf_of` field showing original user subject

### Step 5: `chat_agent/agent.py`

LiteLlmAgent with:
- System message: "You are a helpful financial assistant. Use the get_transactions tool when users ask about their transactions."
- Model from env `CHAT_AGENT_MODEL`
- `get_transactions` tool that:
  1. Takes stored caller JWT from module-level variable
  2. POSTs to auth_server `/token` with grant_type + assertion (using httpx)
  3. Gets OBO token
  4. Calls transactions_server `/transactions` with Bearer OBO token
  5. Returns the transaction data

### Step 6: `chat_agent/main.py`

- Entrypoint for the Docker container
- Maintains `messages_history_memory = []` (stateful, same pattern as `multi_agent_conversation/memory.py`)
- Subscribes to `humans_channel` for `user_message` type
- On each message:
  1. Extract `caller_jwt` and `chat_messages` from payload
  2. Validate caller JWT against `JWT_SECRET` with aud=`chat_agent`
  3. Store JWT in module-level var for tool access
  4. Call `chat_agent.completion(messages=chat_messages)`
  5. Append assistant response to chat_messages
  6. Publish `{type: "chat_response", payload: {chat_messages}}` to `agents_channel`
- Runs forever with `await asyncio.Event().wait()`

### Step 7: `main.py` (host CLI)

Follows `multi_agent_conversation/chat_display.py` + `main.py` pattern:
- `messages_history_memory = []` on host side
- Display agent subscribes to `agents_channel` for `chat_response`, renders with Rich
- Input loop:
  1. Read user input
  2. Create JWT: sub=`user@example.com`, aud=`chat_agent`, signed with `JWT_SECRET`
  3. Append `{role: "user", content}` to messages_history_memory
  4. Publish `{type: "user_message", payload: {chat_messages: messages_history_memory, caller_jwt: token}}`
- On response: extract chat_messages from payload, update local memory, display latest assistant message

### Step 8: `docker-compose.yml`

Standard Redpanda setup (from `multi_agent_conversation/docker-compose.yml`) plus:

- **topic-init**: creates `zt.humans` and `zt.agents` topics
- **auth_server**: build `./auth_server`, port 8000, `env_file: .env`
- **transactions_server**: build `./transactions_server`, port 8001, `env_file: .env`
- **chat_agent**: build context `.` with `dockerfile: chat_agent/Dockerfile`, depends on redpanda (healthy) + auth_server + transactions_server, environment overrides:
  - `KAFKA_BOOTSTRAP_SERVERS=redpanda:9092`
  - `AUTH_SERVER_URL=http://auth_server:8000`
  - `TRANSACTIONS_SERVER_URL=http://transactions_server:8001`
  - `env_file: .env`

### Step 9: Dockerfiles

All use `python:3.11-slim`. The chat_agent Dockerfile uses `zero_trust/` as build context to COPY shared files (`shared.py`, `lite_llm_agent.py`, `jwt_utils.py`) alongside `chat_agent/*.py`.

## Key Design Decisions

- **Separate secrets**: `JWT_SECRET` for caller tokens, `OBO_SECRET` for OBO tokens — enforces audience separation
- **eggai ~0.1.x**: Matches existing examples; uses `KAFKA_BOOTSTRAP_SERVERS` env var for transport config (read by eggai settings/kafka.py)
- **Stateful chat**: Both host and chat_agent maintain message history, synced via `chat_messages` in payloads
- **Module-level JWT context**: Simple global var in chat_agent for passing caller JWT to tools — acceptable for single-user demo

## Files to reuse (copy)

- `multi_agent_conversation/lite_llm_agent.py` → `zero_trust/lite_llm_agent.py`

## Verification

1. `cd zero_trust && cp .env.example .env` — fill in real OPENAI_API_KEY
2. `docker compose up -d` — starts Redpanda, auth_server, transactions_server, chat_agent
3. `pip install -r requirements.txt`
4. `python main.py`
5. Type "Show me my recent transactions" — should see:
   - chat_agent logs: JWT validated, OBO token exchanged, transactions fetched
   - auth_server logs: token exchange request processed
   - transactions_server logs: authenticated request received
   - CLI: formatted transaction list displayed
6. Type "Tell me more about the Coffee Shop transaction" — should use conversation history
7. Verify auth rejection: change `JWT_SECRET` in `.env`, restart auth_server, confirm token exchange fails with clear error
