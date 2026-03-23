import sys

from eggai import Agent
from rich.console import Console
from shared import agents_channel

console = Console()


def clear_last_line():
    sys.stdout.write("\x1b[2K")


def create_display_agent(session_id: str) -> tuple[Agent, list]:
    """Create a display agent scoped to a single session.

    Returns (agent, messages_history) where messages_history is kept in sync
    with the latest chat_response for this session.
    """
    messages_history: list = []
    agent = Agent(name=f"DisplayAgent-{session_id}")

    def filter_for_session(msg) -> bool:
        return (
            msg.get("type") == "chat_response"
            and msg.get("session_id") == session_id
        )

    @agent.subscribe(channel=agents_channel, filter_func=filter_for_session)
    async def display_response(msg):
        try:
            chat_messages = msg.get("payload", {}).get("chat_messages", [])
            if chat_messages:
                messages_history.clear()
                messages_history.extend(chat_messages)

                latest = chat_messages[-1]
                if latest.get("role") == "assistant":
                    clear_last_line()
                    console.print(
                        f"\n[bold green]ChatAgent[/bold green]:\n\t{latest['content']}"
                    )
                    console.print("\n[bold cyan]You[/bold cyan]: ", end="")
        except Exception as e:
            console.print(f"[red]Error displaying response: {e}[/red]")

    return agent, messages_history
