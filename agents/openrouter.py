#!/usr/bin/env python3

# /agents/openrouter.py
# KaliGPT OpenRouter Agent
# Updated: 24 feb 2026

# Agent to use AI Models via OpenRouter OpenAI API

import sys
import json
from types import SimpleNamespace
from openai import OpenAI

from .utils.agent_configs import get_api_key, get_ai_specific_default_model
from .utils.agent_management import AI_MANAGEMENT_OPTIONS, agent_management
from .utils.parse_n_print_response import parse_n_print_response
from .utils.tools import get_tools_info
from .utils.openai_tool_adapter import openai_tool_adapter
from .utils.prompts import WEB_BUG_BOUNTY_AGENT as SYSTEM_PROMPT
from .utils.retry import retry_stream

# ----- Global Variables
OPENROUTER_API_KEY: str
OPENROUTER_MODEL: str
TOOLS_INFO = None
TOOL_FUNCTION_MAP: dict
client: OpenAI


def initialize_agent():
    """Initializes the Tool configs (stored in global variables) like:
    - API KEY
    - AI Model to use for calls
    - Tools information
    """

    global OPENROUTER_API_KEY, OPENROUTER_MODEL, TOOLS_INFO, TOOL_FUNCTION_MAP, client
    try:
        OPENROUTER_API_KEY = get_api_key("openrouter")
        OPENROUTER_MODEL = get_ai_specific_default_model("openrouter")

        if not OPENROUTER_API_KEY or "sk-or-v1-" not in OPENROUTER_API_KEY:
            print("[!] OPENROUTER API Key not Found or not valid. exiting!")
            sys.exit(0)

        tools = get_tools_info()
        TOOLS_INFO = [openai_tool_adapter(f) for f in tools]

        # --- TOOL EXECUTION HELPER (Your Original Function) ---
        TOOL_FUNCTION_MAP = {func.__name__: func for func in tools} if tools else {}

        if not TOOLS_INFO:
            print("[!] No external tools loaded.")

        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )

    except Exception as e:
        print(f"Failed to initialize Agent: {e}")
        sys.exit(1)


MAX_TURNS = 6
MAX_TOOL_CALLS = 10


def trim_history(history):
    """Trim chat history to keep within MAX_TURNS"""
    system = [m for m in history if m["role"] == "system"]
    rest = [m for m in history if m["role"] != "system"]
    return system + rest[-MAX_TURNS * 2 :]


def execute_tool_calls(tool_calls):
    """Executes tools and returns a list of OpenAI-formatted 'tool' messages."""
    tool_messages = []

    for tool_call in tool_calls:
        func_name = tool_call.function.name
        call_id = tool_call.id

        try:
            func_args = json.loads(tool_call.function.arguments)
            print(f"\n[HackerX Tool Use] name: {func_name}, args: {func_args}")
        except Exception as e:
            print(f"[!] Error parsing tool arguments: {e}")
            func_args = {}

        tool_fn = TOOL_FUNCTION_MAP.get(func_name)
        if not tool_fn:
            result = f"Error: Tool '{func_name}' not found"
        else:
            try:
                result = tool_fn(**func_args)
            except Exception as e:
                result = f"Tool execution error: {e}"

        # Correct OpenAI/OpenRouter Tool Message format
        tool_messages.append({"role": "tool", "tool_call_id": call_id, "name": func_name, "content": str(result)})

    return tool_messages


def _stream_completion(messages, tools):
    """Stream a chat completion, print text as it arrives, return (full_text, tool_calls_dict)."""
    full_text = ""
    tool_calls_acc = {}

    stream = retry_stream(
        lambda: client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            tools=tools or [],
            stream=True,
        )
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            print(delta.content, end="", flush=True)
            full_text += delta.content
        if delta and delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_acc:
                    tool_calls_acc[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                if tc.id:
                    tool_calls_acc[idx]["id"] = tc.id
                if tc.function:
                    if tc.function.name:
                        tool_calls_acc[idx]["function"]["name"] = tc.function.name
                    if tc.function.arguments:
                        tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments
    print()

    return full_text, tool_calls_acc


def ask(prompt, chat_history, tools=TOOLS_INFO):
    messages = trim_history(chat_history) + [{"role": "user", "content": prompt}]
    tool_call_count = 0

    try:
        full_text, tool_calls_acc = _stream_completion(messages, tools)

        while tool_calls_acc and tool_call_count < MAX_TOOL_CALLS:
            tool_call_count += 1
            tool_calls_list = [tc for tc in tool_calls_acc.values() if tc["id"]]
            assistant_msg = {"role": "assistant", "content": full_text or None}
            assistant_msg["tool_calls"] = [
                {"id": tc["id"], "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
                for tc in tool_calls_list
            ]
            messages.append(assistant_msg)

            tool_results = execute_tool_calls(
                [
                    SimpleNamespace(
                        id=tc["id"],
                        function=SimpleNamespace(name=tc["function"]["name"], arguments=tc["function"]["arguments"]),
                    )
                    for tc in tool_calls_list
                ]
            )
            messages.extend(tool_results)

            full_text, tool_calls_acc = _stream_completion(messages, tools)

        chat_history.append({"role": "user", "content": prompt})
        chat_history.append({"role": "assistant", "content": full_text})
        return full_text, chat_history

    except Exception as e:
        error_msg = f"API/Logic Error: {str(e)}"

        if "No endpoints found that support tool use" in error_msg:
            full_text, _ = _stream_completion(messages, [])
            chat_history.append({"role": "assistant", "content": full_text})
            return full_text, chat_history

        return error_msg, chat_history


def main(prompt=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    initialize_agent()

    # Initialize chat history with system prompt
    chat_history: list = [{"role": "system", "content": SYSTEM_PROMPT}]

    print(f"> HackerX ( openrouter/{OPENROUTER_MODEL} )")

    while True:
        try:
            if prompt is None:
                prompt = input("\nYou > ")

            if prompt.lower().replace("-", " ").strip() in AI_MANAGEMENT_OPTIONS:
                agent_management(prompt.lower().replace("-", " ").strip())
                initialize_agent()
                prompt = None
                continue

            response, chat_history = ask(chat_history=chat_history, prompt=prompt, tools=TOOLS_INFO)

            # print(f"\nAgent ➤ ")
            parse_n_print_response(response)
            prompt = None

        except KeyboardInterrupt:
            print("\n   Exiting HackerX. See you later!")
            break

        except Exception as err:
            print(f"\n   [!] An error occurred: {err}")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = " ".join(sys.argv[1:])
        main(args)
    else:
        main()
