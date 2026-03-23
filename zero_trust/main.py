import asyncio
import os

import dotenv
import httpx
import jwt

dotenv.load_dotenv()

from display_agent import display_agent, messages_history_memory
from eggai import Channel
from rich.console import Console
from rich.prompt import Prompt
from shared import humans_channel

AUTH_SERVER_URL = os.environ.get("AUTH_SERVER_URL", "http://localhost:8000")

console = Console()


async def authenticate(username: str, password: str) -> str:
    """Log in to the auth server and return an id_token.

    This is a demo, so we use a simple username/password flow.
    In the real world, the user would authenticate interactively (e.g. via a
    login page) and the frontend would handle the token exchange.
    """
    async with httpx.AsyncClient(base_url=AUTH_SERVER_URL) as client:
        resp = await client.post(
            "/auth/login",
            json={"username": username, "password": password},
        )
        resp.raise_for_status()
        return resp.json()["id_token"]


async def get_token(assertion: str, client_id: str, scope: str) -> str:
    """Exchange a token for a scoped access_token via the auth server."""
    async with httpx.AsyncClient(base_url=AUTH_SERVER_URL) as client:
        resp = await client.post(
            "/auth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "assertion": assertion,
                "client_id": client_id,
                "scope": scope,
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def get_claim(token: str, claim: str) -> str | None:
    """Extract a claim from a JWT without verifying the signature."""
    payload = jwt.decode(token, options={"verify_signature": False})
    return payload.get(claim)


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

        username = os.environ.get("DEMO_USERNAME", "alice")
        password = os.environ.get("DEMO_PASSWORD", "password")

        id_token = await authenticate(username, password)
        access_token = await get_token(
            assertion=id_token,
            client_id="chat-agent",
            scope="api://chat-agent/Chat.ReadWrite",
        )
        user_name = get_claim(id_token, "name")

        if not user_name:
            console.print("[red]Failed to extract user name from token.[/red]")
            return

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
