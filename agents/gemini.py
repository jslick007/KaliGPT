#!/usr/bin/env python3

# /agents/gemini.py
# KaliGPT Gemini_agent
# Updated: 24 feb 2026


from google import genai
from google.genai import types
import sys
import time

from .utils.parse_n_print_response import parse_n_print_response
from .utils.prompts import WEB_BUG_BOUNTY_AGENT as SYSTEM_PROMPT
from .utils.agent_configs import get_api_key, get_ai_specific_default_model
from .utils.tools import get_tools_info
from .utils.agent_management import agent_management, AI_MANAGEMENT_OPTIONS
from .utils.debug_logger import log_llm_request, log_llm_response

# --- GLOBAL VARIABLES ---
GEMINI_API_KEY: str
GEMINI_MODEL: str
TOOLS_INFO: list
client = None
TOOL_FUNCTION_MAP: dict


def initialize_configs():
    global GEMINI_API_KEY, GEMINI_MODEL, client, TOOLS_INFO, TOOL_FUNCTION_MAP
    try:
        GEMINI_API_KEY = get_api_key("gemini")
        GEMINI_MODEL = get_ai_specific_default_model("gemini")

        if not GEMINI_API_KEY or 'AIza' not in GEMINI_API_KEY:
            print("[!] GEMINI API Key not Found. exiting!")
            sys.exit(0)

        # Configure the API for the entire library
        client = genai.Client(api_key=GEMINI_API_KEY)

        # 2. LOAD TOOLS
        TOOLS_INFO = get_tools_info()

        # --- TOOL EXECUTION HELPER (Your Original Function) ---
        TOOL_FUNCTION_MAP = {func.__name__: func for func in TOOLS_INFO} if TOOLS_INFO else {}

        if not TOOLS_INFO:
            print("[!] No external tools loaded.")

    except Exception as e:
        print(f"Failed to initialize Agent: {e}")
        sys.exit(1)


def execute_function_calls(function_calls: list):
    response_parts = []
    print("\n[HackerX Tool Use] Owo! I found a tool I need to run! <3")
    for call in function_calls:
        func_name = call.name
        func_args = dict(call.args)
        if func_name in TOOL_FUNCTION_MAP:
            print(f"[HackerX Tool Use] Running tool: {func_name} with args: {func_args}")
            try:
                result_text = TOOL_FUNCTION_MAP[func_name](**func_args)
            except Exception as e:
                result_text = f"Tool execution failed with error: {e}"
        else:
            result_text = f"Tool {func_name} not found in map!"
        response_parts.append(
            types.Part.from_function_response(name=func_name, response={"result": result_text})
        )
        print("[HackerX Tool Use] Tool result ready to send back.")
    return response_parts


MAX_TOOL_CALLS = 10


def get_gemini_response(history: list[types.Content], new_input: str, tools: list):
    contents = history[:]
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=new_input)])
    )
    current_system_instruction = SYSTEM_PROMPT
    tool_call_count = 0

    while True:
        log_llm_request("Gemini", contents)
        stream = client.models.generate_content_stream(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=tools,
                thinking_config=types.ThinkingConfig(thinking_budget=1),
                system_instruction=current_system_instruction
            ),
        )

        full_text = ""
        function_calls = None
        for chunk in stream:
            has_fc = chunk.function_calls
            if has_fc:
                function_calls = has_fc
            if not has_fc:
                try:
                    if chunk.text:
                        print(chunk.text, end="", flush=True)
                        full_text += chunk.text
                except (ValueError, AttributeError):
                    pass
        print()

        current_system_instruction = None

        if function_calls and tool_call_count < MAX_TOOL_CALLS:
            tool_call_count += 1
            function_response_parts = execute_function_calls(function_calls)
            parts = []
            if full_text:
                parts.append(types.Part.from_text(text=full_text))
            parts.extend([
                types.Part.from_function_call(name=fc.name, args=dict(fc.args)) for fc in function_calls
            ])
            contents.append(types.Content(role="model", parts=parts))
            contents.append(types.Content(role="tool", parts=function_response_parts))
            time.sleep(0.5)
            continue

        contents.append(types.Content(
            role="model",
            parts=[types.Part.from_text(text=full_text)]
        ))
        log_llm_response("Gemini", full_text)
        return full_text, contents


def main(prompt=None):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    chat_history: list[types.Content] = []

    initialize_configs()   # initialize configs for gemini

    # Print tool banner
    print(f"> HackerX ( Gemini/{GEMINI_MODEL} )")
    while True:
        try:
            if prompt is None:
                prompt = input("\nYou > ")


            if prompt.lower().replace("-", " ").strip() in AI_MANAGEMENT_OPTIONS:
                agent_management(prompt.lower().replace("-", " ").strip())
                prompt = None
                continue

            gemini_response, chat_history = get_gemini_response(
                history=chat_history,
                new_input=prompt,
                tools=TOOLS_INFO
            )

            # print(f"\nAgent ➤ ")
            parse_n_print_response(gemini_response)
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
