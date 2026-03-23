import asyncio
import logging
import os

import dotenv
from litellm import Choices, ModelResponse

dotenv.load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("chat_agent")

from agent import chat_agent
from jwt_utils import validate_jwt
from shared import agents_channel, humans_channel


def filter_for_chat_agent(msg) -> bool:
    return msg.get("type") == "user_message"


@chat_agent.subscribe(
    channel=humans_channel,
    filter_func=filter_for_chat_agent,
)
async def handle_user_message(msg):
    session_id = msg.get("session_id")
    chat_messages = []
    try:
        payload = msg["payload"]
        caller_jwt = payload["caller_jwt"]
        chat_messages = payload["chat_messages"]

        # Validate the caller's access token (signed with this app's client_secret)
        try:
            claims = validate_jwt(
                caller_jwt,
                audience="chat-agent",
                secret=os.environ["CHAT_AGENT_CLIENT_SECRET"],
            )
            logger.info("JWT validated for sub=%s", claims["sub"])
        except Exception as e:
            logger.warning("JWT validation failed: %s", e)
            await agents_channel.publish({
                "type": "chat_response",
                "session_id": session_id,
                "payload": {
                    "chat_messages": chat_messages + [
                        {"role": "assistant", "content": f"Authentication failed: {e}"}
                    ],
                },
            })
            return

        # Call the LLM with the full conversation history.
        # The caller_jwt is passed via tool_context so tools can perform OBO
        # exchange without any module-level state.
        response = await chat_agent.completion(
            messages=list(chat_messages),
            tool_context={"caller_jwt": caller_jwt},
        )

        if not isinstance(response, ModelResponse):
            raise ValueError("Expected ModelResponse from agent completion")

        choices = response.choices[0]

        if not isinstance(choices, Choices):
            raise ValueError("Expected Choices in ModelResponse")

        reply = choices.message.content

        # Build updated chat history with assistant response
        updated_messages = chat_messages + [{"role": "assistant", "content": reply}]

        logger.info("Response generated for sub=%s", claims["sub"])
        await agents_channel.publish({
            "type": "chat_response",
            "session_id": session_id,
            "payload": {
                "chat_messages": updated_messages,
            },
        })
    except Exception as e:
        logger.error("Error handling message: %s", e, exc_info=True)
        await agents_channel.publish({
            "type": "chat_response",
            "session_id": session_id,
            "payload": {
                "chat_messages": chat_messages + [
                    {"role": "assistant", "content": f"Error: {e}"}
                ],
            },
        })


async def main():
    logger.info("ChatAgent starting...")
    await chat_agent.run()
    logger.info("ChatAgent running. Waiting for messages...")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("ChatAgent shutting down...")
