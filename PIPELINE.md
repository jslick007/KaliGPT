# KaliGPT Pipeline

```
User Input ──► Agent Dispatch ──► LLM Streaming ──► Tool Execution ──► Response
                                        │                    │
                                        ▼                    ▼
                                  Debug Logger          Tool Map
```

## 1. Entrypoint

```
python -m agents "prompt"           # dispatches to default provider (__main__.py)
python -m agents.gemini "prompt"    # direct to Gemini agent
python -m agents.chatgpt "prompt"   # direct to ChatGPT agent
python -m agents.ollama "prompt"    # direct to Ollama agent
python -m agents.openrouter "prompt" # direct to OpenRouter agent
python -m agents --setup-keys       # prints env var setup instructions
```

`agents/__main__.py` reads `default_provider` from `api.config.json` and launches the corresponding agent module via `subprocess.run`.

## 2. Config Initialization

`agents/utils/agent_configs.py` manages two config layers:

| Data | Source | Examples |
|---|---|---|
| API keys | Environment variables | `GEMINI_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_HOST` |
| Models & provider | `api.config.json` | Default model, model lists, default provider |

`get_api_key(ai_name)` maps provider names to env vars:
```
gemini     →  GEMINI_API_KEY
chatgpt    →  OPENAI_API_KEY
openrouter →  OPENROUTER_API_KEY
ollama     →  OLLAMA_HOST (default: http://localhost:11434)
```

## 3. Agent Initialization

Each agent (`gemini.py`, `chatgpt.py`, `ollama.py`, `openrouter.py`) does:

1. `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` — prevents cp1252 encoding crashes on Windows
2. Reads API key from env var, validates format prefix (`AIza`, `sk-`, `sk-or-v1-`)
3. Creates the API client (Gemini SDK, OpenAI SDK, Ollama SDK)
4. Loads tools via `get_tools_info()` and builds `TOOL_FUNCTION_MAP`
5. For OpenAI-compatible agents (ChatGPT, OpenRouter), wraps tools through `openai_tool_adapter()` for schema translation

## 4. Interactive Loop

Each agent enters a prompt loop:

```
┌──────────────────────────────────────────────────┐
│  while True:                                     │
│    if prompt is None:                            │
│      prompt = input("You > ")                    │
│    if prompt in management_options:              │
│      change_model / list_tools / help / exit     │
│    else:                                         │
│      response = llm_chat(history, prompt, tools)  │
│      parse_n_print_response(response)             │
│      prompt = None                                │
└──────────────────────────────────────────────────┘
```

## 5. LLM Streaming Call

All 4 agents stream responses token-by-token:

```
┌─────────────────────────────────────────────────────┐
│  log_llm_request(provider, input_data)               │
│  stream = client.*.create(..., stream=True)          │
│  full_text = ""                                      │
│  tool_calls = None                                   │
│  for chunk in stream:                                │
│    if chunk has text:                                │
│      print(chunk.text, end="", flush=True)           │
│      full_text += chunk.text                         │
│    if chunk has tool/function calls:                 │
│      tool_calls = chunk.tool_calls                   │
│  print()  # newline after streaming                  │
│                                                      │
│  if tool_calls and tool_call_count < MAX_TOOL_CALLS: │
│    execute tools → append results to history → loop  │
│  else:                                               │
│    return full_text, updated_history                 │
└─────────────────────────────────────────────────────┘
```

`MAX_TOOL_CALLS = 10` prevents infinite tool-calling loops.

### Provider-specific streaming APIs

| Provider | API | Chunk structure |
|---|---|---|
| Gemini | `generate_content_stream()` | `chunk.text`, `chunk.function_calls` |
| ChatGPT | `chat.completions.create(stream=True)` | `delta.content`, `delta.tool_calls[].{index,id,function}` |
| OpenRouter | `chat.completions.create(stream=True)` | Same as ChatGPT |
| Ollama | `client.chat(stream=True)` | `chunk.message.content`, `chunk.message.tool_calls` |

### Tool call handling during streaming

For OpenAI-compatible streaming (ChatGPT, OpenRouter), tool calls arrive as partial deltas keyed by index:

