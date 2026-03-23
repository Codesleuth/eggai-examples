import sys

from eggai import Agent
from rich.console import Console
from shared import agents_channel

console = Console()

messages_history_memory = []

display_agent = Agent(name="DisplayAgent")


def clear_last_line():
    sys.stdout.write("\x1b[2K")


def filter_for_display_agent(msg) -> bool:
    return msg.get("type") == "chat_response"


@display_agent.subscribe(
    channel=agents_channel,
    filter_func=filter_for_display_agent,
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
