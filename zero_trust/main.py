import asyncio
import os
import sys

import dotenv

dotenv.load_dotenv()

from rich.console import Console
from rich.prompt import Prompt

from eggai import Agent, Channel
from shared import agents_channel, humans_channel
from jwt_utils import create_jwt

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
            # Update local memory with the full history from the agent
            messages_history_memory.clear()
            messages_history_memory.extend(chat_messages)

            # Display the latest assistant message
            latest = chat_messages[-1]
            if latest.get("role") == "assistant":
                clear_last_line()
                console.print(
                    f"\n[bold green]ChatAgent[/bold green]:\n\t{latest['content']}"
                )
                console.print("\n[bold cyan]You[/bold cyan]: ", end="")
    except Exception as e:
        console.print(f"[red]Error displaying response: {e}[/red]")


async def ask_input(stop_event):
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
                # Create a JWT for this request
                token = create_jwt(
                    subject="user@example.com",
                    audience="chat_agent",
                    secret=os.environ["JWT_SECRET"],
                )

                # Add user message to local history
                messages_history_memory.append(
                    {"role": "user", "content": user_input}
                )

                # Publish with JWT and full chat history
                await humans_channel.publish({
                    "type": "user_message",
                    "payload": {
                        "chat_messages": list(messages_history_memory),
                        "caller_jwt": token,
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
            "[dim]Each message is signed with a JWT. The chat agent exchanges it "
            "for an OBO token to access the transactions server.[/dim]"
        )
        console.print("[dim]Type 'exit' or 'quit' to stop.[/dim]\n")

        await display_agent.run()
        asyncio.create_task(ask_input(stop_event))
        await stop_event.wait()
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
