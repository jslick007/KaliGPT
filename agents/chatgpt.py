#!/usr/bin/env python3

# /agents/chatgpt.py
# KaliGPT ChatGPT_agent
# Updated: 24 feb 2026


import json
from openai import OpenAI
import sys

from .utils.parse_n_print_response import parse_n_print_response
from .utils.prompts import WEB_BUG_BOUNTY_AGENT as SYSTEM_PROMPT
from .utils.agent_configs import get_api_key, get_ai_specific_default_model
from .utils.tools import get_tools_info
from .utils.agent_management import agent_management, AI_MANAGEMENT_OPTIONS
from .utils.openai_tool_adapter import openai_tool_adapter
from .utils.debug_logger import log_llm_request, log_llm_response


# --- GLOBAL VARIABLES ---
OPENAI_API_KEY: str
OPENAI_MODEL: str
TOOLS_INFO: list
client: OpenAI
TOOL_FUNCTION_MAP: dict



def initialize_configs():
    global OPENAI_API_KEY, OPENAI_MODEL, client, TOOLS_INFO, TOOL_FUNCTION_MAP
    try:
        OPENAI_API_KEY = get_api_key("chatgpt")
        OPENAI_MODEL = get_ai_specific_default_model("chatgpt")

        if not OPENAI_API_KEY or 'sk-' not in OPENAI_API_KEY:
            print("[!] ChatGPT API Key not Found or not valid. exiting!")
            sys.exit(0)

        # Configure the API for the entire library
        client = OpenAI(api_key=OPENAI_API_KEY)

        # 2. LOAD TOOLS info for ChatGPT
        tools = get_tools_info()
        TOOLS_INFO = [openai_tool_adapter(f) for f in tools]

        # --- TOOL EXECUTION HELPER (Your Original Function) ---
        TOOL_FUNCTION_MAP = {func.__name__: func for func in tools} if tools else {}

        if not TOOLS_INFO:
            print("[!] No external tools loaded.")

    except Exception as e:
        print(f"Failed to initialize Agent: {e}")
        sys.exit(1)


MAX_TURNS = 6
MAX_TOOL_CALLS = 10

def trim_history(history):
    system = [m for m in history if m["role"] == "system"]
    rest = [m for m in history if m["role"] != "system"]
    return system + rest[-MAX_TURNS * 2:]


def get_chatgpt_response(history: list, new_input: str, tools, tool_call_count=0):

    messages = trim_history(history) + [
        {"role": "user", "content": new_input}
    ]

    log_llm_request("ChatGPT", messages)
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        tools=tools,
        stream=True,
    )

    full_text = ""
    tool_calls_acc = {}

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

    if tool_calls_acc and tool_call_count < MAX_TOOL_CALLS:
        tool_calls = [tc for tc in tool_calls_acc.values() if tc["id"]]
        tool_messages = []
        for tc in tool_calls:
            func_name = tc["function"]["name"]
            func_args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}

            if func_name not in TOOL_FUNCTION_MAP:
                result = f"Tool {func_name} not found"
            else:
                result = TOOL_FUNCTION_MAP[func_name](**func_args)

            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": str(result)
            })

        assistant_msg = {"role": "assistant", "content": full_text or None}
        assistant_msg["tool_calls"] = [
            {"id": tc["id"], "function": {"name": tc["function"]["name"], "arguments": tc["function"]["arguments"]}}
            for tc in tool_calls
        ]

        return get_chatgpt_response(
            messages + [assistant_msg] + tool_messages,
            "",
            tools,
            tool_call_count + 1
        )

    new_history = messages + [
        {"role": "assistant", "content": full_text}
    ]
    log_llm_response("ChatGPT", full_text)
    return full_text, new_history


def main(prompt=None):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # Initialize chat history with system prompt
    chat_history: list = [{"role": "system", "content": SYSTEM_PROMPT}]

    initialize_configs()   # initialize configs for OpenAI ChatGPT

    # Print tool banner
    print(f"> HackerX ( openai/{OPENAI_MODEL} )")
    while True:
        try:
            if prompt is None:
                prompt = input("\nYou > ")


            if prompt.lower().replace("-", " ").strip() in AI_MANAGEMENT_OPTIONS:
                agent_management(prompt.lower().replace("-", " ").strip())
                prompt = None
                continue

            chatgpt_response, chat_history = get_chatgpt_response(
                history=chat_history,
                new_input=prompt,
                tools=TOOLS_INFO
            )

            # print(f"\nAgent ➤ ")
            parse_n_print_response(chatgpt_response)
            prompt = None

        except KeyboardInterrupt:
            print("\n   Exiting HackerX. See you later!")
            break

        except Exception as err:
            print(f"\n[!] An error occurred: {err}")
            break

if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = ' '.join(sys.argv[1:])
        main(args)
    else:
        main()
