#!/usr/bin/env python3

# /agents/gemini.py
# KaliGPT Gemini_agent
# Updated: 24 feb 2026


from google import genai
from google.genai import types
import sys
import time

from .utils.prompts import WEB_BUG_BOUNTY_AGENT as SYSTEM_PROMPT
from .utils.agent_configs import (
    get_api_key,
    get_ai_specific_default_model,
    get_vendor_specific_all_models,
    get_vendor_text_only_models,
)
from .utils.tools import get_tools_info
from .utils.agent_management import agent_management, AI_MANAGEMENT_OPTIONS
from .utils.retry import retry_stream

# --- GLOBAL VARIABLES ---
GEMINI_API_KEY: str
GEMINI_MODEL: str
TOOLS_INFO: list
client = None
TOOL_FUNCTION_MAP: dict
GEMINI_MODELS: list = []
GEMINI_TOOL_MODELS: set = set()  # noqa: F841 — used in model_supports_tools()
MODEL_INDEX: int = 0


def model_supports_tools(model_name: str = None) -> bool:
    """Check if the given (or current) model supports tool/function calling."""
    name = model_name or GEMINI_MODEL
    return name in GEMINI_TOOL_MODELS


def cycle_gemini_model():
    global GEMINI_MODEL, MODEL_INDEX
    if not GEMINI_MODELS:
        return
    MODEL_INDEX = (MODEL_INDEX + 1) % len(GEMINI_MODELS)
    GEMINI_MODEL = GEMINI_MODELS[MODEL_INDEX]
    tool_status = "tools" if model_supports_tools() else "text-only"
    print(f"[!] Switching to fallback model: {GEMINI_MODEL} ({tool_status})")


def initialize_configs():
    global \
        GEMINI_API_KEY, \
        GEMINI_MODEL, \
        client, \
        TOOLS_INFO, \
        TOOL_FUNCTION_MAP, \
        GEMINI_MODELS, \
        GEMINI_TOOL_MODELS, \
        MODEL_INDEX
    try:
        GEMINI_API_KEY = get_api_key("gemini")
        GEMINI_MODEL = get_ai_specific_default_model("gemini")
        tool_models = get_vendor_specific_all_models("gemini")
        GEMINI_MODELS = tool_models + get_vendor_text_only_models("gemini")
        GEMINI_TOOL_MODELS = set(tool_models)

        # Find the current model in the combined list
        try:
            MODEL_INDEX = GEMINI_MODELS.index(GEMINI_MODEL)
        except ValueError:
            MODEL_INDEX = 0

        if not GEMINI_API_KEY or "AIza" not in GEMINI_API_KEY:
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
        # Safety check: ensure 'call' is a FunctionCall object with 'name' and 'args'
        func_name = getattr(call, "name", None)
        func_args = getattr(call, "args", None)

        if not func_name:
            print(f"[!] Invalid tool call received: {call}")
            continue

        if not isinstance(func_args, dict):
            func_args = dict(func_args) if func_args else {}

        if func_name in TOOL_FUNCTION_MAP:
            print(f"[HackerX Tool Use] Running tool: {func_name} with args: {func_args}")
            try:
                result_text = TOOL_FUNCTION_MAP[func_name](**func_args)
            except Exception as e:
                result_text = f"Tool execution failed with error: {e}"
        else:
            result_text = f"Tool {func_name} not found in map!"
        response_parts.append(types.Part.from_function_response(name=func_name, response={"result": result_text}))
        print("[HackerX Tool Use] Tool result ready to send back.")
    return response_parts


MAX_TOOL_CALLS = 10