```
tool_calls_acc = {}  # {index: {id, function: {name, arguments}}}
for tc in delta.tool_calls:
    if tc.index not in tool_calls_acc:
        tool_calls_acc[tc.index] = {id: "", function: {name: "", arguments: ""}}
    if tc.id:                     tool_calls_acc[tc.index]["id"] = tc.id
    if tc.function.name:          tool_calls_acc[tc.index]["function"]["name"] = tc.function.name
    if tc.function.arguments:     tool_calls_acc[tc.index]["function"]["arguments"] += tc.function.arguments
```

After streaming, accumulated dicts are converted to tool messages and the function recurses.

## 6. Tool System

`agents/utils/tools/__init__.py` registers callable Python functions:

| Function | Tool | Purpose |
|---|---|---|
| `check_search_connection` | OpenSearchAPI | Health check at `:5000` |
| `keyword_search` | OpenSearchAPI | Search via keyword |
| `search_as_RAG` | OpenSearchAPI | RAG-style batch search |
| `get_local_server_content` | `locals.py` | Fetch local URL content |
| `execute_generic_linux_command` | `locals.py` | Run shell commands |
| `web_request_analysis` | `web_request_framework.py` | HTTP request with analysis |
| `get_raw_response` | `web_request_framework.py` | Raw HTTP response |

All 4 agents share the same tool set via `get_tools_info()`. Tools are wrapped for OpenAI schema via `openai_tool_adapter()` when needed.

## 7. Debug Logger

`agents/utils/debug_logger.py` prints rich-formatted panels:

```
┌────── LLM Request >> Gemini ──────┐
│  [contents / messages sent to API] │
└────────────────────────────────────┘
┌────── LLM Response << Gemini ──────┐
│  [final accumulated text]           │
└────────────────────────────────────┘
```

- Request panel is shown **before** streaming starts
- Response panel is shown **after** streaming completes (with full accumulated text)
- Streaming text is printed live to stdout between the two panels

## 8. Response Rendering

`agents/utils/parse_n_print_response.py` renders the final AI response:

1. Primary: `rich.Markdown` renderer with `github-dark` code theme
2. Fallback (if Markdown fails): manual parser handling headers, code blocks, tables, lists, inline formatting

Both paths use `rich.Panel` for consistent wrapping.

## 9. Full Data Flow

```
                           ┌─────────────────────────────┐
                           │     api.config.json          │
                           │  default_provider, models    │
                           └──────────┬──────────────────┘
                                      │
                           ┌──────────▼──────────────────┐
                           │       __main__.py            │
                           │  dispatch to provider agent  │
                           └──────────┬──────────────────┘
                                      │
                    ┌─────────────────▼─────────────────────┐
                    │      Provider Agent (gemini/chatgpt/  │
                    │         ollama/openrouter)            │
                    │  ┌─────────────────────────────────┐  │
                    │  │   initialize_configs()           │  │
                    │  │   - read env var API key         │  │
                    │  │   - create API client            │  │
                    │  │   - load tools                   │  │
                    │  └──────────┬──────────────────────┘  │
                    │             │                          │
                    │  ┌──────────▼──────────────────────┐  │
                    │  │   Interactive Loop                │  │
                    │  │   ┌──────────────────────────┐   │  │
                    │  │   │  LLM Streaming Call       │   │  │
                    │  │   │  ┌────────────────────┐   │   │  │
                    │  │   │  │  Stream chunks to   │   │   │  │
                    │  │   │  │  stdout (live text) │   │   │  │
                    │  │   │  └────────┬───────────┘   │   │  │
                    │  │   │           │               │   │  │
                    │  │   │  ┌────────▼───────────┐   │   │  │
                    │  │   │  │  Tool call?         │   │   │  │
                    │  │   │  │  ┌──Yes──┐ ┌No──┐  │   │  │  │
                    │  │   │  │  │Execute│ │Return│  │   │  │  │
                    │  │   │  │  │tools &│ │final │  │   │  │  │
                    │  │   │  │  │loop   │ │text  │  │   │  │  │
                    │  │   │  │  └───────┘ └──────┘  │   │  │  │
                    │  │   │  └──────────────────────┘   │  │  │
                    │  │   └──────────────────────────────┘  │  │
                    │  └──────────────────────────────────────┘  │
                    └────────────────────────────────────────────┘
```
