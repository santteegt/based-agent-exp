import time
import json
import random
import sys
import logging

from swarm import Swarm
from swarm.repl import run_demo_loop
from agents import dao_agent, check_recent_cast_notifications
from openai import OpenAI

from prompt_helpers import set_character_file, get_character_json, get_instructions
from interval_utils import get_interval, set_random_interval


lower_interval = 60
upper_interval = 120

# Configure logging
logging.basicConfig(
    filename="streaming_response.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# this is the main loop that runs the agent in autonomous mode
# you can modify this to change the behavior of the agent
def run_autonomous_loop(agent):
    client = Swarm()
    messages = []

    print("Starting autonomous DAO Agent loop...")
    character_json = get_character_json()

    while True:
        # Generate a thought
        thought = random.choices(
            population=[thought['text'] for thought in character_json["autonomous_thoughts"]],
            weights=[thought['weight'] for thought in character_json["autonomous_thoughts"]],
            k=1
        )[0]
        thought = f"{character_json['pre_autonomous_thought']} {thought} {character_json['post_autonomous_thought']}"

        if check_recent_cast_notifications():
            messages.append({"role": "user", "content": thought})

            print(f"\n\033[90mAgent's Thought:\033[0m {thought}")

            print("\n\033[90mChecking for new cast notifications...\033[0m")
            # Run the agent to generate a response and take action
            response = client.run(agent=agent, messages=messages, stream=True)

            # Process and print the streaming response
            response_obj = process_and_print_streaming_response(response)

            # Update messages with the new response
            messages.extend(response_obj.messages)
        else:
            print("\n\033[90mNo new cast notifications found...\033[0m")

        # Set a random interval between 600 and 3600 seconds
        set_random_interval(lower_interval, upper_interval)

        print(f"\n\033[90mNext thought in {get_interval()} seconds...\033[0m")
        # Wait for the specified interval
        time.sleep(get_interval())


# this is the main loop that runs the agent in two-agent mode
# you can modify this to change the behavior of the agent
def run_openai_conversation_loop(agent):
    """Facilitates a conversation between an OpenAI-powered agent and the DAO Agent."""
    client = Swarm()
    openai_client = OpenAI()
    messages = []

    print("Starting OpenAI-DAO Agent conversation loop...")

    # Initial prompt to start the conversation
    openai_messages = [{
        "role":
        "system",
        "content":
        "You are a user guiding a blockchain agent through various tasks on the Base blockchain. Engage in a conversation, suggesting actions and responding to the agent's outputs. Be creative and explore different blockchain capabilities. You're not simulating a conversation, but you will be in one yourself. Make sure you follow the rules of improv and always ask for some sort of function to occur. Be unique and interesting."
    }, {
        "role":
        "user",
        "content":
        "Start a conversation with the DAO Agent and guide it through some blockchain tasks."
    }]

    while True:
        # Generate OpenAI response
        openai_response = openai_client.chat.completions.create(
            model="gpt-3.5-turbo", messages=openai_messages)

        openai_message = openai_response.choices[0].message.content
        print(f"\n\033[92mOpenAI Guide:\033[0m {openai_message}")

        # Send OpenAI's message to DAO Agent
        messages.append({"role": "user", "content": openai_message})
        response = client.run(agent=agent, messages=messages, stream=True)
        response_obj = process_and_print_streaming_response(response)

        # Update messages with DAO Agent's response
        messages.extend(response_obj.messages)

        # Add DAO Agent's response to OpenAI conversation
        dao_agent_response = response_obj.messages[-1][
            "content"] if response_obj.messages else "No response from DAO Agent."
        openai_messages.append({
            "role":
            "user",
            "content":
            f"DAO Agent response: {dao_agent_response}"
        })

        # Check if user wants to continue
        user_input = input(
            "\nPress Enter to continue the conversation, or type 'exit' to end: "
        )
        if user_input.lower() == 'exit':
            break


def choose_mode():
    while True:
        print("\nAvailable modes:")
        print("1. chat    - Interactive chat mode")
        print("2. auto    - Autonomous action mode")
        print("3. two-agent - AI-to-agent conversation mode")

        choice = input(
            "\nChoose a mode (enter number or name): ").lower().strip()

        mode_map = {
            '1': 'chat',
            '2': 'auto',
            '3': 'two-agent',
            'chat': 'chat',
            'auto': 'auto',
            'two-agent': 'two-agent'
        }

        if choice in mode_map:
            return mode_map[choice]
        print("Invalid choice. Please try again.")


# Boring stuff to make the logs pretty
def process_and_print_streaming_response(response):
    content = ""
    last_sender = ""

    for chunk in response:
        if "sender" in chunk:
            last_sender = chunk["sender"]

        if "content" in chunk and chunk["content"] is not None:
            if not content and last_sender:
                print(f"\033[94m{last_sender}:\033[0m", end=" ", flush=True)
                logging.info(f"{last_sender}: ")  # Log sender
                last_sender = ""
            print(chunk["content"], end="", flush=True)
            logging.info(chunk["content"])  # Log content
            content += chunk["content"]

        if "tool_calls" in chunk and chunk["tool_calls"] is not None:
            for tool_call in chunk["tool_calls"]:
                f = tool_call["function"]
                name = f["name"]
                if not name:
                    continue
                print(f"\033[94m{last_sender}: \033[95m{name}\033[0m()")
                logging.info(f"{last_sender}: {name}()")  # Log tool calls

        if "delim" in chunk and chunk["delim"] == "end" and content:
            print()  # End of response message
            logging.info("End of response.")  # Log end of response
            content = ""

        if "response" in chunk:
            logging.info("Response complete.")  # Log response completion
            return chunk["response"]


def pretty_print_messages(messages) -> None:
    for message in messages:
        if message["role"] != "assistant":
            continue

        # print agent name in blue
        print(f"\033[94m{message['sender']}\033[0m:", end=" ")

        # print response, if any
        if message["content"]:
            print(message["content"])

        # print tool calls in purple, if any
        tool_calls = message.get("tool_calls") or []
        if len(tool_calls) > 1:
            print()
        for tool_call in tool_calls:
            f = tool_call["function"]
            name, args = f["name"], f["arguments"]
            arg_str = json.dumps(json.loads(args)).replace(":", "=")
            print(f"\033[95m{name}\033[0m({arg_str[1:-1]})")


def main(mode):

    mode = mode or choose_mode()
    instructions = get_instructions()
    print(instructions)

    mode_functions = {
        'chat': lambda: run_demo_loop(dao_agent(instructions)),
        'auto': lambda: run_autonomous_loop(dao_agent(instructions)),
        'two-agent': lambda: run_openai_conversation_loop(dao_agent(instructions))
    }

    print(f"\nStarting {mode} mode...")
    mode_functions[mode]()


if __name__ == "__main__":
    mode = ""
    if len(sys.argv) > 1:
        character_file_path = sys.argv[1].lower().strip()
        set_character_file(character_file_path)
        if len(sys.argv) > 2:
            mode = sys.argv[2].lower().strip()
    else:
        character_file_path = "default_character_data.json"
        set_character_file(character_file_path)
    print(f"Starting DAO Agent ({character_file_path})...")
    main(mode)
