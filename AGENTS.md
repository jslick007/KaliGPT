# KaliGPT — Agent Instructions

## Project

Python CLI tool providing a unified interface to 4 AI providers (Gemini, OpenAI, OpenRouter, Ollama) for offensive security assistance. Each agent is a standalone interactive loop with streaming, retry, model fail-over, and tool calling. Ships a bash installer for Debian/Termux.

## Structure & Entrypoints

- `agents/` — Python package; run from repo root via `python -m agents [prompt]` or `python -m agents.{gemini,chatgpt,ollama,openrouter} [prompt]`
- `agents/__main__.py` — dispatches via `subprocess.run(["python", "-m", f"agents.{default_model}", prompt])`. `--setup-keys` prints env var instructions
- `agents/__init__.py` — contains setup comments and unused imports; not loaded at runtime
- Each agent is independently importable and callable: `agents/gemini.py`, `agents/chatgpt.py`, `agents/ollama.py`, `agents/openrouter.py`
- `install.sh` — OS detection (Termux/Debian), downloads platform-specific installer
- `installers/installer.deb.sh` — full system setup (apt pkgs, pip venv, `kaligpt` launcher script)
- No `setup.py`/`pyproject.toml` — no standard Python packaging
- `agents/web_launcher.py` — opens AI web chats in browser (used via `kaligpt --web`)

## Config

- `agents/utils/api.config.json` — model lists, default provider, default model per provider. **NOT** for API keys.
- `agents/utils/agent_configs.py` — reads config JSON, resolves env vars for keys. Fallback defaults hardcoded in `default_data` dict.
- `agents/utils/retry.py` — handles 429 (indefinite retry, respects `Retry-After`) and 500 (3 retries → model fail-over via `on_retry` callback)
- All agents load model list at startup via `get_vendor_specific_all_models()` + `get_vendor_text_only_models()`, track `MODEL_INDEX`, and cycle on retry

### API Keys — Environment Variables Only

| Provider    | Env var            | Validation                    |
|-------------|--------------------|-------------------------------|
| Gemini      | `GEMINI_API_KEY`   | must contain `AIza`           |
| OpenAI      | `OPENAI_API_KEY`   | must contain `sk-`            |
| OpenRouter  | `OPENROUTER_API_KEY`| must contain `sk-or-v1-`      |
| Ollama      | `OLLAMA_HOST`      | defaults to `http://localhost:11434` |

## Running

```bash
# From repo root (no install needed)
python -m agents "find XSS on target.com"
python -m agents.gemini "scan for subdomains"
python -m agents --setup-keys
```

After system install via `install.sh`, use `kaligpt` launcher (see `README.md`).

## Streaming & Retry

- All 4 agents stream responses token-by-token
- Gemini: `client.models.generate_content_stream(...)` — 429 errors surface **during iteration**, handled by `retry_stream()` wrapper
- ChatGPT/OpenRouter: `chat.completions.create(stream=True, ...)` 
- Ollama: `client.chat(stream=True, ...)`
- `retry_stream`/`retry_on_429`: infinite 429 retry, 500→3 retries→cycle to next model via `on_retry` callback
- Gemini SDK raises `ClientError` on 429 **during stream iteration**, not at stream creation — must use `retry_stream` (not `retry_on_429`)

## Linting & Formatting

```bash
ruff check --fix agents/
ruff format agents/
```

Config in `ruff.toml`: target `py310`, line-length `120`, double quotes, space indent.

A pre-commit hook at `.githooks/pre-commit` runs ruff on staged `.py` files. Enable:
```bash
git config core.hooksPath .githooks
```

## Tools System

`agents/utils/tools/__init__.py` registers 10 Python functions via `get_tools_info()`. All 4 agents load the same set. OpenAI-compatible agents (chatgpt, openrouter) wrap them through `openai_tool_adapter()` for OpenAI schema translation.

| Function | Source | Dependency |
|---|---|---|
| `check_search_connection` | `tools/opensearchapi.py:18` | OpenSearchAPI at `:5000` |
| `keyword_search` | `tools/opensearchapi.py:74` | OpenSearchAPI at `:5000` |
| `search_as_RAG` | `tools/opensearchapi.py:171` | OpenSearchAPI at `:5000` |
| `get_local_server_content` | `tools/locals.py:13` | none |
| `execute_generic_linux_command` | `tools/locals.py:68` | none |
| `web_request_analysis` | `tools/web_request_framework.py:32` | none |
| `get_raw_response` | `tools/web_request_framework.py:254` | none |
| `check_kali_server` | `tools/mcp_kali_server.py:20` | Kali server at `192.168.1.55:5000` |
| `list_kali_tools` | `tools/mcp_kali_server.py:31` | Kali server at `192.168.1.55:5000` |
| `run_kali_tool` | `tools/mcp_kali_server.py:46` | Kali server at `192.168.1.55:5000` |
| `run_kali_command` | `tools/mcp_kali_server.py:78` | Kali server at `192.168.1.55:5000` |

OpenSearchAPI (`http://127.0.0.1:5000`) is managed via `agents/utils/openserp_management.py` (not auto-started; agents call `check_search_connection` before using search tools).

Each agent limits tool calls to `MAX_TOOL_CALLS = 10` per response to prevent infinite loops.

## Prompts

- All 4 agents import `WEB_BUG_BOUNTY_AGENT` (aliased as `SYSTEM_PROMPT`) from `agents/utils/prompts.py` — web app security testing agent with autonomous workflow instructions
- Includes explicit instructions: "do not wait for approval between steps", "written authorization exists"
- Unused prompts remain in `prompts.py` for reference: `SYSTEM_PROMPT_OLD` (v1.1), `SYSTEM_PROMPT` (v1.3 jailbreak), `WEB_PENTESTER_AGENT`, `RED_TEAM_AGENT`

## Dependencies

- `requirements/pip-requirements.txt` — `openai`, `ollama`, `google-genai`, `rich`, `requests`, `newspaper3k`, `lxml_html_clean`, `beautifulsoup4`, `flask`, `ddgs`, `curl_cffi`, `nodriver`, `pyvirtualdisplay`, `prompt_toolkit`
- System deps: `libxml2`, `libxslt`, `libjpeg-turbo`, `libpng`, `freetype`, `make`, `pkg-config`, `clang`, `rust`
- Terminal output uses `rich` (Panels, Markdown, Syntax); interactive selection uses `prompt_toolkit`

## Agent Quirks

- `agents/__main__.py` launches subprocess with `python -m agents.{provider}`, so management commands (`/change-model`, etc.) run in the agent's own loop via `agent_management()` from `agents/utils/agent_management.py`
- Ollama tool support varies by model — uses `model_support_check()` from `agents/utils/ollama_tool_think_support_check.py` to determine support stage at startup
- No test suite. No CI beyond a stats tracker at `.github/workflows/stats_tracker.yml`
- `.gitignore` has `__pycache__/` — pyc files were removed from tracking and will not be re-added