def get_gemini_response(history: list[types.Content], new_input: str, tools: list, correction_count=0):
    contents = history[:]
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=new_input)]))
    current_system_instruction = SYSTEM_PROMPT
    tool_call_count = 0

    # Text-only models cannot use tools — skip passing them
    can_use_tools = model_supports_tools()
    active_tools = tools if can_use_tools else None

    while True:
        print("... requesting stream ...", end="\r")
        stream = retry_stream(
            lambda: client.models.generate_content_stream(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    tools=active_tools,
                    system_instruction=current_system_instruction,
                ),
            ),
            on_retry=cycle_gemini_model,
        )

        full_text = ""
        function_calls = None

        # Debug: check if stream is actually a generator
        if stream is None:
            print("\n[!] Error: retry_stream returned None")
            return "Error: No response stream", contents

        for chunk in stream:
            if not chunk.candidates:
                continue

            content = chunk.candidates[0].content
            if not content or not content.parts:
                continue

            for part in content.parts:
                if part.function_call:
                    if function_calls is None:
                        function_calls = []
                    function_calls.append(part.function_call)
                elif part.text:
                    try:
                        print(part.text, end="", flush=True)
                        full_text += part.text
                    except (ValueError, AttributeError):
                        pass
        print()
        print(f"Stream ended. Length: {len(full_text)} chars. Tool calls: {bool(function_calls)}")

        if function_calls and tool_call_count < MAX_TOOL_CALLS:
            tool_call_count += 1
            function_response_parts = execute_function_calls(function_calls)
            parts = []
            if full_text:
                parts.append(types.Part.from_text(text=full_text))
            parts.extend(
                [
                    types.Part.from_function_call(
                        name=getattr(fc, "name", "unknown"), args=dict(getattr(fc, "args", {}))
                    )
                    for fc in function_calls
                ]
            )
            contents.append(types.Content(role="model", parts=parts))
            contents.append(types.Content(role="tool", parts=function_response_parts))
            time.sleep(0.5)
            continue

        # --- AUTO-EXECUTION TRIGGER (tool-capable models only) ---
        if can_use_tools and not function_calls and correction_count < 5:
            planning_keywords = [
                "plan",
                "action",
                "step",
                "let's start",
                "i will now",
                "reconnaissance",
                "initial check",
            ]
            text_lower = full_text.lower()
            is_planning = any(kw in text_lower for kw in planning_keywords)

            if is_planning or len(full_text) > 300:
                if correction_count < 3:
                    print("\n[HackerX Auto-Execute] Model is stuck in planning. Forcing action...")
                    return get_gemini_response(
                        history=contents,
                        new_input="STOP PLANNING. You have already described your plan. Execute the first tool call in your plan IMMEDIATELY. Do not explain yourself, just call the tool.",
                        tools=tools,
                        correction_count=correction_count + 1,
                    )
                else:
                    tool_names = [getattr(t, "name", "unknown") for t in tools] if tools else []
                    tool_list_str = ", ".join(tool_names)
                    print(
                        "\n[HackerX Hard-Override] Model still refusing to call tools. Injecting strict instruction..."
                    )

                    contents.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(
                                    text=f"SYSTEM OVERRIDE: You are failing to execute tools. You MUST now use a `function_call` to execute one of these tools: [{tool_list_str}]. Do NOT describe the action in text. Call the tool NOW."
                                )
                            ],
                        )
                    )

                    return get_gemini_response(
                        history=contents, new_input="EXECUTE NOW.", tools=tools, correction_count=correction_count + 1
                    )

        contents.append(types.Content(role="model", parts=[types.Part.from_text(text=full_text)]))
        return full_text, contents


def main(prompt=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    chat_history: list[types.Content] = []

    initialize_configs()  # initialize configs for gemini

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

            # Handle implicit "proceed" commands to minimize intervention
            if prompt.lower().strip() in ["ok", "continue", "proceed", "go", "yes", "do it"]:
                prompt = "Proceed with your plan and execute the next step immediately."

            gemini_response, chat_history = get_gemini_response(
                history=chat_history, new_input=prompt, tools=TOOLS_INFO
            )

            # print(f"\nAgent ➤ ")
            prompt = None

        except KeyboardInterrupt:
            print("\n   Exiting HackerX. See you later!")
            break

        except Exception as err:
            print(f"\n[!] An error occurred: {err}")
            break


if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = " ".join(sys.argv[1:])
        main(args)
    else:
        main()
