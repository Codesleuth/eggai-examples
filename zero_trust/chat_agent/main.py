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

import agent as agent_module
from agent import chat_agent
from eggai import Channel
from jwt_utils import validate_jwt
from shared import agents_channel, humans_channel

messages_history = []


@chat_agent.subscribe(
    channel=humans_channel,
    filter_func=lambda msg: msg["type"] == "user_message",
)
async def handle_user_message(msg):
    try:
        payload = msg["payload"]
        caller_jwt = payload["caller_jwt"]
        chat_messages = payload["chat_messages"]

        # Validate the caller's access token (issued by auth_server, signed with ACCESS_SECRET)
        try:
            claims = validate_jwt(
                caller_jwt,
                audience="chat_agent",
                secret=os.environ["ACCESS_SECRET"],
            )
            logger.info("JWT validated for sub=%s", claims["sub"])
        except Exception as e:
            logger.warning("JWT validation failed: %s", e)
            await agents_channel.publish({
                "type": "chat_response",
                "payload": {
                    "chat_messages": chat_messages + [
                        {"role": "assistant", "content": f"Authentication failed: {e}"}
                    ],
                },
            })
            return

        # Make the JWT available to tools for OBO exchange
        agent_module._current_caller_jwt = caller_jwt

        # Call the LLM with the full conversation history
        response = await chat_agent.completion(messages=list(chat_messages))

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
            "payload": {
                "chat_messages": updated_messages,
            },
        })
    except Exception as e:
        logger.error("Error handling message: %s", e, exc_info=True)
        await agents_channel.publish({
            "type": "chat_response",
            "payload": {
                "chat_messages": [
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
