import asyncio
import os
import sys

import dotenv
import httpx

dotenv.load_dotenv()

from rich.console import Console
from rich.prompt import Prompt

from eggai import Agent, Channel
from shared import agents_channel, humans_channel

AUTH_SERVER_URL = os.environ.get("AUTH_SERVER_URL", "http://localhost:8000")

console = Console()

messages_history_memory = []

display_agent = Agent(name="DisplayAgent")


def clear_last_line():
    sys.stdout.write("\x1b[2K")


@display_agent.subscribe(
    channel=agents_channel,
    filter_func=lambda msg: msg["type"] == "chat_response",
)
async def display_response(msg):
    try:
        chat_messages = msg.get("payload", {}).get("chat_messages", [])
        if chat_messages:
            messages_history_memory.clear()
            messages_history_memory.extend(chat_messages)

            latest = chat_messages[-1]
            if latest.get("role") == "assistant":
                clear_last_line()
                console.print(
                    f"\n[bold green]ChatAgent[/bold green]:\n\t{latest['content']}"
                )
                console.print("\n[bold cyan]You[/bold cyan]: ", end="")
    except Exception as e:
        console.print(f"[red]Error displaying response: {e}[/red]")


async def authenticate() -> tuple[str, str, str]:
    """Log in to the auth server and obtain an id_token and scoped access_token.

    Returns (id_token, access_token, user_name).
    """
    username = os.environ.get("DEMO_USERNAME", "alice")
    password = os.environ.get("DEMO_PASSWORD", "password")

    async with httpx.AsyncClient(base_url=AUTH_SERVER_URL) as client:
        # Step 1: Login to get id_token
        resp = await client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        login_data = resp.json()
        id_token = login_data["id_token"]

        # Step 2: Exchange id_token for a scoped access_token targeting chat_agent
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:id-token",
                "assertion": id_token,
                "audience": "chat_agent",
                "scope": "chat",
            },
        )
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data["access_token"]

    # Decode the id_token payload to get the user's name (no verification needed
    # here — the auth server just issued it and we trust the local connection)
    import jwt
    claims = jwt.decode(id_token, options={"verify_signature": False})
    user_name = claims.get("name", username)

    return id_token, access_token, user_name


async def ask_input(stop_event, access_token: str):
    loop = asyncio.get_event_loop()
    while not stop_event.is_set():
        try:
            user_input = await loop.run_in_executor(
                None,
                lambda: Prompt.ask("\n[bold cyan]You[/bold cyan]", show_default=False),
            )
            if user_input.lower() in {"exit", "quit"}:
                console.print("\n[bold red]Goodbye![/bold red]")
                stop_event.set()
                break
            elif user_input.strip() == "":
                continue
            else:
                messages_history_memory.append(
                    {"role": "user", "content": user_input}
                )

                await humans_channel.publish({
                    "type": "user_message",
                    "payload": {
                        "chat_messages": list(messages_history_memory),
                        "caller_jwt": access_token,
                    },
                })
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            stop_event.set()


async def main():
    stop_event = asyncio.Event()
    try:
        console.print("[bold cyan]Zero-Trust JWT Bearer (OBO) Chat Demo[/bold cyan]")
        console.print(
            "[dim]Authenticating with auth server...[/dim]"
        )

        id_token, access_token, user_name = await authenticate()

        console.print(f"\n[bold green]Hello, {user_name}![/bold green]")
        console.print(
            "[dim]Your identity has been verified. Messages are signed with a "
            "scoped access token. The chat agent exchanges it for an OBO token "
            "to access downstream services.[/dim]"
        )
        console.print("[dim]Type 'exit' or 'quit' to stop.[/dim]\n")

        await display_agent.run()
        asyncio.create_task(ask_input(stop_event, access_token))
        await stop_event.wait()
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Authentication failed: {e.response.text}[/red]")
    except asyncio.CancelledError:
        pass
    finally:
        await display_agent.stop()
        await Channel.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold red]Exiting...[/bold red]")
